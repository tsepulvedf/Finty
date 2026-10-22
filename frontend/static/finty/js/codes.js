/*
 * Traduccion de los `code` que devuelve la API (ADR-11, D-21).
 *
 * Un solo modulo: el backend responde con codigos estables (errores de dominio,
 * beneficios, insights, recomendaciones, avisos, procedencias) y aqui se
 * convierten en texto con gettext(). Por eso los servicios Flask no necesitan
 * Flask-Babel. Los 401 y 429 del Gateway se traducen por codigo de estado.
 *
 * Los nombres de categoria son datos del catalogo de finance (en espanol); se
 * traducen por nombre con el mismo criterio y, si aparece uno nuevo, se muestra
 * tal cual.
 */
import { money, percent } from "./format.js";
import { format } from "./i18n.js";

const ERRORS = {
  // identity
  invalid_credentials: gettext("El correo o la contraseña no son correctos. Revísalos e inténtalo de nuevo."),
  email_already_registered: gettext("Ya existe una cuenta con ese correo. Ingresa con él o usa otro."),
  weak_password: gettext("La contraseña es muy débil: usa al menos 8 caracteres, que no sean solo números ni una contraseña común."),
  inactive_user: gettext("Esta cuenta está inactiva."),
  // finance
  zero_amount: gettext("El monto debe ser distinto de cero."),
  negative_amount: gettext("Escribe el monto sin signo: el tipo de movimiento ya indica si suma o resta."),
  future_transaction_date: gettext("La fecha del movimiento no puede ser futura."),
  category_not_found: gettext("Esa categoría no existe."),
  category_type_mismatch: gettext("Esa categoría no corresponde al tipo de movimiento."),
  duplicate_account_name: gettext("Ya tienes una cuenta con ese nombre."),
  archived_account: gettext("La cuenta está archivada y no admite movimientos."),
  account_not_found: gettext("No encontramos esa cuenta."),
  account_not_owned: gettext("No encontramos esa cuenta."),
  transaction_not_found: gettext("No encontramos ese movimiento. Puede que ya se haya eliminado."),
  negative_balance_not_allowed: gettext("Este movimiento dejaría la cuenta en negativo, y su tipo no lo permite."),
  currency_mismatch: gettext("La moneda no coincide con la de la cuenta."),
  account_has_transactions: gettext("La cuenta tiene movimientos: archívala en lugar de eliminarla."),
  invalid_transaction_type: gettext("El tipo de movimiento no es válido."),
  uncategorized_transaction: gettext("El movimiento no tiene categoría."),
  // analytics, recommendation y subscription
  invalid_period: gettext("El período no es válido."),
  premium_required: gettext("Esta función es parte del plan Premium."),
  entitlements_unavailable: gettext("No pudimos verificar tu plan en este momento. Intenta de nuevo en unos minutos."),
  unsupported_currency_pair: gettext("Solo se puede convertir entre pesos y dólares."),
  plan_not_purchasable: gettext("El plan Free no requiere pago."),
  subscription_already_active: gettext("Ya tienes una suscripción vigente."),
  payment_in_progress: gettext("Tienes un pago en proceso."),
  no_active_subscription: gettext("No tienes una suscripción activa."),
  risk_profile_not_found: gettext("Todavía no has respondido el cuestionario de perfil de riesgo."),
  risk_profile_required: gettext("Responde el cuestionario de perfil de riesgo antes de guardar un plan."),
  invalid_risk_answer: gettext("Cada respuesta del cuestionario vale 1, 2 o 3."),
  instrument_not_recommended: gettext("Ese instrumento no corresponde a tu perfil de riesgo."),
  invalid_monthly_contribution: gettext("El aporte mensual debe ser mayor que cero."),
  invalid_horizon: gettext("El horizonte del plan está fuera del rango permitido."),
  investment_plan_not_found: gettext("No encontramos ese plan de inversión."),
};

const STATUSES = {
  0: gettext("No pudimos conectar con Finty. Revisa tu conexión e intenta de nuevo."),
  401: gettext("Tu sesión no es válida o expiró. Ingresa de nuevo."),
  403: gettext("No tienes acceso a esta función."),
  404: gettext("No encontramos lo que buscabas."),
  429: gettext("Hiciste demasiadas solicitudes seguidas. Espera un momento e intenta de nuevo."),
  503: gettext("El servicio no está disponible en este momento. Intenta de nuevo en unos minutos."),
};
const UNKNOWN_ERROR = gettext("Algo salió mal. Intenta de nuevo.");

/** Texto de un error de la API: por `code` si lo trae, si no por estado (D-21). */
export function errorMessage(error) {
  if (error && error.code && ERRORS[error.code]) {
    return ERRORS[error.code];
  }
  if (error && STATUSES[error.status] !== undefined) {
    return STATUSES[error.status];
  }
  return UNKNOWN_ERROR;
}

