"""Value Objects transversales del dominio (anillo de Dominio, Python puro).

Aqui vivira `Money`, el Value Object que representa una cantidad monetaria como
la union indivisible de un `Decimal` y una moneda. Se ubica en `core` porque lo
comparten los contextos `identity` y `finance`, y duplicarlo romperia el
lenguaje ubicuo del glosario (ARCHITECTURE.md 12).

Se implementa en M1. Este modulo no importa Django ni ninguna dependencia de
infraestructura.
"""
