"""Adaptadores de clasificacion de transacciones (anillo externo).

Contendra `RuleBasedCategorizer`, `AICategorizer` y `MockCategorizer`, las
implementaciones concretas de la ABC `Categorizer` definida en
`finance/domain/interfaces.py`. Cada una resuelve la misma operacion contra una
fuente distinta y son intercambiables sin tocar los services.

Se implementa en M4.
"""
