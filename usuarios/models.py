from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    nome_empresa = models.CharField(max_length=255, verbose_name='Nome da Empresa', null=True, blank=True, default=None)
    cnpj = models.CharField(max_length=18, verbose_name='CNPJ', null=True, blank=True, default=None)

    def __str__(self):
        return f"{self.nome_empresa} - ({self.first_name} {self.last_name})"