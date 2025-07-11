from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    cpf = models.CharField(max_length=11, unique=True, verbose_name='CPF')

    def __str__(self):
        return self.username