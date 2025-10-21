"""
Custom Middleware for FileFinder
Includes API monitoring and performance tracking
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

logger = logging.getLogger(__name__)

class APIMonitoringMiddleware(MiddlewareMixin):
    """
    Middleware to monitor API response times and log slow requests
    """
    
    def process_request(self, request):
        """Store request start time"""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log API response times"""
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            
            # Log slow requests (>1 second)
            if duration > 1.0:
                logger.warning(
                    f"SLOW API: {request.method} {request.path} - "
                    f"{duration:.3f}s - Status: {response.status_code}"
                )
            
            # Log very slow requests (>3 seconds)
            if duration > 3.0:
                logger.error(
                    f"VERY SLOW API: {request.method} {request.path} - "
                    f"{duration:.3f}s - Status: {response.status_code}"
                )
            
            # Cache API stats
            if request.path.startswith('/api/'):
                self._update_api_stats(request.path, duration, response.status_code)
        
        return response
    
    def _update_api_stats(self, path, duration, status_code):
        """Update API statistics in cache"""
        try:
            stats_key = f"api_stats:{path}"
            stats = cache.get(stats_key, {
                'count': 0,
                'total_time': 0,
                'avg_time': 0,
                'max_time': 0,
                'min_time': float('inf'),
                'error_count': 0
            })
            
            stats['count'] += 1
            stats['total_time'] += duration
            stats['avg_time'] = stats['total_time'] / stats['count']
            stats['max_time'] = max(stats['max_time'], duration)
            stats['min_time'] = min(stats['min_time'], duration)
            
            if status_code >= 400:
                stats['error_count'] += 1
            
            cache.set(stats_key, stats, 3600)  # Cache for 1 hour
            
        except Exception as e:
            logger.error(f"Error updating API stats: {e}")


class CacheHeadersMiddleware(MiddlewareMixin):
    """
    Middleware to add appropriate cache headers
    """
    
    def process_response(self, request, response):
        """Add cache headers based on content type"""
        if request.path.startswith('/static/'):
            # Static files - long cache
            response['Cache-Control'] = 'public, max-age=31536000'  # 1 year
        elif request.path.startswith('/api/'):
            # API responses - short cache
            response['Cache-Control'] = 'private, max-age=300'  # 5 minutes
        elif request.path == '/':
            # Home page - medium cache
            response['Cache-Control'] = 'public, max-age=300'  # 5 minutes
        
        return response