export const BENEFITS = {
  transaction_tracking: gettext("Registro de movimientos"),
  standard_dashboard: gettext("Dashboard estándar"),
  history_3_months: gettext("3 meses de historial"),
  insights: gettext("Insights sobre tus gastos"),
  spending_patterns: gettext("Patrones de gasto recurrente"),
  unlimited_history: gettext("Historial ilimitado"),
  investment_recommendations: gettext("Recomendaciones de inversión"),
  investment_plans: gettext("Planes de inversión"),
};

/** Tipos de instrumento: siempre genericos, nunca un producto o una entidad (§6.6). */
export const INSTRUMENTS = {
  cdt: gettext("CDT"),
  liquidity_fund: gettext("Fondo de liquidez"),
  collective_investment_fund: gettext("Fondo de inversión colectiva"),
  etf: gettext("ETF"),
  stocks: gettext("Acciones"),
};

/** `["cdt", "liquidity_fund"]` → `CDT o Fondo de liquidez`. */
export function instrumentList(codes) {
  const names = (codes || []).map((code) => INSTRUMENTS[code] || code);
  if (names.length < 2) {
    return names.join("");
  }
  return format(gettext("%(first)s o %(last)s"), { first: names.slice(0, -1).join(", "), last: names[names.length - 1] });
}

/** Tipos de perfil de riesgo: nombre y descripcion. El tipo lo decide recommendation-service. */
export const RISK_PROFILES = {
  conservative: {
    name: gettext("Conservador"),
    text: gettext("Priorizas no perder dinero, aunque el crecimiento sea menor."),
  },
  moderate: {
    name: gettext("Moderado"),
    text: gettext("Aceptas algo de variación a cambio de un crecimiento mayor que el de un CDT."),
  },
  aggressive: {
    name: gettext("Agresivo"),
    text: gettext("Toleras caídas temporales buscando el mayor crecimiento a largo plazo."),
  },
};

/** De donde sale cada recomendacion (`source`, veraz como A-14). */
export const RECOMMENDATION_SOURCES = {
  insight: gettext("Origen: un insight de tus gastos"),
  pattern: gettext("Origen: un patrón de gasto recurrente"),
  risk_profile: gettext("Origen: tu perfil de riesgo"),
};

/**
 * Titulo y texto de una recomendacion por `code`. `amount(key)` presenta un
 * monto de `params` o `evidence` (en la moneda de presentacion si la API la
 * convirtio); la pagina lo entrega.
 */
export function recommendationContent(recommendation, amount) {
  const params = recommendation.params || {};
  const evidence = recommendation.evidence || {};
  switch (recommendation.code) {
    case "reduce_category":
      return {
        title: format(gettext("Reduce tu gasto en %(category)s"), { category: categoryName(params.category_name) }),
        text: format(gettext("Este mes gastaste %(current)s, un %(pct)s más que tu promedio. Volver al promedio liberaría unos %(saving)s."), {
          current: amount("current"), pct: percent(Number(params.increase_pct) / 100, 1), saving: amount("potential_saving"),
        }),
      };
    case "build_budget":
      return {
        title: gettext("Arma un presupuesto"),
        text: format(gettext("Este mes tus gastos superaron a tus ingresos en %(deficit)s. Un presupuesto por categoría te ayuda a equilibrarlos."), { deficit: amount("deficit") }),
      };
    case "review_recurring_expense":
      return {
        title: format(gettext("Revisa tu gasto fijo «%(description)s»"), { description: params.description }),
        text: format(gettext("Pagas en promedio %(amount)s y apareció en %(months)s de los últimos %(window)s meses. Al año suma unos %(annual)s."), {
          amount: amount("average_amount"), months: evidence.months_present, window: evidence.window_months, annual: amount("annualized_cost"),
        }),
      };
    case "build_emergency_fund":
      return {
        title: gettext("Primero, un fondo de emergencia"),
        text: format(gettext("Tu excedente mensual promedio es de %(surplus)s. Antes de invertir, construye un ahorro que cubra varios meses de gastos."), { surplus: amount("monthly_surplus") }),
      };
    case "invest_by_risk_profile":
      return {
        title: instrumentList(params.instrument_types),
        text: format(gettext("Para un perfil %(profile)s, Finty sugiere este tipo de instrumento según tu excedente mensual."), {
          profile: (RISK_PROFILES[params.risk_profile_type] || { name: params.risk_profile_type }).name.toLocaleLowerCase(),
        }),
      };
    default:
      return { title: "", text: "" };
  }
}

/** Avisos que la API adjunta por `code` (su `message` queda como respaldo). */
const NOTICES = {
  investment_disclaimer: gettext("Esta es una orientación general por tipo de instrumento, no una asesoría financiera ni una recomendación de un producto o entidad específica."),
};

export function noticeText(notice) {
  return notice ? NOTICES[notice.code] || notice.message || "" : "";
}

