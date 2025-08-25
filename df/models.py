# df/models.py
from django.db import models
from decimal import Decimal
from usuarios.models import Empresa  # <<< agora o escopo é a empresa

# =========================
# FUNDOS (escopo por empresa)
# =========================
class Fundo(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="fundos",
        db_index=True,
        help_text="Empresa (tenant) proprietária deste fundo."
    )
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=20)

    class Meta:
        verbose_name = "Fundo"
        verbose_name_plural = "Fundos"
        # Ordena por empresa e nome para visualização consistente no admin/listas
        ordering = ["empresa", "nome"]
        # Regras de unicidade por tenant:
        # - mesmo CNPJ não pode existir duas vezes dentro da mesma empresa
        # - opcionalmente, mesmo nome não deve repetir dentro da mesma empresa
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "cnpj"], name="uq_fundo_empresa_cnpj"
            ),
            models.UniqueConstraint(
                fields=["empresa", "nome"], name="uq_fundo_empresa_nome"
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "nome"], name="idx_fundo_emp_nome"),
            models.Index(fields=["empresa", "cnpj"], name="idx_fundo_emp_cnpj"),
        ]

    def __str__(self):
        return f"{self.nome} [{self.cnpj}] - {self.empresa.nome}"


# ==========================================
# MAPA DE CONTAS CONTÁBEIS -> GRUPOS DO DF
# ==========================================
class MapeamentoContas(models.Model):
    """
    Mapa global (padrão) de contas para seus grupos/DFs.
    Se cada empresa tiver um plano próprio, veja nota abaixo para torná-lo por-empresa.
    """
    TIPO_CHOICES = [
        (1, "Ativo"),
        (2, "Passivo"),
        (3, "Patrimônio Líquido"),
        (4, "Resultado"),
    ]

    conta = models.CharField(max_length=30, unique=True)
    grupo_df = models.CharField(max_length=255)
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    descricao = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Mapeamento de CC"
        verbose_name_plural = "Mapeamentos de CC"
        ordering = ["tipo", "grupo_df", "conta"]
        indexes = [
            models.Index(fields=["tipo", "grupo_df"], name="idx_map_tipo_grupo"),
        ]

    def __str__(self):
        return f"{self.conta} - {self.grupo_df}"


# =================================================
# BALANCETE (por fundo, ano e conta mapeada)
# =================================================
class BalanceteItem(models.Model):
    fundo = models.ForeignKey(
        Fundo,
        on_delete=models.CASCADE,  # se deletar o Fundo, some o balancete dele
        related_name="balancete",
        db_index=True,
    )
    ano = models.IntegerField()
    conta_corrente = models.ForeignKey(
        MapeamentoContas,
        on_delete=models.PROTECT,  # evita quebrar histórico se alguém mexer no mapa
        null=True, blank=True,
        related_name="itens",
    )
    saldo_final = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    data_importacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Item do Balancete"
        verbose_name_plural = "Itens do Balancete"
        ordering = ["fundo", "conta_corrente"]
        # Se cada (fundo, ano, conta) deve ser único, este constraint evita duplicatas:
        constraints = [
            models.UniqueConstraint(
                fields=["fundo", "ano", "conta_corrente"],
                name="uq_balancete_fundo_ano_conta"
            )
        ]
        indexes = [
            models.Index(fields=["ano"], name="idx_bal_ano"),
            models.Index(fields=["fundo", "ano"], name="idx_bal_fundo_ano"),
        ]

    def __str__(self):
        # cuidado com None no saldo_final/conta
        conta = self.conta_corrente.conta if self.conta_corrente else "—"
        saldo = f"{self.saldo_final:.2f}" if self.saldo_final is not None else "—"
        return f"[{self.ano}] {self.fundo.nome} | {conta} | Saldo: R$ {saldo}"
    
# =================================================
# MEC (por fundo, e Data da posição)
# =================================================
class MecItem(models.Model):
    """
    Linha diária do MEC (movimentação de cotas e PL).
    Um fundo só pode ter uma linha por data_posicao.
    """
    fundo = models.ForeignKey(
        Fundo,
        on_delete=models.CASCADE,
        related_name="mec_itens",
        db_index=True,
    )
    data_posicao = models.DateField(db_index=True)

    aplicacao = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    resgate = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    estorno = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    pl = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))

    qtd_cotas = models.DecimalField(max_digits=24, decimal_places=8, default=Decimal("0"))
    cota = models.DecimalField(max_digits=24, decimal_places=8, default=Decimal("0"))


    class Meta:
        verbose_name = "Item MEC"
        verbose_name_plural = "Itens MEC"
        ordering = ["fundo", "data_posicao"]
        constraints = [
            models.UniqueConstraint(fields=["fundo", "data_posicao"], name="uq_mecitem_fundo_data"),
            models.CheckConstraint(
                check=models.Q(aplicacao__gte=0) & models.Q(resgate__gte=0) & models.Q(estorno__gte=0),
                name="ck_mecitem_valores_nao_negativos",
            ),
            models.CheckConstraint(
                check=models.Q(pl__gte=0) & models.Q(qtd_cotas__gte=0) & models.Q(cota__gte=0),
                name="ck_mecitem_posicoes_nao_negativas",
            ),
        ]
        indexes = [
            models.Index(fields=["data_posicao"], name="idx_mecitem_data"),
            models.Index(fields=["fundo", "data_posicao"], name="idx_mecitem_fundo_data"),
        ]

    def __str__(self):
        return f"[{self.data_posicao:%d/%m/%Y}] {self.fundo.nome} | PL R$ {self.pl} | Cotas {self.qtd_cotas} | Cota {self.cota}"
