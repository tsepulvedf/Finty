"""Casos de uso de recommendation-service (anillo medio).

Dependen solo de los puertos de `domain/interfaces.py` (RULES.md, regla 6): el
adaptador HTTP de analytics, la API de la TRM, el cache de Redis y la tasa fija
los conecta `api/context.py`.
"""
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from domain.exceptions import (
    InvestmentPlanNotFoundError,
    RiskProfileNotFoundError,
    RiskProfileRequiredError,
)
from domain.exchange import (
    COP,
    USD,
    ensure_supported_currency,
    ensure_supported_pair,
    seconds_until_next_day,
)
from domain.interfaces import AnalyticsUnavailable, ExchangeRateUnavailable
from domain.investment_plan import build_plan, project
from domain.period import Period
from domain.recommendations import (
    DEFAULT_CURRENCY,
    investment_recommendations,
    monthly_surpluses,
    optimization_recommendations,
)
from domain.risk_profile import QUESTIONS, RiskProfile
from domain.shared.value_objects import Money
from domain.value_objects import RecommendationKind
from models import InvestmentPlanRecord, RiskProfileRecord

logger = logging.getLogger(__name__)


@contextmanager
def atomic(session):
    """Confirma al salir; revierte ante cualquier excepcion (igual que finance)."""
    try:
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise


# --- Tasas de cambio ----------------------------------------------------------


class ExchangeRateService:
    """Cadena de degradacion de tasas (ADR-12, A-22).

    1. Cache del dia en Redis → `cached`.
    2. API oficial de la TRM → `live`; se guarda en el cache del dia y como
       ultima conocida.
    3. Si la API falla: la ultima tasa conocida → `cached`.
    4. Sin nada de lo anterior: la tasa fija → `fallback`.

    Solo existe la serie USD→COP; COP→USD es su inversa, con la misma procedencia.
    """

    def __init__(self, provider, cache, fallback, clock=datetime.now):
        self._provider = provider
        self._cache = cache
        self._fallback = fallback
        self._clock = clock
        self._resolved = None  # una sola resolucion por peticion

    def rate(self, base, target):
        base, target = ensure_supported_pair(base, target)
        usd_cop = self._usd_cop()
        return usd_cop if (base, target) == (USD, COP) else usd_cop.inverse()

    def _usd_cop(self):
        if self._resolved is None:
            self._resolved = self._resolve()
        return self._resolved

    def _resolve(self):
        now = self._clock()
        today = now.date()
        cached = self._cache.today(USD, COP, today)
        if cached is not None:
            return cached
        try:
            live = self._provider.rate(USD, COP, today)
        except ExchangeRateUnavailable as exc:
            logger.warning("API de tasas no disponible (%s); se degrada", exc)
            last = self._cache.last_known(USD, COP)
            return last if last is not None else self._fallback.rate(USD, COP, today)
        self._cache.store(live, today, seconds_until_next_day(now))
        return live


# --- Perfil de riesgo ---------------------------------------------------------


def _profile_from(record):
    return RiskProfile.from_answers({q: getattr(record, q) for q in QUESTIONS})


@dataclass(frozen=True)
class SavedRiskProfile:
    profile: RiskProfile
    updated_at: datetime


class RiskProfileService:
    def __init__(self, session):
        self._session = session

    def find(self, user_id):
        record = self._session.get(RiskProfileRecord, user_id)
        return _profile_from(record) if record else None

    def get(self, user_id):
        record = self._session.get(RiskProfileRecord, user_id)
        if record is None:
            raise RiskProfileNotFoundError()
        return SavedRiskProfile(_profile_from(record), record.updated_at)

    def save(self, user_id, answers):
        profile = RiskProfile.from_answers(answers)
        with atomic(self._session):
            record = self._session.get(RiskProfileRecord, user_id)
            if record is None:
                record = RiskProfileRecord(user_id=user_id)
                self._session.add(record)
            for question, value in profile.answers:
                setattr(record, question, value)
            # `onupdate` no corre si los valores no cambian; la fecha marca el envio.
            record.updated_at = datetime.now().astimezone()
        return SavedRiskProfile(profile, record.updated_at)


# --- Recomendaciones ----------------------------------------------------------


@dataclass(frozen=True)
class DisplayedRecommendation:
    recommendation: object
    display: tuple  # ((clave, Money en la moneda de presentacion), ...)


@dataclass(frozen=True)
class RecommendationReport:
    period: Period
    degraded: bool
    risk_profile_type: object
    display_currency: str | None
    exchange_rates: tuple
    items: tuple  # DisplayedRecommendation
    locked: tuple = ()  # ((tipo, code), ...): lo que no salio por INV-06


