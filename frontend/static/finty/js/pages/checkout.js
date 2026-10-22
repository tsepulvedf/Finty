/*
 * Checkout simulado (docs/design/Checkout.dc.html; ADR-14, handoff §8).
 *
 * El formulario de tarjeta es una simulacion:
 *   - su formato se valida solo aqui, en el navegador;
 *   - sus valores nunca salen de esta pagina: no se envian, no se guardan en
 *     el almacenamiento del navegador y no se escriben en la consola;
 *   - "Continuar" envia POST /subscriptions/checkout/ con un unico campo, `plan`.
 *     El backend rechaza con 400 cualquier otro (`extra="forbid"`).
 *
 * Con el pago APPROVED, la pagina lleva a la bienvenida. Lo verifica
 * core/tests/test_frontend.py::TestCheckout.
 */
import { api } from "../api.js";
import { PAYMENT_STATUSES, PLANS, errorMessage } from "../codes.js";
import { busy, byId, emptyState, errorState, h, replace, showFieldErrors, showFormError } from "../dom.js";
import { currencyCode, money } from "../format.js";
import { format } from "../i18n.js";
import { requireSession } from "../shell.js";

const CARD_FIELDS = ["number", "name", "expiry", "cvc"];

function field(name) {
  return byId(`card-${name}`);
}

function digits(text) {
  return text.replace(/\D/g, "");
}

// --- Formato mientras se escribe (solo presentacion) ------------------------------

function groupCardNumber() {
  const input = field("number");
  input.value = digits(input.value).slice(0, 19).replace(/(\d{4})(?=\d)/g, "$1 ");
}

function slashExpiry(event) {
  const input = field("expiry");
  const value = digits(input.value).slice(0, 4);
  input.value = value.length > 2 || (value.length === 2 && event.inputType !== "deleteContentBackward")
    ? `${value.slice(0, 2)}/${value.slice(2)}`
    : value;
}

function onlyDigits() {
  const input = field("cvc");
  input.value = digits(input.value).slice(0, 3);
}

/** Validacion de formato, solo en el navegador. Devuelve `{campo: [mensaje]}`. */
function formatErrors() {
  const errors = {};
  if (!/^\d{13,19}$/.test(digits(field("number").value))) {
    errors.number = [gettext("Escribe un número de tarjeta de 13 a 19 dígitos.")];
  }
  if (field("name").value.trim().length < 2) {
    errors.name = [gettext("Escribe el nombre como aparece en la tarjeta.")];
  }
  if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(field("expiry").value.trim())) {
    errors.expiry = [gettext("Usa el formato MM/AA, con un mes entre 01 y 12.")];
  }
  if (!/^\d{3}$/.test(field("cvc").value.trim())) {
    errors.cvc = [gettext("El CVC debe tener 3 dígitos.")];
  }
  return errors;
}

/** Borra lo escrito en la tarjeta: nada queda en la pagina tras el intento. */
function clearCard() {
  for (const name of CARD_FIELDS) {
    field(name).value = "";
  }
}

// --- Resumen y envio --------------------------------------------------------------

function periodText(plan) {
  return format(ngettext("%(count)s mes", "%(count)s meses", plan.period_months), { count: plan.period_months });
}

function row(label, value) {
  return h("div", { class: "summary-row" }, h("span", null, label), h("strong", null, value));
}

function renderSummary(plan) {
  replace(byId("summary"),
    row(PLANS[plan.code] || plan.code, money(plan.price, plan.currency)),
    row(gettext("Período"), periodText(plan)),
    row(gettext("Renovación"), gettext("Manual")),
    h("div", { class: "divider" }),
    h("div", { class: "summary-total" },
      h("span", null, gettext("Total hoy")),
      h("span", null, `${money(plan.price, plan.currency)} ${currencyCode(plan.price, plan.currency)}`.trim())));
  byId("checkout-submit").textContent = format(gettext("Continuar · %(price)s"), { price: money(plan.price, plan.currency) });
}

async function submit(event, plan) {
  event.preventDefault();
  showFormError("checkout-error", "");
  const errors = formatErrors();
  showFieldErrors("card", errors);
  if (Object.keys(errors).length) {
    field(CARD_FIELDS.find((name) => errors[name])).focus();
    return;
  }
  const button = byId("checkout-submit");
  await busy(button, async () => {
    try {
      // Solo el plan. Ningun valor del formulario entra en esta peticion.
      const result = await api("/subscriptions/checkout/", { method: "POST", body: { plan: plan.code } });
      clearCard();
      if (result.payment && result.payment.status === "APPROVED") {
        window.location.assign(document.body.dataset.urlWelcome);
        return;
      }
      const status = result.payment ? PAYMENT_STATUSES[result.payment.status] || result.payment.status : "";
      showFormError("checkout-error", format(gettext("El pago simulado no se aprobó (%(status)s). Puedes intentarlo de nuevo."), { status }));
    } catch (error) {
      showFormError("checkout-error", errorMessage(error));
    }
  });
}

function showAlreadyPremium() {
  const form = byId("checkout-form");
  replace(form, emptyState(
    gettext("Ya tienes el plan Premium"),
    gettext("Tu suscripción está vigente: no necesitas pagar de nuevo."),
    h("a", { class: "btn btn--primary", href: document.body.dataset.urlDashboard }, gettext("Ir al dashboard"))));
}

async function start() {
  if (!requireSession()) {
    return;
  }
  field("number").addEventListener("input", groupCardNumber);
  field("expiry").addEventListener("input", slashExpiry);
  field("cvc").addEventListener("input", onlyDigits);
  try {
    const [plans, subscription] = await Promise.all([api("/subscriptions/plans/"), api("/subscriptions/me/")]);
    if (subscription.premium) {
      showAlreadyPremium();
      replace(byId("summary"), h("p", { class: "state__text" }, PLANS.PREMIUM));
      return;
    }
    const plan = plans.results.find((item) => item.code === "PREMIUM");
    renderSummary(plan);
    byId("checkout-form").addEventListener("submit", (event) => submit(event, plan));
    byId("checkout-submit").disabled = false;
  } catch (error) {
    replace(byId("summary"), errorState(error, () => window.location.reload()));
  }
}

start();
