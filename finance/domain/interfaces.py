"""Contratos abstractos del dominio `finance` (anillo de Dominio, Python puro).

Contendra la ABC `Categorizer`, que define la operacion de clasificar una
transaccion sin decir nada sobre como se implementa. Los services dependen de
esta abstraccion; `infra/categorizers.py` la implementa. Esa inversion es lo que
sostiene el principio de inversion de dependencias (ADR-02).

Se implementa en M4. Este modulo no importa Django.
"""
