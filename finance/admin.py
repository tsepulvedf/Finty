"""Registro de los modelos de `finance` en el admin de Django.

**Todo el admin de este contexto es de solo lectura, y es una decision de
arquitectura, no una restriccion de permisos.**

El admin escribe filas directamente por el ORM, saltandose la capa de servicios,
que es exactamente donde viven las invariantes. Crear una `Transaction` desde el
formulario del admin no pasaria por `TransactionService`: no bloquearia la fila de
la cuenta, no recalcularia el balance y no verificaria INV-14. El resultado seria
una transaccion persistida con el balance de su cuenta sin mover, es decir, INV-07
violada desde dentro del propio sistema.

Permitir esas escrituras abriria un camino que evade la capa de servicios. Por eso
`Category`, `Account` y `Transaction` bloquean alta, cambio y baja, y declaran
todos sus campos en `readonly_fields`.

El admin sigue siendo util para **inspeccionar** datos durante una demostracion,
que es justo para lo que se quiere aqui. Para escribir estan la API y, para
reparar un balance desviado, el comando `verify_invariants --fix`.
"""
from django.contrib import admin

from finance.models import Account, Category, Transaction


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """Base de admin sin escritura.

    Las tres respuestas en `False` son lo que retira los botones de la interfaz
    y, mas importante, lo que hace que Django rechace un POST construido a mano
    contra la URL del formulario.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        """Declara como solo lectura todos los campos concretos del modelo."""
        return [field.name for field in self.model._meta.fields]


@admin.register(Category)
class CategoryAdmin(ReadOnlyModelAdmin):
    """Catalogo de categorias.

    Lo gobierna la migracion de datos: `RuleBasedCategorizer` depende de que los
    nombres sembrados existan tal cual, y crear o borrar categorias a mano
    romperia ese contrato sin dejar rastro en el historial de migraciones.
    """

    list_display = ("name", "applies_to", "created_at")
    list_filter = ("applies_to",)
    search_fields = ("name",)
    ordering = ("applies_to", "name")


@admin.register(Account)
class AccountAdmin(ReadOnlyModelAdmin):
    """Cuentas. Se inspeccionan aqui; se modifican por la API."""

    list_display = (
        "name",
        "user",
        "type",
        "opening_balance",
        "balance",
        "currency",
        "is_archived",
    )
    list_filter = ("type", "currency", "is_archived")
    search_fields = ("name", "user__email")
    ordering = ("user__email", "name")
    raw_id_fields = ("user",)


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyModelAdmin):
    """Transacciones. Crear una desde aqui dejaria el balance sin actualizar."""

    list_display = (
        "occurred_on",
        "account",
        "type",
        "amount",
        "category",
        "categorization_source",
        "categorization_confidence",
    )
    list_filter = ("type", "categorization_source", "occurred_on", "category")
    search_fields = ("description", "account__name", "account__user__email")
    date_hierarchy = "occurred_on"
    # Evita cargar un select con todas las cuentas del sistema.
    raw_id_fields = ("account",)
