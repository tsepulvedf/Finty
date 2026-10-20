"""Nucleo compartido del dominio: `Money` y la jerarquia `DomainError`.

Copia propia de `core/domain/` del monolito (D-13). Cada servicio lleva la suya:
un paquete compartido acoplaria los despliegues de todos los servicios, porque
cambiarlo obligaria a reconstruir y desplegar a la vez a todos los que lo usan.
Las reglas son identicas a las del original; solo cambian los imports.
"""
