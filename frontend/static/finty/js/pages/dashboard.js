/*
 * Dashboard (docs/design/Dashboard.dc.html).
 *
 * Datos, todos de la API:
 *   GET /analytics/dashboard/?period=     indicadores, tendencia y categorias
 *   GET /accounts/                        cuentas y sus saldos
 *   GET /transactions/                    ultimos movimientos
 *   GET /exchange-rates/?base=&target=    conversion de presentacion y su fuente
 *   GET /subscriptions/plans/             meses de historial del plan Free
 *   GET /analytics/insights/ y /analytics/spending-patterns/   (solo Premium)
 *
 * Sin reglas de negocio: no se suman saldos ni se comparan periodos. Se presenta
 * lo que la API calculo y, si la moneda difiere, se convierte con la tasa que la
 * API entrego (presentacion, INV-11).
 */
import { api, listAll } from "../api.js";
import { ACCOUNT_TYPES, RATE_SOURCES, categoryName, errorMessage, sourceLabel } from "../codes.js";
import { busy, byId, emptyState, errorState, h, replace, showFieldErrors, showFormError, skeletonRows, toast } from "../dom.js";
import { balance, money, monthName, parseAmount, percent, periodLabel, plainAmount, shortDate, signedMoney } from "../format.js";
import { format } from "../i18n.js";
import { periodOf, requestedPeriod, shift } from "../period.js";
import { startShell } from "../shell.js";

const state = {
  period: null,
  current: null,
  display: "COP",
  premium: false,
  freeHistoryMonths: null,
  accounts: [],
  rates: {},
};

// --- Periodos -------------------------------------------------------------

/** Primer periodo navegable: sin Premium, el limite de historial del plan Free. */
function firstAllowedPeriod() {
  if (state.premium || !state.freeHistoryMonths) {
    return null;
  }
  return shift(state.current, -(state.freeHistoryMonths - 1));
}

function renderPeriodControls() {
  byId("period-label").textContent = periodLabel(state.period);
  byId("period-title").textContent = format(gettext("Tu resumen de %(month)s"), { month: monthName(state.period) });
  const first = firstAllowedPeriod();
  byId("period-prev").disabled = first !== null && state.period <= first;
  byId("period-next").disabled = state.period >= state.current;
}

function changePeriod(months) {
  state.period = shift(state.period, months);
  const url = new URL(window.location.href);
  url.searchParams.set("period", state.period);
  window.history.replaceState(null, "", url);
  renderPeriodControls();
  loadPeriod();
}

// --- Tasas de cambio ---------------------------------------------------------

async function rate(base, target) {
  const key = `${base}-${target}`;
  if (!state.rates[key]) {
    state.rates[key] = api("/exchange-rates/", { query: { base, target } });
  }
  return state.rates[key];
}

/** Monto convertido a la moneda de presentacion con la tasa de la API. */
async function inDisplay(amount, currency) {
  if (currency === state.display) {
    return { amount: Number(amount), currency, converted: false };
  }
  const found = await rate(currency, state.display);
  return { amount: Number(amount) * Number(found.rate), currency: state.display, converted: true };
}

async function renderRateNote(currencies) {
  const note = byId("rate-note");
  const foreign = currencies.filter((currency) => currency !== state.display);
  if (!foreign.length) {
    note.hidden = true;
    return;
  }
  try {
    const usd = await rate("USD", "COP");
    const values = {
      rate: money(usd.rate, "COP"),
      source: RATE_SOURCES[usd.source] || usd.source,
    };
    note.textContent = usd.valid_from
      ? format(gettext("Conversión con la TRM oficial del %(date)s: %(rate)s por dólar · fuente: %(source)s. Los montos guardados no cambian."),
        Object.assign(values, { date: shortDate(usd.valid_from) }))
      : format(gettext("Conversión con una tasa de %(rate)s por dólar · fuente: %(source)s. Los montos guardados no cambian."), values);
    note.hidden = false;
  } catch (error) {
    note.textContent = gettext("No pudimos obtener la tasa de cambio: los montos se muestran en su moneda original.");
    note.hidden = false;
  }
}

