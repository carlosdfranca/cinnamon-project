# views.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from df.models import Fundo, BalanceteItem
from usuarios.models import Empresa, Membership
from usuarios.utils.company_scope import query_por_empresa_ativa
from usuarios.permissions import (
    company_can_view_data,
    company_can_manage_fundos,
    get_empresa_escopo,
    role_na_empresa,
    is_global_admin,
)

from .forms import FundoForm

# Camadas novas (core)
from core.export.df_excel import criar_aba_dpf, criar_aba_dre, criar_aba_dmpl, criar_aba_dfc
from core.processing.import_service import import_balancete, import_mec
from core.processing.dre_service import gerar_dados_dre
from core.processing.dpf_service import gerar_dados_dpf
from core.processing.dmpl_service import gerar_dados_dmpl
from core.processing.dfc_service import gerar_tabela_dfc
from core.upload.balancete_parser import parse_excel, BalanceteSchemaError
from core.upload.mec_parser import parse_excel_mec, MecSchemaError

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime


# --------- helpers de escopo/flags para UI ---------
def _empresas_do_usuario(user):
    has_global = getattr(user, "has_global_scope", None)
    if has_global and user.has_global_scope():
        return Empresa.objects.all()
    empresa_ids = Membership.objects.filter(usuario=user, is_active=True).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=list(empresa_ids))

def _can_manage_fundos(request):
    """
    Habilita botões na UI de Fundos conforme a mesma regra do decorator company_can_manage_fundos.
    """
    empresa = get_empresa_escopo(request)
    if not empresa:
        return False
    if is_global_admin(request.user):
        return True
    user_role = role_na_empresa(request.user, empresa)
    return user_role in {Membership.Role.MASTER, Membership.Role.ADMIN, Membership.Role.MEMBER}


# ===============================
# PÁGINA: Demonstração Financeira
# ===============================
@login_required
@company_can_view_data
def demonstracao_financeira(request):
    fundos_qs = query_por_empresa_ativa(
        Fundo.objects.select_related("empresa"),
        request,
        "empresa",
    ).order_by("nome")
    fundos = list(fundos_qs)

    # Agrupar as datas disponíveis por fundo (substitui fundos_anos)
    fundos_datas = {}
    for fundo in fundos:
        datas_qs = (
            BalanceteItem.objects.filter(fundo=fundo)
            .order_by()
            .values_list("data_referencia", flat=True)
            .distinct()
        )
        # Converter para strings únicas
        datas_formatadas = sorted({d.isoformat() for d in datas_qs if d}, reverse=True)
        fundos_datas[fundo.id] = datas_formatadas

    return render(request, "demonstracao_financeira.html", {
        "fundos": fundos,
        "fundos_datas": fundos_datas,
        "can_enviar_balancete": _can_manage_fundos(request),
    })


