/*
 * Recomendaciones e inversion (docs/design/Inversiones.dc.html; §6.6, handoff §8).
 *
 * Datos, todos de la API:
 *   GET /recommendations/?display_currency=   optimizacion, inversion y `locked`
 *   GET /recommendations/risk-profile/        el perfil (404 si no hay)
 *   GET /investment-plans/ y POST             planes (solo Premium)
 *   GET /exchange-rates/?base=USD&target=COP  la tasa y su fuente
 *
 * Que se recomienda, el excedente, el instrumento por perfil y la proyeccion de
 * un plan los calcula recommendation-service. Cuando la parte de inversion
 * llega en `locked`, se muestra el bloqueo con la invitacion a Premium; si el
 * bloqueo es por `entitlements_unavailable`, "intenta de nuevo".
 */
import { api, displayCurrency } from "../api.js";
import {
  INSTRUMENTS, RATE_SOURCES, RECOMMENDATION_SOURCES, RISK_PROFILES,
  errorMessage, noticeText, recommendationContent,
} from "../codes.js";
import { busy, byId, emptyState, errorState, h, replace, showFieldErrors, showFormError, toast } from "../dom.js";
import { longDate, monthName, money, parseAmount, percent } from "../format.js";
import { format } from "../i18n.js";
import { startShell } from "../shell.js";

const state = { display: "COP", premium: false, profile: null, instruments: Object.keys(INSTRUMENTS) };

function icon(id) {
  return byId(id).content.firstElementChild.cloneNode(true);
}

function stat(label, value, note) {
  return h("div", { class: "stat" },
    h("span", { class: "stat__label" }, label),
    h("span", { class: "stat__value" }, value),
    note ? h("span", { class: "stat__note" }, note) : null);
}

/** Presenta un monto de la recomendacion: el convertido por la API si lo hay. */
function amountOf(recommendation) {
  return (key) => {
    const display = recommendation.display;
    if (display && display.amounts && display.amounts[key] !== undefined) {
      return money(display.amounts[key], display.currency);
    }
    const value = recommendation.params[key] !== undefined ? recommendation.params[key] : recommendation.evidence[key];
    return value === null || value === undefined ? "" : money(value, recommendation.params.currency);
  };
}

function disclaimer(notice) {
  const text = noticeText(notice);
  return text ? h("p", { class: "disclaimer" }, icon("icon-info"), h("span", null, text)) : null;
}

function recommendationCard(recommendation) {
  const content = recommendationContent(recommendation, amountOf(recommendation));
  return h("article", { class: "recommendation" },
    h("span", { class: recommendation.kind === "investment" ? "icon-tile icon-tile--warning" : "icon-tile" },
      icon(recommendation.kind === "investment" ? "icon-shield" : "icon-spark")),
    h("div", { class: "recommendation__body" },
      h("h3", { class: "recommendation__title" }, content.title),
      h("p", { class: "recommendation__text" }, content.text),
      h("span", { class: "fine-print" }, RECOMMENDATION_SOURCES[recommendation.source] || ""),
      disclaimer(recommendation.disclaimer)));
}

function surplusRange(months) {
  if (!months || !months.length) {
    return "";
  }
  return format(gettext("%(first)s a %(last)s"), {
    first: monthName(months[0].period), last: monthName(months[months.length - 1].period),
  });
}

function investCard(recommendation) {
  const amount = amountOf(recommendation);
  const profile = RISK_PROFILES[recommendation.params.risk_profile_type] || { name: recommendation.params.risk_profile_type };
  const content = recommendationContent(recommendation, amount);
  const surplus = recommendation.params.monthly_surplus;
  return h("article", { class: "card" },
    h("div", { class: "stats" },
      stat(gettext("Excedente mensual promedio"),
        surplus === null ? gettext("No disponible ahora") : amount("monthly_surplus"),
        surplusRange(recommendation.evidence.surplus_months)),
      stat(gettext("Tu perfil"), profile.name,
        state.profile ? format(gettext("Puntaje: %(score)s"), { score: state.profile.score }) : null)),
    h("div", { class: "stack-tight" },
      h("span", { class: "eyebrow-tag" }, gettext("Instrumento sugerido")),
      h("h3", { class: "recommendation__title" }, content.title),
      h("p", { class: "recommendation__text" }, content.text)),
    disclaimer(recommendation.disclaimer));
}

