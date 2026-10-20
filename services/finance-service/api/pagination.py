"""Paginacion por numero de pagina, con el formato de DRF.

Reproduce `PageNumberPagination` con `PAGE_SIZE = 50`, que es lo que devolvia el
monolito en todo listado: `{"count", "next", "previous", "results"}`, con
`next` y `previous` como URL absolutas y `?page=last` como alias de la ultima
pagina. Una pagina fuera de rango o mal formada responde 404 `Página inválida.`

Los enlaces se construyen igual que DRF (`replace_query_param`,
`remove_query_param`): los parametros quedan ordenados alfabeticamente.
"""
from math import ceil
from urllib import parse

from flask import request

import messages
from api.errors import NotFound
from api.parsing import query_value

PAGE_SIZE = 50
PAGE_QUERY_PARAM = "page"
LAST_PAGE_STRINGS = ("last",)

# `django.utils.encoding.escape_uri_path`: caracteres que no se escapan.
URI_PATH_SAFE = "/:@&+$,-_.!~*'()"


def _absolute_uri():
    """URL absoluta de la peticion (`HttpRequest.build_absolute_uri()`)."""
    path = parse.quote(request.path, safe=URI_PATH_SAFE)
    query = request.query_string.decode("latin-1")
    url = f"{request.scheme}://{request.host}{path}"
    return f"{url}?{query}" if query else url


def _replace_query_param(url, key, value):
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict[key] = [str(value)]
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def _remove_query_param(url, key):
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict.pop(key, None)
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def _page_number(raw, num_pages):
    """Valida el numero de pagina como `Paginator.validate_number` de Django."""
    if raw in LAST_PAGE_STRINGS:
        return num_pages
    try:
        number = int(raw)
    except (TypeError, ValueError) as exc:
        raise NotFound(messages.INVALID_PAGE) from exc
    if number < 1 or number > num_pages:
        raise NotFound(messages.INVALID_PAGE)
    return number


def paginate(listing, serialize):
    """Pagina un `Listing` y devuelve el cuerpo de la respuesta."""
    count = listing.count()
    # Con cero filas sigue existiendo la pagina 1, vacia (`allow_empty_first_page`).
    num_pages = ceil(max(1, count) / PAGE_SIZE)
    number = _page_number(query_value(PAGE_QUERY_PARAM) or 1, num_pages)

    rows = listing.fetch((number - 1) * PAGE_SIZE, PAGE_SIZE)

    url = _absolute_uri()
    next_link = (
        _replace_query_param(url, PAGE_QUERY_PARAM, number + 1)
        if number < num_pages
        else None
    )
    if number == 1:
        previous_link = None
    elif number - 1 == 1:
        previous_link = _remove_query_param(url, PAGE_QUERY_PARAM)
    else:
        previous_link = _replace_query_param(url, PAGE_QUERY_PARAM, number - 1)

    return {
        "count": count,
        "next": next_link,
        "previous": previous_link,
        "results": [serialize(row) for row in rows],
    }