// --- Indicadores, tendencia y categorias ------------------------------------------

function kpi(label, value, note, modifiers = "") {
  return h("div", { class: `kpi ${modifiers}` },
    h("span", { class: "kpi__label" }, label),
    h("span", { class: "kpi__value" }, value),
    note ? h("span", { class: "kpi__note" }, note) : null);
}

function previousPoint(section) {
  const index = section.trend.findIndex((point) => point.period === state.period);
  return index > 0 ? section.trend[index - 1] : null;
}

async function renderKpis(section, others) {
  const [income, expense, net] = await Promise.all([
    inDisplay(section.income, section.currency),
    inDisplay(section.expense, section.currency),
    inDisplay(section.net, section.currency),
  ]);
  const previous = previousPoint(section);
  const previousNote = (field) => previous
    ? format(gettext("%(month)s: %(amount)s"), { month: periodLabel(previous.period), amount: money(previous[field], section.currency) })
    : null;
  const originalNote = income.converted
    ? format(gettext("Convertido desde %(currency)s"), { currency: section.currency })
    : null;

  const cards = [
    kpi(gettext("Ingresos"), signedMoney(income.amount, income.currency, "income"), previousNote("income") || originalNote),
    kpi(gettext("Gastos"), signedMoney(expense.amount, expense.currency, "expense"), previousNote("expense") || originalNote),
    kpi(gettext("Neto del mes"), signedMoney(net.amount, net.currency), gettext("Ingresos menos gastos del período"), "kpi--dark"),
  ];
  cards[0].querySelector(".kpi__value").classList.add("amount--income");
  cards[1].querySelector(".kpi__value").classList.add("amount--expense");

  const extra = others.map((other) => h("p", { class: "notice notice--info" },
    format(gettext("También tienes movimientos en %(currency)s este mes: ingresos %(income)s y gastos %(expense)s."), {
      currency: other.currency,
      income: money(other.income, other.currency),
      expense: money(other.expense, other.currency),
    })));
  replace(byId("kpis"), h("div", { class: "kpis" }, cards), extra);
}

function renderTrend(section) {
  const points = section.trend;
  const top = Math.max(1, ...points.flatMap((point) => [Number(point.income), Number(point.expense)]));
  const height = (value) => `${Math.round((Number(value) / top) * 200)}px`;
  const description = points.map((point) => format(gettext("%(month)s: ingresos %(income)s, gastos %(expense)s"), {
    month: periodLabel(point.period),
    income: money(point.income, section.currency),
    expense: money(point.expense, section.currency),
  })).join(". ");

  const bars = h("div", { class: "bars", role: "img", "aria-label": description, style: { "--bar-groups": points.length } },
    points.map((point) => h("div", { class: "bars__group" },
      h("div", { class: "bars__bar", style: { height: height(point.income) } }),
      h("div", { class: "bars__bar bars__bar--expense", style: { height: height(point.expense) } }))));
  const labels = h("div", { class: "bars__labels", "aria-hidden": "true", style: { "--bar-groups": points.length } },
    points.map((point) => h("span", {}, monthName(point.period, true))));
  replace(byId("trend"), bars, labels);
}

function renderCategories(section) {
  const expenses = section.categories
    .filter((category) => category.transaction_type === "expense")
    .sort((a, b) => Number(b.total) - Number(a.total));
  if (!expenses.length) {
    replace(byId("categories"), emptyState(gettext("Sin gastos en este período"), gettext("Cuando registres gastos, verás aquí en qué se va tu dinero.")));
    return;
  }
  replace(byId("categories"), h("div", { class: "shares" }, expenses.map((category) => h("div", { class: "share" },
    h("div", { class: "share__head" },
      h("span", { class: "share__name" }, categoryName(category.category_name)),
      h("span", { class: "share__value" }, `${money(category.total, section.currency)} · ${percent(category.share)}`)),
    h("div", { class: "meter", role: "presentation" },
      h("div", { class: "meter__fill", style: { width: `${Number(category.share) * 100}%` } }))))));
}

