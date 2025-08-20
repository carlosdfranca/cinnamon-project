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

# Camadas novas (seu core)
from core.upload.balancete_parser import parse_excel, BalanceteSchemaError
from core.processing.import_service import import_balancete
from core.processing.dre_service import gerar_dados_dre

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side


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
# PÁGINA: Demonstração Financeira (view-only; POST = importar -> precisa poder GERENCIAR)
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

    fundos_anos = {}
    for fundo in fundos:
        anos = BalanceteItem.objects.filter(fundo=fundo).values_list("ano", flat=True).distinct()
        fundos_anos[fundo.id] = sorted(set(anos), reverse=True)

    # IMPORTAÇÃO = ação de GERENCIAR (bloqueia VIEWER)
    if request.method == "POST":
        if not _can_manage_fundos(request):
            messages.error(request, "Você não tem permissão para importar balancete.")
            return redirect("demonstracao_financeira")

        fundo_id = request.POST.get("fundo_id")
        ano_str = request.POST.get("ano")
        arquivo = request.FILES.get("planilha")

        if not ano_str:
            messages.error(request, "O campo Ano é obrigatório.")
            return render(request, "demonstracao_financeira.html", {
                "fundos": fundos,
                "fundos_anos": fundos_anos,
                "can_enviar_balancete": _can_manage_fundos(request),
            })
        try:
            ano = int(ano_str)
        except ValueError:
            messages.error(request, "Ano inválido.")
            return render(request, "demonstracao_financeira.html", {
                "fundos": fundos,
                "fundos_anos": fundos_anos,
                "can_enviar_balancete": _can_manage_fundos(request),
            })

        fundo_qs2 = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
        fundo = get_object_or_404(fundo_qs2, id=fundo_id)

        if not arquivo:
            messages.error(request, "Selecione um arquivo XLSX ou CSV.")
            return redirect("demonstracao_financeira")

        try:
            rows = parse_excel(arquivo)
        except BalanceteSchemaError as e:
            messages.error(request, f"Planilha inválida. Faltam colunas: {', '.join(e.missing_columns)}")
            return redirect("demonstracao_financeira")
        except Exception as e:
            messages.error(request, f"Erro ao ler o arquivo: {e}")
            return redirect("demonstracao_financeira")

        report = import_balancete(fundo_id=fundo.id, ano=ano, rows=rows)

        if report.errors:
            messages.warning(
                request,
                f"Importação concluída: {report.imported} inseridos, {report.updated} atualizados, "
                f"{report.ignored} ignorados. Erros: {len(report.errors)}."
            )
        else:
            messages.success(
                request,
                f"Importação concluída: {report.imported} inseridos, {report.updated} atualizados, {report.ignored} ignorados."
            )
        return redirect("demonstracao_financeira")

    # GET
    return render(request, "demonstracao_financeira.html", {
        "fundos": fundos,
        "fundos_anos": fundos_anos,
        "can_enviar_balancete": _can_manage_fundos(request),
    })



@login_required
@company_can_view_data
def download_modelo_balancete(request):
    caminho_arquivo = os.path.join(settings.STATIC_ROOT, "modelos", "modelo_balancete.xlsx")
    if settings.DEBUG:
        caminho_arquivo = os.path.join(settings.BASE_DIR, "static", "modelos", "modelo_balancete.xlsx")
    return FileResponse(open(canho_arquivo := caminho_arquivo, "rb"), as_attachment=True, filename="Modelo Balancete.xlsx")


# ===============================
# DRE (visualização/exportação) — view-only
# ===============================
@login_required
@company_can_view_data
def dre_resultado(request, fundo_id, ano):
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    dict_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, int(ano))
    return render(request, "dre_resultado.html", {
        "dict_tabela": dict_tabela,
        "ano": int(ano),
        "fundo": fundo,
        "resultado_exercicio": resultado_exercicio,
        "resultado_exercicio_anterior": resultado_exercicio_anterior
    })


