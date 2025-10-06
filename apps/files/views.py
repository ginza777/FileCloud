"""
Files app views - Only contains non-API related functionality
Note: All API endpoints have been moved to core_api.api.web.views
"""
from django.shortcuts import render

def login_view(request):
    """Login page view - moved to core_api.api.web.views"""
    return render(request, 'login.html')

def index(request):
    """Main page view - moved to core_api.api.web.views"""
    return render(request, 'index.html')