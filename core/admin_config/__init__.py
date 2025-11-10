from django.contrib.admin import AdminSite

class CustomAdminSite(AdminSite):
    site_header = "FileFinder Administration"
    site_title = "FileFinder Admin"
    index_title = "FileFinder Dashboard"
