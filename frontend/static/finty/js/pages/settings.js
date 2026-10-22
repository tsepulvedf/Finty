/*
 * Ajustes (docs/design/Ajustes.dc.html).
 *
 * Datos, todos de la API:
 *   GET / PUT /profile/                 nombre visible, moneda preferida e idioma
 *   GET /subscriptions/me/              estado y fin del periodo (lo trae shell.js)
 *   GET /subscriptions/plans/           precio del plan, para la ficha
 *   POST /subscriptions/me/cancel/      cancelar; se conserva el acceso hasta el fin
 *
 * El idioma se guarda en el perfil (es el de los correos, E2-M7) y, si cambia,
 * tambien en la cookie de Django con `set_language`, igual que el selector
 * ES/EN, para que la pagina cambie de idioma. Cerrar sesion borra el token de
 * este navegador.
 */
import { api, forgetProfile, logout } from "../api.js";
import { PLANS, SUBSCRIPTION_STATUSES, errorMessage } from "../codes.js";
import { busy, byId, errorState, h, replace, showFieldErrors, showFormError } from "../dom.js";
import { longDate, money } from "../format.js";
import { format } from "../i18n.js";
import { startShell } from "../shell.js";

const SAVED_FLAG = "guardado";

// --- Perfil ------------------------------------------------------------------

function fillProfile(profile) {
  byId("profile-display_name").value = profile.display_name || "";
  byId("profile-email").value = profile.email || "";
  byId("profile-preferred_currency").value = profile.preferred_currency === "USD" ? "USD" : "COP";
  byId("profile-submit").disabled = false;
}

function changeLanguage(language) {
  const next = new URL(window.location.href);
  next.searchParams.set(SAVED_FLAG, "1");
  byId("language-next").value = next.pathname + next.search;
  byId("language-value").value = language;
  byId("language-form").submit();
}

async function saveProfile(event) {
  event.preventDefault();
  showFormError("profile-error", "");
  showFieldErrors("profile", {});
  byId("profile-saved").hidden = true;
  const displayName = byId("profile-display_name").value.trim();
  if (!displayName) {
    showFieldErrors("profile", { display_name: [gettext("Este campo es obligatorio.")] });
    byId("profile-display_name").focus();
    return;
  }
  await busy(byId("profile-submit"), async () => {
    try {
      const language = byId("profile-language");
      await api("/profile/", {
        method: "PUT",
        body: {
          display_name: displayName,
          preferred_currency: byId("profile-preferred_currency").value,
          language: language.value,
        },
      });
      forgetProfile();
      if (language.value !== language.dataset.current) {
        changeLanguage(language.value);
        return;
      }
      byId("profile-saved").hidden = false;
    } catch (error) {
      if (error.fields) {
        showFormError("profile-error", showFieldErrors("profile", error.fields).join(" "));
      } else {
        showFormError("profile-error", errorMessage(error));
      }
    }
  });
}

// --- Suscripcion ---------------------------------------------------------------

function periodEnd(subscription) {
  return subscription.current_period_end ? longDate(subscription.current_period_end.slice(0, 10)) : "";
}

function fact(label, value) {
  return h("div", null, h("dt", null, label), h("dd", null, value));
}

function planLine(subscription, plans) {
  const plan = (plans || []).find((item) => item.code === subscription.plan);
  const name = PLANS[subscription.plan] || subscription.plan;
  if (!plan || plan.price_in_cents === 0) {
    return name;
  }
  return format(ngettext("%(plan)s · %(price)s al mes", "%(plan)s · %(price)s cada %(count)s meses", plan.period_months), {
    plan: name, price: money(plan.price, plan.currency), count: plan.period_months,
  });
}

function renderSubscription(subscription, plans) {
  const chip = byId("subscription-status");
  const container = byId("subscription");
  const status = subscription.status;
  chip.hidden = !status;
  chip.textContent = status ? SUBSCRIPTION_STATUSES[status] || status : "";
  chip.className = status === "ACTIVE" ? "status-chip"
    : status === "CANCELED" ? "status-chip status-chip--warning" : "status-chip status-chip--neutral";

  if (!subscription.premium) {
    replace(container,
      h("dl", { class: "facts" }, fact(gettext("Plan"), planLine(subscription, plans))),
      h("div", { class: "card__foot" },
        h("p", null, gettext("Con Premium ves tus insights, tus gastos recurrentes, todo tu historial y recomendaciones de inversión.")),
        h("a", { class: "btn btn--premium", href: document.body.dataset.urlPlans }, gettext("Ver planes"))));
    return;
  }
  const until = periodEnd(subscription);
  const facts = h("dl", { class: "facts" },
    fact(gettext("Plan"), planLine(subscription, plans)),
    fact(status === "CANCELED" ? gettext("Acceso premium hasta") : gettext("Activa hasta"), until),
    fact(gettext("Renovación"), gettext("Manual")));
  if (status === "CANCELED") {
    replace(container, facts, h("div", { class: "card__foot" },
      h("p", null, format(gettext("Cancelaste tu suscripción. Conservas las funciones premium hasta el %(date)s; después vuelves al plan Free sin perder tus datos."), { date: until }))));
    return;
  }
  replace(container, facts, h("div", { class: "card__foot" },
    h("p", null, format(gettext("Si cancelas, conservas las funciones premium hasta el %(date)s. Después vuelves al plan Free sin perder tus datos."), { date: until })),
    h("button", { type: "button", class: "btn btn--danger", id: "cancel-open", onclick: () => openCancel(subscription, plans) }, gettext("Cancelar suscripción"))));
}

function openCancel(subscription, plans) {
  const dialog = byId("cancel-dialog");
  byId("cancel-dialog-text").textContent = format(
    gettext("Conservas las funciones premium hasta el %(date)s. No se hace ningún reembolso: es un pago simulado."),
    { date: periodEnd(subscription) });
  showFormError("cancel-error", "");
  byId("cancel-keep").onclick = () => dialog.close();
  byId("cancel-confirm").onclick = () => busy(byId("cancel-confirm"), async () => {
    try {
      const updated = await api("/subscriptions/me/cancel/", { method: "POST" });
      dialog.close();
      renderSubscription(updated, plans);
      byId("subscription-title").focus();
    } catch (error) {
      showFormError("cancel-error", errorMessage(error));
    }
  });
  dialog.showModal();
  byId("cancel-keep").focus();
}

async function loadSubscription(subscription) {
  const container = byId("subscription");
  try {
    const [me, plans] = await Promise.all([
      subscription ? Promise.resolve(subscription) : api("/subscriptions/me/"),
      api("/subscriptions/plans/").then((data) => data.results).catch(() => null),
    ]);
    renderSubscription(me, plans);
  } catch (error) {
    replace(container, errorState(error, () => loadSubscription(null)));
  }
}

// --- Arranque ------------------------------------------------------------------

async function start() {
  const { profile, subscription } = await startShell();
  fillProfile(profile);
  const params = new URLSearchParams(window.location.search);
  if (params.has(SAVED_FLAG)) {
    byId("profile-saved").hidden = false;
    params.delete(SAVED_FLAG);
    window.history.replaceState(null, "", window.location.pathname + (params.toString() ? `?${params}` : ""));
  }
  byId("profile-form").addEventListener("submit", saveProfile);
  byId("logout").addEventListener("click", logout);
  byId("subscription-title").setAttribute("tabindex", "-1");
  loadSubscription(subscription);
}

start();
