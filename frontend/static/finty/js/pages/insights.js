/*
 * Insights (docs/design/Insights.dc.html). Funcion Premium (INV-06).
 *
 * Datos, todos de la API:
 *   GET /subscriptions/me/                       si el usuario es Premium (shell.js)
 *   GET /analytics/insights/?period=             hallazgos con `params` y `evidence`
 *   GET /analytics/spending-patterns/?period=    gastos recurrentes de la ventana
 *
 * El plan Free ve la invitacion sin pedir nada premium. Las reglas (umbral,
 * meses comparados, ventana) las pone analytics; la pagina presenta su
 * `evidence`, no la recalcula.
 */
import { api } from "../api.js";
import { INSIGHT_TAGS, categoryName, insightRule, insightText } from "../codes.js";
import { byId, cell, emptyState, errorState, h, replace, tableRegion } from "../dom.js";
import { money, monthName, periodLabel, shortDate } from "../format.js";
import { format } from "../i18n.js";
import { periodOf, requestedPeriod, shift } from "../period.js";
import { startShell } from "../shell.js";

const state = { period: null, current: null };

// --- Hallazgos ---------------------------------------------------------------

function icon(id) {
  return byId(id).content.firstElementChild.cloneNode(true);
}

function stat(label, value) {
  return h("div", { class: "stat" }, h("span", { class: "stat__label" }, label), h("span", { class: "stat__value" }, value));
}

function monthRange(months) {
  if (!months.length) {
    return "";
  }
  const first = monthName(months[0].period);
  const last = monthName(months[months.length - 1].period);
  return first === last ? first : format(gettext("%(first)s a %(last)s"), { first, last });
}

/** Los numeros con los que se decidio cada hallazgo, tal como los entrego la API. */
function evidenceOf(insight) {
  const currency = insight.params.currency;
  const evidence = insight.evidence;
  if (insight.code === "category_spike") {
    return h("div", { class: "stats" },
      stat(monthName(insight.period, true), money(evidence.current, currency)),
      stat(format(gettext("Promedio de %(range)s"), { range: monthRange(evidence.previous_months || []) }),
        money(evidence.previous_average, currency)));
  }
  if (insight.code === "top_category") {
    return h("div", { class: "stack-tight" },
      h("div", { class: "meter meter--lg", role: "presentation" },
        h("div", { class: "meter__fill", style: { width: `${Math.min(Number(insight.params.share_pct), 100)}%` } })),
      h("span", { class: "fine-print" }, format(gettext("%(part)s de %(total)s en gastos"), {
        part: money(evidence.category_total, currency), total: money(evidence.expense_total, currency),
      })));
  }
  if (insight.code === "negative_savings") {
    return h("div", { class: "stats" },
      stat(gettext("Ingresos"), money(evidence.income, currency)),
      stat(gettext("Gastos"), money(evidence.expense, currency)));
  }
  return null;
}

function finding(insight) {
  const warning = insight.severity === "warning";
  return h("article", { class: warning ? "card insight insight--warning" : "card insight" },
    h("div", { class: "insight__head" },
      h("span", { class: warning ? "icon-tile icon-tile--warning" : "icon-tile" }, icon(warning ? "icon-warning" : "icon-info")),
      h("span", { class: "insight__tag" }, INSIGHT_TAGS[insight.code] || insight.code)),
    h("h3", { class: "insight__title" }, insightText(insight)),
    evidenceOf(insight),
    h("p", { class: "fine-print" }, insightRule(insight)));
}

async function loadFindings() {
  const container = byId("findings");
  container.setAttribute("aria-busy", "true");
  try {
    const data = await api("/analytics/insights/", { query: { period: state.period } });
    replace(container, data.insights.length
      ? data.insights.map(finding)
      : h("div", { class: "card" }, emptyState(
        gettext("Sin hallazgos este mes"),
        gettext("Cuando una categoría cambie frente a tus meses anteriores o tus gastos superen a tus ingresos, lo verás aquí."))));
  } catch (error) {
    replace(container, h("div", { class: "card" }, errorState(error, loadFindings)));
  }
}