function lockedCard(lock) {
  if (lock.code === "entitlements_unavailable") {
    return h("div", { class: "card" }, errorState({ status: 503, code: lock.code }, () => loadRecommendations()));
  }
  return h("article", { class: "locked-card" },
    h("span", { class: "icon-tile icon-tile--warning icon-tile--lg" }, icon("icon-lock")),
    h("div", { class: "locked-card__body" },
      h("h3", { class: "recommendation__title" }, gettext("Invierte tu excedente con Premium")),
      h("p", { class: "recommendation__text" },
        gettext("Con Premium te sugerimos en qué tipo de instrumento invertirlo según tu perfil, y puedes guardar planes con su proyección."))),
    h("a", { class: "btn btn--premium", href: document.body.dataset.urlPlans }, gettext("Desbloquear")));
}

function noProfileCard() {
  return h("div", { class: "card" }, emptyState(
    gettext("Primero, tu perfil de riesgo"),
    gettext("Responde cinco preguntas para que Finty te sugiera un tipo de instrumento."),
    h("a", { class: "btn btn--primary", href: document.body.dataset.urlRiskProfile }, gettext("Responder el cuestionario"))));
}

async function loadRecommendations() {
  const optimization = byId("optimization");
  const investment = byId("investment");
  optimization.setAttribute("aria-busy", "true");
  investment.setAttribute("aria-busy", "true");
  try {
    const report = await api("/recommendations/", { query: { display_currency: state.display } });
    const optimizing = report.recommendations.filter((item) => item.kind === "optimization");
    const investing = report.recommendations.filter((item) => item.kind === "investment");
    replace(byId("degraded-notice"), report.degraded
      ? h("p", { class: "notice notice--info", role: "status" },
        gettext("Parte del análisis de tus gastos no está disponible en este momento: las recomendaciones pueden estar incompletas."))
      : null);
    replace(optimization, optimizing.length
      ? optimizing.map(recommendationCard)
      : h("div", { class: "card" }, emptyState(
        gettext("Nada que optimizar este mes"),
        gettext("Cuando un gasto se dispare o se repita cada mes, aquí verás cómo ajustarlo."))));
    const lock = (report.locked || []).find((item) => item.kind === "investment");
    if (lock) {
      replace(investment, lockedCard(lock));
    } else if (!report.risk_profile_type) {
      replace(investment, noProfileCard());
    } else {
      state.instruments = instrumentsOf(investing) || state.instruments;
      replace(investment, investing.map((item) => (item.code === "invest_by_risk_profile" ? investCard(item) : recommendationCard(item))));
    }
  } catch (error) {
    replace(optimization, h("div", { class: "card" }, errorState(error, loadRecommendations)));
    replace(investment);
  }
}

function instrumentsOf(investing) {
  const invest = investing.find((item) => item.code === "invest_by_risk_profile");
  return invest && invest.params.instrument_types && invest.params.instrument_types.length ? invest.params.instrument_types : null;
}

// --- Perfil y tasa -------------------------------------------------------------

async function loadProfile() {
  const card = byId("profile-card");
  const body = byId("profile-card-body");
  try {
    state.profile = await api("/recommendations/risk-profile/");
    const current = state.profile.risk_profile_type;
    const profile = RISK_PROFILES[current] || { name: current, text: "" };
    const types = Object.keys(RISK_PROFILES);
    replace(body,
      h("span", { class: "profile-card__name" }, profile.name),
      h("div", { class: "scale", role: "img", "aria-label": format(gettext("Escala de perfil: %(current)s de %(all)s"), {
        current: profile.name, all: types.map((type) => RISK_PROFILES[type].name).join(", "),
      }) }, types.map((type) => h("span", { class: type === current ? "scale__step is-current" : "scale__step" }))),
      h("div", { class: "scale__labels", "aria-hidden": "true" },
        types.map((type) => h("span", { class: type === current ? "is-current" : null }, RISK_PROFILES[type].name))),
      h("p", { class: "profile-card__text" }, profile.text));
  } catch (error) {
    state.profile = null;
    if (error.status === 404) {
      replace(body, h("p", { class: "profile-card__text" }, gettext("Aún no has respondido el cuestionario.")));
      byId("profile-card-link").textContent = gettext("Responder el cuestionario");
    } else {
      replace(body, h("p", { class: "profile-card__text" }, errorMessage(error)));
    }
  }
  card.removeAttribute("aria-busy");
}

