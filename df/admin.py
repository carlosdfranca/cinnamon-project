from django.contrib import admin
from .models import Fundo, MapeamentoContas, BalanceteItem

@admin.register(Fundo)
class FundoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cnpj', 'get_usuario_nome_completo')
    search_fields = ('nome', 'cnpj', 'usuario__username', 'usuario__first_name', 'usuario__last_name')
    list_filter = ('usuario',)
    ordering = ('usuario', 'nome')

    def get_usuario_nome_completo(self, obj):
        nome = obj.usuario.first_name or ''
        sobrenome = obj.usuario.last_name or ''
        return f"{nome} {sobrenome}".strip()
    get_usuario_nome_completo.short_description = 'Usuário'
    get_usuario_nome_completo.admin_order_field = 'usuario__first_name'


@admin.register(MapeamentoContas)
class MapeamentoContasAdmin(admin.ModelAdmin):
    list_display = ('conta', 'grupo_df', 'get_tipo_display')
    search_fields = ('conta', 'grupo_df')
    list_filter = ('tipo',)
    ordering = ('tipo', 'grupo_df', 'conta')

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()
    get_tipo_display.short_description = 'Tipo'


@admin.register(BalanceteItem)
class BalanceteItemAdmin(admin.ModelAdmin):
    list_display = ('fundo', 'ano', 'conta_corrente', 'saldo_final', 'data_importacao')
    search_fields = (
        'fundo__usuario__first_name',
        'fundo__usuario__last_name',
        'fundo__nome',
    ) 
    list_filter = ('ano', )
    ordering = ('-data_importacao',)
    readonly_fields = ('data_importacao',)