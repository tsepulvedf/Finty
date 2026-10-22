/*
 * Formato de presentacion con Intl, segun el idioma activo.
 *
 * Solo presenta lo que la API ya entrego: montos (texto decimal), fechas,
 * porcentajes y periodos. No calcula saldos ni reglas.
 */
import { intlLocale } from "./i18n.js";

const MINUS = "\u2212";

/** `"38000.00"` en COP → `$ 38.000`; en USD (`US$ 10,00`) siempre con dos decimales. */
export function money(amount, currency) {
  const value = Number(amount);
  const cents = Math.round(Math.abs(value) * 100) % 100 !== 0;
  const formatter = new Intl.NumberFormat(intlLocale(), {
    style: "currency",
    currency,
    // `symbol` evita la ambiguedad del "$": en espanol el dolar es "US$" y en
    // ingles el peso es "COP"; la moneda local de cada idioma queda como "$".
    currencyDisplay: "symbol",
    minimumFractionDigits: currency === "COP" && !cents ? 0 : 2,
    maximumFractionDigits: 2,
  });
  return formatter.format(Math.abs(value)).replace(/[\u00a0\u202f]/g, " ").replace(/^\$(?=\d)/, "$ ");
}

/** Cifra sin simbolo de moneda: `1.250,00` (para anteponer el codigo, `USD 1.250,00`). */
export function plainAmount(amount, currency) {
  const digits = currency === "COP" ? 0 : 2;
  return new Intl.NumberFormat(intlLocale(), { minimumFractionDigits: digits, maximumFractionDigits: 2 })
    .format(Number(amount));
}

/** Monto con signo explicito, como en los diseños: `+ $ 3.100.000` o `− $ 38.000`. */
export function signedMoney(amount, currency, type) {
  const negative = type ? type === "expense" : Number(amount) < 0;
  return (negative ? MINUS : "+") + " " + money(amount, currency);
}

/** Saldo: negativo con el signo menos tipografico, positivo sin signo. */
export function balance(amount, currency) {
  return (Number(amount) < 0 ? MINUS + " " : "") + money(amount, currency);
}

export function percent(fraction, digits = 0) {
  return new Intl.NumberFormat(intlLocale(), {
    style: "percent",
    maximumFractionDigits: digits,
  }).format(Number(fraction));
}

/** `"2026-10-18"` → `18 oct` (sin desplazar por zona horaria). */
export function shortDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(intlLocale(), { day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, day)))
    .replace(/\.$/, "");
}

export function longDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(intlLocale(), { dateStyle: "long", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, day)));
}

function capitalize(text) {
  return text.charAt(0).toLocaleUpperCase(intlLocale()) + text.slice(1);
}

/** `"2026-10"` → `octubre` (o `October`); con `title`, `Octubre`. */
export function monthName(period, title = false) {
  const [year, month] = period.split("-").map(Number);
  const name = new Intl.DateTimeFormat(intlLocale(), { month: "long", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, 1)));
  return title ? capitalize(name) : name;
}

/** `"2026-10"` → `Octubre 2026`, como en los diseños. */
export function periodLabel(period) {
  return `${monthName(period, true)} ${period.slice(0, 4)}`;
}

/** Iniciales para el avatar: `Tomas Sepulveda` → `TS`. */
export function initials(name) {
  return (name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toLocaleUpperCase())
    .join("");
}

/**
 * Lo que la persona escribe en un campo de monto → texto decimal para la API.
 * Acepta el separador del idioma activo: `120.000,5` en espanol, `120,000.5` en
 * ingles. Es lectura de formato, no validacion: el monto lo valida la API.
 */
export function parseAmount(text) {
  const raw = String(text || "").trim().replace(/\s/g, "");
  if (!raw) {
    return "";
  }
  const decimal = intlLocale() === "es-CO" ? "," : ".";
  const thousands = decimal === "," ? "." : ",";
  return raw.split(thousands).join("").replace(decimal, ".");
}
