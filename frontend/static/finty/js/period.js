/*
 * Periodos `YYYY-MM` para navegar entre meses (stepper y `?period=`).
 *
 * Es navegacion, no regla: que meses puede ver cada plan lo decide la API
 * (403 premium_required fuera de la ventana del plan Free).
 */

export function periodOf(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function shift(period, months) {
  const [year, month] = period.split("-").map(Number);
  return periodOf(new Date(year, month - 1 + months, 1));
}

export function validPeriod(text) {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(text || "");
}

/** El `?period=` de la URL si es valido y no es futuro; si no, el mes actual. */
export function requestedPeriod(current) {
  const requested = new URLSearchParams(window.location.search).get("period");
  return validPeriod(requested) && requested <= current ? requested : current;
}
