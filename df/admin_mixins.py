# df/admin_mixins.py
from django.contrib import admin
from usuarios.utils.query import restrict_by_empresa

class TenantScopedAdminMixin(admin.ModelAdmin):
    """
    Restringe visualização/edição no admin para usuários sem escopo global.
    Exige que o model tenha FK direta para Empresa em `empresa`,
    ou que você sobrescreva `empresa_field`.
    """
    empresa_field = "empresa"  # ajuste nos admins onde a empresa vem via fundo etc.

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return restrict_by_empresa(qs, request.user, self.empresa_field)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Limita escolhas de FKs por empresa quando aplicável
        if db_field.name == "empresa" and not request.user.has_global_scope():
            from usuarios.models import Membership
            empresa_ids = Membership.objects.filter(
                usuario=request.user, is_active=True
            ).values_list("empresa_id", flat=True)
            kwargs["queryset"] = kwargs.get("queryset", db_field.remote_field.model.objects).filter(
                id__in=list(empresa_ids)
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
