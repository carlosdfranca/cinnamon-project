# usuarios/views_company.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from usuarios.models import Empresa, Membership
from usuarios.utils.company_scope import set_empresa_ativa

@login_required
def trocar_empresa_ativa(request):
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER", "/"))

    emp_id = request.POST.get("empresa_id")
    if not emp_id:
        set_empresa_ativa(request, None)
        messages.info(request, "Empresa ativa limpa.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    empresa = get_object_or_404(Empresa, id=emp_id)

    user = request.user
    # Validação: global pode tudo; senão, precisa vínculo ativo
    if getattr(user, "has_global_scope", None) and user.has_global_scope():
        set_empresa_ativa(request, empresa.id)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    tem_vinculo = Membership.objects.filter(
        usuario=user, empresa=empresa, is_active=True
    ).exists()
    if not tem_vinculo:
        messages.error(request, "Você não tem acesso a essa empresa.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    set_empresa_ativa(request, empresa.id)
    return redirect(request.META.get("HTTP_REFERER", "/"))
