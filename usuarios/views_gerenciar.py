# usuarios/views_gerenciar.py
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.models import Usuario, Empresa, Membership


# ---------- helpers globais ----------
def _is_global(user):
    return bool(getattr(user, "has_global_scope", None) and user.has_global_scope())

def _is_global_admin(user):
    return bool(user.is_superuser or getattr(user, "global_role", "") == Usuario.GlobalRole.PLATFORM_ADMIN)

def _get_empresa_escopo(request):
    """
    Empresa atual: empresa_ativa (middleware) ou primeira empresa do membership (não-global, fallback).
    """
    emp = getattr(request, "empresa_ativa", None)
    if emp:
        return emp
    memb = Membership.objects.filter(usuario=request.user, is_active=True).select_related("empresa").first()
    return memb.empresa if memb else None

def _role_do_usuario_na_empresa(user, empresa):
    memb = Membership.objects.filter(usuario=user, empresa=empresa, is_active=True).only("role").first()
    return memb.role if memb else None


# ---------- decorators ----------
def _company_can_view(view):
    """
    Pode VER a página de gestão:
    - Qualquer usuário global (admin ou viewer), com empresa no escopo
    - Ou MASTER/ADMIN da empresa
    """
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        empresa = _get_empresa_escopo(request)
        if not empresa:
            messages.error(request, "Selecione uma empresa na barra superior para gerenciar usuários.")
            return redirect("demonstracao_financeira")
        if _is_global(request.user):
            return view(request, empresa, *args, **kwargs)
        role = _role_do_usuario_na_empresa(request.user, empresa)
        if role in {Membership.Role.MASTER, Membership.Role.ADMIN}:
            return view(request, empresa, *args, **kwargs)
        return HttpResponseForbidden("Você não tem permissão para visualizar os usuários desta empresa.")
    return _wrapped

def _company_can_manage(view):
    """
    Pode GERENCIAR (CRUD):
    - Global ADMIN
    - MASTER/ADMIN da empresa
    (Global VIEWER NÃO pode)
    """
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        empresa = _get_empresa_escopo(request)
        if not empresa:
            messages.error(request, "Selecione uma empresa na barra superior para gerenciar usuários.")
            return redirect("demonstracao_financeira")
        if _is_global_admin(request.user):
            return view(request, empresa, *args, **kwargs)
        role = _role_do_usuario_na_empresa(request.user, empresa)
        if role in {Membership.Role.MASTER, Membership.Role.ADMIN}:
            return view(request, empresa, *args, **kwargs)
        return HttpResponseForbidden("Você não tem permissão para gerenciar usuários desta empresa.")
    return _wrapped


# ---------- regras de atribuição ----------
def _pode_atribuir_role(request_user, empresa, target_role):
    """
    ADMIN não pode atribuir MASTER.
    MASTER pode tudo.
    Global ADMIN pode tudo.
    Global VIEWER não pode.
    """
    if _is_global_admin(request_user):
        return True
    if _is_global(request_user):
        return False  # global viewer
    role = _role_do_usuario_na_empresa(request_user, empresa)
    if role == Membership.Role.MASTER:
        return True
    if role == Membership.Role.ADMIN:
        return target_role != Membership.Role.MASTER
    return False

def _pode_alterar_ou_excluir(request_user, empresa, alvo_membership):
    """
    ADMIN não pode alterar/excluir ADMIN/MASTER; MASTER pode tudo; Global ADMIN pode tudo;
    Global VIEWER não pode.
    """
    if _is_global_admin(request_user):
        return True
    if _is_global(request_user):
        return False  # global viewer
    my_role = _role_do_usuario_na_empresa(request_user, empresa)
    if my_role == Membership.Role.MASTER:
        return True
    if my_role == Membership.Role.ADMIN:
        return alvo_membership.role not in {Membership.Role.ADMIN, Membership.Role.MASTER}
    return False


# ---------- views ----------
@login_required
@_company_can_view
def gerenciar_usuarios(request, empresa: Empresa):
    memberships = (
        Membership.objects.filter(empresa=empresa, is_active=True)
        .select_related("usuario")
        .order_by("usuario__first_name", "usuario__username")
    )

    # Flags de UI
    can_manage = _is_global_admin(request.user) or (
        _role_do_usuario_na_empresa(request.user, empresa) in {Membership.Role.MASTER, Membership.Role.ADMIN}
    )
    can_assign_master = _is_global_admin(request.user) or (
        _role_do_usuario_na_empresa(request.user, empresa) == Membership.Role.MASTER
    )

    return render(request, "usuarios/gerenciar.html", {
        "empresa": empresa,
        "memberships": memberships,
        "create_form": None,  # formulario será simples no template
        "update_form_dummy": None,
        "can_manage": can_manage,
        "can_assign_master": can_assign_master,
    })


