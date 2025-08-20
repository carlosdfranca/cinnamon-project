from django import forms
from django.core.exceptions import ValidationError
from usuarios.models import Usuario, Membership

class CompanyUserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=Membership.Role.choices,
        label="Papel na empresa",
    )
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "email"]

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("As senhas não coincidem.")
        return cleaned


class CompanyUserUpdateForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=Membership.Role.choices,
        label="Papel na empresa",
    )
    # Campos de redefinição de senha (opcionais)
    password1 = forms.CharField(label="Nova senha", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirmar nova senha", widget=forms.PasswordInput, required=False)

    class Meta:
        model = Usuario
        fields = ["first_name", "email"]

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if (p1 or p2) and p1 != p2:
            raise ValidationError("As senhas não coincidem.")
        return cleaned
