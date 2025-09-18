from rest_framework import permissions
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the object.
        return obj.user == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to edit objects.
    """
    def has_permission(self, request, view):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to admin users.
        return request.user and request.user.is_staff


class IsBotAdmin(permissions.BasePermission):
    """
    Custom permission to only allow bot admin users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is Django admin or bot admin
        return request.user.is_staff or getattr(request.user, 'is_admin', False)


class IsTelegramUser(permissions.BasePermission):
    """
    Custom permission to only allow Telegram users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has telegram_id (is a Telegram user)
        return hasattr(request.user, 'telegram_id') and request.user.telegram_id is not None


class ReadOnlyOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow read-only access to all users,
    but write access only to admin users.
    """
    def has_permission(self, request, view):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to admin users.
        return request.user and request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow owners or admin users to access objects.
    """
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user and request.user.is_staff:
            return True

        # Owners have full access
        if hasattr(obj, 'user') and obj.user == request.user:
            return True

        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        return False


class IsActiveUser(permissions.BasePermission):
    """
    Custom permission to only allow active users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is active and not blocked
        if hasattr(request.user, 'is_blocked'):
            return not request.user.is_blocked
        
        return request.user.is_active


class IsBotAdminOrOwner(permissions.BasePermission):
    """
    Custom permission to allow bot admin users or object owners.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Bot admin users have full access
        if getattr(request.user, 'is_admin', False):
            return True
        
        # Django admin users have full access
        if request.user.is_staff:
            return True
        
        return True

    def has_object_permission(self, request, view, obj):
        # Bot admin users have full access
        if getattr(request.user, 'is_admin', False):
            return True
        
        # Django admin users have full access
        if request.user.is_staff:
            return True

        # Owners have full access
        if hasattr(obj, 'user') and obj.user == request.user:
            return True

        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        return False


# Default authentication classes
DEFAULT_AUTHENTICATION_CLASSES = [
    TokenAuthentication,
    SessionAuthentication,
]

# Default permission classes
DEFAULT_PERMISSION_CLASSES = [
    IsAuthenticated,
]

# Bot API permission classes
BOT_API_PERMISSION_CLASSES = [
    IsBotAdminOrOwner,
]

# Multiparser API permission classes
MULTIPARSER_API_PERMISSION_CLASSES = [
    ReadOnlyOrAdmin,
]

# Dashboard API permission classes
DASHBOARD_API_PERMISSION_CLASSES = [
    IsAdminUser,
]
