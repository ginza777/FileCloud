"""
Web API URLs for FileFinder
"""
from django.urls import path
from . import views

urlpatterns = [
    # API endpoints (must come before the catch-all root path)
    path('search/', views.search_documents, name='search_documents'),
    path('recent/', views.recent_documents, name='recent_documents'),
    path('top-downloads/', views.top_downloads, name='top_downloads'),
    path('<int:product_id>/view/', views.increment_view_count, name='increment_view_count'),
    path('<int:product_id>/download/', views.increment_download_count, name='increment_download_count'),
    path('<uuid:document_id>/images/', views.document_images, name='document_images'),
    
    # Pages (must come after API endpoints)
    path('login/', views.login_view, name='login'),
    path('', views.index_view, name='index'),
]
