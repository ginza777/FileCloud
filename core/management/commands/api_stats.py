"""
Management command to view API performance statistics
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
import json

class Command(BaseCommand):
    help = 'Display API performance statistics'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== API Performance Statistics ===\n'))
        
        # Get all API stats from cache
        api_stats = {}
        for key in cache._cache.keys():
            if key.startswith('api_stats:'):
                path = key.replace('api_stats:', '')
                stats = cache.get(key)
                if stats:
                    api_stats[path] = stats
        
        if not api_stats:
            self.stdout.write(self.style.WARNING('No API statistics found in cache'))
            return
        
        # Sort by average response time (slowest first)
        sorted_stats = sorted(api_stats.items(), 
                            key=lambda x: x[1]['avg_time'], 
                            reverse=True)
        
        self.stdout.write(f"{'API Endpoint':<40} {'Count':<8} {'Avg(s)':<8} {'Max(s)':<8} {'Min(s)':<8} {'Errors':<8}")
        self.stdout.write('-' * 90)
        
        for path, stats in sorted_stats:
            self.stdout.write(
                f"{path:<40} "
                f"{stats['count']:<8} "
                f"{stats['avg_time']:.3f}   "
                f"{stats['max_time']:.3f}   "
                f"{stats['min_time']:.3f}   "
                f"{stats['error_count']:<8}"
            )
        
        # Show slowest APIs
        self.stdout.write(self.style.WARNING('\n=== Slowest APIs (>1s average) ==='))
        slow_apis = [item for item in sorted_stats if item[1]['avg_time'] > 1.0]
        
        if slow_apis:
            for path, stats in slow_apis:
                self.stdout.write(
                    self.style.ERROR(
                        f"{path}: {stats['avg_time']:.3f}s average "
                        f"({stats['count']} requests)"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS('No slow APIs found!'))
        
        # Show error-prone APIs
        self.stdout.write(self.style.WARNING('\n=== APIs with Errors ==='))
        error_apis = [item for item in sorted_stats if item[1]['error_count'] > 0]
        
        if error_apis:
            for path, stats in error_apis:
                error_rate = (stats['error_count'] / stats['count']) * 100
                self.stdout.write(
                    self.style.ERROR(
                        f"{path}: {stats['error_count']} errors "
                        f"({error_rate:.1f}% error rate)"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS('No APIs with errors found!'))
