// Auditoria automatizada de accesibilidad de Finty (E2-M9a).
//
//   cd tools/ux-audit && npm install && node audit.mjs <etiqueta> [base]
//
// Contra el stack en Docker (por defecto http://localhost). Crea una usuaria
// Free y una Premium con datos, y por cada pagina, idioma (es, en), ancho (1440
// y 390 px) y usuario corre axe-core y Lighthouse (accesibilidad y buenas
// practicas). Deja el resultado en ../../docs/ux-audit/<etiqueta>.json y un
// resumen en Markdown en <etiqueta>.md. Las capturas de cada combinacion van a
// UX_AUDIT_SHOTS (por defecto, una carpeta temporal): no se versionan todas.
//
// Usa el Chrome instalado (CHROME_PATH). Solo desarrollo: no entra en ninguna imagen.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import { navigation } from "lighthouse";

const HERE = dirname(fileURLToPath(import.meta.url));
const LABEL = process.argv[2] || "resultado";
const BASE = (process.argv[3] || "http://localhost").replace(/\/$/, "");
const OUT = join(HERE, "..", "..", "docs", "ux-audit");
const SHOTS = process.env.UX_AUDIT_SHOTS || join(tmpdir(), `finty-ux-audit-${LABEL}`);
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const AXE = readFileSync(join(HERE, "node_modules", "axe-core", "axe.min.js"), "utf-8");
const ONLY = process.env.UX_AUDIT_ONLY ? process.env.UX_AUDIT_ONLY.split(",") : null;

const PUBLIC = [["ingreso", "/"], ["registro", "/registro/"]];
const PRIVATE = [
  ["dashboard", "/dashboard/"], ["movimientos", "/movimientos/"], ["insights", "/insights/"],
  ["inversiones", "/inversiones/"], ["perfil-de-riesgo", "/perfil-de-riesgo/"], ["planes", "/planes/"],
  ["pago", "/pago/"], ["bienvenida", "/bienvenida/"], ["ajustes", "/ajustes/"],
];
const LANGS = ["es", "en"];
const WIDTHS = [1440, 390];

mkdirSync(OUT, { recursive: true });
mkdirSync(SHOTS, { recursive: true });

// --- Datos por la API ------------------------------------------------------------

async function call(method, path, token, body, lang = "es") {
  for (let attempt = 0; attempt < 80; attempt++) {
    const response = await fetch(BASE + "/api/v1" + path, {
      method,
      headers: Object.assign(
        { "Content-Type": "application/json", "Accept-Language": lang },
        token ? { Authorization: `Token ${token}` } : {},
      ),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 429 || response.status >= 502) {
      await new Promise((r) => setTimeout(r, response.status === 429 ? 300 : 1000));
      continue;
    }
    const text = await response.text();
    return { status: response.status, body: text ? JSON.parse(text) : null };
  }
  throw new Error(`429 persistente en ${path}`);
}

function monthsAgo(n, day) {
  const d = new Date();
  const date = new Date(d.getFullYear(), d.getMonth() - n, n === 0 ? Math.min(day, d.getDate()) : day);
  return date.toISOString().slice(0, 10);
}

async function makeUser(name, premium) {
  const email = `ux-${name.toLowerCase()}-${Date.now()}@finty.co`;
  const registered = await call("POST", "/auth/register/", null, { email, password: "Contrasena-Segura-2026", display_name: name });
  if (registered.status !== 201) throw new Error(JSON.stringify(registered));
  const token = registered.body.token;
  const account = (await call("POST", "/accounts/", token, { name: "Banco principal", type: "bank", currency: "COP", initial_balance: "20000000.00" })).body;
  await call("POST", "/accounts/", token, { name: "Cuenta en dolares", type: "bank", currency: "USD", initial_balance: "1250.00" });
  for (let n = 4; n >= 0; n--) {
    for (const t of [
      { type: "income", amount: "3100000.00", occurred_on: monthsAgo(n, 1), description: "Salario" },
      { type: "expense", amount: "44900.00", occurred_on: monthsAgo(n, 2), description: "Netflix", category_name: "Entretenimiento" },
      { type: "expense", amount: "1600000.00", occurred_on: monthsAgo(n, 3), description: "Arriendo", category_name: "Vivienda" },
      { type: "expense", amount: n === 0 ? "512000.00" : "180000.00", occurred_on: monthsAgo(n, 4), description: "Ropa y zapatos", category_name: "Compras" },
    ]) {
      await call("POST", "/transactions/", token, Object.assign({ account_id: account.id }, t));
    }
  }
  if (premium) {
    await call("POST", "/subscriptions/checkout/", token, { plan: "PREMIUM" });
    await call("PUT", "/recommendations/risk-profile/", token, { investment_horizon: 2, loss_reaction: 2, experience: 3, income_stability: 2, goal: 2 });
    await call("POST", "/investment-plans/", token, { instrument_type: "collective_investment_fund", monthly_contribution: "400000", horizon_months: 36 });
  }
  return { name, token, premium };
}

// --- Auditoria de una pagina ---------------------------------------------------------

async function prepare(page, lang, user) {
  await page.goto(BASE + "/jsi18n/", { waitUntil: "load" });
  await page.setCookie({ name: "django_language", value: lang, url: BASE + "/" });
  await page.evaluate((token) => {
    sessionStorage.clear();
    if (token) {
      localStorage.setItem("finty.token", token);
    } else {
      localStorage.removeItem("finty.token");
    }
  }, user ? user.token : null);
}

async function settle(page) {
  try {
    await page.waitForNetworkIdle({ idleTime: 500, timeout: 15000 });
  } catch (error) {
    /* sigue: se audita lo que haya */
  }
  await page.waitForFunction(
    () => !document.querySelector(".skeleton") && !document.querySelector("[aria-busy='true']"),
    { timeout: 15000 },
  ).catch(() => {});
}

async function runAxe(page) {
  await page.addScriptTag({ content: AXE });
  return page.evaluate(async () => {
    const result = await window.axe.run(document, { resultTypes: ["violations"] });
    return result.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
      targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
  });
}

async function runLighthouse(page, url, width) {
  const mobile = width < 700;
  const result = await navigation(page, url, {
    config: {
      extends: "lighthouse:default",
      settings: {
        onlyCategories: ["accessibility", "best-practices"],
        formFactor: mobile ? "mobile" : "desktop",
        screenEmulation: { mobile, width, height: mobile ? 844 : 1000, deviceScaleFactor: 1, disabled: false },
        throttlingMethod: "provided",
        disableStorageReset: true,
        locale: "es",
      },
    },
  });
  const lhr = result.lhr;
  const failed = Object.values(lhr.audits)
    .filter((a) => a.score !== null && a.score < 1 && lhr.categories.accessibility.auditRefs.some((r) => r.id === a.id && r.weight > 0))
    .map((a) => a.id);
  return {
    accessibility: Math.round(lhr.categories.accessibility.score * 100),
    bestPractices: Math.round(lhr.categories["best-practices"].score * 100),
    failedA11y: failed,
  };
}

// --- Recorrido ------------------------------------------------------------------------

function launch() {
  return puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-first-run", "--no-default-browser-check"],
  });
}

