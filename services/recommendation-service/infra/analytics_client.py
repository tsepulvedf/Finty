"""Cliente de analytics-service: implementa el puerto `AnalyticsReader` (E2-M5).

Llama por la red interna a los endpoints que ya existen (§10.6), reenviando el
`X-User-Id` que puso el Gateway: analytics confia en esa cabecera igual que este
servicio (ADR-09). No construye otra proyeccion de eventos: lee la de analytics.

Ante timeout, error de red, una respuesta que no es 200 o un cuerpo fuera de
contrato, lanza `AnalyticsUnavailable`; `RecommendationService` degrada.

Traduce el JSON a los value objects de `domain/analytics.py`. Los insights que
no generan recomendaciones (`top_category`) y los `code` desconocidos se ignoran.
"""
import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal

from domain.analytics import (
    AnalyticsSnapshot,
    CategorySpike,
    MonthlyNet,
    NegativeSavings,
    RecurringExpense,
)
from domain.interfaces import AnalyticsReader, AnalyticsUnavailable
from domain.period import Period
from domain.shared.value_objects import Money

DEFAULT_TIMEOUT_SECONDS = 1.0
USER_ID_HEADER = "X-User-Id"
# Se identifica como llamada interna: las recomendaciones de optimizacion son
# gratuitas aunque lean insights y patrones, que son premium para el usuario (INV-06).
# Nginx borra esta cabecera de toda peticion externa.
INTERNAL_CALLER_HEADER = "X-Finty-Caller"
CALLER_NAME = "recommendation-service"
PATHS = {
    "dashboard": "/api/v1/analytics/dashboard/",
    "insights": "/api/v1/analytics/insights/",
    "patterns": "/api/v1/analytics/spending-patterns/",
}


class HttpAnalyticsReader(AnalyticsReader):
    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def snapshot(self, user_id, period):
        try:
            insights = self._get("insights", user_id, period)["insights"]
            patterns = self._get("patterns", user_id, period)["patterns"]
            dashboard = self._get("dashboard", user_id, period)["currencies"]
            return AnalyticsSnapshot(
                period=period,
                spikes=tuple(_spike(i) for i in insights if i["code"] == "category_spike"),
                negative_savings=tuple(_negative(i) for i in insights if i["code"] == "negative_savings"),
                recurring=tuple(_recurring(p) for p in patterns),
                monthly_nets=tuple(
                    MonthlyNet(Period.parse(point["period"]), Money(point["net"], section["currency"]))
                    for section in dashboard
                    for point in section["trend"]
                ),
            )
        except AnalyticsUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — cualquier fallo del remoto degrada
            raise AnalyticsUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def _get(self, name, user_id, period):
        query = urllib.parse.urlencode({"period": str(period)})
        request = urllib.request.Request(
            f"{self._base_url}{PATHS[name]}?{query}",
            headers={
                USER_ID_HEADER: str(user_id),
                INTERNAL_CALLER_HEADER: CALLER_NAME,
                "Accept": "application/json",
            },
        )
        # urlopen lanza HTTPError ante 4xx y 5xx, y URLError o TimeoutError ante
        # fallos de red: todos terminan en AnalyticsUnavailable.
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _spike(item):
    params, evidence = item["params"], item["evidence"]
    currency = params["currency"]
    return CategorySpike(
        category_name=params["category_name"],
        increase_pct=Decimal(params["increase_pct"]),
        current=Money(evidence["current"], currency),
        previous_average=Money(evidence["previous_average"], currency),
    )


def _negative(item):
    params, evidence = item["params"], item["evidence"]
    currency = params["currency"]
    return NegativeSavings(
        deficit=Money(params["deficit"], currency),
        income=Money(evidence["income"], currency),
        expense=Money(evidence["expense"], currency),
    )


def _recurring(item):
    return RecurringExpense(
        description=item["description"],
        category_name=item["category_name"],
        average_amount=Money(item["average_amount"], item["currency"]),
        months_present=int(item["months_present"]),
        window_months=int(item["window_months"]),
        monthly_frequency=Decimal(item["monthly_frequency"]),
        last_seen=date.fromisoformat(item["last_seen"]),
    )
