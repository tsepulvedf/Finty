/*
 * Movimientos (docs/design/Movimientos.dc.html).
 *
 *   GET  /transactions/?account_id=&category_id=&date_from=&date_to=&page=
 *   POST /transactions/                       registrar
 *   POST /transactions/{id}/categorize/       recategorizar
 *   DELETE /transactions/{id}/                eliminar (con confirmacion)
 *   GET  /accounts/ y /categories/            opciones de los selectores
 *
 * Los filtros son los que admite la API; la clasificacion, el saldo y la
 * validacion los hace finance-service. La lista de categorias del formulario se
 * filtra por el tipo elegido solo para no ofrecer opciones que la API
 * rechazaria (category_type_mismatch).
 */
import { api, listAll } from "../api.js";
import { categoryName, errorMessage, sourceLabel } from "../codes.js";
import { busy, byId, emptyState, errorState, h, replace, showFieldErrors, showFormError, skeletonRows, toast } from "../dom.js";
import { longDate, parseAmount, percent, shortDate, signedMoney } from "../format.js";
import { format } from "../i18n.js";
import { startShell } from "../shell.js";

const state = {
  accounts: [],
  categories: [],
  page: 1,
  // Posicion del primer movimiento de cada pagina visitada: el rango
  // "Mostrando a–b" sale de lo que la API devolvio, sin suponer su tamaño de pagina.
  offsets: [0],
  data: null,
  selected: null,
  type: "expense",
};

function currencyOf(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  return account ? account.currency : "COP";
}

function filters() {
  return {
    account_id: byId("filter-account").value,
    category_id: byId("filter-category").value,
    date_from: byId("filter-from").value,
    date_to: byId("filter-to").value,
  };
}

function option(value, label) {
  return h("option", { value }, label);
}

function categoryOptions(type) {
  return state.categories
    .filter((category) => !type || category.applies_to === type)
    .map((category) => option(category.name, categoryName(category.name)));
}

// --- Lista ------------------------------------------------------------------------

function provenance(transaction) {
  const label = sourceLabel(transaction.categorization_source);
  if (transaction.categorization_source && transaction.categorization_source !== "manual" && transaction.categorization_confidence !== null) {
    return `${label} · ${percent(transaction.categorization_confidence)}`;
  }
  return label;
}

function chipClass(transaction) {
  if (!transaction.category_name) {
    return "chip chip--none";
  }
  return transaction.categorization_source === "manual" ? "chip chip--manual" : "chip";
}

function renderSummary() {
  const count = state.data.count;
  const scope = byId("filter-account").value
    ? byId("filter-account").selectedOptions[0].textContent
    : gettext("todas las cuentas");
  byId("tx-summary").textContent = format(
    ngettext("%(count)s movimiento · %(scope)s", "%(count)s movimientos · %(scope)s", count),
    { count, scope },
  );
}

function renderList() {
  const list = byId("tx-list");
  const results = state.data.results;
  renderSummary();
  if (!results.length) {
    const filtered = Object.values(filters()).some(Boolean);
    replace(list, filtered
      ? emptyState(gettext("Ningún movimiento coincide con los filtros"), gettext("Cambia o limpia los filtros para ver más movimientos."))
      : emptyState(gettext("Todavía no hay movimientos"), gettext("Registra tu primer gasto o ingreso con el formulario. Finty lo clasificará por ti.")));
    byId("tx-pager").hidden = true;
    return;
  }
  const rows = results.map((transaction) => h("tr", {
    "aria-selected": state.selected && state.selected.id === transaction.id ? "true" : "false",
    onclick: () => select(transaction),
  },
    h("td", { class: "muted" }, shortDate(transaction.occurred_on)),
    h("td", {}, h("button", { type: "button", class: "row-button", onclick: (event) => { event.stopPropagation(); select(transaction); } },
      transaction.description || categoryName(transaction.category_name))),
    h("td", {}, h("div", { class: "stack-tight" },
      h("span", { class: chipClass(transaction) }, categoryName(transaction.category_name)),
      h("span", { class: "provenance" }, provenance(transaction)))),
    h("td", { class: "muted" }, transaction.account_name),
    h("td", { class: `num amount--${transaction.type}` }, signedMoney(transaction.amount, currencyOf(transaction.account), transaction.type))));

  const table = h("div", { class: "table-wrap" }, h("table", { class: "table" },
    h("caption", { class: "visually-hidden" }, gettext("Movimientos: elige uno para ver su detalle.")),
    h("thead", {}, h("tr", {},
      h("th", { scope: "col" }, gettext("Fecha")),
      h("th", { scope: "col" }, gettext("Descripción")),
      h("th", { scope: "col" }, gettext("Categoría")),
      h("th", { scope: "col" }, gettext("Cuenta")),
      h("th", { scope: "col", class: "num" }, gettext("Monto")))),
    h("tbody", {}, rows)));
  replace(list, table);

  const first = state.offsets[state.offsets.length - 1] + 1;
  byId("tx-range").textContent = format(gettext("Mostrando %(first)s–%(last)s de %(count)s"), {
    first, last: first + results.length - 1, count: state.data.count,
  });
  byId("tx-prev").disabled = !state.data.previous;
  byId("tx-next").disabled = !state.data.next;
  byId("tx-pager").hidden = false;
}