/** Descripcion corta de cada beneficio, para la bienvenida. */
export const BENEFIT_DETAILS = {
  transaction_tracking: gettext("Registra efectivo, banco y tarjeta."),
  standard_dashboard: gettext("Ingresos, gastos y saldos del mes."),
  history_3_months: gettext("Consulta los últimos 3 meses."),
  insights: gettext("Te avisamos cuando una categoría se dispara."),
  spending_patterns: gettext("Ves lo que pagas todos los meses."),
  unlimited_history: gettext("Consulta cualquier mes, sin límite."),
  investment_recommendations: gettext("Según tu perfil y tu excedente mensual."),
  investment_plans: gettext("Guarda metas con su proyección."),
};

/** Estados de un pago simulado. */
export const PAYMENT_STATUSES = {
  APPROVED: gettext("Aprobado"),
  DECLINED: gettext("Rechazado"),
  ERROR: gettext("Con error"),
  PENDING: gettext("Pendiente"),
};

export const ACCOUNT_TYPES = {
  bank: gettext("Banco"),
  cash: gettext("Efectivo"),
  credit: gettext("Crédito"),
};

export const TRANSACTION_TYPES = {
  income: gettext("Ingreso"),
  expense: gettext("Gasto"),
};

/** Procedencia de la categoria (A-14): cada mecanismo con su nombre. */
const SOURCES = {
  rule: gettext("Automática · por reglas"),
  ai: gettext("Automática · por IA"),
  mock: gettext("Automática · simulada"),
  manual: gettext("Manual"),
};

export function sourceLabel(source) {
  return SOURCES[source] || gettext("Sin clasificar");
}

/** Procedencia de una tasa de cambio (ADR-12). */
export const RATE_SOURCES = {
  live: gettext("en vivo"),
  cached: gettext("en caché"),
  fallback: gettext("tasa de respaldo"),
};

export const PLANS = {
  FREE: gettext("Plan Free"),
  PREMIUM: gettext("Plan Premium"),
};

const CATEGORIES = {
  "Alimentación": gettext("Alimentación"),
  "Transporte": gettext("Transporte"),
  "Vivienda": gettext("Vivienda"),
  "Servicios públicos": gettext("Servicios públicos"),
  "Salud": gettext("Salud"),
  "Educación": gettext("Educación"),
  "Entretenimiento": gettext("Entretenimiento"),
  "Compras": gettext("Compras"),
  "Deudas y créditos": gettext("Deudas y créditos"),
  "Otros gastos": gettext("Otros gastos"),
  "Salario": gettext("Salario"),
  "Freelance": gettext("Freelance"),
  "Inversiones": gettext("Inversiones"),
  "Reembolsos": gettext("Reembolsos"),
  "Otros ingresos": gettext("Otros ingresos"),
};

export function categoryName(name) {
  if (!name) {
    return gettext("Sin categoría");
  }
  return CATEGORIES[name] || name;
}

/** Textos de los insights de analytics, interpolados con sus `params`. */
const INSIGHTS = {
  category_spike: gettext("Tu gasto en %(category_name)s subió %(increase_pct)s frente a tu promedio"),
  negative_savings: gettext("Este mes tus gastos superaron a tus ingresos en %(deficit)s"),
  top_category: gettext("%(category_name)s concentra el %(share_pct)s de tus gastos del mes"),
};

/**
 * Titulo de un insight, interpolado con sus `params` ya presentados: la
 * categoria traducida, los porcentajes con Intl y los montos en su moneda.
 */
export function insightText(insight) {
  const template = INSIGHTS[insight.code];
  if (!template) {
    return "";
  }
  const params = Object.assign({}, insight.params);
  if (params.category_name) {
    params.category_name = categoryName(params.category_name);
  }
  for (const key of ["increase_pct", "share_pct"]) {
    if (params[key] !== undefined) {
      params[key] = percent(Number(params[key]) / 100, 1);
    }
  }
  if (params.deficit !== undefined) {
    params.deficit = money(params.deficit, params.currency);
  }
  return format(template, params);
}

/** Etiqueta de cada insight, como en el diseño ("Alerta · Gasto inusual"). */
export const INSIGHT_TAGS = {
  category_spike: gettext("Alerta · Gasto inusual"),
  negative_savings: gettext("Alerta · Gastas más de lo que ingresas"),
  top_category: gettext("Dato · Categoría principal"),
};

/**
 * Por que se marco cada insight. Los numeros de la regla salen de la
 * `evidence` que entrega analytics, no de este archivo.
 */
export function insightRule(insight) {
  const evidence = insight.evidence || {};
  if (insight.code === "category_spike") {
    return format(
      ngettext(
        "Se marca cuando una categoría supera en %(threshold)s o más el promedio del mes anterior.",
        "Se marca cuando una categoría supera en %(threshold)s o más el promedio de los %(count)s meses anteriores.",
        (evidence.previous_months || []).length,
      ),
      { threshold: percent(Number(evidence.threshold_pct) / 100), count: (evidence.previous_months || []).length },
    );
  }
  if (insight.code === "negative_savings") {
    return gettext("Se marca cuando los gastos del período superan a los ingresos.");
  }
  if (insight.code === "top_category") {
    return gettext("La categoría con mayor participación en los gastos del período.");
  }
  return "";
}
