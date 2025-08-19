from django.contrib import admin
from .models import Fundo, MapeamentoContas, BalanceteItem
from .admin_mixins import TenantScopedAdminMixin

class BalanceteInline(admin.TabularInline):
    model = BalanceteItem
    extra = 0
    fields = ("ano", "conta_corrente", "saldo_final", "data_importacao")
    readonly_fields = ("data_importacao",)
    autocomplete_fields = ("conta_corrente",)
    show_change_link = True

@admin.register(Fundo)
class FundoAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "cnpj", "empresa")
    list_filter = ("empresa",)
    search_fields = ("nome", "cnpj", "empresa__nome")
    ordering = ("empresa", "nome")
    autocomplete_fields = ("empresa",)
    inlines = [BalanceteInline]
    list_select_related = ("empresa",)

@admin.register(MapeamentoContas)
class MapeamentoContasAdmin(admin.ModelAdmin):
    list_display = ("conta", "grupo_df", "tipo")
    list_filter = ("tipo", "grupo_df")
    search_fields = ("conta", "grupo_df", "descricao")
    ordering = ("tipo", "grupo_df", "conta")

@admin.register(BalanceteItem)
class BalanceteItemAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    empresa_field = "fundo__empresa"  # <- importante!
    list_display = ("fundo", "ano", "conta_corrente", "saldo_final", "data_importacao")
    list_filter = ("fundo__empresa", "ano", "conta_corrente__tipo")
    search_fields = ("fundo__nome", "fundo__cnpj", "conta_corrente__conta", "conta_corrente__grupo_df")
    ordering = ("fundo", "ano", "conta_corrente")
    autocomplete_fields = ("fundo", "conta_corrente")
    readonly_fields = ("data_importacao",)
    date_hierarchy = "data_importacao"
    list_select_related = ("fundo", "fundo__empresa", "conta_corrente")