async function loadList() {
  const list = byId("tx-list");
  list.setAttribute("aria-busy", "true");
  replace(list, skeletonRows(6));
  list.setAttribute("aria-busy", "true");
  try {
    state.data = await api("/transactions/", { query: Object.assign(filters(), { page: state.page }) });
    renderList();
  } catch (error) {
    if (error.status === 404 && state.page > 1) {
      resetPaging();
      loadList();
      return;
    }
    replace(list, errorState(error, loadList));
    byId("tx-pager").hidden = true;
  }
}

function resetPaging() {
  state.page = 1;
  state.offsets = [0];
}

function nextPage() {
  state.offsets.push(state.offsets[state.offsets.length - 1] + state.data.results.length);
  state.page += 1;
  loadList();
}

function previousPage() {
  if (state.offsets.length > 1) {
    state.offsets.pop();
  }
  state.page -= 1;
  loadList();
}

// --- Detalle ------------------------------------------------------------------------

function select(transaction) {
  state.selected = transaction;
  document.querySelectorAll("#tx-list tbody tr").forEach((row, index) => {
    row.setAttribute("aria-selected", state.data.results[index].id === transaction.id ? "true" : "false");
  });
  byId("tx-detail-title").textContent = transaction.description || categoryName(transaction.category_name);
  byId("tx-detail-empty").hidden = true;
  byId("tx-detail-body").hidden = false;
  showFormError("detail-error", "");
  const amount = byId("detail-amount");
  amount.textContent = signedMoney(transaction.amount, currencyOf(transaction.account), transaction.type);
  amount.className = `amount--${transaction.type}`;
  byId("detail-date").textContent = longDate(transaction.occurred_on);
  byId("detail-account").textContent = transaction.account_name;
  byId("detail-source").textContent = provenance(transaction);
  const categorySelect = byId("detail-category");
  categorySelect.replaceChildren(...categoryOptions(transaction.type));
  if (transaction.category_name) {
    categorySelect.value = transaction.category_name;
  }
}

function clearDetail() {
  state.selected = null;
  byId("tx-detail-title").textContent = gettext("Ninguno");
  byId("tx-detail-empty").hidden = false;
  byId("tx-detail-body").hidden = true;
}

