"""
User API URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.UserListCreateView.as_view(), name='user-list-create'),
    path('<int:id>/', views.UserDetailView.as_view(), name='user-detail'),
    path('stats/', views.UserStatsView.as_view(), name='user-stats'),
]
