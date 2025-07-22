from django import forms
from df.models import Fundo

class FundoForm(forms.ModelForm):
    class Meta:
        model = Fundo
        fields = ['nome', 'cnpj']