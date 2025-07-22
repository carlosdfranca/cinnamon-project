from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from df.models import Fundo
from .forms import FundoForm

# Funções
@login_required
def importar_balancete(request):
    """
    Função que importa a planilha com os dados do balancete do ano que o cliente quer que analisemos.
    """
    return render(request, 'importar_balancete.html')


@login_required
def demosntracao_financeira(request):
    """
    Página que vai ser responsável para o cliente visualizar as Demonstrações Financeiras que ele Subiu no sistema
    """
    return render(request, 'demosntracao_financeira.html')

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
