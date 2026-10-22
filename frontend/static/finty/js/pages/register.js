/*
 * Registro: POST /api/v1/auth/register/, que ya devuelve el token.
 *
 * Los errores por campo (400) salen junto a cada campo, con el texto de la API
 * en el idioma activo; los de dominio, por su `code`.
 */
import { api, saveSession, token } from "../api.js";
import { errorMessage } from "../codes.js";
import { busy, byId, showFieldErrors, showFormError } from "../dom.js";

if (token()) {
  window.location.replace(document.body.dataset.urlDashboard);
}

const FIELD_IDS = { display_name: "register-name", email: "register-email", password: "register-password" };

function showErrors(fields) {
  const mapped = {};
  for (const [field, messages] of Object.entries(fields || {})) {
    mapped[FIELD_IDS[field] ? FIELD_IDS[field].replace("register-", "") : field] = messages;
  }
  return showFieldErrors("register", mapped);
}

byId("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showFormError("register-error", "");
  showErrors({});
  const body = {
    display_name: byId("register-name").value.trim(),
    email: byId("register-email").value.trim(),
    password: byId("register-password").value,
  };
  const missing = {};
  for (const [field, value] of Object.entries(body)) {
    if (!value) {
      missing[field] = [gettext("Este campo es obligatorio.")];
    }
  }
  if (Object.keys(missing).length) {
    showErrors(missing);
    return;
  }
  await busy(byId("register-submit"), async () => {
    try {
      const session = await api("/auth/register/", { method: "POST", body, auth: false });
      saveSession(session.token);
      window.location.assign(document.body.dataset.urlDashboard);
    } catch (error) {
      if (error.fields) {
        const orphans = showErrors(error.fields);
        showFormError("register-error", orphans.join(" "));
      } else {
        showFormError("register-error", errorMessage(error));
      }
    }
  });
});