@login_required
@_company_can_manage
@transaction.atomic
def empresa_usuario_adicionar(request, empresa: Empresa):
    if request.method != "POST":
        return redirect("gerenciar_usuarios")

    username = request.POST.get("username") or ""
    first_name = request.POST.get("first_name") or ""
    email = request.POST.get("email") or ""
    role_value = request.POST.get("role") or Membership.Role.MEMBER
    p1 = request.POST.get("password1") or ""
    p2 = request.POST.get("password2") or ""

    if p1 != p2 or not p1:
        messages.error(request, "Senhas inválidas.")
        return redirect("gerenciar_usuarios")

    if not _pode_atribuir_role(request.user, empresa, role_value):
        messages.error(request, "Você não tem permissão para atribuir este papel.")
        return redirect("gerenciar_usuarios")

    if Usuario.objects.filter(username=username).exists():
        messages.error(request, "Já existe um usuário com esse username.")
        return redirect("gerenciar_usuarios")

    usuario = Usuario(username=username, first_name=first_name, email=email)
    usuario.set_password(p1)
    usuario.save()

    memb, created = Membership.objects.get_or_create(
        empresa=empresa, usuario=usuario, defaults={"role": role_value}
    )
    if not created:
        memb.role = role_value
        memb.is_active = True
        memb.save()

    messages.success(request, f"Usuário {usuario} adicionado à empresa {empresa.nome}.")
    return redirect("gerenciar_usuarios")


@login_required
@_company_can_manage
@transaction.atomic
def empresa_usuario_editar(request, empresa: Empresa, membership_id: int):
    memb = get_object_or_404(
        Membership.objects.select_related("usuario", "empresa"),
        id=membership_id, empresa=empresa
    )
    if request.method != "POST":
        return redirect("gerenciar_usuarios")

    if not _pode_alterar_ou_excluir(request.user, empresa, memb):
        messages.error(request, "Você não tem permissão para editar este usuário.")
        return redirect("gerenciar_usuarios")

    first_name = request.POST.get("first_name") or memb.usuario.first_name
    email = request.POST.get("email") or memb.usuario.email
    new_role = request.POST.get("role") or memb.role
    p1 = request.POST.get("password1") or ""
    p2 = request.POST.get("password2") or ""

    if (p1 or p2) and p1 != p2:
        messages.error(request, "As senhas não coincidem.")
        return redirect("gerenciar_usuarios")

    if not _pode_atribuir_role(request.user, empresa, new_role):
        messages.error(request, "Você não tem permissão para atribuir este papel.")
        return redirect("gerenciar_usuarios")

    usuario = memb.usuario
    usuario.first_name = first_name
    usuario.email = email
    if p1:
        usuario.set_password(p1)
    usuario.save()

    was_master = memb.role == Membership.Role.MASTER
    memb.role = new_role
    memb.save()

    if was_master and new_role != Membership.Role.MASTER:
        if not Membership.objects.filter(empresa=empresa, role=Membership.Role.MASTER, is_active=True).exists():
            messages.warning(request, "Atenção: a empresa está sem MASTER. Defina um MASTER.")

    messages.success(request, "Usuário atualizado com sucesso.")
    return redirect("gerenciar_usuarios")


@login_required
@_company_can_manage
@transaction.atomic
def empresa_usuario_excluir(request, empresa: Empresa, membership_id: int):
    memb = get_object_or_404(
        Membership.objects.select_related("usuario", "empresa"),
        id=membership_id, empresa=empresa
    )

    if request.method != "POST":
        return redirect("gerenciar_usuarios")

    if not _pode_alterar_ou_excluir(request.user, empresa, memb):
        return HttpResponseForbidden("Você não tem permissão para excluir este usuário.")

    if empresa.master_id == memb.usuario_id and memb.role == Membership.Role.MASTER:
        messages.error(request, "Transfira o MASTER para outro usuário antes de remover este.")
        return redirect("gerenciar_usuarios")

    memb.is_active = False
    memb.save()
    messages.success(request, "Vínculo removido com sucesso.")
    return redirect("gerenciar_usuarios")
