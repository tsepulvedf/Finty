"""Correos y vencimiento de suscripciones (E2-M7), con reloj controlado.

- La bienvenida se encola al activar, sale una sola vez y nunca bloquea el pago.
- El aviso de vencimiento sale 3 dias antes del fin del periodo, una sola vez.
- `expire_all` persiste EXPIRED en las vencidas.
- Si identity no responde, no queda registro y la tarea reintenta despues.
"""
from datetime import timedelta
from uuid import uuid4

import pytest

from domain.interfaces import ContactUnavailable
from models import SentNotificationRecord, SubscriptionRecord
from services import ALREADY_SENT, NO_CONTACT, SENT, SKIPPED, NotificationService, SubscriptionService

CHECKOUT = "/api/v1/subscriptions/checkout/"
ME = "/api/v1/subscriptions/me/"
CANCEL = "/api/v1/subscriptions/me/cancel/"


@pytest.fixture
def notifications(session, adapters):
    def build():
        return NotificationService(session, adapters["contacts"], adapters["composer"], adapters["sender"], adapters["clock"])

    return build


@pytest.fixture
def subscriptions(session, adapters, app):
    def build():
        return SubscriptionService(session, adapters["gateway"], app.config["SUBSCRIPTION_PLANS"], adapters["clock"])

    return build


def activate(client):
    response = client.post(CHECKOUT, {"plan": "PREMIUM"})
    assert response.status_code == 201 and response.json["payment"]["status"] == "APPROVED"
    return response.json["subscription"]


def record_of(session, user_id):
    return session.query(SubscriptionRecord).filter_by(user_id=user_id).one()


def sent_rows(session, user_id):
    return session.query(SentNotificationRecord).filter_by(user_id=user_id).all()


class TestBienvenida:
    def test_activar_encola_la_bienvenida(self, ana, adapters, session):
        activate(ana)
        assert adapters["queue"].welcomes == [record_of(session, ana.user_id).id]

    def test_un_pago_rechazado_no_la_encola(self, ana, adapters):
        adapters["gateway"].outcome = "DECLINED"
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert adapters["queue"].welcomes == []

    def test_broker_caido_no_bloquea_la_activacion(self, ana, adapters):
        adapters["queue"].down = True
        subscription = activate(ana)
        assert subscription["status"] == "ACTIVE" and subscription["premium"] is True
        assert ana.get(ME).json["premium"] is True

    def test_sale_una_sola_vez(self, ana, adapters, session, notifications):
        activate(ana)
        subscription_id = record_of(session, ana.user_id).id

        assert notifications().send_premium_welcome(subscription_id) == SENT
        assert notifications().send_premium_welcome(subscription_id) == ALREADY_SENT

        [message] = adapters["sender"].sent
        assert message.subject == "¡Bienvenido a Finty Premium!"
        assert "Hola, Ana:" in message.body and "21 de noviembre de 2026" in message.body
        assert len(sent_rows(session, ana.user_id)) == 1

    def test_en_el_idioma_del_contacto(self, ana, adapters, session, notifications):
        adapters["contacts"].language = "en"
        activate(ana)
        notifications().send_premium_welcome(record_of(session, ana.user_id).id)

        [message] = adapters["sender"].sent
        assert message.subject == "Welcome to Finty Premium!"
        assert "Hi Ana," in message.body and "November 21, 2026" in message.body
        assert sent_rows(session, ana.user_id)[0].language == "en"

    def test_identity_caido_reintenta_sin_dejar_registro(self, ana, adapters, session, notifications):
        activate(ana)
        subscription_id = record_of(session, ana.user_id).id
        adapters["contacts"].down = True

        with pytest.raises(ContactUnavailable):
            notifications().send_premium_welcome(subscription_id)
        assert sent_rows(session, ana.user_id) == [] and adapters["sender"].sent == []

        adapters["contacts"].down = False
        assert notifications().send_premium_welcome(subscription_id) == SENT
        assert len(adapters["sender"].sent) == 1

    def test_sin_contacto_no_envia_ni_reintenta(self, ana, adapters, session, notifications):
        activate(ana)
        subscription_id = record_of(session, ana.user_id).id
        adapters["contacts"].missing.add(ana.user_id)

        assert notifications().send_premium_welcome(subscription_id) == NO_CONTACT
        assert notifications().send_premium_welcome(subscription_id) == ALREADY_SENT
        assert adapters["sender"].sent == []

    def test_una_suscripcion_sin_acceso_no_recibe_bienvenida(self, ana, adapters, session, notifications):
        adapters["gateway"].outcome = "DECLINED"
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        assert notifications().send_premium_welcome(record_of(session, ana.user_id).id) == SKIPPED
        assert adapters["sender"].sent == []