@login_required
@company_can_view_data
def exportar_dre_excel(request, fundo_id, ano):
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    dict_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, int(ano))

    wb = Workbook()
    ws = wb.active
    ws.title = "DRE"
    ws.sheet_view.showGridLines = False

    # Estilos
    bold = Font(bold=True)
    italic = Font(italic=True)
    right = Alignment(horizontal="right")
    left = Alignment(horizontal="left")
    indent2 = Alignment(horizontal="left", indent=2)
    bottom_border = Border(bottom=Side(style="thin"))
    double_bottom_border = Border(bottom=Side(style="double"))

    nome_fundo = str(fundo.nome).upper()

    # Cabeçalhos principais
    ws["A1"] = nome_fundo
    ws["A1"].font = bold
    ws["A1"].alignment = left

    ws["A2"] = f"CNPJ: {fundo.cnpj}"
    ws["A2"].font = bold
    ws["A2"].alignment = left

    ws["A3"] = fundo.empresa.nome
    ws["A3"].alignment = left

    ws["A4"] = f"CNPJ: {fundo.empresa.cnpj or ''}"
    ws["A4"].alignment = left

    ws.append([])  # Linha em branco

    ws["A6"] = "Demonstração do Resultado do Exercício"
    ws["A6"].font = bold
    ws["A6"].alignment = left

    ano = int(ano)
    ws["A7"] = f"Exercícios findos em 31 de dezembro de {ano} e {ano - 1}"
    ws["A7"].font = bold
    ws["A7"].alignment = left

    ws["A8"] = "(Valores expressos em milhares de reais)"
    ws["A8"].font = italic
    ws["A8"].alignment = left

    ws.append([])  # Linha em branco
    ws.insert_cols(3)

    ws["A8"].border = bottom_border
    ws["B8"].border = bottom_border
    ws["C8"].border = bottom_border
    ws["D8"].border = bottom_border

    # Cabeçalho das datas
    ws.append(["", f"31/12/{ano}", "", f"31/12/{ano - 1}"])
    ws.append([])

    row_header = ws.max_row
    for col in (2, 4):
        ws.cell(row=row_header, column=col).alignment = right
        ws.cell(row=row_header, column=col).font = bold
        ws.cell(row=row_header, column=col).border = bottom_border

    # Dados
    for grupo, dados in dict_tabela.items():
        ws.append([grupo, dados["SOMA"], "", dados["SOMA_ANTERIOR"]])
        row = ws.max_row
        ws.cell(row=row, column=1).font = Font(bold=True)
        ws.cell(row=row, column=1).alignment = left
        for col in (2, 4):
            cell = ws.cell(row=row, column=col)
            cell.font = Font(bold=True)
            cell.alignment = right
            cell.number_format = "#,##0_);(#,##0)"
            cell.border = bottom_border

        for item, valores in dados.items():
            if item in ["SOMA", "SOMA_ANTERIOR"]:
                continue
            ws.append([item, valores["ATUAL"], "", valores["ANTERIOR"]])
            row = ws.max_row
            ws.cell(row=row, column=1).alignment = indent2
            for col in (2, 4):
                cell = ws.cell(row=row, column=col)
                cell.alignment = right
                cell.number_format = "#,##0_);(#,##0)"

        ws.append([])

    # Resultado do exercício
    row = ws.max_row
    ws.append([
        "Resultado do exercício",
        resultado_exercicio,
        "",
        resultado_exercicio_anterior
    ])
    row = ws.max_row
    ws.cell(row=row, column=1).font = Font(bold=True)
    ws.cell(row=row, column=1).alignment = left
    for col in (2, 4):
        cell = ws.cell(row=row, column=col)
        cell.number_format = "#,##0_);(#,##0)"
        cell.font = Font(bold=True)
        cell.alignment = right
        cell.border = double_bottom_border

    ws.insert_cols(1)

    # Larguras
    from openpyxl.utils import get_column_letter
    col_widths = {1: 3, 2: 65, 3: 12, 4: 5, 5: 12, 6: 3}
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nome_curto = "_".join(str(fundo.nome).replace("-", "").split())
    response["Content-Disposition"] = f"attachment; filename=DRE_{ano}_{nome_curto}.xlsx"
    wb.save(response)
    return response


# ===========================
# CRUD de Fundos (multiempresa)
# ===========================
@login_required
@company_can_view_data
def listar_fundos(request):
    fundos = query_por_empresa_ativa(
        Fundo.objects.select_related("empresa"),
        request,
        "empresa",
    ).order_by("nome")
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

            # 1) Coletar possíveis fontes de empresa:
            empresas_user = list(_empresas_do_usuario(request.user))
            empresa_ativa = getattr(request, "empresa_ativa", None)
            empresa_id_post = (
                request.POST.get("empresa")
                or request.POST.get("empresa_id")
                or (empresa_ativa.id if empresa_ativa else None)
                or request.session.get("empresa_ativa_id")
            )

            # 2) Resolver empresa conforme escopo do usuário:
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
