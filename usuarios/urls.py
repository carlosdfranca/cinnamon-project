# usuarios/urls.py
from django.urls import path
from usuarios.views_gerenciar import (
    gerenciar_usuarios,
    empresa_usuario_adicionar,
    empresa_usuario_editar,
    empresa_usuario_excluir,
)
from usuarios.views_selecao import selecionar_empresa

urlpatterns = [
    path("empresa/usuarios/", gerenciar_usuarios, name="gerenciar_usuarios"),
    path("empresa/usuarios/adicionar/", empresa_usuario_adicionar, name="empresa_usuario_adicionar"),
    path("empresa/usuarios/<int:membership_id>/editar/", empresa_usuario_editar, name="empresa_usuario_editar"),
    path("empresa/usuarios/<int:membership_id>/excluir/", empresa_usuario_excluir, name="empresa_usuario_excluir"),

    # nova página neutra para seleção
    path("selecionar-empresa/", selecionar_empresa, name="selecionar_empresa"),
]
