"""
Service layer para gerenciamento de redefinição de senha ("esqueci minha senha").

Este módulo contém a lógica de negócio para:
- Solicitar redefinição de senha (gera token e dispara email)
- Validar token de redefinição
- Efetivar a redefinição de senha

Separação de responsabilidades:
- Services: Lógica de negócio e orquestração
- Models: Estrutura de dados e validações básicas
- Views: Interface HTTP e user feedback
- Tasks: Operações assíncronas (envio de email)
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from typing import Optional
import logging

from usuarios.models import PasswordResetToken

Usuario = get_user_model()
logger = logging.getLogger(__name__)


# ===== Exceções Customizadas =====

class PasswordResetError(Exception):
    """Exceção base para erros relacionados a redefinição de senha."""
    pass


class PasswordResetInvalidoError(PasswordResetError):
    """Token inválido, expirado ou já utilizado."""
    pass


# ===== Funções Principais =====

@transaction.atomic
def solicitar_reset(
    email: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    Solicita a redefinição de senha para o email informado.

    Por segurança, esta função NUNCA informa se o email existe ou não na base
    (evita enumeração de contas). Se houver usuário(s) ativo(s) com o email,
    um token é criado e o email de redefinição é enfileirado para cada um.
    Se não houver, a função simplesmente não faz nada.

    Args:
        email: Email informado pelo usuário
        ip_address: IP de quem solicitou (audit)
        user_agent: User agent de quem solicitou (audit)
    """
    email = email.lower().strip()

    usuarios = Usuario.objects.filter(email__iexact=email, is_active=True)

    for usuario in usuarios:
        # Cancela tokens pendentes anteriores deste usuário
        PasswordResetToken.objects.filter(
            usuario=usuario,
            status=PasswordResetToken.Status.PENDING
        ).update(status=PasswordResetToken.Status.CANCELLED)

        reset_token = PasswordResetToken.objects.create(
            usuario=usuario,
            ip_address=ip_address,
            user_agent=(user_agent[:500] if user_agent else ""),
        )

        logger.info(
            f"Token de redefinição de senha criado: {reset_token.id} | "
            f"Usuário: {usuario.username}"
        )

        # Enfileira envio de email (importado aqui para evitar circular import)
        envio_sincrono = getattr(settings, 'PASSWORD_RESET_ENVIO_SINCRONO', False)
        if envio_sincrono:
            from usuarios.tasks import enviar_email_reset_senha_sync
            enviar_email_reset_senha_sync(reset_token.id)
        else:
            from usuarios.tasks import enviar_email_reset_senha_async
            enviar_email_reset_senha_async.delay(reset_token.id)

    if not usuarios.exists():
        logger.info(f"Solicitação de redefinição de senha para email não cadastrado: {email}")


def validar_token(token: str) -> PasswordResetToken:
    """
    Valida um token de redefinição de senha e retorna o objeto se válido.

    Args:
        token: Token UUID da solicitação

    Returns:
        PasswordResetToken: Objeto do token se válido

    Raises:
        PasswordResetInvalidoError: Se token inválido, expirado ou já utilizado
    """
    try:
        reset_token = PasswordResetToken.objects.select_related('usuario').get(token=token)
    except PasswordResetToken.DoesNotExist:
        logger.warning(f"Tentativa de acesso com token de redefinição inválido: {token}")
        raise PasswordResetInvalidoError(_("Link inválido ou não encontrado."))

    if reset_token.status == PasswordResetToken.Status.USED:
        raise PasswordResetInvalidoError(_("Este link já foi utilizado."))

    if reset_token.status == PasswordResetToken.Status.CANCELLED:
        raise PasswordResetInvalidoError(_("Este link não é mais válido."))

    if timezone.now() > reset_token.expira_em:
        raise PasswordResetInvalidoError(
            _("Este link expirou. Solicite uma nova redefinição de senha.")
        )

    if not reset_token.usuario.is_active:
        raise PasswordResetInvalidoError(_("Este link não é mais válido."))

    return reset_token


@transaction.atomic
def redefinir_senha(
    token: str,
    nova_senha: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Usuario:
    """
    Redefine a senha do usuário associado ao token.

    Args:
        token: Token UUID da solicitação
        nova_senha: Nova senha a ser definida
        ip_address: IP de quem efetivou a redefinição (audit)
        user_agent: User agent de quem efetivou a redefinição (audit)

    Returns:
        Usuario: Usuário que teve a senha redefinida

    Raises:
        PasswordResetInvalidoError: Se token inválido
    """
    reset_token = validar_token(token)

    # Revalida status (proteção contra race condition)
    if reset_token.status != PasswordResetToken.Status.PENDING:
        raise PasswordResetInvalidoError(_("Este link não está mais disponível."))

    usuario = reset_token.usuario
    usuario.set_password(nova_senha)
    usuario.save(update_fields=['password'])

    reset_token.ip_address = ip_address or reset_token.ip_address
    if user_agent:
        reset_token.user_agent = user_agent[:500]
    reset_token.status = PasswordResetToken.Status.USED
    reset_token.usado_em = timezone.now()
    reset_token.save(update_fields=['status', 'usado_em', 'ip_address', 'user_agent'])

    # Cancela quaisquer outros tokens pendentes do mesmo usuário
    PasswordResetToken.objects.filter(
        usuario=usuario,
        status=PasswordResetToken.Status.PENDING
    ).exclude(id=reset_token.id).update(status=PasswordResetToken.Status.CANCELLED)

    logger.info(f"Senha redefinida com sucesso: Usuário {usuario.username} | Token {reset_token.id}")

    return usuario
