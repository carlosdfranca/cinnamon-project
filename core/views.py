from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now


from df.models import Fundo, BalanceteItem, MapeamentoContas

from .forms import FundoForm

import os
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
            saldo = row['SALDOATUAL']

            try:
                conta_mapeada = MapeamentoContas.objects.get(conta=conta_codigo)
                BalanceteItem.objects.create(
                    fundo=fundo,
                    ano=int(ano),
                    conta_corrente=conta_mapeada,
                    saldo_final=saldo
                )
                importados += 1
            except MapeamentoContas.DoesNotExist:
                ignorados += 1
                continue

        messages.success(request, f"Importação concluída: {importados} itens salvos, {ignorados} ignorados.")

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

    return FileResponse(open(caminho_arquivo, 'rb'), as_attachment=True, filename='Modelo_DF.xlsx')


def dre_resultado(request, fundo_id, ano):

    contas_dre = [
        "7.1.1.10.00.001-5", 
        "7.1.1.10.00.016-1", 
        "8.1.5.10.00.001-4", 
        "8.1.9.99.00.001-3", 
        "7.1.4.10.10.007-1", 
        "7.1.9.99.00.016-0", 
        "8.1.7.81.00.001-8", 
        "8.1.7.81.00.004-9", 
        "8.1.7.54.00.003-8", 
        "8.1.7.54.00.008-3", 
        "8.1.7.48.00.001-3", 
        "8.1.7.54.00.005-2", 
        "8.1.7.63.00.001-2", 
        "8.1.7.63.00.002-9", 
        "8.1.7.99.00.001-7", 
    ]


    itens_dre = BalanceteItem.objects.filter(fundo_id=fundo_id, ano=ano, conta_corrente__conta__in=contas_dre)

    estrutura_dre = {
        "Direitos creditórios sem aquisição substancial de riscos e benefícios": [
            "Rendimentos de  direitos creditórios",
            "(-) Provisão para perdas por redução no valor de recuperação"
        ],
        "Rendas de aplicações interfinanceiras de liquidez": [
            "Letra Financeiras do Tesouro - LFT"
        ],
        "Outras receitas operacionais": [
            "Outras receitas operacionais"
        ],
        "Demais despesas": [
            "Taxa de administração",
            "Taxa de gestão",
            "Despesas bancárias",
            "Despesas com publicações",
            "Taxa de fiscalização CVM",
            "Serviços de auditoria",
            "Serviços de consultoria",
            "Outras despesas"
        ]
    }


    dict_tabela = {}

    for grupo_dre, subgrupos in estrutura_dre.items():
        grupo_data = {}
        soma_total = 0

        for subgrupo in subgrupos:
            valor = sum(
                item.saldo_final
                for item in itens_dre
                if item.conta_corrente.grupo_df.strip().lower() == subgrupo.strip().lower()
            )

            grupo_data[subgrupo] = valor
            soma_total += valor

        grupo_data["SOMA"] = soma_total
        dict_tabela[grupo_dre] = grupo_data
    
    resultado_exercicio = sum(grupo_data["SOMA"] for grupo_data in dict_tabela.values())


    return render(request, 'dre_resultado.html', {
        'dict_tabela': dict_tabela,
        'fundo_id': fundo_id,
        'ano': ano,
        'resultado_exercicio': resultado_exercicio
    })


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