function renderHistoryNotice() {
  const notice = byId("history-notice");
  if (state.premium || !state.freeHistoryMonths) {
    notice.hidden = true;
    return;
  }
  byId("history-notice-text").textContent = format(
    gettext("El plan Free muestra los últimos %(months)s meses. Con Premium ves todo tu historial."),
    { months: state.freeHistoryMonths },
  );
  notice.hidden = false;
}

function renderEmptyPeriod() {
  const action = state.accounts.length
    ? h("a", { class: "btn btn--primary btn--small", href: document.body.dataset.urlTransactions }, gettext("Registrar un movimiento"))
    : h("button", { type: "button", class: "btn btn--primary btn--small", onclick: openAccountDialog }, gettext("Crea tu primera cuenta"));
  replace(byId("kpis"), h("div", { class: "card" }, emptyState(
    format(gettext("No hay movimientos en %(period)s"), { period: periodLabel(state.period) }),
    gettext("Los indicadores aparecen cuando registras ingresos o gastos en el período."),
    action,
  )));
  replace(byId("trend"), emptyState(gettext("Sin datos para la tendencia"), gettext("Registra movimientos para ver cómo cambian tus ingresos y gastos mes a mes.")));
  replace(byId("categories"), emptyState(gettext("Sin gastos en este período"), gettext("Cuando registres gastos, verás aquí en qué se va tu dinero.")));
}

function renderPeriodError(error) {
  const notice = byId("period-notice");
  if (error.code === "premium_required") {
    replace(notice, h("div", { class: "notice notice--premium", role: "status" },
      h("span", {}, format(gettext("Este período está fuera de los últimos %(months)s meses que incluye el plan Free."), { months: state.freeHistoryMonths || 3 }))));
    replace(byId("kpis"), h("div", { class: "card" }, emptyState(gettext("Período no disponible en tu plan"), gettext("Vuelve a un mes reciente o pásate a Premium para ver todo tu historial."))));
    replace(byId("trend"));
    replace(byId("categories"));
    return;
  }
  replace(byId("kpis"), errorState(error, loadPeriod));
  replace(byId("trend"), errorState(error, loadPeriod));
  replace(byId("categories"), errorState(error, loadPeriod));
}

async function loadPeriod() {
  replace(byId("period-notice"));
  replace(byId("kpis"), h("div", { class: "kpis" }, [1, 2, 3].map(() => h("div", { class: "kpi" },
    h("span", { class: "skeleton skeleton--text" }), h("span", { class: "skeleton skeleton--title" })))));
  loadPremiumCard();
  try {
    const dashboard = await api("/analytics/dashboard/", { query: { period: state.period }, premiumRedirect: false });
    renderHistoryNotice();
    if (!dashboard.currencies.length) {
      renderEmptyPeriod();
      return;
    }
    const main = dashboard.currencies.find((section) => section.currency === state.display) || dashboard.currencies[0];
    const others = dashboard.currencies.filter((section) => section !== main);
    renderTrend(main);
    renderCategories(main);
    await renderKpis(main, others);
  } catch (error) {
    renderPeriodError(error);
  }
}

// --- Cuentas -------------------------------------------------------------------