class TestBienvenidaDeRespaldo:
    """D-32: la pasada periodica envia la bienvenida que no se pudo encolar."""

    def test_broker_caido_al_activar_la_recupera_la_pasada(self, ana, adapters, session, notifications):
        adapters["queue"].down = True
        activate(ana)
        assert adapters["queue"].welcomes == [] and adapters["sender"].sent == []

        assert notifications().send_missing_welcomes() == 1
        [message] = adapters["sender"].sent
        assert message.subject == "¡Bienvenido a Finty Premium!"
        assert [row.kind for row in sent_rows(session, ana.user_id)] == ["premium_welcome"]

    def test_no_repite_la_que_ya_salio_por_el_camino_rapido(self, ana, adapters, session, notifications):
        activate(ana)
        notifications().send_premium_welcome(record_of(session, ana.user_id).id)

        assert notifications().send_missing_welcomes() == 0
        assert len(adapters["sender"].sent) == 1

    def test_la_pasada_es_idempotente(self, ana, juan, adapters, notifications):
        adapters["queue"].down = True
        activate(ana)
        activate(juan)
        assert notifications().send_missing_welcomes() == 2
        assert notifications().send_missing_welcomes() == 0
        assert len(adapters["sender"].sent) == 2

    def test_si_el_camino_rapido_llega_despues_no_duplica(self, ana, adapters, session, notifications):
        activate(ana)
        notifications().send_missing_welcomes()
        assert notifications().send_premium_welcome(record_of(session, ana.user_id).id) == ALREADY_SENT
        assert len(adapters["sender"].sent) == 1

    def test_solo_activas_en_periodo(self, ana, juan, client_for, adapters, session, notifications):
        adapters["queue"].down = True
        activate(ana)
        ana.post(CANCEL)
        adapters["gateway"].outcome = "DECLINED"
        juan.post(CHECKOUT, {"plan": "PREMIUM"})
        assert notifications().send_missing_welcomes() == 0

        adapters["gateway"].outcome = "APPROVED"
        pedro = client_for(uuid4())
        activate(pedro)
        adapters["clock"].advance(days=40)
        assert notifications().send_missing_welcomes() == 0
        assert adapters["sender"].sent == []

    def test_activada_hace_mas_de_24_horas_no_recibe_la_bienvenida(self, ana, juan, adapters, session, notifications):
        adapters["queue"].down = True
        activate(ana)
        adapters["clock"].advance(hours=24, minutes=1)
        activate(juan)

        assert notifications().send_missing_welcomes() == 1
        [message] = adapters["sender"].sent
        assert message.to.startswith(juan.user_id.hex[:8])
        assert sent_rows(session, ana.user_id) == []

    def test_la_ventana_es_configurable(self, ana, adapters, session):
        adapters["queue"].down = True
        activate(ana)
        adapters["clock"].advance(hours=3)
        corta = NotificationService(session, adapters["contacts"], adapters["composer"], adapters["sender"],
                                    adapters["clock"], welcome_recovery_hours=2)
        larga = NotificationService(session, adapters["contacts"], adapters["composer"], adapters["sender"],
                                    adapters["clock"], welcome_recovery_hours=4)
        assert corta.send_missing_welcomes() == 0
        assert larga.send_missing_welcomes() == 1

    @pytest.mark.parametrize("valor", ["0", "-5", "media"])
    def test_una_ventana_menor_a_una_hora_impide_arrancar(self, monkeypatch, connection, valor):
        from app import create_app
        from infra.configuration import ConfigurationError
        from tests.conftest import _session_on

        monkeypatch.setenv("WELCOME_RECOVERY_WINDOW_HOURS", valor)
        with pytest.raises(ConfigurationError):
            create_app(session_factory=lambda: _session_on(connection))

    def test_la_ventana_se_lee_del_entorno(self, monkeypatch, connection):
        from app import create_app
        from tests.conftest import _session_on

        monkeypatch.setenv("WELCOME_RECOVERY_WINDOW_HOURS", "48")
        assert create_app(session_factory=lambda: _session_on(connection)).config["WELCOME_RECOVERY_WINDOW_HOURS"] == 48

    def test_identity_caido_reintenta_sin_marcar(self, ana, adapters, session, notifications):
        adapters["queue"].down = True
        activate(ana)
        adapters["contacts"].down = True
        with pytest.raises(ContactUnavailable):
            notifications().send_missing_welcomes()
        assert sent_rows(session, ana.user_id) == []
        adapters["contacts"].down = False
        assert notifications().send_missing_welcomes() == 1