# ===============================
# IMPORTAR BALANCETE (com data_referencia)
# ===============================
@login_required
@company_can_manage_fundos
def importar_balancete_view(request):
    if request.method == "POST":
        fundo_id = request.POST.get("fundo_id")
        data_str = request.POST.get("data_referencia")
        arquivo_balancete = request.FILES.get("arquivo_balancete")

        if not data_str:
            messages.error(request, "Selecione a data de referência do balancete.")
            return redirect("demonstracao_financeira")

        try:
            data_referencia = datetime.strptime(data_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Data inválida.")
            return redirect("demonstracao_financeira")

        fundo_qs = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
        fundo = get_object_or_404(fundo_qs, id=fundo_id)

        try:
            rows = parse_excel(arquivo_balancete)
            report = import_balancete(fundo_id=fundo.id, data_referencia=data_referencia, rows=rows)
        except BalanceteSchemaError as e:
            messages.error(request, f"Planilha inválida: faltam colunas {', '.join(e.missing_columns)}")
            return redirect("demonstracao_financeira")
        except Exception as e:
            messages.error(request, f"Erro ao importar balancete: {e}")
            return redirect("demonstracao_financeira")

        if report.errors:
            messages.warning(request, f"Balancete importado com erros. {report.imported} inseridos, {report.updated} atualizados, {report.ignored} ignorados.")
        else:
            messages.success(request, f"Balancete importado: {report.imported} inseridos, {report.updated} atualizados, {report.ignored} ignorados.")

    return redirect("demonstracao_financeira")


# ===============================
# IMPORTAR MEC (sem alterações)
# ===============================
@login_required
@company_can_manage_fundos
def importar_mec_view(request):
    if request.method == "POST":
        fundo_id = request.POST.get("fundo_id")
        arquivo_mec = request.FILES.get("arquivo_mec")

        fundo_qs = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
        fundo = get_object_or_404(fundo_qs, id=fundo_id)

        if not arquivo_mec:
            messages.error(request, "Selecione o arquivo do MEC.")
            return redirect("demonstracao_financeira")

        try:
            rows_mec = parse_excel_mec(arquivo_mec)
            report = import_mec(fundo_id=fundo.id, rows=rows_mec)
        except MecSchemaError as e:
            messages.error(request, f"Planilha do MEC inválida: faltam colunas {', '.join(e.missing_columns)}")
            return redirect("demonstracao_financeira")
        except Exception as e:
            messages.error(request, f"Erro ao importar MEC: {e}")
            return redirect("demonstracao_financeira")

        if report.errors:
            messages.warning(request, f"MEC importado com erros. {report.imported} inseridos, {report.updated} atualizados, {report.ignored} ignorados.")
        else:
            messages.success(request, f"MEC importado com sucesso. {report.imported} inseridos, {report.updated} atualizados, {report.ignored} ignorados.")

    return redirect("demonstracao_financeira")


# ===============================
# DRE / Exportações (sem mudanças)
# ===============================
@login_required
@company_can_view_data
def df_resultado(request, fundo_id, data_atual, data_anterior):
    """
    Exibe as Demonstrações Financeiras comparando duas datas de balancete.
    """
    # 🔹 Conversão de strings para objetos date
    try:
        data_atual = datetime.strptime(data_atual, "%Y-%m-%d").date()
        data_anterior = datetime.strptime(data_anterior, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Formato de data inválido. Use o padrão YYYY-MM-DD.")
        return redirect("demonstracao_financeira")

    # 🔹 Busca o fundo dentro do escopo da empresa ativa
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    # === DRE ===
    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior,
    )

    # === DPF ===
    dpf_tabela, _metricas_dpf = gerar_dados_dpf(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior,
    )

    # === PL ajustado ===
    pl_atual = (dpf_tabela["PL"]["TOTAL_PL"]["ATUAL"] or 0) + (resultado_exercicio or 0)
    pl_anterior = (dpf_tabela["PL"]["TOTAL_PL"]["ANTERIOR"] or 0) + (resultado_exercicio_anterior or 0)
    total_pl_passivo_atual = pl_atual + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ATUAL"] or 0)
    total_pl_passivo_anterior = pl_anterior + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ANTERIOR"] or 0)

    # === DMPL ===
    dados_dmpl = gerar_dados_dmpl(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior,
    )

    # === DFC ===
    dfc_tabela, variacao_atual, variacao_ant = gerar_tabela_dfc(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior,
    )

    # === Renderiza o template ===
    return render(request, "df_resultado.html", {
        "fundo": fundo,
        "data_atual": data_atual,
        "data_anterior": data_anterior,
        "dre_tabela": dre_tabela,
        "dpf_tabela": dpf_tabela,
        "dados_dmpl": dados_dmpl,
        "dfc_tabela": dfc_tabela,
        "resultado_exercicio": resultado_exercicio,
        "resultado_exercicio_anterior": resultado_exercicio_anterior,
        "variacao_atual": variacao_atual,
        "variacao_ant": variacao_ant,
        "pl_ajustado_atual": pl_atual,
        "pl_ajustado_anterior": pl_anterior,
        "total_pl_passivo_atual": total_pl_passivo_atual,
        "total_pl_passivo_anterior": total_pl_passivo_anterior,
    })



@login_required
@company_can_view_data
def exportar_dfs_excel(request, fundo_id, data_atual, data_anterior):
    """
    Exporta todas as Demonstrações Financeiras (DPF, DRE, DMPL e DFC)
    comparando duas datas específicas de balancete.
    """
    # =====================
    # Conversão das datas
    # =====================
    try:
        data_atual = datetime.strptime(data_atual, "%Y-%m-%d").date()
        data_anterior = datetime.strptime(data_anterior, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Datas inválidas para exportação.")
        return redirect("demonstracao_financeira")

    # =====================
    # Fundo
    # =====================
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    # =====================
    # Gerar dados das DFs
    # =====================
    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior
    )
    dpf_tabela, _ = gerar_dados_dpf(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior
    )
    dados_dmpl = gerar_dados_dmpl(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior
    )
    dfc_tabela, variacao_atual, variacao_ant = gerar_tabela_dfc(
        fundo_id=fundo.id,
        data_atual=data_atual,
        data_anterior=data_anterior
    )

    # =====================
    # Cálculos auxiliares
    # =====================
    pl_atual = (dpf_tabela["PL"]["TOTAL_PL"]["ATUAL"] or 0) + (resultado_exercicio or 0)
    pl_anterior = (dpf_tabela["PL"]["TOTAL_PL"]["ANTERIOR"] or 0) + (resultado_exercicio_anterior or 0)
    total_pl_passivo_atual = pl_atual + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ATUAL"] or 0)
    total_pl_passivo_anterior = pl_anterior + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ANTERIOR"] or 0)

    # =====================
    # Criar o workbook
    # =====================
    wb = Workbook()

    # Aba DPF
    criar_aba_dpf(
        wb, fundo,
        data_atual, data_anterior,
        dpf_tabela,
        pl_atual, pl_anterior,
        total_pl_passivo_atual, total_pl_passivo_anterior
    )

    # Aba DRE
    criar_aba_dre(
        wb, fundo,
        data_atual, data_anterior,
        dre_tabela,
        resultado_exercicio, resultado_exercicio_anterior
    )

    # Aba DMPL
    criar_aba_dmpl(
        wb, fundo,
        data_atual, data_anterior,
        dados_dmpl,
        resultado_exercicio, resultado_exercicio_anterior,
        pl_atual, pl_anterior
    )

    # Aba DFC
    criar_aba_dfc(
        wb, fundo,
        data_atual, data_anterior,
        dfc_tabela,
        variacao_atual, variacao_ant
    )

    # =====================
    # Exportar o arquivo Excel
    # =====================
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nome_curto = "_".join(str(fundo.nome).replace("-", "").split())
    response["Content-Disposition"] = (
        f"attachment; filename=DFs_{data_atual.strftime('%Y%m%d')}_{data_anterior.strftime('%Y%m%d')}_{nome_curto}.xlsx"
    )

    wb.save(response)
    return response

# ===========================
# CRUD de Fundos (inalterado)
# ===========================
@login_required
@company_can_view_data
def listar_fundos(request):
    fundos = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa").order_by("nome")
    form = FundoForm()
    return render(request, "fundos/listar.html", {
        "fundos": fundos,
        "form": form,
        "can_manage_fundos": _can_manage_fundos(request),
    })


@login_required
@company_can_manage_fundos
def adicionar_fundo(request):
    if request.method == "POST":
        form = FundoForm(request.POST)
        if form.is_valid():
            fundo = form.save(commit=False)

            empresas_user = list(_empresas_do_usuario(request.user))
            empresa_ativa = getattr(request, "empresa_ativa", None)
            empresa_id_post = (
                request.POST.get("empresa")
                or request.POST.get("empresa_id")
                or (empresa_ativa.id if empresa_ativa else None)
                or request.session.get("empresa_ativa_id")
            )

            if getattr(request.user, "has_global_scope", None) and request.user.has_global_scope():
                if not getattr(fundo, "empresa_id", None):
                    if empresa_id_post:
                        fundo.empresa_id = empresa_id_post
                    else:
                        messages.error(request, "Selecione a empresa do Fundo (ou escolha uma empresa ativa na navbar).")
                        return redirect("listar_fundos")
            else:
                if len(empresas_user) == 1:
                    fundo.empresa = empresas_user[0]
                else:
                    if not getattr(fundo, "empresa_id", None):
                        if empresa_id_post and any(str(e.id) == str(empresa_id_post) for e in empresas_user):
                            fundo.empresa_id = empresa_id_post
                        else:
                            messages.error(request, "Selecione uma empresa válida que você participa.")
                            return redirect("listar_fundos")

            fundo.save()
            messages.success(request, "Fundo criado com sucesso.")
            return redirect("listar_fundos")
    else:
        form = FundoForm()
    return render(request, "fundos/form.html", {"form": form, "modo": "Adicionar"})


@login_required
@company_can_manage_fundos
def editar_fundo(request, fundo_id):
    qs = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
    fundo = get_object_or_404(qs, id=fundo_id)

    if request.method == "POST":
        form = FundoForm(request.POST, instance=fundo)
        if form.is_valid():
            obj = form.save(commit=False)
            nova_empresa_id = getattr(obj, "empresa_id", fundo.empresa_id)
            if nova_empresa_id != fundo.empresa_id:
                empresas_user_ids = set(_empresas_do_usuario(request.user).values_list("id", flat=True))
                if (getattr(request.user, "has_global_scope", None) and request.user.has_global_scope()) or (
                    nova_empresa_id in empresas_user_ids
                ):
                    pass
                else:
                    messages.error(request, "Você não tem permissão para mover o fundo para essa empresa.")
                    return redirect("listar_fundos")
            obj.save()
            messages.success(request, "Fundo atualizado com sucesso.")
            return redirect("listar_fundos")
    else:
        form = FundoForm(instance=fundo)
    return render(request, "fundos/form.html", {"form": form, "modo": "Editar"})


@login_required
@company_can_manage_fundos
def excluir_fundo(request, fundo_id):
    qs = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
    fundo = get_object_or_404(qs, id=fundo_id)

    if request.method == "POST":
        fundo.delete()
        messages.success(request, "Fundo excluído com sucesso.")
        return redirect("listar_fundos")
    return render(request, "fundos/confirmar_exclusao.html", {"fundo": fundo})


# ===========================
# Perfil do usuário
# ===========================
@login_required
def editar_perfil(request):
    user = request.user

    if request.method == "POST":
        user.first_name = request.POST.get("first_name") or user.first_name
        user.email = request.POST.get("email") or user.email

        nova_senha = request.POST.get("password")
        if nova_senha:
            user.set_password(nova_senha)

        user.save()
        messages.success(request, "Perfil atualizado com sucesso!")

        if nova_senha:
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        return redirect("editar_perfil")

    return render(request, "editar_perfil.html")
