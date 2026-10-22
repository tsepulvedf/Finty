/*
 * Cabecera comun de las pantallas autenticadas (app_base.html).
 *
 * - Sin token, lleva al ingreso antes de pedir nada.
 * - Indicador de plan: GET /api/v1/subscriptions/me/. Free enlaza a Planes;
 *   Premium, a Ajustes.
 * - Avatar con las iniciales del perfil, que enlaza a Ajustes (donde se cierra
 *   la sesion).
 * - En movil la navegacion es una fila que se desplaza: la seccion activa se
 *   deja a la vista al cargar.
 */
import { api, goToLogin, profile, token } from "./api.js";
import { PLANS } from "./codes.js";
import { byId } from "./dom.js";
import { initials } from "./format.js";

function renderPlan(subscription) {
  const chip = byId("plan-chip");
  if (subscription.premium) {
    chip.textContent = PLANS.PREMIUM;
    chip.classList.add("plan-chip--premium");
    chip.href = document.body.dataset.urlSettings;
  } else {
    chip.textContent = gettext("Plan Free · Mejorar");
    chip.classList.remove("plan-chip--premium");
    chip.href = document.body.dataset.urlPlans;
  }
}

function revealActiveSection() {
  const active = document.querySelector('.nav [aria-current="page"]');
  if (active) {
    active.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

/** Sin token, al ingreso. Para las paginas sin cabecera (checkout, bienvenida). */
export function requireSession() {
  if (!token()) {
    goToLogin();
    return false;
  }
  return true;
}

/**
 * Prepara la cabecera. Devuelve `{profile, subscription}` para la pagina; la
 * suscripcion puede ser `null` si subscription-service no responde: la pagina
 * sigue funcionando con lo gratuito (INV-06).
 */
export async function startShell() {
  if (!requireSession()) {
    return new Promise(() => {});
  }
  revealActiveSection();
  const [me, subscription] = await Promise.all([
    profile(),
    api("/subscriptions/me/").catch(() => null),
  ]);
  byId("avatar-initials").textContent = initials(me.display_name || me.email);
  if (subscription) {
    renderPlan(subscription);
  } else {
    byId("plan-chip").hidden = true;
  }
  return { profile: me, subscription };
}
