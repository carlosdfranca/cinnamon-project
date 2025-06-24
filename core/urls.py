from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='uploads/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    # path('', views.upload_files, name='upload_files'),
    # path('process/', views.process_files, name='process_files'),
    # path('download/', views.download_file, name='download_file'),
]