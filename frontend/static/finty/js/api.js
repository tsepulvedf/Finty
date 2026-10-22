/*
 * Cliente de /api/v1/ (ADR-11): mismo origen, a traves del Gateway.
 *
 * - Agrega `Authorization: Token <token>`; el token vive en localStorage.
 * - Centraliza los errores:
 *     401 → borra la sesion y lleva al ingreso;
 *     403 premium_required → lleva a la pantalla de planes;
 *     503 entitlements_unavailable → "intenta de nuevo", nunca la invitacion a pagar;
 *     503 service_unavailable (el Gateway: el servicio no responde) → su texto,
 *       que la pantalla muestra en su estado de error;
 *     429 → aviso.
 *   Despues lanza `ApiError` para que la pantalla muestre su estado de error.
 * - `displayCurrency()` da el `preferred_currency` del perfil, que se envia como
 *   `?display_currency=` donde la API lo admite.
 *
 * No contiene reglas de negocio: pide, devuelve y traduce errores.
 */
import { errorMessage } from "./codes.js";
import { toast } from "./dom.js";
import { language } from "./i18n.js";

const BASE = "/api/v1";
const TOKEN_KEY = "finty.token";
const PROFILE_KEY = "finty.profile";

export class ApiError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body || null;
    // Los errores de dominio traen `{"error": {"code"}}`; el 503 del Gateway,
    // `{"detail", "code"}` (la forma de sus 401 y 429).
    this.code = body && body.error ? body.error.code : (body && body.code) || null;
    // Un 400 de validacion trae `{"campo": ["mensaje"]}`.
    this.fields = status === 400 && body && !body.error && !body.detail ? body : null;
  }
}

function storage() {
  try {
    return window.localStorage;
  } catch (error) {
    return null;
  }
}

export function token() {
  const store = storage();
  return store ? store.getItem(TOKEN_KEY) : null;
}

export function saveSession(newToken) {
  const store = storage();
  if (store) {
    store.setItem(TOKEN_KEY, newToken);
    window.sessionStorage.removeItem(PROFILE_KEY);
  }
}

/** Cierra la sesion en este navegador y vuelve al ingreso. */
export function logout() {
  clearSession();
  window.location.assign(urls().urlLogin);
}

/** Olvida el perfil guardado en la pestaña (tras cambiarlo en Ajustes). */
export function forgetProfile() {
  try {
    window.sessionStorage.removeItem(PROFILE_KEY);
  } catch (error) {
    /* sin sessionStorage no hay nada que olvidar */
  }
}

export function clearSession() {
  const store = storage();
  if (store) {
    store.removeItem(TOKEN_KEY);
  }
  try {
    window.sessionStorage.removeItem(PROFILE_KEY);
  } catch (error) {
    /* sin sessionStorage no hay nada que limpiar */
  }
}

function urls() {
  return document.body.dataset;
}

export function goToLogin() {
  const next = window.location.pathname + window.location.search;
  const login = urls().urlLogin;
  window.location.assign(next && next !== login ? `${login}?next=${encodeURIComponent(next)}` : login);
}

function buildUrl(path, query) {
  const url = new URL(BASE + path, window.location.origin);
  for (const [name, value] of Object.entries(query || {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(name, value);
    }
  }
  return url.pathname + url.search;
}

function handle(error, options) {
  if (error.status === 401 && options.auth !== false) {
    clearSession();
    goToLogin();
    return;
  }
  if (error.code === "premium_required" && options.premiumRedirect !== false) {
    window.location.assign(urls().urlPlans);
    return;
  }
  if (error.code === "entitlements_unavailable" || error.status === 429) {
    toast(errorMessage(error), "error");
  }
}

/**
 * `api("/accounts/", {method: "POST", body: {...}})` → cuerpo JSON.
 *
 * Opciones: `query` (parametros de consulta), `auth: false` (login y registro:
 * sin token y sin redirigir ante un 401), `premiumRedirect: false` (la pantalla
 * muestra el 403 a su manera) y `localized: true` (envia `Accept-Language` con
 * el idioma de la pagina, para lo que el servidor redacta, como el reporte).
 */
export async function api(path, options = {}) {
  const response = await send(path, options, "application/json");
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch (parseError) {
    body = null;
  }
  if (!response.ok) {
    const error = new ApiError(response.status, body);
    handle(error, options);
    throw error;
  }
  return body;
}

async function send(path, options, accept) {
  const headers = { Accept: accept };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.auth !== false && token()) {
    headers.Authorization = `Token ${token()}`;
  }
  if (options.localized) {
    headers["Accept-Language"] = language();
  }
  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
  } catch (networkError) {
    throw new ApiError(0, null);
  }
}

/**
 * Descarga un archivo con el token (un enlace simple no lo lleva) y lo entrega
 * al navegador con el nombre de `Content-Disposition`.
 */
export async function download(path, fallbackName) {
  const response = await send(path, {}, "*/*");
  if (!response.ok) {
    const text = await response.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch (parseError) {
      body = null;
    }
    const error = new ApiError(response.status, body);
    handle(error, {});
    throw error;
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Perfil del usuario, una vez por pestaña. */
export async function profile() {
  try {
    const cached = window.sessionStorage.getItem(PROFILE_KEY);
    if (cached) {
      return JSON.parse(cached);
    }
  } catch (error) {
    /* sin sessionStorage: se pide cada vez */
  }
  const data = await api("/profile/");
  try {
    window.sessionStorage.setItem(PROFILE_KEY, JSON.stringify(data));
  } catch (error) {
    /* no se pudo guardar: no pasa nada */
  }
  return data;
}

/** Moneda de presentacion: el `preferred_currency` del perfil (ADR-12). */
export async function displayCurrency() {
  return (await profile()).preferred_currency || "COP";
}

/** Agrega `display_currency` a una consulta, para las rutas que lo admiten. */
export async function withDisplayCurrency(query = {}) {
  return Object.assign({ display_currency: await displayCurrency() }, query);
}

/** Todas las paginas de un listado paginado (`count`, `next`, `results`). */
export async function listAll(path, query) {
  const results = [];
  let page = 1;
  for (;;) {
    const data = await api(path, { query: Object.assign({}, query, { page }) });
    results.push(...data.results);
    if (!data.next) {
      return results;
    }
    page += 1;
  }
}
