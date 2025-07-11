from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'cpf', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'cpf')
    # Formulário de edição de usuário
    fieldsets = UserAdmin.fieldsets + (
        ("Dados Complementares", {"fields": ("cpf",)}),
    )
    # Formulário de criação de novo usuário
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Dados Complementares", {"fields": ("cpf",)}),
    )
