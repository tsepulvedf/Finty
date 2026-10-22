/*
 * Bienvenida a Premium (docs/design/Bienvenida.dc.html; handoff §8).
 *
 * Datos, todos de la API:
 *   GET /subscriptions/me/      plan vigente y fin del periodo
 *   GET /subscriptions/plans/   beneficios de cada plan, traducidos por `code`
 *   GET /profile/               el nombre para el saludo
 *
 * Se listan los beneficios del plan Premium que el plan Free no tiene: lo que
 * se acaba de desbloquear.
 */
import { api, profile } from "../api.js";
import { BENEFITS, BENEFIT_DETAILS } from "../codes.js";
import { byId, emptyState, errorState, h, replace } from "../dom.js";
import { longDate } from "../format.js";
import { format } from "../i18n.js";
import { requireSession } from "../shell.js";

function icon() {
  return byId("benefit-icon").content.firstElementChild.cloneNode(true);
}

function benefit(code) {
  return h("li", { class: "benefit" },
    h("span", { class: "icon-tile" }, icon()),
    h("div", { class: "stack-tight" },
      h("span", { class: "benefit__title" }, BENEFITS[code] || code),
      BENEFIT_DETAILS[code] ? h("span", { class: "benefit__text" }, BENEFIT_DETAILS[code]) : null));
}

function notPremium() {
  byId("welcome-title").textContent = gettext("Todavía no tienes Premium");
  byId("welcome-lead").textContent = gettext("Si acabas de pagar y ves este mensaje, vuelve a intentarlo desde los planes.");
  replace(byId("benefits"));
  const primary = byId("welcome-primary");
  primary.href = document.body.dataset.urlPlans;
  primary.textContent = gettext("Ver los planes");
}

async function start() {
  if (!requireSession()) {
    return;
  }
  try {
    const [me, plans, subscription] = await Promise.all([
      profile(), api("/subscriptions/plans/"), api("/subscriptions/me/"),
    ]);
    if (!subscription.premium) {
      notPremium();
      return;
    }
    const name = (me.display_name || "").split(" ")[0];
    byId("welcome-title").textContent = name
      ? format(gettext("¡Gracias, %(name)s! Ya eres Premium"), { name })
      : gettext("¡Gracias! Ya eres Premium");
    const until = subscription.current_period_end ? longDate(subscription.current_period_end.slice(0, 10)) : "";
    byId("welcome-lead").textContent = until
      ? format(gettext("Tu plan está activo hasta el %(date)s. Esto es lo que acabas de desbloquear:"), { date: until })
      : gettext("Esto es lo que acabas de desbloquear:");
    const free = plans.results.find((plan) => plan.code === "FREE");
    const premium = plans.results.find((plan) => plan.code === "PREMIUM");
    const unlocked = premium.benefits.filter((code) => !(free && free.benefits.includes(code)));
    replace(byId("benefits"), unlocked.length
      ? unlocked.map(benefit)
      : h("li", null, emptyState(gettext("Tu plan Premium está activo"), null)));
  } catch (error) {
    byId("welcome-title").textContent = gettext("No pudimos cargar tu plan");
    replace(byId("benefits"), h("li", null, errorState(error, start)));
  }
}

start();
