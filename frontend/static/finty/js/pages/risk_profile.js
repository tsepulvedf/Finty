/*
 * Perfil de riesgo (docs/design/PerfilRiesgo.dc.html; §6.6).
 *
 * Datos, todos de la API:
 *   GET /recommendations/risk-profile/   respuestas guardadas (404 si aun no hay)
 *   PUT /recommendations/risk-profile/   las cinco respuestas → puntaje y tipo
 *   GET /recommendations/                instrumento sugerido para el perfil, si
 *                                        el plan lo incluye (Premium)
 *
 * El diseño recalcula el resultado en vivo; aqui no: el puntaje y los rangos
 * son reglas de recommendation-service. El resultado se muestra despues de
 * guardar, con lo que devuelve el PUT.
 */
import { api } from "../api.js";
import { RISK_PROFILES, errorMessage, instrumentList } from "../codes.js";
import { busy, byId, h, replace, showFormError, toast } from "../dom.js";
import { format } from "../i18n.js";
import { startShell } from "../shell.js";

const QUESTIONS = ["investment_horizon", "loss_reaction", "experience", "income_stability", "goal"];

function fillAnswers(answers) {
  for (const code of QUESTIONS) {
    const input = document.querySelector(`input[name="${code}"][value="${answers[code]}"]`);
    if (input) {
      input.checked = true;
    }
  }
}

function readAnswers() {
  const answers = {};
  for (const code of QUESTIONS) {
    const checked = document.querySelector(`input[name="${code}"]:checked`);
    if (checked) {
      answers[code] = Number(checked.value);
    }
  }
  return answers;
}

/** Instrumento sugerido, solo si GET /recommendations/ ya lo trae. */
async function suggestedInstrument() {
  try {
    const report = await api("/recommendations/", { premiumRedirect: false });
    const invest = report.recommendations.find((item) => item.code === "invest_by_risk_profile");
    return invest ? instrumentList(invest.params.instrument_types) : "";
  } catch (error) {
    return "";
  }
}

async function renderResult(saved) {
  const container = byId("risk-result");
  const body = byId("risk-result-body");
  if (!saved) {
    replace(body, h("p", { class: "result__text" },
      gettext("Responde las cinco preguntas y guarda tu perfil para ver el resultado.")));
    container.removeAttribute("aria-busy");
    return;
  }
  const profile = RISK_PROFILES[saved.risk_profile_type] || { name: saved.risk_profile_type, text: "" };
  const instrument = await suggestedInstrument();
  replace(body, h("div", { class: "stack" },
    h("span", { class: "result__name" }, profile.name),
    h("span", { class: "result__score" }, format(gettext("Puntaje: %(score)s"), { score: saved.score })),
    h("p", { class: "result__text" }, profile.text),
    instrument
      ? h("div", { class: "result__box" },
        h("span", { class: "eyebrow-tag" }, gettext("Instrumento sugerido")),
        h("span", null, instrument))
      : null,
    h("a", { class: "btn btn--light", href: document.body.dataset.urlInvestments }, gettext("Ver mis inversiones"))));
  container.removeAttribute("aria-busy");
}

async function submit(event) {
  event.preventDefault();
  showFormError("risk-error", "");
  const answers = readAnswers();
  const missing = QUESTIONS.filter((code) => !(code in answers));
  if (missing.length) {
    showFormError("risk-error", gettext("Responde las cinco preguntas antes de guardar."));
    document.querySelector(`input[name="${missing[0]}"]`).focus();
    return;
  }
  await busy(byId("risk-submit"), async () => {
    try {
      const saved = await api("/recommendations/risk-profile/", { method: "PUT", body: answers });
      await renderResult(saved);
      toast(gettext("Perfil guardado."));
      byId("risk-result").scrollIntoView({ block: "nearest" });
    } catch (error) {
      showFormError("risk-error", errorMessage(error));
    }
  });
}

async function start() {
  await startShell();
  byId("risk-form").addEventListener("submit", submit);
  try {
    const saved = await api("/recommendations/risk-profile/");
    fillAnswers(saved.answers);
    await renderResult(saved);
  } catch (error) {
    if (error.status === 404) {
      await renderResult(null);
    } else {
      replace(byId("risk-result-body"), h("p", { class: "result__text" }, errorMessage(error)));
      byId("risk-result").removeAttribute("aria-busy");
    }
  }
}

start();