async function renderAccounts() {
  const container = byId("accounts");
  if (!state.accounts.length) {
    replace(container, emptyState(gettext("Crea tu primera cuenta"),
      gettext("Registra dónde tienes tu dinero: efectivo, banco o tarjeta de crédito."),
      h("button", { type: "button", class: "btn btn--primary btn--small", onclick: openAccountDialog }, gettext("Crear cuenta"))));
    byId("rate-note").hidden = true;
    return;
  }
  const items = await Promise.all(state.accounts.map(async (account) => {
    let shown = balance(account.balance, account.currency);
    let original = null;
    try {
      const value = await inDisplay(account.balance, account.currency);
      if (value.converted) {
        shown = balance(value.amount, value.currency);
        original = `${account.currency} ${plainAmount(account.balance, account.currency)}`;
      }
    } catch (error) {
      /* sin tasa: se muestra en su moneda original */
    }
    const amount = h("span", { class: Number(account.balance) < 0 ? "amount--expense" : "" }, shown);
    return h("li", { class: "account" },
      h("div", { class: "stack-tight" },
        h("span", { class: "account__name" }, account.name),
        h("span", { class: "account__meta" }, `${ACCOUNT_TYPES[account.type] || account.type} · ${account.currency}`)),
      h("span", { class: "account__balance" }, amount, original ? h("span", { class: "account__original" }, original) : null));
  }));
  replace(container, h("ul", { class: "accounts" }, items));
  renderRateNote([...new Set(state.accounts.map((account) => account.currency))]);
}

async function loadAccounts() {
  replace(byId("accounts"), skeletonRows(3));
  try {
    state.accounts = (await listAll("/accounts/")).filter((account) => !account.is_archived);
    await renderAccounts();
  } catch (error) {
    replace(byId("accounts"), errorState(error, loadAccounts));
  }
}

// --- Ultimos movimientos ------------------------------------------------------------

const ICONS = {
  income: "M3 6h18v12H3zM12 9.5a2.5 2.5 0 110 5 2.5 2.5 0 010-5",
  expense: "M6 4h12l-1 16H7zM9 8h6",
};

function icon(type) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "22");
  svg.setAttribute("height", "22");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICONS[type] || ICONS.expense);
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.8");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

function provenance(transaction) {
  const label = sourceLabel(transaction.categorization_source);
  return transaction.categorization_source && transaction.categorization_source !== "manual" && transaction.categorization_confidence !== null
    ? `${label} ${percent(transaction.categorization_confidence)}`
    : label;
}

async function loadLatest() {
  const container = byId("latest");
  replace(container, skeletonRows(4));
  try {
    const page = await api("/transactions/");
    const latest = page.results.slice(0, 5);
    if (!latest.length) {
      replace(container, emptyState(gettext("Todavía no hay movimientos"),
        gettext("Registra tu primer gasto o ingreso y Finty lo clasificará por ti."),
        h("a", { class: "btn btn--primary btn--small", href: document.body.dataset.urlTransactions }, gettext("Registrar un movimiento"))));
      return;
    }
    const currencies = Object.fromEntries(state.accounts.map((account) => [account.id, account.currency]));
    replace(container, h("ul", { class: "rows" }, latest.map((transaction) => h("li", { class: "row" },
      h("span", { class: "row__icon" }, icon(transaction.type)),
      h("div", { class: "row__body" },
        h("span", { class: "row__title" }, transaction.description || categoryName(transaction.category_name)),
        h("span", { class: "row__meta" }, [shortDate(transaction.occurred_on), transaction.account_name, categoryName(transaction.category_name), provenance(transaction)].join(" · "))),
      h("span", { class: `row__amount amount--${transaction.type}` },
        signedMoney(transaction.amount, currencies[transaction.account] || "COP", transaction.type))))));
  } catch (error) {
    replace(container, errorState(error, loadLatest));
  }
}

// --- Tarjeta Premium ------------------------------------------------------------

