"""Comando de auditoria de invariantes: `flask verify-invariants`.

Traslado de `finance/management/commands/verify_invariants.py` del monolito
(E2-M3a): audita INV-07 (balance consistente) e INV-08 (categoria tras
procesamiento), que ahora viven en este servicio. Mismas opciones, mismo
reporte y mismos codigos de salida, con una diferencia obligada por ADR-10: el
propietario se identifica por su `user_id` y no por su email, porque el email
vive en `finty_identity` y este servicio no consulta otra base.

    flask verify-invariants                 # todas las cuentas
    flask verify-invariants --user <uuid>   # solo las de un usuario
    flask verify-invariants --fix           # recalcula los balances desviados

**Un comando es un mecanismo de entrega, igual que un blueprint** (RULES.md,
regla 3): no calcula, no reimplementa reglas y no consulta la base. Pide los
datos a `AccountService`, los formatea y elige el codigo de salida. La suite de
arquitectura lo verifica recorriendo el AST.
"""
from uuid import UUID

import click
from flask.cli import with_appcontext

from api.context import db_session
from services import AccountService

EXIT_OK = 0
EXIT_INCONSISTENT = 1

ANCHO_CUENTA = 24
ANCHO_PROPIETARIO = 36
ANCHO_MONTO = 18
SEPARADOR = "  " + "-" * (ANCHO_CUENTA + ANCHO_PROPIETARIO + ANCHO_MONTO * 3 + 6)
FILA = "  {:<{c}}  {:<{p}}  {:>{m}}  {:>{m}}  {:>{m}}"


def _parse_user(_ctx, _param, value):
    """Valida `--user`: debe ser el UUID de un usuario."""
    if value is None:
        return None
    try:
        return UUID(value.strip())
    except ValueError as exc:
        raise click.BadParameter(
            f"'{value}' no es un identificador de usuario valido (UUID)."
        ) from exc


@click.command("verify-invariants")
@click.option("--fix", is_flag=True, help="Recalcula el balance de las cuentas desviadas.")
@click.option(
    "--user",
    "owner_id",
    metavar="USER_ID",
    callback=_parse_user,
    help="Restringe la auditoria a las cuentas de un usuario (su UUID).",
)
@click.pass_context
@with_appcontext
def verify_invariants(ctx, fix, owner_id):
    """Audita INV-07 (balance consistente) e INV-08 (categoria tras
    procesamiento). Con --fix recalcula los balances desviados. Devuelve codigo
    de salida 1 si quedan desviaciones, para poder encadenarlo en un pipeline.
    """
    accounts = AccountService(db_session())

    balance_findings = accounts.audit_balances(owner_id)
    deviated = [result for result in balance_findings if not result.is_consistent()]

    _report_scope(owner_id, len(balance_findings))
    _report_balances(deviated)

    if deviated and fix:
        deviated = _fix(accounts, owner_id, deviated)

    categorization_findings = accounts.audit_categorization(owner_id)
    _report_categorization(categorization_findings, fix)

    _report_summary(len(balance_findings), deviated, categorization_findings)

    ctx.exit(EXIT_INCONSISTENT if deviated else EXIT_OK)


# --- Alcance ----------------------------------------------------------------


def _heading(text):
    click.secho(text, bold=True)


def _report_scope(owner_id, total):
    alcance = f"las cuentas de {owner_id}" if owner_id else "todas las cuentas"
    click.echo(f"Auditando {alcance} ({total} en total).")
    click.echo("")


# --- Balances ---------------------------------------------------------------


def _report_balances(deviated):
    """Imprime la tabla de cuentas desviadas."""
    _heading("INV-07 - balance consistente")

    if not deviated:
        click.secho("  Todos los balances coinciden con sus movimientos.", fg="green")
        click.echo("")
        return

    click.echo(_line("CUENTA", "PROPIETARIO", "PERSISTIDO", "CALCULADO", "DIFERENCIA"))
    click.echo(SEPARADOR)
    for result in deviated:
        click.secho(
            _line(
                result.account_name[:ANCHO_CUENTA],
                str(result.owner_id),
                str(result.persisted),
                str(result.calculated),
                str(result.difference()),
            ),
            fg="yellow",
        )
    click.echo("")


def _line(*columns):
    return FILA.format(*columns, c=ANCHO_CUENTA, p=ANCHO_PROPIETARIO, m=ANCHO_MONTO)


def _fix(accounts, owner_id, deviated):
    """Recalcula las cuentas desviadas y vuelve a auditar."""
    _heading("Correccion (--fix)")

    for result in deviated:
        # `recompute_balance` exige el propietario porque su consulta va
        # filtrada por usuario: ni una tarea de mantenimiento alcanza la cuenta
        # de otro sin nombrarlo. Sale del propio resultado de la auditoria.
        repaired = accounts.recompute_balance(result.owner_id, result.account_id)
        click.echo(f"  {result.account_name}: {result.persisted} -> {repaired.balance}")
    click.echo("")

    remaining = [
        result for result in accounts.audit_balances(owner_id) if not result.is_consistent()
    ]
    if remaining:
        click.secho(
            f"  {len(remaining)} cuenta(s) siguen desviadas tras el recalculo.", fg="red"
        )
    else:
        click.secho("  Todos los balances quedaron al dia.", fg="green")
    click.echo("")
    return remaining


# --- Categorizacion ---------------------------------------------------------


def _report_categorization(findings, fixing):
    """Imprime las incoherencias de categorizacion, que nunca se corrigen."""
    _heading("INV-08 - categoria tras procesamiento")

    if not findings:
        click.secho("  Ninguna transaccion en estado incoherente.", fg="green")
        click.echo("")
        return

    for finding in findings:
        click.secho(
            "  {}  {}  [{}]  categoria={}  procedencia={}".format(
                str(finding.transaction_id)[:8],
                finding.account_name[:ANCHO_CUENTA],
                finding.reason,
                finding.category_name or "-",
                finding.categorization_source or "-",
            ),
            fg="yellow",
        )

    if fixing:
        click.echo("")
        click.secho(
            "  --fix NO corrige estas incoherencias. Reasignar la categoria de una "
            "transaccion es una decision humana sobre que significa ese "
            "movimiento, no un recalculo aritmetico. Usa el endpoint de "
            "recategorizacion.",
            fg="yellow",
        )
    click.echo("")


# --- Resumen ----------------------------------------------------------------


def _report_summary(audited, deviated, categorization_findings):
    _heading("Resumen")
    click.echo(f"  Cuentas auditadas          : {audited}")
    click.echo(f"  Balances desviados         : {len(deviated)}")
    click.echo(f"  Transacciones incoherentes : {len(categorization_findings)}")

    if deviated:
        click.secho("  Estado: INCONSISTENTE. Ejecuta con --fix para recalcular.", fg="red")
    else:
        click.secho("  Estado: CONSISTENTE.", fg="green")
