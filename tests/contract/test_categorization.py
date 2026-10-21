"""Categorizacion de punta a punta, por el Gateway (A-13 y A-22).

Dependen de como este el stack, asi que solo corren cuando se pide:

**A-13, el Factory es observable desde fuera.** El mismo `POST
/api/v1/transactions/` devuelve otra procedencia segun `CATEGORIZER_PROVIDER` de
`categorization-service`:

    CATEGORIZER_PROVIDER=RULE docker compose up -d categorization-service
    CONTRACT_CATEGORIZER_PROVIDER=RULE python -m pytest test_categorization.py -v
    CATEGORIZER_PROVIDER=MOCK docker compose up -d categorization-service
    CONTRACT_CATEGORIZER_PROVIDER=MOCK python -m pytest test_categorization.py -v

**A-22, resiliencia.** Con el servicio detenido, la transaccion se registra igual
y la clasifica el respaldo local de `finance-service`, con procedencia `rule`:

    docker compose stop categorization-service
    CONTRACT_CATEGORIZATION_DOWN=1 python -m pytest test_categorization.py -v
    docker compose start categorization-service

La suite principal debe correr con el proveedor en `RULE` y el servicio arriba.
"""
import os

import pytest

from helpers import create_account, register

PROVIDER_ENV = "CONTRACT_CATEGORIZER_PROVIDER"
DOWN_ENV = "CONTRACT_CATEGORIZATION_DOWN"

DESCRIPTION = "Almuerzo en el restaurante"

# Lo que debe grabarse con cada proveedor para la misma descripcion de gasto.
EXPECTED_BY_PROVIDER = {
    "RULE": ("Alimentación", "rule", 0.75),
    "MOCK": ("Otros gastos", "mock", 1.0),
    # Sin cliente configurado (D-07), AI degrada a sus reglas: procedencia `rule`.
    "AI": ("Alimentación", "rule", 0.75),
}


@pytest.fixture
def cuenta(ana):
    return create_account(ana, initial_balance="1000000")


@pytest.mark.skipif(not os.environ.get(PROVIDER_ENV), reason=f"activar con {PROVIDER_ENV}=RULE|MOCK|AI")
def test_a13_la_procedencia_sigue_al_proveedor_configurado(ana, cuenta):
    provider = os.environ[PROVIDER_ENV].strip().upper()

    response = register(ana, cuenta["id"], description=DESCRIPTION)

    assert response.status == 201
    body = response.json
    assert (body["category_name"], body["categorization_source"], body["categorization_confidence"]) == (
        EXPECTED_BY_PROVIDER[provider]
    )


@pytest.mark.skipif(os.environ.get(DOWN_ENV) != "1", reason=f"activar con {DOWN_ENV}=1 y el servicio detenido")
def test_a22_sin_categorization_service_registra_con_el_respaldo(ana, cuenta):
    response = register(ana, cuenta["id"], description=DESCRIPTION)

    assert response.status == 201
    body = response.json
    assert (body["category_name"], body["categorization_source"], body["categorization_confidence"]) == (
        "Alimentación", "rule", 0.75,
    )


@pytest.mark.skipif(os.environ.get(DOWN_ENV) != "1", reason=f"activar con {DOWN_ENV}=1 y el servicio detenido")
def test_a22_el_resto_del_contrato_sigue_en_pie(ana, cuenta):
    """Sin el remoto, lo que no clasifica no cambia: listar, consultar, borrar."""
    created = register(ana, cuenta["id"], "1000", description="taxi al centro").json
    assert created["category_name"] == "Transporte"
    assert ana.client.get(f"/api/v1/transactions/{created['id']}/").status == 200
    assert ana.client.delete(f"/api/v1/transactions/{created['id']}/").status == 204
