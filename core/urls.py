from django.urls import path, include
from django.contrib.auth import views as auth_views
from .views import *
from usuarios.views import trocar_empresa_ativa

urlpatterns = [
    # User Views
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('perfil/', editar_perfil, name='editar_perfil'),
    path('trocar-empresa/', trocar_empresa_ativa, name='trocar_empresa_ativa'),

    path("", include("usuarios.urls")),

    # Demonstração Financeira
    path('', demonstracao_financeira, name='demonstracao_financeira'),
    path("importar-balancete/", importar_balancete_view, name="importar_balancete"),
    path("importar-mec/", importar_mec_view, name="importar_mec"),
    path('dre-resultado/<int:fundo_id>/<int:ano>/', df_resultado, name='dre_resultado'),
    path('dre-exportar-xlsx/<int:fundo_id>/<int:ano>/', exportar_dfs_excel, name='exportar_dre_excel'),


    # Fundos
    path('fundos/', listar_fundos, name='listar_fundos'),
    path('fundos/adicionar/', adicionar_fundo, name='adicionar_fundo'),
    path('fundos/<int:fundo_id>/editar/', editar_fundo, name='editar_fundo'),
    path('fundos/<int:fundo_id>/excluir/', excluir_fundo, name='excluir_fundo'),
]   