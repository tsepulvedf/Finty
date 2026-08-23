"""Fabricas de adaptadores de `finance` (anillo externo).

Contendra `CategorizerFactory`, el Factory Method que resuelve que
implementacion de `Categorizer` usar segun `settings.CATEGORIZER_PROVIDER`.
Concentrar aqui la decision permite agregar un proveedor nuevo sin modificar los
services (principio abierto/cerrado).

Se implementa en M4.
"""
