from django.db import models
from usuarios.models import Usuario

class Fundo(models.Model):
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=20)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Fundo"
        verbose_name_plural = "Fundos"
        ordering = ["usuario", "nome"]

    def __str__(self):
        return f"{self.nome[:25]} ({self.usuario.first_name} {self.usuario.last_name})"
    

class MapeamentoContas(models.Model):
    TIPO_CHOICES = [
        (1, 'Ativo'),
        (2, 'Passivo'),
        (3, 'Patrimônio Líquido'),
        (4, 'Resultado'),
    ]

    conta = models.CharField(max_length=30, unique=True)
    grupo_df = models.CharField(max_length=255)
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    descricao = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Mapeamento de CC"
        verbose_name_plural = "Mapeamentos de CC"
        ordering = ["tipo", "grupo_df", "conta"]

    def __str__(self):
        return f"{self.conta} - {self.grupo_df}"
    

class BalanceteItem(models.Model):
    fundo = models.ForeignKey(Fundo, on_delete=models.SET_NULL, null=True, blank=True)
    ano = models.IntegerField()
    conta_corrente = models.ForeignKey('MapeamentoContas', on_delete=models.SET_NULL, null=True, blank=True)
    saldo_final = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    data_importacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Item do Balancete'
        verbose_name_plural = 'Itens do Balancete'
        ordering = ['conta_corrente']

    def __str__(self):
        return f"[{self.ano}] {self.conta_corrente} | Saldo: R$ {self.saldo_final:,.2f}"