class TestAvisoDeVencimiento:
    """El periodo empieza el 21 de octubre a las 15:00 UTC y termina un mes despues."""

    def test_solo_a_3_dias_y_una_sola_vez(self, ana, adapters, session, notifications):
        activate(ana)
        end = record_of(session, ana.user_id).current_period_end
        clock = adapters["clock"]

        clock.now = end - timedelta(days=3, minutes=1)
        assert notifications().notify_expiring() == 0

        clock.now = end - timedelta(days=3)
        assert notifications().notify_expiring() == 1

        clock.now = end - timedelta(days=2)
        assert notifications().notify_expiring() == 0
        clock.now = end - timedelta(hours=1)
        assert notifications().notify_expiring() == 0

        [message] = adapters["sender"].sent
        assert message.subject == "Tu plan Premium termina el 21 de noviembre de 2026"
        kinds = [row.kind for row in sent_rows(session, ana.user_id)]
        assert kinds == ["subscription_expiring"]

    def test_tambien_avisa_a_una_cancelada(self, ana, adapters, session, notifications):
        activate(ana)
        ana.post(CANCEL)
        end = record_of(session, ana.user_id).current_period_end
        adapters["clock"].now = end - timedelta(days=1)
        assert notifications().notify_expiring() == 1

    def test_una_ya_vencida_no_recibe_aviso(self, ana, adapters, session, notifications):
        activate(ana)
        adapters["clock"].now = record_of(session, ana.user_id).current_period_end + timedelta(minutes=1)
        assert notifications().notify_expiring() == 0

    def test_identity_caido_no_deja_el_aviso_marcado(self, ana, adapters, session, notifications):
        activate(ana)
        adapters["clock"].now = record_of(session, ana.user_id).current_period_end - timedelta(days=2)
        adapters["contacts"].down = True
        with pytest.raises(ContactUnavailable):
            notifications().notify_expiring()
        adapters["contacts"].down = False
        assert notifications().notify_expiring() == 1

    def test_varios_usuarios(self, ana, juan, adapters, session, notifications):
        activate(ana)
        activate(juan)
        adapters["clock"].now = record_of(session, ana.user_id).current_period_end - timedelta(days=1)
        assert notifications().notify_expiring() == 2
        assert notifications().notify_expiring() == 0


class TestVencimiento:
    def test_la_vencida_pasa_a_expired(self, ana, adapters, session, subscriptions):
        activate(ana)
        end = record_of(session, ana.user_id).current_period_end

        adapters["clock"].now = end - timedelta(seconds=1)
        assert subscriptions().expire_all() == 0
        adapters["clock"].now = end
        assert subscriptions().expire_all() == 1
        assert record_of(session, ana.user_id).status == "EXPIRED"
        assert subscriptions().expire_all() == 0

        me = ana.get(ME).json
        assert (me["plan"], me["premium"]) == ("FREE", False)

    def test_tambien_vence_una_cancelada_y_no_toca_las_pendientes(self, ana, juan, adapters, session, subscriptions):
        activate(ana)
        ana.post(CANCEL)
        adapters["gateway"].outcome = "DECLINED"
        juan.post(CHECKOUT, {"plan": "PREMIUM"})

        adapters["clock"].advance(days=40)
        assert subscriptions().expire_all() == 1
        assert record_of(session, ana.user_id).status == "EXPIRED"
        assert record_of(session, juan.user_id).status == "PENDING_PAYMENT"

    def test_tras_vencer_se_puede_volver_a_pagar(self, ana, adapters, session, subscriptions):
        activate(ana)
        adapters["clock"].advance(days=40)
        subscriptions().expire_all()
        assert activate(ana)["status"] == "ACTIVE"
