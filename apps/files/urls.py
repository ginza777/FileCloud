from django.urls import path
from . import views

app_name = 'files'

urlpatterns = [
    # Pages
    path('login/', views.login_view, name='login'),
    
    # API endpoints
    path('search/', views.search_documents, name='search_documents'),
    path('recent/', views.recent_documents, name='recent_documents'),
    path('top-downloads/', views.top_downloads, name='top_downloads'),
    path('<int:product_id>/view/', views.increment_view_count, name='increment_view_count'),
    path('<int:product_id>/download/', views.increment_download_count, name='increment_download_count'),
    path('<uuid:document_id>/images/', views.document_images, name='document_images'),
]