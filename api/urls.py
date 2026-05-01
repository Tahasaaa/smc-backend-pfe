from django.urls import path
from .views import (
    login,
    verify_code,
    logout,
    get_all_users,
    get_user,
    delete_user,
    get_logs,
    ChangePasswordView
    
)

urlpatterns = [
    path('auth/login/', login, name='login'),
    path('auth/verify-code/', verify_code, name='verify_code'),
    path('auth/logout/', logout, name='logout'),

    path('users/', get_all_users, name='get_all_users'),
    path('users/<int:user_id>/', get_user, name='get_user'),
    path('users/<int:user_id>/delete/', delete_user, name='delete_user'),

    path('logs/', get_logs, name='get_logs'),
    
    path("auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
]