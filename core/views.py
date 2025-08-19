from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now

from django.db import transaction

from df.models import Fundo, BalanceteItem, MapeamentoContas
from usuarios.models import Empresa, Membership
from usuarios.utils.query import restrict_by_empresa  # << escopo por empresa

from .forms import FundoForm
from core.utils.utils import gerar_dados_dre

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd


# --------- helpers de escopo ---------
def _empresas_do_usuario(user):
    """
    Retorna QS de empresas visíveis:
    - Papel global (viewer/admin/superuser): todas
    - Senão: empresas com Membership ativo
    """
    has_global = getattr(user, "has_global_scope", None)
    if has_global and user.has_global_scope():
        return Empresa.objects.all()
    empresa_ids = Membership.objects.filter(usuario=user, is_active=True).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=list(empresa_ids))


# ===============================
# PÁGINA: Demonstração Financeira
# ===============================
@login_required
def demonstracao_financeira(request):
    fundos_qs = restrict_by_empresa(
        Fundo.objects.select_related("empresa"),
        request.user,
        "empresa",
    ).order_by("nome")
    fundos = list(fundos_qs)

    fundos_anos = {}
    for fundo in fundos:
        anos = BalanceteItem.objects.filter(fundo=fundo).values_list("ano", flat=True).distinct()
        fundos_anos[fundo.id] = sorted(set(anos), reverse=True)

    if request.method == "POST":
        fundo_id = request.POST.get("fundo_id")
        ano_str = request.POST.get("ano")
        arquivo = request.FILES.get("planilha")

        if not ano_str:
            messages.error(request, "O campo Ano é obrigatório.")
            return render(request, "demonstracao_financeira.html", {"fundos": fundos, "fundos_anos": fundos_anos})
        try:
            ano = int(ano_str)
        except ValueError:
            messages.error(request, "Ano inválido.")
            return render(request, "demonstracao_financeira.html", {"fundos": fundos, "fundos_anos": fundos_anos})

        fundo_qs = restrict_by_empresa(Fundo.objects.all(), request.user, "empresa")
        fundo = get_object_or_404(fundo_qs, id=fundo_id)

        try:
            df = pd.read_excel(arquivo)
        except Exception as e:
            messages.error(request, f"Erro ao ler o arquivo: {e}")
            return redirect("demonstracao_financeira")

        importados = 0
        ignorados = 0

        with transaction.atomic():
            for _, row in df.iterrows():
                conta_codigo = str(row.get("CONTA", "")).strip()
                if not conta_codigo:
                    ignorados += 1
                    continue

                saldo_atual = row.get("SALDO ATUAL")
                saldo_anterior = row.get("SALDO ANTERIOR")

                try:
                    conta_mapeada = MapeamentoContas.objects.get(conta=conta_codigo)
                except MapeamentoContas.DoesNotExist:
                    ignorados += 1
                    continue

                # Saldo do ano atual
                if not pd.isna(saldo_atual):
                    _, created = BalanceteItem.objects.update_or_create(
                        fundo=fundo,
                        ano=ano,
                        conta_corrente=conta_mapeada,
                        defaults={"saldo_final": saldo_atual},
                    )
                    importados += 1 if created else 1  # conta como operação bem-sucedida

                # Saldo do ano anterior
                if not pd.isna(saldo_anterior):
                    _, created = BalanceteItem.objects.update_or_create(
                        fundo=fundo,
                        ano=ano - 1,
                        conta_corrente=conta_mapeada,
                        defaults={"saldo_final": saldo_anterior},
                    )
                    importados += 1 if created else 1

        messages.success(
            request,
            f"Importação concluída: {importados} itens salvos/atualizados (anos {ano} e {ano-1}), {ignorados} ignorados."
        )
        return redirect("demonstracao_financeira")

    return render(request, "demonstracao_financeira.html", {
        "fundos": fundos,
        "fundos_anos": fundos_anos
    })


@login_required
def download_modelo_balancete(request):
    caminho_arquivo = os.path.join(settings.STATIC_ROOT, "modelos", "modelo_balancete.xlsx")
    if settings.DEBUG:
        caminho_arquivo = os.path.join(settings.BASE_DIR, "static", "modelos", "modelo_balancete.xlsx")
    return FileResponse(open(caminho_arquivo, "rb"), as_attachment=True, filename="Modelo Balancete.xlsx")


