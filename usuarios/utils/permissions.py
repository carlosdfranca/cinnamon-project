# usuarios/utils/permissions.py
from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from usuarios.models import Empresa, Membership

ROLE_ORDER = ["VIEWER", "MEMBER", "ADMIN", "MASTER"]

def _role_rank(role: str) -> int:
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return -1

def user_min_role_in_empresa(user, empresa, min_role: str) -> bool:
    # override global
    if getattr(user, "has_global_scope", None) and user.has_global_scope():
        return True
    memb = Membership.objects.filter(empresa=empresa, usuario=user, is_active=True).first()
    if not memb:
        return False
    return _role_rank(memb.role) >= _role_rank(min_role)

def require_empresa_role(min_role: str):
    """
    Protege views por empresa, com override global.
    Uso:
    @login_required
    @require_empresa_role("ADMIN")
    def view(request, empresa_id): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, empresa_id, *args, **kwargs):
            empresa = get_object_or_404(Empresa, pk=empresa_id)
            # override global (viewer pode ver, admin pode editar; ajuste se quiser)
            if request.method in ("GET", "HEAD"):
                # viewer global já passa
                if getattr(request.user, "is_platform_viewer", None) and request.user.is_platform_viewer():
                    request.empresa = empresa
                    return view_func(request, empresa_id, *args, **kwargs)
            # demais métodos exigem min_role ou admin global
            if user_min_role_in_empresa(request.user, empresa, min_role):
                request.empresa = empresa
                return view_func(request, empresa_id, *args, **kwargs)
            return HttpResponseForbidden(f"Acesso negado (mínimo: {min_role}).")
        return _wrapped
    return decorator
