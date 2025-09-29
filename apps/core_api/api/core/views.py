"""
Core API Views
"""
from rest_framework import generics, permissions

from apps.core_api.models import Feedback
from apps.core_api.serializers import FeedbackSerializer

__all__ = [
    'FeedbackCreateView'
]


class FeedbackCreateView(generics.CreateAPIView):
    """Create feedback"""
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.AllowAny]