# ===============================
# DRE (visualização/exportação)
# ===============================
@login_required
def dre_resultado(request, fundo_id, ano):
    fundo_qs = restrict_by_empresa(Fundo.objects.select_related("empresa"), request.user, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    dict_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, ano)
    return render(request, "dre_resultado.html", {
        "dict_tabela": dict_tabela,
        "ano": ano,
        "fundo": fundo,
        "resultado_exercicio": resultado_exercicio,
        "resultado_exercicio_anterior": resultado_exercicio_anterior
    })


@login_required
def exportar_dre_excel(request, fundo_id, ano):
    fundo_qs = restrict_by_empresa(Fundo.objects.select_related("empresa"), request.user, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    dict_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, ano)

    wb = Workbook()
    ws = wb.active
    ws.title = "DRE"
    ws.sheet_view.showGridLines = False

    # Estilos
    bold = Font(bold=True)
    italic = Font(italic=True)
    center = Alignment(horizontal="center")
    right = Alignment(horizontal="right")
    left = Alignment(horizontal="left")
    indent = Alignment(horizontal="left", indent=1)
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
    ws.append([])  # Linha em branco

    row_header = ws.max_row
    for col in (2, 4):
        ws.cell(row=row_header, column=col).alignment = right
        ws.cell(row=row_header, column=col).font = bold
        ws.cell(row=row_header, column=col).border = bottom_border

    # Dados
    for grupo, dados in dict_tabela.items():
        ws.append([grupo, dados["SOMA"], "", dados["SOMA_ANTERIOR"]])
        row = ws.max_row
        ws.cell(row=row, column=1).font = bold
        ws.cell(row=row, column=1).alignment = left
        for col in (2, 4):
            cell = ws.cell(row=row, column=col)
            cell.font = bold
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

        ws.append([])  # Linha em branco entre grupos


    # Resultado do exercício
    row = ws.max_row
    ws.append([
        "Resultado do exercício",
        resultado_exercicio,
        "",
        resultado_exercicio_anterior
    ])
    row = ws.max_row
    ws.cell(row=row, column=1).font = bold
    ws.cell(row=row, column=1).alignment = left
    for col in (2, 4):
        cell = ws.cell(row=row, column=col)
        cell.number_format = "#,##0_);(#,##0)"
        cell.font = bold
        cell.alignment = right
        cell.border = double_bottom_border

    ws.insert_cols(1)

    # Larguras
    col_widths = {1: 3, 2: 65, 3: 12, 4: 5, 5: 12, 6: 3}
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    # Resposta
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
def listar_fundos(request):
    fundos = restrict_by_empresa(
        Fundo.objects.select_related("empresa"),
        request.user,
        "empresa",
    ).order_by("nome")
    form = FundoForm()
    return render(request, "fundos/listar.html", {"fundos": fundos, "form": form})


@login_required
def adicionar_fundo(request):
    if request.method == "POST":
        form = FundoForm(request.POST)
        if form.is_valid():
            fundo = form.save(commit=False)

            # Resolver a empresa do fundo
            empresas_user = list(_empresas_do_usuario(request.user))
            empresa_id_post = request.POST.get("empresa") or request.POST.get("empresa_id")

            if getattr(request.user, "has_global_scope", None) and request.user.has_global_scope():
                # Global pode escolher qualquer empresa (se o form não tiver, tenta pelo POST)
                if not getattr(fundo, "empresa_id", None):
                    if empresa_id_post:
                        fundo.empresa_id = empresa_id_post
                    else:
                        messages.error(request, "Selecione a empresa do Fundo.")
                        return redirect("listar_fundos")
            else:
                # Sem escopo global: se ele só tem 1 empresa, usa ela; se tiver várias, exige seleção
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
def editar_fundo(request, fundo_id):
    qs = restrict_by_empresa(Fundo.objects.all(), request.user, "empresa")
    fundo = get_object_or_404(qs, id=fundo_id)

    if request.method == "POST":
        form = FundoForm(request.POST, instance=fundo)
        if form.is_valid():
            obj = form.save(commit=False)
            # Não permitir trocar empresa para uma que o usuário não tenha acesso
            nova_empresa_id = getattr(obj, "empresa_id", fundo.empresa_id)
            if nova_empresa_id != fundo.empresa_id:
                # valida se pode
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
def excluir_fundo(request, fundo_id):
    qs = restrict_by_empresa(Fundo.objects.all(), request.user, "empresa")
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
