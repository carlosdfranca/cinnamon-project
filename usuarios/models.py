from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

_cnpj_regex_validator = RegexValidator(
    regex=r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$|^\d{14}$",
    message="CNPJ deve estar no formato 00.000.000/0000-00 ou apenas 14 dígitos."
)

# ===== Usuário =====
class Usuario(AbstractUser):
    class GlobalRole(models.TextChoices):
        NONE = "NONE", "Sem papel global"
        PLATFORM_ADMIN = "PLATFORM_ADMIN", "Admin da Plataforma"   # vê/edita tudo
        PLATFORM_VIEWER = "PLATFORM_VIEWER", "Viewer da Plataforma" # vê tudo, sem editar

    global_role = models.CharField(
        max_length=20,
        choices=GlobalRole.choices,
        default=GlobalRole.NONE,
        help_text="Papel global (plataforma). Admin/Viewer vê todas as empresas."
    )

    def __str__(self):
        return f"{self.get_full_name() or self.username}"

    # ---- helpers globais ----
    def is_platform_admin(self) -> bool:
        # superuser continua sendo 'deus'; global admin também
        return self.is_superuser or self.global_role == self.GlobalRole.PLATFORM_ADMIN

    def is_platform_viewer(self) -> bool:
        return self.is_superuser or self.global_role in {
            self.GlobalRole.PLATFORM_ADMIN, self.GlobalRole.PLATFORM_VIEWER
        }

    def has_global_scope(self) -> bool:
        # qualquer papel global (viewer/admin) ou superuser
        return self.is_platform_viewer()


# ===== Empresa =====
class Empresa(models.Model):
    """
    Entidade 'tenant' que agrupa usuários e dados.
    Mantém um ponteiro explícito para o usuário Master para garantir unicidade
    de forma simples e performática (especialmente em MySQL).
    """
    nome = models.CharField(max_length=255, unique=True)
    cnpj = models.CharField(
        max_length=18, null=True, blank=True, unique=True,
        validators=[_cnpj_regex_validator],
        help_text="Opcional. Use 00.000.000/0000-00 ou 14 dígitos."
    )

    # Um (e apenas um) Master por empresa.
    # Usamos PROTECT para impedir deletar o Master sem antes trocar o master da empresa.
    master = models.ForeignKey(
        "Usuario",
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="empresas_como_master",
        help_text="Usuário Master desta empresa (um por empresa)."
    )

    # Campos operacionais úteis
    is_ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        indexes = [
            models.Index(name="idx_empresa_nome", fields=["nome"]),
        ]

    def __str__(self):
        return self.nome

    # ---- Regras de consistência com Membership (iremos criar a classe Membership depois) ----
    def clean(self):
        """
        Se um master está definido, ele precisa ter vínculo com a empresa e role MASTER.
        """
        if self.master_id:
            has_master_link = Membership.objects.filter(
                empresa=self, usuario_id=self.master_id, role=Membership.Role.MASTER
            ).exists()
            if not has_master_link:
                raise ValidationError(_("O usuário definido como master precisa ter vínculo MASTER nesta empresa."))

    @transaction.atomic
    def definir_master(self, usuario):
        """
        Centraliza a troca do Master: cria/ajusta Membership e seta empresa.master.
        """
        memb, _ = Membership.objects.get_or_create(
            empresa=self, usuario=usuario, defaults={"role": Membership.Role.MASTER}
        )
        if memb.role != Membership.Role.MASTER:
            memb.role = Membership.Role.MASTER
            memb.save(update_fields=["role"])
        self.master = usuario
        self.full_clean()
        self.save(update_fields=["master"])

    # Azulejos de conveniência
    def is_master(self, usuario):
        return self.master_id == getattr(usuario, "id", None)

    def usuarios(self):
        """
        Retorna todos os usuários vinculados à empresa via Membership.
        """
        return Usuario.objects.filter(
            memberships__empresa=self,
            memberships__is_active=True
        )


class Membership(models.Model):
    class Role(models.TextChoices):
        MASTER = "MASTER", "Master (administra tudo da empresa)"
        ADMIN = "ADMIN", "Admin (gerencia usuários/permissões da empresa)"
        MEMBER = "MEMBER", "Membro (acesso padrão)"
        VIEWER = "VIEWER", "Somente leitura"

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="memberships")
    usuario = models.ForeignKey("Usuario", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vínculo de Usuário com Empresa"
        verbose_name_plural = "Vínculos de Usuários com Empresas"
        unique_together = (("empresa", "usuario"),)  # um vínculo por par empresa-usuário
        indexes = [
            models.Index(fields=["empresa", "role"], name="idx_memb_empresa_role"),
            models.Index(fields=["usuario", "empresa"], name="idx_memb_usuario_empresa"),
        ]

    def __str__(self):
        return f"{self.usuario} @ {self.empresa} ({self.role})"

    # --- Regras de integridade e sincronização com Empresa.master ---
    def clean(self):
        """
        Garante coerência do papel MASTER com Empresa.master.
        - Se este vínculo é MASTER e a empresa já tem outro master, erro.
        - Se a empresa.master está definido e for diferente do usuário, este vínculo não pode ser MASTER.
        """
        if not self.empresa_id or not self.usuario_id:
            return

        empresa = self.empresa

        if self.role == self.Role.MASTER:
            if empresa.master_id and empresa.master_id != self.usuario_id:
                raise ValidationError(_("Esta empresa já possui um Master diferente."))
        else:
            pass

    @transaction.atomic
    def save(self, *args, **kwargs):
        creating = self._state.adding
        old_role = None
        if not creating:
            old = type(self).objects.filter(pk=self.pk).only("role").first()
            old_role = old.role if old else None

        super().save(*args, **kwargs)

        # Sincronização com Empresa.master
        empresa = self.empresa
        if self.role == self.Role.MASTER:
            if empresa.master_id != self.usuario_id:
                empresa.master = self.usuario
                empresa.full_clean(exclude=None)
                empresa.save(update_fields=["master"])
        else:
            if empresa.master_id == self.usuario_id:
                empresa.master = None
                empresa.save(update_fields=["master"])

    # --- Helpers de permissão ---
    def can_manage_company_users(self) -> bool:
        return self.role in {self.Role.MASTER, self.Role.ADMIN} and self.is_active

    def can_edit_data(self) -> bool:
        return self.role in {self.Role.MASTER, self.Role.ADMIN, self.Role.MEMBER} and self.is_active

    def can_view(self) -> bool:
        return self.is_active
