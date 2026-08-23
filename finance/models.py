"""Persistencia del contexto `finance` (anillo externo).

Contendra `Account`, `Transaction` y `Category`. Modelos anemicos por ADR-03:
solo campos, `Meta`, constraints de base de datos, relaciones y `__str__`. Las
invariantes que se replican aqui (INV-02, INV-04, INV-09, INV-13) son defensa en
profundidad; la fuente autoritativa es el dominio.

Se implementa en M3.
"""
