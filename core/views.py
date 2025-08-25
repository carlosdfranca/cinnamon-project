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
from core.upload.mec_parser import parse_excel_mec, MecSchemaError
from core.processing.import_service import import_balancete, import_mec
from core.processing.dre_service import gerar_dados_dre
from core.processing.dpf_service import gerar_dados_dpf

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


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

    if request.method == "POST":
        if not _can_manage_fundos(request):
            messages.error(request, "Você não tem permissão para importar.")
            return redirect("demonstracao_financeira")

        fundo_id = request.POST.get("fundo_id")
        ano_str = request.POST.get("ano")
        arquivo_balancete = request.FILES.get("arquivo_balancete")
        arquivo_mec = request.FILES.get("arquivo_mec")

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
            return redirect("demonstracao_financeira")

        fundo_qs2 = query_por_empresa_ativa(Fundo.objects.all(), request, "empresa")
        fundo = get_object_or_404(fundo_qs2, id=fundo_id)

        if not arquivo_balancete or not arquivo_mec:
            messages.error(request, "Você precisa selecionar as duas planilhas (Balancete e MEC).")
            return redirect("demonstracao_financeira")

        try:
            rows_balancete = parse_excel(arquivo_balancete)
            rows_mec = parse_excel_mec(arquivo_mec)
        except BalanceteSchemaError as e:
            messages.error(request, f"Planilha do Balancete Inválida: faltam colunas {', '.join(e.missing_columns)}")
            return redirect("demonstracao_financeira")
        except MecSchemaError as e:
            messages.error(request, f"Planilha do MEC Inválida: faltam colunas {', '.join(e.missing_columns)}")
            return redirect("demonstracao_financeira")
        except Exception as e:
            messages.error(request, f"Erro ao ler arquivos: {e}")
            return redirect("demonstracao_financeira")

        report_bal = import_balancete(fundo_id=fundo.id, ano=ano, rows=rows_balancete)
        report_mec = import_mec(fundo_id=fundo.id, rows=rows_mec)

        msg = (
            f"Balancete → {report_bal.imported} ins., {report_bal.updated} upd., {report_bal.ignored} ign. | "
            f"MEC → {report_mec.imported} ins., {report_mec.updated} upd., {report_mec.ignored} ign."
        )
        if report_bal.errors or report_mec.errors:
            messages.warning(request, "Importação concluída com erros. " + msg)
        else:
            messages.success(request, "Importação concluída com sucesso. " + msg)

        return redirect("demonstracao_financeira")

    return render(request, "demonstracao_financeira.html", {
        "fundos": fundos,
        "fundos_anos": fundos_anos,
        "can_enviar_balancete": _can_manage_fundos(request),
    })