function save(results) {
  writeFileSync(join(OUT, `${LABEL}.json`), JSON.stringify({ base: BASE, date: new Date().toISOString(), results }, null, 2));
}

// Una combinacion en un navegador propio: si Chrome se cae, solo se pierde esa.
async function audit(combo, who) {
  const browser = await launch();
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: combo.width, height: combo.width < 700 ? 844 : 1000, isMobile: combo.width < 700, hasTouch: combo.width < 700 });
    await prepare(page, combo.lang, combo.user);
    await page.goto(BASE + combo.path, { waitUntil: "load" });
    await settle(page);
    const axe = await runAxe(page);
    const shot = join(SHOTS, `${combo.name}-${combo.lang}-${combo.width}-${who}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    const lighthouse = await runLighthouse(page, BASE + combo.path, combo.width);
    const counts = { critical: 0, serious: 0, moderate: 0, minor: 0 };
    for (const v of axe) counts[v.impact] = (counts[v.impact] || 0) + 1;
    return { page: combo.name, path: combo.path, lang: combo.lang, width: combo.width, user: who, ...lighthouse, axe: counts, violations: axe, screenshot: shot };
  } finally {
    await browser.close().catch(() => {});
  }
}

const results = [];
console.log("Creando usuarias Free y Premium...");
const free = await makeUser("Lucia", false);
const premium = await makeUser("Mateo", true);
// Que analytics proyecte los movimientos antes de mirar las pantallas.
await new Promise((r) => setTimeout(r, 8000));

const combos = [];
for (const lang of LANGS) {
  for (const width of WIDTHS) {
    for (const [name, path] of PUBLIC) combos.push({ lang, width, user: null, name, path });
    for (const user of [free, premium]) {
      for (const [name, path] of PRIVATE) combos.push({ lang, width, user, name, path });
    }
  }
}
for (const combo of combos) {
  if (ONLY && !ONLY.includes(combo.name)) continue;
  const who = combo.user ? (combo.user.premium ? "premium" : "free") : "anonimo";
  let row = null;
  for (let attempt = 1; attempt <= 2 && !row; attempt++) {
    try {
      row = await audit(combo, who);
    } catch (error) {
      console.log(`${combo.name} ${combo.lang} ${combo.width} ${who}: intento ${attempt} fallo (${error.message})`);
      if (attempt === 2) {
        row = { page: combo.name, path: combo.path, lang: combo.lang, width: combo.width, user: who, error: error.message };
      }
    }
  }
  results.push(row);
  save(results);
  if (!row.error) {
    const c = row.axe;
    console.log(`${combo.name.padEnd(17)} ${combo.lang} ${String(combo.width).padStart(4)} ${who.padEnd(8)} a11y=${row.accessibility} bp=${row.bestPractices} axe(c/s/m/m)=${c.critical}/${c.serious}/${c.moderate}/${c.minor} ${row.failedA11y.join(",")}`);
  }
}

save(results);
const lines = [
  `# Auditoria automatizada: ${LABEL}`, "",
  `Base: ${BASE} · ${new Date().toISOString()} · Lighthouse 13.5.0 y axe-core 4.14.0`, "",
  "| Pagina | Idioma | Ancho | Usuario | Accesibilidad | Buenas practicas | axe criticos | axe serios | axe moderados | axe menores |",
  "|---|---|---|---|---|---|---|---|---|---|",
  ...results.map((r) => r.error
    ? `| ${r.page} | ${r.lang} | ${r.width} | ${r.user} | error | error | | | | |`
    : `| ${r.page} | ${r.lang} | ${r.width} | ${r.user} | ${r.accessibility} | ${r.bestPractices} | ${r.axe.critical} | ${r.axe.serious} | ${r.axe.moderate} | ${r.axe.minor} |`),
];
writeFileSync(join(OUT, `${LABEL}.md`), lines.join("\n") + "\n");
console.log(`\nResultados en ${join(OUT, LABEL)}.json y .md · capturas en ${SHOTS}`);
