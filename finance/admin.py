"""Registro de los modelos de `finance` en el admin de Django."""
from django.contrib import admin

from finance.models import Account, Category, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin del catalogo de categorias, en modo lectura.

    En la Entrega 1 el catalogo lo gobierna la migracion de datos, no el admin:
    `RuleBasedCategorizer` (M4) depende de que los nombres sembrados existan tal
    cual. Crear o borrar categorias a mano romperia ese contrato sin dejar rastro
    en el historial de migraciones.
    """

    list_display = ("name", "applies_to", "created_at")
    list_filter = ("applies_to",)
    search_fields = ("name",)
    ordering = ("applies_to", "name")
    readonly_fields = ("id", "name", "applies_to", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """Admin de cuentas."""

    list_display = ("name", "user", "type", "balance", "currency", "is_archived")
    list_filter = ("type", "currency", "is_archived")
    search_fields = ("name", "user__email")
    ordering = ("user__email", "name")
    raw_id_fields = ("user",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin de transacciones."""

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
    readonly_fields = ("id", "created_at", "updated_at")
