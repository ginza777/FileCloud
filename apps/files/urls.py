from django.urls import path
from . import views

app_name = 'files'

urlpatterns = [
    # Pages
    path('login/', views.login_view, name='login'),
    
    # API endpoints
    path('api/search/', views.search_documents, name='search_documents'),
    path('api/recent/', views.recent_documents, name='recent_documents'),
    path('api/top-downloads/', views.top_downloads, name='top_downloads'),
    path('api/<int:product_id>/view/', views.increment_view_count, name='increment_view_count'),
    path('api/<int:product_id>/download/', views.increment_download_count, name='increment_download_count'),
    path('api/<uuid:document_id>/images/', views.document_images, name='document_images'),
]