"""Views del contrato REST de `identity` (anillo externo).

Contendra las APIView de registro, login y perfil. Cada una se limita a validar
con el serializer, invocar al service correspondiente y traducir el resultado a
HTTP; ningun calculo ni regla de negocio (ADR-05, CLAUDE.md regla 3).

Se implementa en M1.
"""