# ===============================
# DRE (visualização/exportação) — view-only
# ===============================
@login_required
@company_can_view_data
def df_resultado(request, fundo_id, ano):
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    # --- DRE ---
    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, int(ano))

    # --- DPF ---
    dpf_tabela, _metricas_dpf = gerar_dados_dpf(fundo_id, int(ano))  # ignorando métricas internas

    # PL ajustado pelo resultado (como você já faz)
    pl_atual = (dpf_tabela["PL"]["TOTAL_PL"]["ATUAL"] or 0) + (resultado_exercicio or 0)
    pl_anterior = (dpf_tabela["PL"]["TOTAL_PL"]["ANTERIOR"] or 0) + (resultado_exercicio_anterior or 0)

    total_pl_passivo_atual = pl_atual + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ATUAL"] or 0)
    total_pl_passivo_anterior = pl_anterior + (dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ANTERIOR"] or 0)

    def _pct(v, base):
        try:
            v = float(v or 0)
            b = float(base or 0)
            return round((v / b) * 100, 2) if b != 0 else 0.0
        except Exception:
            return 0.0

    def annotate_percents(dpf: dict, pl_atual_val: float, pl_ant_val: float) -> dict:
        """
        Adiciona PERC_ATUAL/PERC_ANTERIOR em:
          - cada TOTAL_* (com base em ATUAL/ANTERIOR)
          - cada grupo (com base em SOMA/SOMA_ANTERIOR)
          - cada subgrupo (com base em ATUAL/ANTERIOR)
        """
        for sec_name, sec in dpf.items():  # ATIVO, PASSIVO, PL
            if not isinstance(sec, dict):
                continue
            for grupo_label, bloco in sec.items():
                # Totais da seção (ex.: TOTAL_ATIVO)
                if isinstance(bloco, dict) and grupo_label.startswith("TOTAL_"):
                    atual = bloco.get("ATUAL", 0)
                    anterior = bloco.get("ANTERIOR", 0)
                    bloco["PERC_ATUAL"] = _pct(atual, pl_atual_val)
                    bloco["PERC_ANTERIOR"] = _pct(anterior, pl_ant_val)
                    continue

                # Grupos "normais" (ex.: 'Disponibilidades', 'Valores a pagar', etc.)
                if isinstance(bloco, dict):
                    soma_atual = bloco.get("SOMA", 0)
                    soma_ant = bloco.get("SOMA_ANTERIOR", 0)
                    # Percentual do grupo (linha de grupo)
                    bloco["PERC_ATUAL"] = _pct(soma_atual, pl_atual_val)
                    bloco["PERC_ANTERIOR"] = _pct(soma_ant, pl_ant_val)

                    # Subgrupos (folhas): 'Banco conta movimento', etc.
                    for sub_label, valores in bloco.items():
                        if sub_label in ("SOMA", "SOMA_ANTERIOR"):
                            continue
                        if isinstance(valores, dict) and ("ATUAL" in valores or "ANTERIOR" in valores):
                            atual_v = valores.get("ATUAL", 0)
                            ant_v = valores.get("ANTERIOR", 0)
                            valores["PERC_ATUAL"] = _pct(atual_v, pl_atual_val)
                            valores["PERC_ANTERIOR"] = _pct(ant_v, pl_ant_val)
        return dpf

    dpf_tabela = annotate_percents(dpf_tabela, pl_atual, pl_anterior)

    # % para agregados extras (se quiser exibir/usar)
    perc_total_pl_passivo_atual = _pct(total_pl_passivo_atual, pl_atual)
    perc_total_pl_passivo_anterior = _pct(total_pl_passivo_anterior, pl_anterior)

    return render(request, "df_resultado.html", {
        # DRE
        "dre_tabela": dre_tabela,
        "resultado_exercicio": resultado_exercicio,
        "resultado_exercicio_anterior": resultado_exercicio_anterior,

        # DPF
        "dpf_tabela": dpf_tabela,
        "pl_ajustado_atual": pl_atual,
        "pl_ajustado_anterior": pl_anterior,
        "total_pl_passivo_atual": total_pl_passivo_atual,
        "total_pl_passivo_anterior": total_pl_passivo_anterior,
        "perc_total_pl_passivo_atual": perc_total_pl_passivo_atual,
        "perc_total_pl_passivo_anterior": perc_total_pl_passivo_anterior,

        # contexto comum
        "ano": int(ano),
        "fundo": fundo,
    })



@login_required
@company_can_view_data
def exportar_dfs_excel(request, fundo_id, ano):
    fundo_qs = query_por_empresa_ativa(Fundo.objects.select_related("empresa"), request, "empresa")
    fundo = get_object_or_404(fundo_qs, id=fundo_id)

    # --- Dados base ---
    ano = int(ano)
    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, ano)
    dpf_tabela, _metricas_dpf = gerar_dados_dpf(fundo_id, ano)

    # Ajustes solicitados
    pl_atual = dpf_tabela["PL"]["TOTAL_PL"]["ATUAL"] + resultado_exercicio
    pl_anterior = dpf_tabela["PL"]["TOTAL_PL"]["ANTERIOR"] + resultado_exercicio_anterior
    total_pl_passivo_atual = pl_atual + dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ATUAL"]
    total_pl_passivo_anterior = pl_anterior + dpf_tabela["PASSIVO"]["TOTAL_PASSIVO"]["ANTERIOR"]

    # --- Workbook com múltiplas guias ---
    wb = Workbook()

    # Estilos
    bold = Font(bold=True)
    italic = Font(italic=True)
    left = Alignment(horizontal="left")
    right = Alignment(horizontal="right")
    center = Alignment(horizontal="center")
    indent2 = Alignment(horizontal="left", indent=2)
    bottom_border = Border(bottom=Side(style="thin"))
    underline_single = Border(bottom=Side(style="thin"))
    underline_double = Border(bottom=Side(style="double"))
    double_bottom_border = Border(bottom=Side(style="double"))

    nome_fundo = str(fundo.nome).upper()

    # ====== GUIA DPF ======
    # A primeira aba criada pelo openpyxl vem ativa: usaremos para a DPF
    ws_dpf = wb.active
    ws = ws_dpf
    ws.title = "DPF"
    ws.sheet_view.showGridLines = False
    
    def _dash(v):
        try:
            return "-" if (v is None or float(v) == 0) else v
        except Exception:
            return v

    def _write_money(cell, value, underline=None, bold_=False):
        if value == "-" or value is None:
            cell.value = "-"
            cell.alignment = right
            cell.border = underline
            return
        cell.value = value
        cell.number_format = "#,##0_);(#,##0)"
        cell.alignment = right
        if bold_:
            cell.font = Font(bold=True)
        if underline:
            cell.border = underline

    def _write_percent(cell, value, underline=None, bold_=False):
        if value in (None, "-"):
            cell.value = "-"
            cell.alignment = right
            return
        cell.value = float(value)  # já vem como 37,35 etc.
        cell.number_format = "#,##0.00"
        cell.alignment = right
        if bold_:
            cell.font = Font(bold=True)
        if underline:
            cell.border = underline

    nome_fundo = str(fundo.nome).upper()

    # Cabeçalho principal
    ws["A1"] = nome_fundo; ws["A1"].font = bold; ws["A1"].alignment = left
    ws["A2"] = f"CNPJ: {fundo.cnpj}"; ws["A2"].font = bold; ws["A2"].alignment = left
    ws["A3"] = f"Administrado por {fundo.empresa.nome}"; ws["A3"].alignment = left
    ws["A4"] = f"CNPJ: {fundo.empresa.cnpj or ''}"; ws["A4"].alignment = left

    ws.append([])
    ws["A6"] = "Demonstração da Posição Financeira"; ws["A6"].font = bold; ws["A6"].alignment = left
    ws["A7"] = f"Em 31 de dezembro de {ano} e {ano - 1}"; ws["A7"].alignment = left
    ws["A8"] = "(Valores expressos em milhares de reais, exceto quando apresentado de outra forma)"
    ws["A8"].font = italic; ws["A8"].alignment = left

    ws.append([])

    # ✅ Inserir a coluna vazia entre A e B ANTES de escrever cabeçalhos/dados
    ws.insert_cols(2)

    # Mapa de colunas (mais legível e fácil de manter)
    COL = {
        "DESC": 1,      # A
        "SEP_LEFT": 2,  # B (vazia)
        "Q_CUR": 3,     # C
        "R_CUR": 4,     # D
        "P_CUR": 5,     # E
        "SEP_MID": 6,   # F (vazia separadora entre os anos)
        "Q_PRI": 7,     # G
        "R_PRI": 8,     # H
        "P_PRI": 9,     # I
    }

    # Larguras (B e F finas)
    col_widths = {
        COL["DESC"]: 55,
        COL["SEP_LEFT"]: 3,  # coluna vazia fina
        COL["Q_CUR"]: 9,
        COL["R_CUR"]: 14,
        COL["P_CUR"]: 16,
        COL["SEP_MID"]: 3,   # separador entre blocos de anos
        COL["Q_PRI"]: 9,
        COL["R_PRI"]: 14,
        COL["P_PRI"]: 16,
    }
    for idx, w in col_widths.items():
        ws.column_dimensions[get_column_letter(idx)].width = w

    # Cabeçalho por ano (duas linhas com mesclagem)
    row0 = ws.max_row + 2
    ws.cell(row=row0, column=COL["Q_CUR"], value=f"31/12/{ano}").font = bold
    ws.cell(row=row0, column=COL["Q_CUR"]).alignment = center
    for c in range(COL["Q_CUR"], COL["P_CUR"] + 1):
        ws.cell(row=row0, column=c).border = bottom_border
    ws.merge_cells(start_row=row0, start_column=COL["Q_CUR"], end_row=row0, end_column=COL["P_CUR"])

    ws.cell(row=row0, column=COL["Q_PRI"], value=f"31/12/{ano - 1}").font = bold
    ws.cell(row=row0, column=COL["Q_PRI"]).alignment = center
    for c in range(COL["Q_PRI"], COL["P_PRI"] + 1):
        ws.cell(row=row0, column=c).border = bottom_border
    ws.merge_cells(start_row=row0, start_column=COL["Q_PRI"], end_row=row0, end_column=COL["P_PRI"])

    # Subcabeçalhos
    row1 = row0 + 1
    ws.cell(row=row1, column=COL["DESC"], value="Ativo").font = bold
    ws.cell(row=row1, column=COL["DESC"]).alignment = center
    ws.cell(row=row1, column=COL["DESC"]).border = bottom_border

    ws.cell(row=row1, column=COL["Q_CUR"], value="Quant").font = bold
    ws.cell(row=row1, column=COL["Q_CUR"]).alignment = center
    ws.cell(row=row1, column=COL["Q_CUR"]).border = bottom_border

    ws.cell(row=row1, column=COL["R_CUR"], value="R$").font = bold
    ws.cell(row=row1, column=COL["R_CUR"]).alignment = center
    ws.cell(row=row1, column=COL["R_CUR"]).border = bottom_border

    ws.cell(row=row1, column=COL["P_CUR"], value="% sobre o patrimônio líquido").font = bold
    ws.cell(row=row1, column=COL["P_CUR"]).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.cell(row=row1, column=COL["P_CUR"]).border = bottom_border

    ws.cell(row=row1, column=COL["Q_PRI"], value="Quant").font = bold
    ws.cell(row=row1, column=COL["Q_PRI"]).alignment = center
    ws.cell(row=row1, column=COL["Q_PRI"]).border = bottom_border

    ws.cell(row=row1, column=COL["R_PRI"], value="R$").font = bold
    ws.cell(row=row1, column=COL["R_PRI"]).alignment = center
    ws.cell(row=row1, column=COL["R_PRI"]).border = bottom_border

    ws.cell(row=row1, column=COL["P_PRI"], value="% sobre o patrimônio líquido").font = bold
    ws.cell(row=row1, column=COL["P_PRI"]).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.cell(row=row1, column=COL["P_PRI"]).border = bottom_border

    # Linha vazia para separar cabeçalhos do conteúdo
    ws.append([])
    current_row = ws.max_row + 1

    def _add_linha(descricao, v_atual=None, p_atual=None, v_ant=None, p_ant=None,
                bold_line=False, indent=False, underline_kind=None):
        nonlocal current_row
        r = current_row

        # Descrição
        ws.cell(row=r, column=COL["DESC"], value=descricao)
        ws.cell(row=r, column=COL["DESC"]).alignment = indent2 if indent else left
        if bold_line:
            ws.cell(row=r, column=COL["DESC"]).font = Font(bold=True)

        # Ano atual
        ws.cell(row=r, column=COL["Q_CUR"], value="-").alignment = right
        _write_money(ws.cell(row=r, column=COL["R_CUR"]), _dash(v_atual), underline=underline_kind, bold_=bold_line)
        _write_percent(ws.cell(row=r, column=COL["P_CUR"]), p_atual, underline=underline_kind, bold_=bold_line)

        # Coluna separadora do meio
        ws.cell(row=r, column=COL["SEP_MID"], value="")

        # Ano anterior
        ws.cell(row=r, column=COL["Q_PRI"], value="-").alignment = right
        _write_money(ws.cell(row=r, column=COL["R_PRI"]), _dash(v_ant), underline=underline_kind, bold_=bold_line)
        _write_percent(ws.cell(row=r, column=COL["P_PRI"]), p_ant, underline=underline_kind, bold_=bold_line)

        current_row += 1

    def _perc_from(val, base):
        try:
            return round((float(val or 0)/float(base or 0))*100, 2) if base else 0.0
        except:
            return 0.0

    # ===== Seção: ATIVO =====
    ws.append([])   # <-- aqui garante linha 100% vazia
    current_row = ws.max_row + 2
    ws.cell(row=current_row-1, column=COL["DESC"]).font = Font(bold=True)

    ativo = dpf_tabela["ATIVO"]
    for grupo_label, bloco in ativo.items():
        if grupo_label.startswith("TOTAL_"):
            continue
        # linha do GRUPO (SOMA)
        soma_atual = bloco.get("SOMA", 0)
        soma_ant = bloco.get("SOMA_ANTERIOR", 0)
        p_atual = bloco.get("PERC_ATUAL", _perc_from(soma_atual, pl_atual))
        p_ant = bloco.get("PERC_ANTERIOR", _perc_from(soma_ant, pl_anterior))
        _add_linha(grupo_label, soma_atual, p_atual, soma_ant, p_ant, bold_line=True, underline_kind=underline_single)

        # linhas dos SUBGRUPOS (folhas)
        for sub, valores in bloco.items():
            if sub in ("SOMA", "SOMA_ANTERIOR"):
                continue
            if isinstance(valores, dict):
                v_at = valores.get("ATUAL", 0)
                v_an = valores.get("ANTERIOR", 0)
                p_at = valores.get("PERC_ATUAL", _perc_from(v_at, pl_atual))
                p_an = valores.get("PERC_ANTERIOR", _perc_from(v_an, pl_anterior))
                _add_linha(sub, v_at, p_at, v_an, p_an, indent=True)

        ws.append([])
        current_row = ws.max_row + 2

    # TOTAL ATIVO (duplo)
    tot_ativo_at = ativo["TOTAL_ATIVO"]["ATUAL"]
    tot_ativo_an = ativo["TOTAL_ATIVO"]["ANTERIOR"]
    p_tot_ativo_at = _perc_from(tot_ativo_at, pl_atual)
    p_tot_ativo_an = _perc_from(tot_ativo_an, pl_anterior)
    _add_linha("Total do ativo", tot_ativo_at, p_tot_ativo_at, tot_ativo_an, p_tot_ativo_an,
            bold_line=True, underline_kind=underline_double)

    # ===== Seção: PASSIVO =====
    ws.append([]); current_row = ws.max_row + 2
    passivo = dpf_tabela["PASSIVO"]

    for grupo_label, bloco in passivo.items():
        if grupo_label.startswith("TOTAL_"):
            continue
        soma_atual = bloco.get("SOMA", 0)
        soma_ant = bloco.get("SOMA_ANTERIOR", 0)
        p_atual = bloco.get("PERC_ATUAL", _perc_from(soma_atual, pl_atual))
        p_ant = bloco.get("PERC_ANTERIOR", _perc_from(soma_ant, pl_anterior))
        _add_linha(grupo_label, soma_atual, p_atual, soma_ant, p_ant, bold_line=True, underline_kind=underline_single)

        for sub, valores in bloco.items():
            if sub in ("SOMA", "SOMA_ANTERIOR"):
                continue
            if isinstance(valores, dict):
                v_at = valores.get("ATUAL", 0)
                v_an = valores.get("ANTERIOR", 0)
                p_at = valores.get("PERC_ATUAL", _perc_from(v_at, pl_atual))
                p_an = valores.get("PERC_ANTERIOR", _perc_from(v_an, pl_anterior))
                _add_linha(sub, v_at, p_at, v_an, p_an, indent=True)
        
        ws.append([])
        current_row = ws.max_row + 2

    # TOTAL PASSIVO (duplo)
    tot_passivo_at = passivo["TOTAL_PASSIVO"]["ATUAL"]
    tot_passivo_an = passivo["TOTAL_PASSIVO"]["ANTERIOR"]
    p_tot_passivo_at = _perc_from(tot_passivo_at, pl_atual)
    p_tot_passivo_an = _perc_from(tot_passivo_an, pl_anterior)
    _add_linha("Total do passivo", tot_passivo_at, p_tot_passivo_at, tot_passivo_an, p_tot_passivo_an,
            bold_line=True, underline_kind=underline_double)

    ws.append([]); current_row = ws.max_row + 2

    # PL ajustado (100% por definição)
    pl_ajustado_atual = pl_atual
    pl_ajustado_anterior = pl_anterior
    _add_linha("Patrimônio líquido", pl_ajustado_atual, 100.00, pl_ajustado_anterior, 100.00,
            bold_line=True, underline_kind=underline_double)
    
    ws.append([]); current_row = ws.max_row + 2

    # Total do PL e Passivo
    p_tot_pl_pass_at = _perc_from(total_pl_passivo_atual, pl_ajustado_atual)
    p_tot_pl_pass_an = _perc_from(total_pl_passivo_anterior, pl_ajustado_anterior)
    _add_linha("Total do patrimônio líquido e do passivo",
            total_pl_passivo_atual, p_tot_pl_pass_at,
            total_pl_passivo_anterior, p_tot_pl_pass_an,
            bold_line=True, underline_kind=underline_double)
    
    ws.append([]); current_row = ws.max_row + 2

    last_col = max(ws.max_column, 9)  # força mínimo 9 se seu layout tem até a coluna I

    # Mescla da coluna A até a última coluna do layout
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=last_col)

    cell = ws.cell(row=current_row, column=1)
    cell.value = "As notas explicativas são parte integrante das demonstrações financeiras."
    cell.font = Font(italic=True, bold=True)  # ou bold=True se preferir
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)


    # ====== GUIA DRE ======
    ws_dre = wb.create_sheet(title="DRE")
    ws = ws_dre
    ws.sheet_view.showGridLines = False
    
    ws["A1"] = nome_fundo; ws["A1"].font = bold; ws["A1"].alignment = left
    ws["A2"] = f"CNPJ: {fundo.cnpj}"; ws["A2"].font = bold; ws["A2"].alignment = left
    ws["A3"] = fundo.empresa.nome; ws["A3"].alignment = left
    ws["A4"] = f"CNPJ: {fundo.empresa.cnpj or ''}"; ws["A4"].alignment = left
    ws.append([])

    ws["A6"] = "Demonstração do Resultado do Exercício"
    ws["A6"].font = bold; ws["A6"].alignment = left
    ws["A7"] = f"Exercícios findos em 31 de dezembro de {ano} e {ano - 1}"
    ws["A7"].font = bold; ws["A7"].alignment = left
    ws["A8"] = "(Valores expressos em milhares de reais)"
    ws["A8"].font = italic; ws["A8"].alignment = left

    ws.append([])
    ws.insert_cols(3)
    ws.append(["", f"31/12/{ano}", "", f"31/12/{ano - 1}"])
    row_header = ws.max_row
    for col in (2, 4):
        c = ws.cell(row=row_header, column=col)
        c.alignment = right; c.font = bold; c.border = bottom_border

    for grupo, dados in dre_tabela.items():
        ws.append([grupo, dados["SOMA"], "", dados["SOMA_ANTERIOR"]])
        row = ws.max_row
        ws.cell(row=row, column=1).font = bold
        ws.cell(row=row, column=1).alignment = left
        for col in (2, 4):
            cell = ws.cell(row=row, column=col)
            cell.font = bold; cell.alignment = right
            cell.number_format = "#,##0_);(#,##0)"; cell.border = bottom_border

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

    ws.append(["Resultado do exercício", resultado_exercicio, "", resultado_exercicio_anterior])
    row = ws.max_row
    ws.cell(row=row, column=1).font = bold
    ws.cell(row=row, column=1).alignment = left
    for col in (2, 4):
        cell = ws.cell(row=row, column=col)
        cell.number_format = "#,##0_);(#,##0)"
        cell.font = bold; cell.alignment = right; cell.border = double_bottom_border


    ws.insert_cols(1)
    for col_num, width in {1:3, 2:65, 3:12, 4:5, 5:12, 6:3}.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    # --- Resposta HTTP ---
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nome_curto = "_".join(str(fundo.nome).replace("-", "").split())
    response["Content-Disposition"] = f"attachment; filename=DFs_{ano}_{nome_curto}.xlsx"
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
