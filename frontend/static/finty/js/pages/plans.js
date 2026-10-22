/*
 * Planes (docs/design/Planes.dc.html). Destino del 403 premium_required.
 *
 * Datos, todos de la API:
 *   GET /subscriptions/plans/   precio, periodo y beneficios de cada plan
 *   GET /subscriptions/me/      el plan que da acceso ahora (lo trae shell.js)
 *
 * Los beneficios se traducen por `code`. Que plan es el actual lo dice la API;
 * la pagina solo decide que boton mostrar.
 */
import { api } from "../api.js";
import { BENEFITS, PLANS } from "../codes.js";
import { byId, errorState, h, replace } from "../dom.js";
import { currencyCode, money } from "../format.js";
import { format } from "../i18n.js";
import { startShell } from "../shell.js";

function checkIcon() {
  return byId("check-icon").content.firstElementChild.cloneNode(true);
}

function checks(items) {
  return h("ul", { class: "checks" }, items.map((text) => h("li", null, checkIcon(), h("span", null, text))));
}

function priceUnit(plan) {
  if (plan.price_in_cents === 0) {
    return gettext("para siempre");
  }
  return format(
    ngettext("%(currency)s al mes", "%(currency)s cada %(count)s meses", plan.period_months),
    { currency: currencyCode(plan.price, plan.currency), count: plan.period_months },
  ).trim();
}

function action(plan, subscription) {
  if (subscription && subscription.plan === plan.code) {
    return h("span", { class: "current-plan" }, gettext("Tu plan actual"));
  }
  if (plan.code === "PREMIUM" && subscription) {
    return h("a", { class: "btn btn--premium btn--lg btn--block", href: document.body.dataset.urlCheckout },
      gettext("Pasar a Premium"));
  }
  return null;
}

function card(plan, free, subscription) {
  const premium = plan.code === "PREMIUM";
  const included = premium && free
    ? [gettext("Todo lo del plan Free"), ...plan.benefits.filter((code) => !free.benefits.includes(code)).map((code) => BENEFITS[code] || code)]
    : plan.benefits.map((code) => BENEFITS[code] || code);
  return h("section", { class: premium ? "price-card price-card--premium" : "price-card", "aria-labelledby": `plan-${plan.code}` },
    h("div", { class: "stack" },
      h("div", { class: "price-card__head" },
        h("h2", { class: "price-card__name", id: `plan-${plan.code}` }, PLANS[plan.code] || plan.code),
        premium ? h("span", { class: "badge-premium" }, gettext("Recomendado")) : null),
      h("div", { class: "price" },
        h("span", { class: "price__amount" }, money(plan.price, plan.currency)),
        h("span", { class: "price__unit" }, priceUnit(plan)))),
    checks(included),
    action(plan, subscription));
}

async function load(subscription) {
  const container = byId("pricing");
  container.setAttribute("aria-busy", "true");
  try {
    const { results } = await api("/subscriptions/plans/");
    const free = results.find((plan) => plan.code === "FREE");
    replace(container, results.map((plan) => card(plan, free, subscription)));
  } catch (error) {
    replace(container, errorState(error, () => load(subscription)));
  }
}

async function start() {
  const { subscription } = await startShell();
  if (!subscription) {
    // Sin subscription-service no se sabe el plan actual: se muestran los
    // planes, sin ofrecer un pago que podria duplicarse.
    replace(byId("plans-notice"), h("p", { class: "notice notice--error", role: "status" },
      gettext("No pudimos verificar tu plan en este momento. Intenta de nuevo en unos minutos.")));
  }
  await load(subscription);
}

start();
