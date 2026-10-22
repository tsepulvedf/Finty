/*
 * Textos de JavaScript (ADR-11, A-23).
 *
 * `gettext`, `ngettext` e `interpolate` los define el JavaScriptCatalog de
 * Django (/jsi18n/), que base.html carga antes que cualquier modulo. Todo texto
 * visible que genera el JavaScript pasa por aqui; `makemessages -d djangojs` los
 * extrae de las llamadas literales a gettext() de cada archivo.
 */

/** Interpola `%(nombre)s` con los valores de `values` (formato de Django). */
export function format(template, values) {
  return window.interpolate(template, values, true);
}

/** Idioma activo de la pagina, el que eligio el selector ES/EN. */
export function language() {
  // Sin `document` (los tests de Node), espanol.
  return (typeof document !== "undefined" && document.documentElement.lang) || "es";
}

/** Locale de Intl para cifras y fechas: Colombia en espanol, EE. UU. en ingles. */
export function intlLocale() {
  return language().startsWith("en") ? "en-US" : "es-CO";
}
