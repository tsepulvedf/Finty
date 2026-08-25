"""Comando de auditoria de invariantes.

**Un comando de gestion es un mecanismo de entrega, igual que una vista.** Le
aplica la regla 3 de `RULES.md` sin descuento: no calcula nada, no reimplementa
ninguna regla y no consulta el ORM. Solo pide datos al servicio, los formatea y
elige un codigo de salida.

Por eso este modulo importa `AccountService` y nada mas del sistema: ni
`BalanceCalculator`, ni `Money`, ni los modelos. La suite de arquitectura lo
verifica recorriendo el AST.
"""
from django.core.management.base import BaseCommand, CommandError

from finance.services import AccountService

EXIT_OK = 0
EXIT_INCONSISTENT = 1

ANCHO_CUENTA = 24
ANCHO_EMAIL = 26
ANCHO_MONTO = 18


class Command(BaseCommand):
    """Verifica que los balances persistidos coincidan con sus transacciones."""

    help = (
        "Audita INV-07 (balance consistente) e INV-08 (categoria tras "
        "procesamiento). Con --fix recalcula los balances desviados. Devuelve "
        "codigo de salida 1 si quedan desviaciones, para poder encadenarlo en un "
        "pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Recalcula el balance de las cuentas desviadas.",
        )
        parser.add_argument(
            "--user",
            metavar="EMAIL",
            help="Restringe la auditoria a las cuentas de un usuario.",
        )

    def handle(self, *args, **options):
        """Audita, informa y decide el codigo de salida."""
        accounts = AccountService()
        owner = self._resolve_user(options.get("user"))

        balance_findings = accounts.audit_balances(owner)
        deviated = [result for result in balance_findings if not result.is_consistent()]

        self._report_scope(owner, len(balance_findings))
        self._report_balances(deviated)

        if deviated and options["fix"]:
            deviated = self._fix(accounts, owner, deviated)

        categorization_findings = accounts.audit_categorization(owner)
        self._report_categorization(categorization_findings, options["fix"])

        self._report_summary(len(balance_findings), deviated, categorization_findings)

        raise SystemExit(EXIT_INCONSISTENT if deviated else EXIT_OK)

    # --- Alcance ------------------------------------------------------------

    @staticmethod
    def _resolve_user(email):
        """Traduce el email recibido a un usuario, o falla."""
        if email is None:
            return None

        # Importacion diferida: el modelo de usuario se resuelve por
        # configuracion, no por import directo entre apps.
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.filter(email=email.strip().lower()).first()
        if owner is None:
            raise CommandError(f"No existe ningun usuario con el email '{email}'.")
        return owner

    def _report_scope(self, owner, total):
        alcance = f"las cuentas de {owner.email}" if owner else "todas las cuentas"
        self.stdout.write(f"Auditando {alcance} ({total} en total).")
        self.stdout.write("")

    # --- Balances -----------------------------------------------------------

    def _report_balances(self, deviated):
        """Imprime la tabla de cuentas desviadas."""
        self.stdout.write(self.style.MIGRATE_HEADING("INV-07 - balance consistente"))

        if not deviated:
            self.stdout.write(
                self.style.SUCCESS("  Todos los balances coinciden con sus movimientos.")
            )
            self.stdout.write("")
            return

        self.stdout.write(self._header())
        self.stdout.write("  " + "-" * (ANCHO_CUENTA + ANCHO_EMAIL + ANCHO_MONTO * 3 + 6))
        for result in deviated:
            self.stdout.write(self.style.WARNING(self._row(result)))
        self.stdout.write("")

    @staticmethod
    def _header():
        return "  {:<{c}}  {:<{e}}  {:>{m}}  {:>{m}}  {:>{m}}".format(
            "CUENTA",
            "PROPIETARIO",
            "PERSISTIDO",
            "CALCULADO",
            "DIFERENCIA",
            c=ANCHO_CUENTA,
            e=ANCHO_EMAIL,
            m=ANCHO_MONTO,
        )

    @staticmethod
    def _row(result):
        return "  {:<{c}}  {:<{e}}  {:>{m}}  {:>{m}}  {:>{m}}".format(
            result.account_name[:ANCHO_CUENTA],
            result.owner_email[:ANCHO_EMAIL],
            str(result.persisted),
            str(result.calculated),
            str(result.difference()),
            c=ANCHO_CUENTA,
            e=ANCHO_EMAIL,
            m=ANCHO_MONTO,
        )

    def _fix(self, accounts, owner, deviated):
        """Recalcula las cuentas desviadas y vuelve a auditar."""
        self.stdout.write(self.style.MIGRATE_HEADING("Correccion (--fix)"))

        for result in deviated:
            # `recompute_balance` exige el propietario porque su consulta va
            # filtrada por usuario: ni siquiera una tarea de mantenimiento puede
            # alcanzar la cuenta de otro sin nombrarlo. Se resuelve desde el
            # email que trae el propio resultado de la auditoria.
            propietario = owner or self._resolve_user(result.owner_email)
            repaired = accounts.recompute_balance(propietario, result.account_id)
            self.stdout.write(
                "  {}: {} -> {}".format(
                    result.account_name, result.persisted, repaired.balance
                )
            )
        self.stdout.write("")

        remaining = [
            result
            for result in accounts.audit_balances(owner)
            if not result.is_consistent()
        ]
        if remaining:
            self.stdout.write(
                self.style.ERROR(
                    f"  {len(remaining)} cuenta(s) siguen desviadas tras el recalculo."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Todos los balances quedaron al dia."))
        self.stdout.write("")
        return remaining

    # --- Categorizacion -----------------------------------------------------

    def _report_categorization(self, findings, fixing):
        """Imprime las incoherencias de categorizacion, que nunca se corrigen."""
        self.stdout.write(
            self.style.MIGRATE_HEADING("INV-08 - categoria tras procesamiento")
        )

        if not findings:
            self.stdout.write(
                self.style.SUCCESS("  Ninguna transaccion en estado incoherente.")
            )
            self.stdout.write("")
            return

        for finding in findings:
            self.stdout.write(
                self.style.WARNING(
                    "  {}  {}  [{}]  categoria={}  procedencia={}".format(
                        str(finding.transaction_id)[:8],
                        finding.account_name[:ANCHO_CUENTA],
                        finding.reason,
                        finding.category_name or "-",
                        finding.categorization_source or "-",
                    )
                )
            )

        if fixing:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "  --fix NO corrige estas incoherencias. Reasignar la categoria "
                    "de una transaccion es una decision humana sobre que significa "
                    "ese movimiento, no un recalculo aritmetico. Usa el endpoint de "
                    "recategorizacion."
                )
            )
        self.stdout.write("")

    # --- Resumen ------------------------------------------------------------

    def _report_summary(self, audited, deviated, categorization_findings):
        self.stdout.write(self.style.MIGRATE_HEADING("Resumen"))
        self.stdout.write(f"  Cuentas auditadas          : {audited}")
        self.stdout.write(f"  Balances desviados         : {len(deviated)}")
        self.stdout.write(
            f"  Transacciones incoherentes : {len(categorization_findings)}"
        )

        if deviated:
            self.stdout.write(
                self.style.ERROR(
                    "  Estado: INCONSISTENTE. Ejecuta con --fix para recalcular."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Estado: CONSISTENTE."))
