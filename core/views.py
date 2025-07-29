from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now


from df.models import Fundo, BalanceteItem, MapeamentoContas

from .forms import FundoForm
from core.utils.utils import gerar_dados_dre

import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, NamedStyle, PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd



# Funções da Página de Demonstração Financeira
@login_required
def demonstracao_financeira(request):
    fundos = Fundo.objects.filter(usuario=request.user).order_by('nome')
    fundos_anos = {}
    for fundo in fundos:
        anos = BalanceteItem.objects.filter(fundo=fundo).values_list('ano', flat=True).distinct()
        fundos_anos[fundo.id] = sorted(set(anos), reverse=True)

    if request.method == 'POST':
        fundo_id = request.POST.get('fundo_id')
        ano = request.POST.get('ano')
        arquivo = request.FILES.get('planilha')

        # Validação do ano
        if not ano:
            messages.error(request, "O campo Ano é obrigatório.")
            return render(request, 'demonstracao_financeira.html', {'fundos': fundos})

        try:
            fundo = Fundo.objects.get(id=fundo_id, usuario=request.user)
        except Fundo.DoesNotExist:
            messages.error(request, "Fundo inválido.")
            return redirect('demonstracao_financeira')

        try:
            df = pd.read_excel(arquivo)
        except Exception as e:
            messages.error(request, f"Erro ao ler o arquivo: {e}")
            return redirect('demonstracao_financeira')

        importados = 0
        ignorados = 0

        for _, row in df.iterrows():
            conta_codigo = str(row['CONTA']).strip()

            saldo_atual = row.get('SALDO ATUAL')
            saldo_anterior = row.get('SALDO ANTERIOR')

            try:
                conta_mapeada = MapeamentoContas.objects.get(conta=conta_codigo)

                # Inserção do saldo atual
                if not pd.isna(saldo_atual):
                    BalanceteItem.objects.create(
                        fundo=fundo,
                        ano=int(ano),
                        conta_corrente=conta_mapeada,
                        saldo_final=saldo_atual
                    )
                    importados += 1

                # Inserção do saldo anterior (ano - 1)
                if not pd.isna(saldo_anterior):
                    BalanceteItem.objects.create(
                        fundo=fundo,
                        ano=int(ano) - 1,
                        conta_corrente=conta_mapeada,
                        saldo_final=saldo_anterior
                    )
                    importados += 1

            except MapeamentoContas.DoesNotExist:
                ignorados += 1
                continue

        messages.success(
            request,
            f"Importação concluída: {importados} itens salvos (incluindo anos anterior e atual), {ignorados} ignorados."
        )
        return redirect('demonstracao_financeira')

    return render(request, 'demonstracao_financeira.html', {
        'fundos': fundos,
        'fundos_anos': fundos_anos
    })

@login_required
def download_modelo_balancete(request):
    caminho_arquivo = os.path.join(settings.STATIC_ROOT, 'modelos', 'modelo_balancete.xlsx')
    
    # Se estiver usando DEBUG = True (modo dev), pode usar STATICFILES_DIRS:
    if settings.DEBUG:
        caminho_arquivo = os.path.join(settings.BASE_DIR, 'static', 'modelos', 'modelo_balancete.xlsx')

    return FileResponse(open(caminho_arquivo, 'rb'), as_attachment=True, filename='Modelo Balancete.xlsx')

@login_required
def dre_resultado(request, fundo_id, ano):
    fundo = Fundo.objects.get(id=fundo_id)

    dict_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, ano)


    return render(request, 'dre_resultado.html', {
        'dict_tabela': dict_tabela,
        'ano': ano,
        'fundo': fundo,
        'resultado_exercicio': resultado_exercicio,
        'resultado_exercicio_anterior': resultado_exercicio_anterior
    })

