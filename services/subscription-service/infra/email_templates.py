"""Textos de los correos en espanol y en ingles (E2-M7).

Adaptador de `EmailComposer`. Los servicios Flask no usan gettext (ADR-11): el
frontend traduce por `code` lo que se ve en pantalla. Un correo no pasa por el
navegador, asi que su texto en los dos idiomas vive aqui, y se elige con el
idioma del contacto que guarda identity.
"""
from domain.interfaces import EmailComposer
from domain.notifications import EmailMessage, NotificationKind

MONTHS = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"),
}

TEMPLATES = {
    ("es", NotificationKind.PREMIUM_WELCOME): (
        "¡Bienvenido a Finty Premium!",
        "Hola, {name}:\n\n"
        "Tu plan Premium está activo hasta el {date}. Ya puedes ver tus insights, tus "
        "gastos recurrentes, todo tu historial y las recomendaciones de inversión.\n\n"
        "Este pago fue una simulación: no se realizó ningún cobro.\n\n"
        "El equipo de Finty",
    ),
    ("en", NotificationKind.PREMIUM_WELCOME): (
        "Welcome to Finty Premium!",
        "Hi {name},\n\n"
        "Your Premium plan is active until {date}. You can now see your insights, your "
        "recurring expenses, your whole history and investment recommendations.\n\n"
        "This payment was a simulation: no charge was made.\n\n"
        "The Finty team",
    ),
    ("es", NotificationKind.SUBSCRIPTION_EXPIRING): (
        "Tu plan Premium termina el {date}",
        "Hola, {name}:\n\n"
        "Tu plan Premium termina el {date}. Finty no lo renueva automáticamente: si "
        "quieres seguir en Premium, renuévalo desde Planes. Si vuelves al plan Free, "
        "conservas todos tus movimientos.\n\n"
        "El equipo de Finty",
    ),
    ("en", NotificationKind.SUBSCRIPTION_EXPIRING): (
        "Your Premium plan ends on {date}",
        "Hi {name},\n\n"
        "Your Premium plan ends on {date}. Finty doesn't renew it automatically: if you "
        "want to stay on Premium, renew it from Plans. If you go back to the Free plan, "
        "you keep all your transactions.\n\n"
        "The Finty team",
    ),
}


def format_date(moment, language):
    """En la zona del proceso: `22 de noviembre de 2026` o `November 22, 2026`."""
    local = moment.astimezone()
    month = MONTHS[language][local.month - 1]
    return f"{local.day} de {month} de {local.year}" if language == "es" else f"{month} {local.day}, {local.year}"


class TemplateEmailComposer(EmailComposer):
    def compose(self, kind, contact, period_end):
        subject, body = TEMPLATES[(contact.language, NotificationKind(kind))]
        values = {
            # Sin nombre visible (identity siempre lo exige), la parte local del correo.
            "name": contact.display_name.split(" ")[0] if contact.display_name else contact.email.split("@")[0],
            "date": format_date(period_end, contact.language),
        }
        return EmailMessage(contact.email, subject.format(**values), body.format(**values))
