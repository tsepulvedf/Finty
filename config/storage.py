"""Almacen de estaticos con nombres con hash (ADR-11).

`collectstatic` copia cada archivo como `api.3f2a9c1b7d4e.js` y escribe
`staticfiles.json`; `{% static %}` resuelve el nombre con hash. Un despliegue
nuevo cambia el nombre de todo archivo que cambio, asi que el navegador nunca
reutiliza un JavaScript o un CSS viejo, y Nginx puede guardarlos un año.

`support_js_module_import_aggregation` reescribe tambien los `import ... from
"./api.js"` de los modulos de JavaScript: sin eso, una pagina con hash cargaria
dependencias sin hash.
"""
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class FintyStaticFilesStorage(ManifestStaticFilesStorage):
    support_js_module_import_aggregation = True