async function loadRate() {
  const container = byId("rate");
  try {
    const rate = await api("/exchange-rates/", { query: { base: "USD", target: "COP" } });
    replace(container,
      h("span", { class: "stat__value" }, money(rate.rate, "COP")),
      h("span", { class: "fine-print" }, format(
        rate.valid_from
          ? gettext("TRM del %(date)s por 1 USD · fuente: %(source)s")
          : gettext("Por 1 USD · fuente: %(source)s"),
        { date: rate.valid_from ? longDate(rate.valid_from) : "", source: RATE_SOURCES[rate.source] || rate.source })));
  } catch (error) {
    replace(container, errorState(error, loadRate));
  }
}

// --- Planes de inversion ---------------------------------------------------------

function planCard(plan) {
  const profile = RISK_PROFILES[plan.risk_profile_type] || { name: plan.risk_profile_type };
  const projection = plan.projection;
  return h("article", { class: "plan-card" },
    h("div", { class: "plan-card__head" },
      h("h3", { class: "plan-card__title" }, format(gettext("%(instrument)s · %(months)s"), {
        instrument: INSTRUMENTS[plan.instrument_type] || plan.instrument_type,
        months: format(ngettext("%(count)s mes", "%(count)s meses", plan.horizon_months), { count: plan.horizon_months }),
      })),
      h("span", { class: "fine-print" }, format(gettext("Creado con perfil %(profile)s"), { profile: profile.name }))),
    h("div", { class: "stats" },
      stat(gettext("Aporte mensual"), money(plan.monthly_contribution, plan.currency)),
      stat(gettext("Total aportado"), money(projection.total_contributed, plan.currency)),
      stat(gettext("Proyección"), money(projection.projected_value, plan.currency))),
    h("p", { class: "fine-print" }, format(
      gettext("Proyección ilustrativa con una tasa anual de referencia del %(rate)s. No es un rendimiento garantizado."),
      { rate: percent(projection.annual_rate, 1) })),
    disclaimer(plan.disclaimer));
}

async function loadPlans() {
  const container = byId("plans");
  container.setAttribute("aria-busy", "true");
  try {
    const data = await api("/investment-plans/", { premiumRedirect: false });
    replace(container, data.results.length
      ? data.results.map(planCard)
      : emptyState(gettext("Aún no tienes planes"), gettext("Guarda una meta con su aporte mensual y su horizonte para ver la proyección.")));
  } catch (error) {
    replace(container, errorState(error, loadPlans));
  }
}

function openPlanDialog() {
  const select = byId("plan-instrument");
  select.replaceChildren(...state.instruments.map((code) => h("option", { value: code }, INSTRUMENTS[code] || code)));
  byId("plan-form").reset();
  byId("plan-currency").value = state.display;
  showFieldErrors("plan", {});
  showFormError("plan-error", "");
  byId("plan-dialog").showModal();
  select.focus();
}

function bindPlanDialog() {
  const dialog = byId("plan-dialog");
  const close = () => dialog.close();
  byId("new-plan").addEventListener("click", openPlanDialog);
  byId("plan-close").addEventListener("click", close);
  byId("plan-cancel").addEventListener("click", close);
  dialog.addEventListener("close", () => byId("new-plan").focus());
  byId("plan-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    showFormError("plan-error", "");
    const body = {
      instrument_type: byId("plan-instrument").value,
      monthly_contribution: parseAmount(byId("plan-contribution").value),
      horizon_months: Number(byId("plan-horizon").value),
      currency: byId("plan-currency").value,
    };
    await busy(byId("plan-submit"), async () => {
      try {
        await api("/investment-plans/", { method: "POST", body });
        close();
        toast(gettext("Plan de inversión guardado."));
        await loadPlans();
      } catch (error) {
        if (error.fields) {
          showFormError("plan-error", showFieldErrors("plan", error.fields).join(" "));
        } else {
          showFormError("plan-error", errorMessage(error));
        }
      }
    });
  });
}

// --- Arranque --------------------------------------------------------------------

async function start() {
  const { subscription } = await startShell();
  state.premium = Boolean(subscription && subscription.premium);
  state.display = (await displayCurrency()) === "USD" ? "USD" : "COP";
  const select = byId("display-currency");
  select.value = state.display;
  select.addEventListener("change", () => {
    state.display = select.value;
    loadRecommendations();
  });
  if (state.premium) {
    byId("plans-section").hidden = false;
    bindPlanDialog();
    loadPlans();
  }
  loadRate();
  await loadProfile();
  await loadRecommendations();
}

start();
