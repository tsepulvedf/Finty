"""Builders del dominio `finance` (anillo de Dominio, Python puro).

Contendra `TransactionBuilder` y `AccountBuilder`. Construyen agregados paso a
paso y validan las invariantes de entidad en `build()` (INV-04, INV-08, INV-11,
INV-12) antes de devolver un objeto valido; nunca se obtiene una instancia a
medio construir.

Viven en `domain/` y no en `infra/` porque construir un agregado es logica de
dominio, no de infraestructura (ADR-04). Se implementa en M3.
"""
