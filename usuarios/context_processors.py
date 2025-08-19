# usuarios/context_processors.py
from usuarios.models import Empresa, Membership

def _empresas_do_usuario(user):
    if not user.is_authenticated:
        return Empresa.objects.none()
    # Escopo global vê todas
    has_global = getattr(user, "has_global_scope", None)
    if has_global and user.has_global_scope():
        return Empresa.objects.all().only("id", "nome").order_by("nome")
    # Caso contrário, apenas empresas com vínculo ativo
    empresa_ids = Membership.objects.filter(
        usuario=user, is_active=True
    ).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=list(empresa_ids)).only("id", "nome").order_by("nome")

def empresas_contexto(request):
    """
    Disponibiliza empresas para a navbar e a empresa ativa atual, além de uma flag
    booleana 'user_is_global' para controle de exibição do seletor.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    # Flag booleana segura para template (evita chamar método no template)
    has_global = getattr(request.user, "has_global_scope", None)
    user_is_global = bool(has_global and request.user.has_global_scope())

    empresas = _empresas_do_usuario(request.user)

    return {
        "empresa_ativa": getattr(request, "empresa_ativa", None),
        "empresas_disponiveis": empresas,
        "user_is_global": user_is_global,
    }