function bindDetail() {
  byId("detail-recategorize").addEventListener("click", (event) => busy(event.currentTarget, async () => {
    const transaction = state.selected;
    showFormError("detail-error", "");
    try {
      const updated = await api(`/transactions/${transaction.id}/categorize/`, {
        method: "POST", body: { category_name: byId("detail-category").value },
      });
      toast(format(gettext("Movimiento recategorizado como %(category)s."), { category: categoryName(updated.category_name) }));
      await loadList();
      const fresh = state.data.results.find((item) => item.id === updated.id);
      select(fresh || updated);
    } catch (error) {
      showFormError("detail-error", errorMessage(error));
    }
  }));

  const dialog = byId("delete-dialog");
  byId("detail-delete").addEventListener("click", () => {
    dialog.showModal();
    byId("delete-cancel").focus();
  });
  byId("delete-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => byId("detail-delete").focus());
  byId("delete-confirm").addEventListener("click", (event) => busy(event.currentTarget, async () => {
    const transaction = state.selected;
    try {
      await api(`/transactions/${transaction.id}/`, { method: "DELETE" });
      dialog.close();
      clearDetail();
      toast(gettext("Movimiento eliminado."));
      await refreshAccounts();
      await loadList();
      byId("tx-list").focus();
    } catch (error) {
      dialog.close();
      showFormError("detail-error", errorMessage(error));
    }
  }));
}

// --- Registro ---------------------------------------------------------------------

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function renderFormOptions() {
  const hasAccounts = state.accounts.length > 0;
  byId("tx-form-empty").hidden = hasAccounts;
  byId("tx-form-fields").hidden = !hasAccounts;
  byId("tx-account").replaceChildren(...state.accounts.map((account) => option(account.id, `${account.name} · ${account.currency}`)));
  const category = byId("tx-category");
  const automatic = category.options[0];
  category.replaceChildren(automatic, ...categoryOptions(state.type));
}

function setType(type) {
  state.type = type;
  document.querySelectorAll("[data-type]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.type === type));
  });
  renderFormOptions();
}

async function refreshAccounts() {
  state.accounts = (await listAll("/accounts/")).filter((account) => !account.is_archived);
  const filter = byId("filter-account");
  const current = filter.value;
  filter.replaceChildren(filter.options[0], ...state.accounts.map((account) => option(account.id, account.name)));
  filter.value = current;
  renderFormOptions();
}

function bindForm() {
  document.querySelectorAll("[data-type]").forEach((button) => {
    button.addEventListener("click", () => setType(button.dataset.type));
  });
  byId("tx-date").value = today();
  byId("tx-date").max = today();
  byId("tx-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    showFormError("tx-error", "");
    const body = {
      account_id: byId("tx-account").value,
      amount: parseAmount(byId("tx-amount").value),
      type: state.type,
      occurred_on: byId("tx-date").value,
      description: byId("tx-description").value.trim(),
    };
    if (byId("tx-category").value) {
      body.category_name = byId("tx-category").value;
    }
    const missing = {};
    for (const field of ["account_id", "amount", "occurred_on"]) {
      if (!body[field]) {
        missing[field] = [gettext("Este campo es obligatorio.")];
      }
    }
    if (Object.keys(missing).length) {
      showFieldErrors("tx", missing);
      return;
    }
    showFieldErrors("tx", {});
    await busy(byId("tx-submit"), async () => {
      try {
        const created = await api("/transactions/", { method: "POST", body });
        toast(format(gettext("Movimiento guardado en %(category)s · %(source)s."), {
          category: categoryName(created.category_name),
          source: provenance(created),
        }));
        byId("tx-amount").value = "";
        byId("tx-description").value = "";
        byId("tx-category").value = "";
        resetPaging();
        await loadList();
        const fresh = state.data.results.find((item) => item.id === created.id);
        select(fresh || created);
      } catch (error) {
        if (error.fields) {
          showFormError("tx-error", showFieldErrors("tx", error.fields).join(" "));
        } else {
          showFormError("tx-error", errorMessage(error));
        }
      }
    });
  });
}

// --- Arranque -----------------------------------------------------------------------

async function start() {
  await startShell();
  bindForm();
  bindDetail();
  byId("tx-prev").addEventListener("click", previousPage);
  byId("tx-next").addEventListener("click", nextPage);
  byId("filters").addEventListener("change", () => { resetPaging(); clearDetail(); loadList(); });
  byId("filters").addEventListener("submit", (event) => event.preventDefault());
  byId("tx-list").setAttribute("tabindex", "-1");

  try {
    const [, categories] = await Promise.all([refreshAccounts(), listAll("/categories/")]);
    state.categories = categories;
    byId("filter-category").append(...categories.map((category) => option(category.id, categoryName(category.name))));
    renderFormOptions();
  } catch (error) {
    byId("tx-form-fields").replaceChildren(errorState(error, () => window.location.reload()));
  }
  loadList();
}

start();
