from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Empresa, Membership

# ----- Inlines -----
class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("usuario",)
    fields = ("usuario", "role", "is_active", "criado_em", "atualizado_em")
    readonly_fields = ("criado_em", "atualizado_em")
    show_change_link = True


# ----- Usuario -----
@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "global_role", "is_active", "is_staff", "last_login")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("global_role", "is_staff", "is_superuser", "is_active", "groups")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Escopo Global", {"fields": ("global_role",)}),  # << aqui
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )

    inlines = [MembershipInline]


# ----- Empresa -----
@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "master", "is_ativo", "criado_em")
    search_fields = ("nome", "cnpj", "master__username", "master__first_name", "master__last_name")
    list_filter = ("is_ativo",)
    autocomplete_fields = ("master",)
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [MembershipInline]


# ----- Membership -----
@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("usuario", "empresa", "role", "is_active", "criado_em")
    list_filter = ("role", "is_active", "empresa")
    search_fields = (
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "empresa__nome",
        "empresa__cnpj",
    )
    autocomplete_fields = ("usuario", "empresa")
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("empresa", "usuario")
