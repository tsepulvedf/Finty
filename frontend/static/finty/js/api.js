/*
 * Cliente de /api/v1/ (ADR-11): mismo origen, a traves del Gateway.
 *
 * - Agrega `Authorization: Token <token>`; el token vive en localStorage.
 * - Centraliza los errores:
 *     401 → borra la sesion y lleva al ingreso;
 *     403 premium_required → lleva a la pantalla de planes;
 *     503 entitlements_unavailable → "intenta de nuevo", nunca la invitacion a pagar;
 *     429 → aviso.
 *   Despues lanza `ApiError` para que la pantalla muestre su estado de error.
 * - `displayCurrency()` da el `preferred_currency` del perfil, que se envia como
 *   `?display_currency=` donde la API lo admite.
 *
 * No contiene reglas de negocio: pide, devuelve y traduce errores.
 */
import { errorMessage } from "./codes.js";
import { toast } from "./dom.js";

const BASE = "/api/v1";
const TOKEN_KEY = "finty.token";
const PROFILE_KEY = "finty.profile";

export class ApiError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body || null;
    this.code = body && body.error ? body.error.code : null;
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
 * muestra el 403 a su manera).
 */
export async function api(path, options = {}) {
  const headers = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.auth !== false && token()) {
    headers.Authorization = `Token ${token()}`;
  }
  let response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
  } catch (networkError) {
    throw new ApiError(0, null);
  }
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
