"""Reglas y servicios de dominio de `finance` (anillo de Dominio, Python puro).

Contendra `BalanceCalculator`, que deriva el balance de una cuenta a partir de
sus transacciones (INV-07), y las reglas de transaccion que no pertenecen a
ninguna entidad concreta.

Se implementa en M2. Este modulo no importa Django ni consulta la base de datos:
recibe los datos que necesita como argumentos.
"""
