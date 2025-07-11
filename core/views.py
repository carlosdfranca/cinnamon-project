from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages


# Pagina Principal
@login_required
def index(request):
    """
    Rendeniza a página do index.
    """
    return render(request, 'index.html')


# Funções
@login_required
def importar_planilha(request):
    """
    Função que importa a planilha que o cliente quer que analisemos.
    """
    return render(request, 'importar_planilha.html')


# User Functions
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

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
