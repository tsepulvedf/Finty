"""Casos de uso del contexto `identity` (anillo de Servicios).

Contendra `ProfileService`, que orquesta la lectura y actualizacion del perfil
del usuario autenticado: valida la semantica de los datos apoyandose en el
dominio y coordina la persistencia.

Se implementa en M1. Las views no ejecutan reglas: delegan aqui (CLAUDE.md,
regla 3). Este modulo depende de `domain/` y de `models.py`, nunca al reves.
"""