class RecommendationService:
    """Optimizacion desde analytics e inversion desde el excedente y el perfil.

    Si analytics no responde, la respuesta se degrada: sin optimizacion, la
    inversion solo con el perfil y `degraded = True`. Nunca un 500.
    """

    def __init__(self, session, analytics, exchange_rates, settings, clock=datetime.now):
        self._profiles = RiskProfileService(session)
        self._analytics = analytics
        self._exchange_rates = exchange_rates
        self._settings = settings
        self._clock = clock

    def recommendations(self, user_id, display_currency=None, investment_lock=None):
        """`investment_lock`: el `code` por el que el usuario no recibe las de inversion
        (INV-06, lo decide el gating de la capa de entrada), o `None`."""
        if display_currency is not None:
            # Se valida antes de consultar nada: solo USD o COP.
            display_currency = ensure_supported_currency(display_currency)
        period = Period.of(self._clock().date())
        profile = self._profiles.find(user_id)
        profile_type = profile.profile_type if profile else None

        try:
            snapshot = self._analytics.snapshot(user_id, period)
        except AnalyticsUnavailable as exc:
            logger.warning("analytics-service no disponible (%s); recomendaciones degradadas", exc)
            snapshot = None

        if investment_lock is not None:
            investment = ()
        elif snapshot is None:
            investment = investment_recommendations(profile_type, None)
        else:
            surpluses = monthly_surpluses(period, snapshot.monthly_nets, self._settings.surplus_months)
            investment = investment_recommendations(profile_type, surpluses)
        optimization = optimization_recommendations(snapshot) if snapshot is not None else ()
        found = optimization + investment

        items, rates = self._display(found, display_currency)
        return RecommendationReport(
            period=period,
            degraded=snapshot is None,
            risk_profile_type=profile_type,
            display_currency=display_currency,
            exchange_rates=rates,
            items=items,
            locked=((RecommendationKind.INVESTMENT, investment_lock),) if investment_lock else (),
        )

    def _display(self, found, display_currency):
        """Equivalentes de presentacion de cada monto. Nada persistido cambia (INV-11)."""
        if display_currency is None:
            return tuple(DisplayedRecommendation(r, ()) for r in found), ()
        rates = {}
        items = []
        for recommendation in found:
            converted = []
            for key, money in recommendation.money_entries():
                if money.currency == display_currency:
                    converted.append((key, money))
                    continue
                if money.currency not in rates:
                    rates[money.currency] = self._exchange_rates.rate(money.currency, display_currency)
                converted.append((key, rates[money.currency].convert(money)))
            items.append(DisplayedRecommendation(recommendation, tuple(converted)))
        return tuple(items), tuple(rates.values())


# --- Planes de inversion ------------------------------------------------------


@dataclass(frozen=True)
class PlanView:
    record: InvestmentPlanRecord
    projection: object


class InvestmentPlanService:
    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._profiles = RiskProfileService(session)

    def create(self, user_id, instrument_type, monthly_contribution, currency, horizon_months):
        """Sin `currency`, la moneda por defecto de una cuenta (COP)."""
        profile = self._profiles.find(user_id)
        if profile is None:
            raise RiskProfileRequiredError()
        draft = build_plan(
            instrument_type,
            profile.profile_type,
            Money(monthly_contribution, currency or DEFAULT_CURRENCY),
            horizon_months,
            self._settings.max_horizon_months,
        )
        with atomic(self._session):
            record = InvestmentPlanRecord(
                user_id=user_id,
                instrument_type=draft.instrument_type.value,
                risk_profile_type=draft.risk_profile_type.value,
                monthly_contribution=draft.monthly_contribution.amount,
                currency=draft.monthly_contribution.currency,
                horizon_months=draft.horizon_months,
            )
            self._session.add(record)
        return self._view(record)

    def list(self, user_id):
        records = self._session.scalars(
            select(InvestmentPlanRecord)
            .where(InvestmentPlanRecord.user_id == user_id)
            .order_by(InvestmentPlanRecord.created_at.desc(), InvestmentPlanRecord.id)
        ).all()
        return [self._view(r) for r in records]

    def get(self, user_id, plan_id):
        return self._view(self._owned(user_id, plan_id))

    def delete(self, user_id, plan_id):
        with atomic(self._session):
            self._session.delete(self._owned(user_id, plan_id))

    def _owned(self, user_id, plan_id):
        record = self._session.get(InvestmentPlanRecord, plan_id)
        # Ajeno o inexistente: el mismo 404 (D-08).
        if record is None or record.user_id != user_id:
            raise InvestmentPlanNotFoundError()
        return record

    def _view(self, record):
        projection = project(
            Money(record.monthly_contribution, record.currency),
            record.horizon_months,
            self._settings.illustrative_rate(record.risk_profile_type),
        )
        return PlanView(record, projection)
