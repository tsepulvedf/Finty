"""Registro de los modelos de `identity` en el admin de Django."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from identity.models import User, UserProfile


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin de `User` adaptado a email como identificador."""

    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informacion personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin del perfil de usuario."""

    list_display = ("user", "display_name", "preferred_currency", "onboarding_completed")
    list_filter = ("onboarding_completed", "preferred_currency")
    search_fields = ("display_name", "user__email")
    readonly_fields = ("created_at", "updated_at")