@login_required
def exportar_dre_excel(request, fundo_id, ano):
    fundo = Fundo.objects.get(id=fundo_id)
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

    bottom_border = Border(bottom=Side(style='thin'))
    double_bottom_border = Border(bottom=Side(style="double"))

    nome_fundo = str(fundo.nome).upper()

    # Cabeçalhos principais
    ws["A1"] = nome_fundo
    ws["A1"].font = bold
    ws["A1"].alignment = left

    ws["A2"] = f"CNPJ: {fundo.cnpj}"
    ws["A2"].font = bold
    ws["A2"].alignment = left

    ws["A3"] = request.user.nome_empresa
    ws["A3"].alignment = left

    ws["A4"] = f"CNPJ: {request.user.nome_empresa}"
    ws["A4"].alignment = left

    ws.append([])  # Linha em branco

    ws["A6"] = "Demonstração do Resultado do Exercício"
    ws["A6"].font = bold
    ws["A6"].alignment = left

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

    # Dados da DRE
    for grupo, dados in dict_tabela.items():
        # Adiciona o grupo + valores
        ws.append([grupo, dados["SOMA"], "", dados["SOMA_ANTERIOR"]])
        row = ws.max_row  

        # Estilização do grupo
        ws.cell(row=row, column=1).font = bold
        ws.cell(row=row, column=1).alignment = left

        for col in (2, 4):
            cell = ws.cell(row=row, column=col)
            cell.font = bold
            cell.alignment = right
            cell.number_format = '#,##0_);(#,##0)'
            cell.border = bottom_border

        # Subitens
        for item, valores in dados.items():
            if item in ["SOMA", "SOMA_ANTERIOR"]:
                continue

            ws.append([item, valores["ATUAL"], "", valores["ANTERIOR"]])
            row = ws.max_row

            ws.cell(row=row, column=1).alignment = indent2

            for col in (2, 4):
                cell = ws.cell(row=row, column=col)
                cell.alignment = right
                cell.number_format = '#,##0_);(#,##0)'

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
        cell.number_format = '#,##0_);(#,##0)'
        cell.font = bold
        cell.alignment = right
        cell.border = double_bottom_border

    ws.insert_cols(1)

    # Ajuste de largura de colunas
    col_widths = {1:3, 2: 65, 3: 12, 4: 5, 5: 12, 6:3}
    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width



    # Resposta HTTP com conteúdo do Excel
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nome_fundo = fundo.nome.replace("-", "")
    nome_curto = "_".join(nome_fundo.split())
    response["Content-Disposition"] = f'attachment; filename=DRE_{ano}_{nome_curto}.xlsx'
    wb.save(response)
    return response

# Funções para Ver, Editar e Excluir os Fundos
@login_required
def listar_fundos(request):
    fundos = Fundo.objects.filter(usuario=request.user)
    form = FundoForm()
    return render(request, 'fundos/listar.html', {'fundos': fundos, 'form': form})

@login_required
def adicionar_fundo(request):
    if request.method == 'POST':
        form = FundoForm(request.POST)
        if form.is_valid():
            fundo = form.save(commit=False)
            fundo.usuario = request.user
            fundo.save()
            return redirect('listar_fundos')
    else:
        form = FundoForm()
    return render(request, 'fundos/form.html', {'form': form, 'modo': 'Adicionar'})

@login_required
def editar_fundo(request, fundo_id):
    fundo = get_object_or_404(Fundo, id=fundo_id, usuario=request.user)
    if request.method == 'POST':
        form = FundoForm(request.POST, instance=fundo)
        if form.is_valid():
            form.save()
            return redirect('listar_fundos')
    else:
        form = FundoForm(instance=fundo)
    return render(request, 'fundos/form.html', {'form': form, 'modo': 'Editar'})

@login_required
def excluir_fundo(request, fundo_id):
    fundo = get_object_or_404(Fundo, id=fundo_id, usuario=request.user)
    if request.method == 'POST':
        fundo.delete()
        return redirect('listar_fundos')
    return render(request, 'fundos/confirmar_exclusao.html', {'fundo': fundo})





# Views para Edição do Usuário
@login_required
def editar_perfil(request):
    user = request.user

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name')
        user.email = request.POST.get('email')
        user.cpf = request.POST.get('cpf')

        nova_senha = request.POST.get('password')
        if nova_senha:
            user.set_password(nova_senha)

        user.save()
        messages.success(request, 'Perfil atualizado com sucesso!')

        # Se mudou a senha, precisa fazer login de novo
        if nova_senha:
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        return redirect('editar_perfil')

    return render(request, 'editar_perfil.html')
