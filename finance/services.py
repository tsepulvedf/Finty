"""Casos de uso del contexto `finance` (anillo de Servicios).

Contendra `AccountService` y `TransactionService`, que orquestan los casos de uso
del camino critico: verificar la propiedad de la cuenta (INV-03), obtener el
`Categorizer` de la Factory, construir la transaccion con el Builder y recalcular
el balance dentro de una transaccion atomica (INV-07).

Se implementa en M5. Depende de las ABC de `domain/interfaces.py`, nunca de una
implementacion concreta de `infra/` (CLAUDE.md, regla 6).
"""
