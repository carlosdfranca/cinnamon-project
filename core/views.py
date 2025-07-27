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
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side



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

    bold_font = Font(bold=True)
    center = Alignment(horizontal="center")
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    ws.append(["Demonstração do Resultado do Exercício"])
    ws.append([f"Exercícios findos em 31 de dezembro de {ano} e {ano - 1}"])
    ws.append([])
    ws.append(["", f"31/12/{ano}", f"31/12/{ano - 1}"])

    ws["A1"].font = bold_font
    ws["A2"].font = bold_font

    for grupo, dados in dict_tabela.items():
        ws.append([grupo])
        ws.cell(row=ws.max_row, column=1).font = bold_font

        for item, valores in dados.items():
            if item in ["SOMA", "SOMA_ANTERIOR"]:
                continue
            ws.append([f"    {item}", valores["ATUAL"], valores["ANTERIOR"]])

        ws.append([
            f"  Total {grupo}",
            dados.get("SOMA", 0),
            dados.get("SOMA_ANTERIOR", 0)
        ])
        ws.cell(row=ws.max_row, column=1).font = bold_font

    ws.append([])
    ws.append([
        "Resultado do exercício",
        resultado_exercicio,
        resultado_exercicio_anterior
    ])
    ws.cell(row=ws.max_row, column=1).font = bold_font

    # Ajustes de layout
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=3):
        for cell in row:
            cell.alignment = center
            cell.border = border

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
