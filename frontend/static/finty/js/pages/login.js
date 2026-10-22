/*
 * Ingreso: POST /api/v1/auth/login/ y el token a localStorage.
 *
 * Con sesion abierta, va directo al dashboard. Tras ingresar vuelve a `?next=`
 * si apunta a una pagina de Finty.
 */
import { api, saveSession, token } from "../api.js";
import { errorMessage } from "../codes.js";
import { busy, byId, showFormError } from "../dom.js";

function destination() {
  const next = new URLSearchParams(window.location.search).get("next");
  // Solo rutas locales: nunca otro origen.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : document.body.dataset.urlDashboard;
}

if (token()) {
  window.location.replace(destination());
}

const form = byId("login-form");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showFormError("login-error", "");
  const email = byId("login-email").value.trim();
  const password = byId("login-password").value;
  if (!email || !password) {
    showFormError("login-error", gettext("Escribe tu correo y tu contraseña."));
    return;
  }
  await busy(byId("login-submit"), async () => {
    try {
      const session = await api("/auth/login/", { method: "POST", body: { email, password }, auth: false });
      saveSession(session.token);
      window.location.assign(destination());
    } catch (error) {
      showFormError("login-error", errorMessage(error));
      byId("login-password").focus();
    }
  });
});
