/*
 * Utilidades de DOM y estados de pantalla (Phase 1: carga, vacio y error).
 *
 * Todo el contenido se arma con nodos y `textContent`: un dato de la API nunca
 * se interpreta como HTML.
 */
import { errorMessage } from "./codes.js";

/** `h("p", {class: "x"}, "texto", otroNodo)` → elemento. */
export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) {
      continue;
    }
    if (name === "class") {
      node.className = value;
    } else if (name === "style") {
      for (const [property, setting] of Object.entries(value)) {
        node.style.setProperty(property.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`), setting);
      }
    } else if (name.startsWith("on") && typeof value === "function") {
      node.addEventListener(name.slice(2), value);
    } else {
      node.setAttribute(name, value === true ? "" : value);
    }
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) {
      continue;
    }
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function byId(id) {
  return document.getElementById(id);
}

export function replace(container, ...nodes) {
  container.replaceChildren(...nodes.flat().filter(Boolean));
  container.removeAttribute("aria-busy");
}

export function skeletonRows(count) {
  return h("div", { class: "skeleton-stack" },
    Array.from({ length: count }, () => h("span", { class: "skeleton skeleton--row" })));
}

/** Estado vacio: un mensaje util y, si hay, la accion principal. */
export function emptyState(title, text, action) {
  return h("div", { class: "state" },
    h("p", { class: "state__title" }, title),
    text ? h("p", { class: "state__text" }, text) : null,
    action || null);
}

/** Estado de error con reintento. */
export function errorState(error, retry) {
  return h("div", { class: "state state--error", role: "alert" },
    h("p", { class: "state__title" }, gettext("No pudimos cargar esta sección")),
    h("p", { class: "state__text" }, errorMessage(error)),
    retry ? h("button", { type: "button", class: "btn btn--plain btn--small", onclick: retry }, gettext("Reintentar")) : null);
}

/** Aviso breve en la region `aria-live` de la pagina. */
export function toast(message, kind = "info") {
  const region = byId("toasts");
  if (!region) {
    return;
  }
  const node = h("div", { class: kind === "error" ? "toast toast--error" : "toast", role: kind === "error" ? "alert" : null }, message);
  region.append(node);
  setTimeout(() => node.remove(), 6000);
}

/** Muestra u oculta un aviso de error de formulario (`<id>` y `<id>-text`). */
export function showFormError(id, message) {
  const box = byId(id);
  if (!box) {
    return;
  }
  byId(id + "-text").textContent = message || "";
  box.hidden = !message;
}

/**
 * Errores por campo de un 400 (`{"campo": ["mensaje"]}`) junto a cada campo.
 * `prefix` arma el id del contenedor: `<prefix>-<campo>-error`. Devuelve los
 * mensajes que no tienen un campo donde mostrarse.
 */
export function showFieldErrors(prefix, fields) {
  document.querySelectorAll(`[id^="${prefix}-"][id$="-error"].field__error`).forEach((node) => {
    node.hidden = true;
    node.textContent = "";
    const input = node.parentElement.querySelector("input, select");
    if (input) {
      input.removeAttribute("aria-invalid");
    }
  });
  const orphans = [];
  for (const [field, messages] of Object.entries(fields || {})) {
    const node = byId(`${prefix}-${field}-error`);
    const text = [].concat(messages).join(" ");
    if (node) {
      node.textContent = text;
      node.hidden = false;
      const input = node.parentElement.querySelector("input, select");
      if (input) {
        input.setAttribute("aria-invalid", "true");
      }
    } else {
      orphans.push(text);
    }
  }
  return orphans;
}

/** Deshabilita un boton mientras dura `task` y lo marca como ocupado. */
export async function busy(button, task) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}