async function loadPremiumCard() {
  const title = byId("premium-card-title");
  const link = byId("premium-card-link");
  if (!state.premium) {
    title.textContent = gettext("Con Premium, Finty detecta hallazgos y gastos recurrentes en tus movimientos.");
    link.textContent = gettext("Conoce el plan Premium →");
    return;
  }
  byId("premium-card").href = document.body.dataset.urlInsights;
  try {
    const [insights, patterns] = await Promise.all([
      api("/analytics/insights/", { query: { period: state.period }, premiumRedirect: false }),
      api("/analytics/spending-patterns/", { query: { period: state.period }, premiumRedirect: false }),
    ]);
    const findings = insights.insights.length;
    const recurring = patterns.patterns.length;
    title.textContent = format(gettext("Este mes: %(findings)s y %(recurring)s."), {
      findings: format(ngettext("%(count)s hallazgo", "%(count)s hallazgos", findings), { count: findings }),
      recurring: format(ngettext("%(count)s gasto recurrente", "%(count)s gastos recurrentes", recurring), { count: recurring }),
    });
    link.textContent = gettext("Ver los insights →");
  } catch (error) {
    title.textContent = errorMessage(error);
    link.textContent = "";
  }
}

// --- Dialogo de nueva cuenta ------------------------------------------------------

let dialogOpener = null;

function openAccountDialog(event) {
  dialogOpener = event && event.currentTarget ? event.currentTarget : byId("new-account");
  byId("account-form").reset();
  showFieldErrors("account", {});
  showFormError("account-error", "");
  byId("account-currency").value = state.display;
  byId("account-dialog").showModal();
  byId("account-name").focus();
}

function closeAccountDialog() {
  byId("account-dialog").close();
}

function bindAccountDialog() {
  const dialog = byId("account-dialog");
  byId("new-account").addEventListener("click", openAccountDialog);
  byId("account-dialog-close").addEventListener("click", closeAccountDialog);
  byId("account-cancel").addEventListener("click", closeAccountDialog);
  dialog.addEventListener("close", () => {
    if (dialogOpener) {
      dialogOpener.focus();
    }
  });
  byId("account-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    showFormError("account-error", "");
    const name = byId("account-name").value.trim();
    if (!name) {
      showFieldErrors("account", { name: [gettext("Este campo es obligatorio.")] });
      byId("account-name").focus();
      return;
    }
    const body = { name, type: byId("account-type").value, currency: byId("account-currency").value };
    const opening = parseAmount(byId("account-balance").value);
    if (opening) {
      body.initial_balance = opening;
    }
    await busy(byId("account-submit"), async () => {
      try {
        await api("/accounts/", { method: "POST", body });
        closeAccountDialog();
        toast(format(gettext("Cuenta «%(name)s» creada."), { name }));
        await loadAccounts();
        loadLatest();
      } catch (error) {
        if (error.fields) {
          showFormError("account-error", showFieldErrors("account", error.fields).join(" "));
        } else {
          showFormError("account-error", errorMessage(error));
        }
      }
    });
  });
}

// --- Arranque ------------------------------------------------------------------------

async function start() {
  const { profile, subscription } = await startShell();
  state.current = periodOf(new Date());
  state.period = requestedPeriod(state.current);
  state.premium = Boolean(subscription && subscription.premium);
  state.display = profile.preferred_currency === "USD" ? "USD" : "COP";

  byId("greeting").textContent = format(gettext("Hola, %(name)s"), { name: (profile.display_name || "").split(" ")[0] || profile.email });
  const currency = byId("display-currency");
  currency.value = state.display;
  currency.addEventListener("change", () => {
    state.display = currency.value;
    renderAccounts();
    loadPeriod();
  });

  try {
    const plans = await api("/subscriptions/plans/");
    const free = plans.results.find((plan) => plan.code === "FREE");
    state.freeHistoryMonths = free ? free.history_months : null;
  } catch (error) {
    state.freeHistoryMonths = null;
  }

  bindAccountDialog();
  byId("period-prev").addEventListener("click", () => changePeriod(-1));
  byId("period-next").addEventListener("click", () => changePeriod(1));
  renderPeriodControls();

  await loadAccounts();
  loadLatest();
  loadPeriod();

  if (new URLSearchParams(window.location.search).has("nueva-cuenta")) {
    openAccountDialog();
  }
}

start();
