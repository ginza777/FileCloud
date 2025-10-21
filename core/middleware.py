"""
Custom middleware for video caching
"""
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class VideoCacheMiddleware(MiddlewareMixin):
    """
    Middleware to add cache headers for video files
    """
    
    def process_response(self, request, response):
        # Check if the request is for a video file
        if request.path.endswith(('.mp4', '.webm', '.avi', '.mov', '.mkv')):
            # Add cache headers for video files
            response['Cache-Control'] = 'max-age=31536000, public, immutable'  # 1 year
            response['Expires'] = 'Thu, 31 Dec 2025 23:59:59 GMT'
            response['ETag'] = f'"{request.path}"'
            
        # Also cache static images and other media
        elif request.path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
            response['Cache-Control'] = 'max-age=2592000, public'  # 30 days
            
        return response
