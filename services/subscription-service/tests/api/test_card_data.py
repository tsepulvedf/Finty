"""El checkout nunca recibe datos de tarjeta (ADR-14, C-33).

`POST /api/v1/subscriptions/checkout/` acepta solo `{plan}`. Cualquier otro campo
es 400, y ningun valor de la peticion aparece en la respuesta, en el log ni en la
base: el formulario de tarjeta del frontend es una simulacion (E2-M8).
"""
import logging

import pytest
from sqlalchemy import func, select

from models import PaymentRecord, SubscriptionRecord

CHECKOUT = "/api/v1/subscriptions/checkout/"
CARD = {
    "card_number": "4242424242424242",
    "cvc": "987",
    "expiry": "12/31",
    "card_holder": "Titular De Prueba",
}
SENSITIVE_VALUES = ("4242424242424242", "987", "12/31", "Titular De Prueba")
NOT_ALLOWED = ["Este campo no está permitido."]


def rows(session, model):
    return session.execute(select(func.count()).select_from(model)).scalar_one()


@pytest.fixture
def all_logs(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


class TestSoloPlan:
    @pytest.mark.parametrize("field", list(CARD))
    def test_cada_campo_de_tarjeta_es_400(self, ana, field):
        response = ana.post(CHECKOUT, {"plan": "PREMIUM", field: CARD[field]})
        assert response.status_code == 400
        assert response.json == {field: NOT_ALLOWED}

    def test_todos_juntos_es_400_y_no_crea_nada(self, ana, adapters, session):
        response = ana.post(CHECKOUT, {"plan": "PREMIUM", **CARD})
        assert response.status_code == 400
        assert response.json == {field: NOT_ALLOWED for field in CARD}
        assert adapters["gateway"].requests == []
        assert (rows(session, SubscriptionRecord), rows(session, PaymentRecord)) == (0, 0)

    def test_cualquier_otro_campo_tambien(self, ana):
        assert ana.post(CHECKOUT, {"plan": "PREMIUM", "coupon": "X"}).json == {"coupon": NOT_ALLOWED}

    def test_un_plan_invalido_con_tarjeta_reporta_los_dos(self, ana):
        body = ana.post(CHECKOUT, {"plan": "GOLD", "cvc": "987"}).json
        assert body == {"plan": ['"GOLD" no es una elección válida.'], "cvc": NOT_ALLOWED}

    def test_solo_plan_sigue_funcionando(self, ana):
        assert ana.post(CHECKOUT, {"plan": "PREMIUM"}).status_code == 201


class TestNingunValorSeFiltra:
    def test_ni_en_la_respuesta_ni_en_el_log(self, ana, all_logs):
        response = ana.post(CHECKOUT, {"plan": "PREMIUM", **CARD})
        text = response.get_data(as_text=True)
        for value in SENSITIVE_VALUES:
            assert value not in text
            assert value not in all_logs.text

    def test_un_checkout_valido_tampoco_registra_la_peticion(self, ana, all_logs, adapters):
        from domain.value_objects import PaymentStatus

        adapters["gateway"].outcome = PaymentStatus.DECLINED  # el camino que si escribe en el log
        ana.post(CHECKOUT, {"plan": "PREMIUM"})
        ana.post(CHECKOUT, {"plan": "PREMIUM", **CARD})
        for value in SENSITIVE_VALUES:
            assert value not in all_logs.text

    def test_el_error_no_encadena_la_excepcion_de_pydantic(self, app):
        """La excepcion de pydantic guarda `input_value`; no debe viajar con el 400."""
        from api.errors import InvalidInput
        from api.schemas import CheckoutInput, validate_input

        with pytest.raises(InvalidInput) as raised:
            validate_input(CheckoutInput, {"plan": "PREMIUM", **CARD})
        assert raised.value.__cause__ is None and raised.value.__suppress_context__ is True
