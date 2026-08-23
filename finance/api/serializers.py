"""Serializers del contrato REST de `finance` (anillo externo).

Contendra los serializers de cuentas, transacciones y categorias. Validan solo
sintaxis: formato, tipos y campos requeridos. Las reglas de negocio (monto no
nulo, cuenta propia, fecha no futura) viven en el dominio y en los services
(CLAUDE.md, regla 4).

Se implementa en M6.
"""
