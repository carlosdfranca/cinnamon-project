"""
Views para o fluxo de redefinição de senha ("esqueci minha senha").

Views incluídas:
- esqueci_senha: Solicitar redefinição informando o email (público)
- redefinir_senha: Definir nova senha a partir do link recebido por email (público)
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods

from usuarios.forms import SolicitarResetSenhaForm, RedefinirSenhaForm
from usuarios.services import password_reset_service
from usuarios.services.password_reset_service import PasswordResetInvalidoError

import logging

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    """Helper para pegar o IP do request (considera proxy reverso)."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# ===== Esqueci minha senha (Público) =====

@require_http_methods(["GET", "POST"])
def esqueci_senha(request):
    """
    View pública para solicitar a redefinição de senha por email.

    GET: Exibe form para informar o email
    POST: Processa a solicitação e sempre exibe a mesma confirmação genérica
           (não revela se o email está ou não cadastrado, evitando enumeração de contas).
    """
    if request.method == "POST":
        form = SolicitarResetSenhaForm(request.POST)

        if form.is_valid():
            try:
                password_reset_service.solicitar_reset(
                    email=form.cleaned_data['email'],
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            except Exception as e:
                # Nunca expõe o erro ao usuário: loga e segue para a confirmação genérica.
                logger.exception(f"Erro ao processar solicitação de redefinição de senha: {e}")

            return render(request, 'senha/esqueci_senha_enviado.html')
    else:
        form = SolicitarResetSenhaForm()

    return render(request, 'senha/esqueci_senha.html', {'form': form})


# ===== Redefinir senha (Público) =====

@require_http_methods(["GET", "POST"])
def redefinir_senha(request, token):
    """
    View pública para definir uma nova senha a partir do link recebido por email.

    GET: Valida o token e exibe o form de nova senha
    POST: Processa a redefinição da senha
    """
    try:
        reset_token = password_reset_service.validar_token(str(token))
    except PasswordResetInvalidoError as e:
        return render(request, 'senha/link_invalido.html', {'erro': str(e)})

    if request.method == "POST":
        form = RedefinirSenhaForm(request.POST)

        if form.is_valid():
            try:
                password_reset_service.redefinir_senha(
                    token=str(token),
                    nova_senha=form.cleaned_data['password1'],
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

                messages.success(
                    request,
                    "Senha redefinida com sucesso! Entre com sua nova senha."
                )
                return redirect('login')

            except PasswordResetInvalidoError as e:
                return render(request, 'senha/link_invalido.html', {'erro': str(e)})

            except Exception as e:
                logger.exception(f"Erro ao redefinir senha com token {token}: {e}")
                messages.error(request, "Erro ao redefinir a senha. Tente novamente.")
    else:
        form = RedefinirSenhaForm()

    return render(request, 'senha/redefinir_senha.html', {
        'form': form,
        'usuario': reset_token.usuario,
    })
