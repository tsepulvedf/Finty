"""Views del contrato REST de `finance` (anillo externo).

Contendra el `ModelViewSet` de cuentas y el read-only de categorias, y las
APIView de transacciones y de reclasificacion, que orquestan casos de uso con
reglas de negocio (ADR-05). Cada view valida con el serializer, obtiene sus
dependencias de la factory, llama al service y traduce el resultado a HTTP.

Se implementa en M6.
"""
