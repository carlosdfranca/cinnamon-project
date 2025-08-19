# usuarios/utils/query.py
from usuarios.models import Membership

def restrict_by_empresa(queryset, user, empresa_field: str):
    """
    Restringe queryset a empresas do usuário, a menos que ele tenha escopo global.
    - queryset: ex.: Fundo.objects.all()
    - user: request.user
    - empresa_field: caminho até empresa, ex.: "empresa" ou "fundo__empresa"
    """
    # global scope (viewer/admin/superuser) vê tudo
    if getattr(user, "has_global_scope", None) and user.has_global_scope():
        return queryset
    # pega empresas do user
    empresa_ids = Membership.objects.filter(
        usuario=user, is_active=True
    ).values_list("empresa_id", flat=True)
    return queryset.filter(**{f"{empresa_field}__in": list(empresa_ids)})
