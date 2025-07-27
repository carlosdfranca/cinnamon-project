from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Informações da Empresa", {"fields": ("nome_empresa", "cnpj")}),
    )
    list_display = ("username", "nome_empresa", "cnpj", "email")
    search_fields = ("username", "nome_empresa", "cnpj")
