/*
 * Cabecera comun de las pantallas autenticadas (app_base.html).
 *
 * - Sin token, lleva al ingreso antes de pedir nada.
 * - Indicador de plan: GET /api/v1/subscriptions/me/.
 * - Avatar con las iniciales del perfil y el menu para cerrar sesion.
 */
import { api, clearSession, goToLogin, profile, token } from "./api.js";
import { PLANS } from "./codes.js";
import { byId } from "./dom.js";
import { initials } from "./format.js";

function bindMenu() {
  const button = byId("avatar");
  const menu = byId("account-menu");
  const close = () => {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };
  button.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) {
      byId("logout").focus();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      close();
      button.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !button.contains(event.target)) {
      close();
    }
  });
  byId("logout").addEventListener("click", () => {
    clearSession();
    window.location.assign(document.body.dataset.urlLogin);
  });
}

function renderPlan(subscription) {
  const chip = byId("plan-chip");
  if (subscription.premium) {
    chip.textContent = PLANS.PREMIUM;
    chip.classList.add("is-premium");
  } else {
    chip.textContent = gettext("Plan Free · Mejorar");
    chip.classList.remove("is-premium");
  }
}

/**
 * Prepara la cabecera. Devuelve `{profile, subscription}` para la pagina; la
 * suscripcion puede ser `null` si subscription-service no responde: la pagina
 * sigue funcionando con lo gratuito (INV-06).
 */
export async function startShell() {
  if (!token()) {
    goToLogin();
    return new Promise(() => {});
  }
  bindMenu();
  const [me, subscription] = await Promise.all([
    profile(),
    api("/subscriptions/me/").catch(() => null),
  ]);
  byId("avatar-initials").textContent = initials(me.display_name || me.email);
  byId("account-email").textContent = me.email;
  if (subscription) {
    renderPlan(subscription);
  } else {
    byId("plan-chip").hidden = true;
  }
  return { profile: me, subscription };
}