// --- Gastos recurrentes --------------------------------------------------------

const PATTERN_COLUMNS = {
  expense: gettext("Gasto"), category: gettext("Categoría"), months: gettext("Meses presentes"),
  last: gettext("Última vez"), average: gettext("Monto promedio"),
};

function patternRow(pattern) {
  return h("tr", null,
    cell(PATTERN_COLUMNS.expense, { class: "cell--title" }, h("strong", null, pattern.description)),
    cell(PATTERN_COLUMNS.category, null, categoryName(pattern.category_name)),
    cell(PATTERN_COLUMNS.months, null, format(gettext("%(present)s de %(window)s"), { present: pattern.months_present, window: pattern.window_months })),
    cell(PATTERN_COLUMNS.last, null, shortDate(pattern.last_seen)),
    cell(PATTERN_COLUMNS.average, { class: "num" }, money(pattern.average_amount, pattern.currency)));
}

async function loadPatterns() {
  const container = byId("patterns");
  const count = byId("patterns-count");
  container.setAttribute("aria-busy", "true");
  try {
    const data = await api("/analytics/spending-patterns/", { query: { period: state.period } });
    byId("patterns-rule").textContent = format(
      gettext("Misma descripción y categoría, con un monto parecido, presente en varios de los últimos %(window)s meses."),
      { window: data.window_months });
    count.textContent = format(ngettext("%(count)s detectado", "%(count)s detectados", data.patterns.length), { count: data.patterns.length });
    count.hidden = false;
    if (!data.patterns.length) {
      replace(container, emptyState(
        gettext("Sin gastos recurrentes"),
        gettext("Aparecerán cuando un mismo gasto se repita en varios meses.")));
      return;
    }
    const caption = gettext("Gastos recurrentes detectados");
    replace(container, tableRegion(caption,
      h("table", { class: "table table--stack" },
        h("caption", { class: "visually-hidden" }, caption),
        h("thead", null, h("tr", null,
          h("th", { scope: "col" }, PATTERN_COLUMNS.expense),
          h("th", { scope: "col" }, PATTERN_COLUMNS.category),
          h("th", { scope: "col" }, PATTERN_COLUMNS.months),
          h("th", { scope: "col" }, PATTERN_COLUMNS.last),
          h("th", { scope: "col", class: "num" }, PATTERN_COLUMNS.average))),
        h("tbody", null, data.patterns.map(patternRow)))));
  } catch (error) {
    count.hidden = true;
    replace(container, errorState(error, loadPatterns));
  }
}

// --- Periodo -------------------------------------------------------------------

function renderPeriod() {
  byId("period-label").textContent = periodLabel(state.period);
  byId("insights-title").textContent = format(gettext("Insights de %(month)s"), { month: monthName(state.period) });
  byId("period-next").disabled = state.period >= state.current;
}

function move(months) {
  state.period = shift(state.period, months);
  const url = new URL(window.location.href);
  url.searchParams.set("period", state.period);
  window.history.replaceState(null, "", url);
  renderPeriod();
  loadFindings();
  loadPatterns();
}

async function start() {
  const { subscription } = await startShell();
  state.current = periodOf(new Date());
  state.period = requestedPeriod(state.current);
  if (!subscription) {
    // Sin saber el plan no se invita a pagar: "intenta de nuevo" (INV-06).
    byId("insights-premium").replaceChildren(h("div", { class: "card" }, errorState({ status: 503, code: "entitlements_unavailable" }, () => window.location.reload())));
    return;
  }
  if (!subscription.premium) {
    byId("insights-locked").hidden = false;
    byId("insights-premium").remove();
    return;
  }
  byId("period-tools").hidden = false;
  byId("period-prev").addEventListener("click", () => move(-1));
  byId("period-next").addEventListener("click", () => move(1));
  renderPeriod();
  loadFindings();
  loadPatterns();
}

start();
