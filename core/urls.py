from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    # User Views
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('perfil/', editar_perfil, name='editar_perfil'),

    # Demonstração Financeira
    path('', demonstracao_financeira, name='demonstracao_financeira'),
    path('download-modelo-balancete/', download_modelo_balancete, name='download_modelo_balancete'),
    path('dre-resultado/<int:fundo_id>/<int:ano>/', dre_resultado, name='dre_resultado'),

    # Fundos
    path('fundos/', listar_fundos, name='listar_fundos'),
    path('fundos/adicionar/', adicionar_fundo, name='adicionar_fundo'),
    path('fundos/<int:fundo_id>/editar/', editar_fundo, name='editar_fundo'),
    path('fundos/<int:fundo_id>/excluir/', excluir_fundo, name='excluir_fundo'),

]   