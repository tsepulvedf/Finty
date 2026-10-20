"""Registro de rutas con las variantes de sufijo de formato del router de DRF.

`DefaultRouter` del monolito publicaba cada ruta de `categories` y `accounts`
tambien con sufijo de formato: `/accounts.json`, `/accounts/{pk}.json`,
`/accounts/{pk}/archive.json`, con o sin barra final y sin redirigir. Las de
`transactions` se declaraban a mano, sin sufijo. `router_route()` reproduce eso
para que, tras la conmutacion, ninguna variante cambie de comportamiento.

Solo `.json`: DRF aceptaba ademas `.api` (la API navegable en HTML), que no
existe en el servicio (C-32), y respondia 404 a cualquier otro sufijo.
"""
FORMAT_SUFFIX = ".json"


def suffix_variants(rule):
    """La ruta y sus dos variantes con sufijo: sin barra final y con ella."""
    base = rule.rstrip("/")
    return (rule, base + FORMAT_SUFFIX, base + FORMAT_SUFFIX + "/")


def router_route(blueprint, rule, methods):
    """Decorador: registra la vista en `rule` y en sus variantes con sufijo."""

    def decorator(view):
        for variant in suffix_variants(rule):
            blueprint.add_url_rule(variant, view_func=view, methods=methods)
        return view

    return decorator
