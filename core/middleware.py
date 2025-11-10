"""
Custom Middleware for FileFinder
Includes API monitoring and performance tracking
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from redis.exceptions import RedisError

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
        """Update API statistics in cache with proper error handling"""
        try:
            stats_key = f"api_stats:{path}"
            stats = cache.get(stats_key) or {
                'count': 0,
                'total_time': 0,
                'avg_time': 0,
                'status_codes': {},
                'slow_requests': 0
            }

            # Update stats
            stats['count'] += 1
            stats['total_time'] += duration
            stats['avg_time'] = stats['total_time'] / stats['count']
            stats['status_codes'][str(status_code)] = stats['status_codes'].get(str(status_code), 0) + 1

            if duration > 1.0:
                stats['slow_requests'] += 1

            # Cache for 1 hour
            cache.set(stats_key, stats, timeout=3600)

        except (RedisError, ConnectionError) as e:
            logger.warning(f"Redis cache error in API stats: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error updating API stats: {str(e)}")


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