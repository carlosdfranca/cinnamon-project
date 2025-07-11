from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    # User Views
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('perfil/', editar_perfil, name='editar_perfil'),

    # Index
    path('', index, name='index'),

    # Functions
    path('importar_planilha/', importar_planilha, name='importar_planilha'),
    # path('process/', views.process_files, name='process_files'),
    # path('download/', views.download_file, name='download_file'),
]