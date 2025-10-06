"""
Logging Utility Module
======================

Bu modul loyiha bo'ylab logging uchun utility funksiyalarini o'z ichiga oladi.
"""

import logging
import functools
import time
from typing import Any, Callable, Optional


def get_logger(name: str) -> logging.Logger:
    """
    Logger obyektini olish.
    
    Args:
        name: Logger nomi (odatda __name__)
    
    Returns:
        Logger obyekti
    """
    return logging.getLogger(name)


def log_function_call(logger: Optional[logging.Logger] = None):
    """
    Funksiya chaqiruvlarini log qilish uchun decorator.
    
    Args:
        logger: Logger obyekti (agar None bo'lsa, funksiya nomi bo'yicha logger yaratiladi)
    
    Returns:
        Decorator funksiya
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            # Funksiya boshlanishi
            func_logger.info(f"Starting {func.__name__} with args={args}, kwargs={kwargs}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # Muvaffaqiyatli tugash
                func_logger.info(f"Completed {func.__name__} in {execution_time:.2f}s")
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Xatolik bilan tugash
                func_logger.error(f"Failed {func.__name__} in {execution_time:.2f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator


def log_database_query(logger: Optional[logging.Logger] = None):
    """
    Database query'larni log qilish uchun decorator.
    
    Args:
        logger: Logger obyekti
    
    Returns:
        Decorator funksiya
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            func_logger.debug(f"Database query: {func.__name__}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                func_logger.debug(f"Query completed in {execution_time:.3f}s")
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(f"Query failed in {execution_time:.3f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator


def log_api_request(logger: Optional[logging.Logger] = None):
    """
    API request'larni log qilish uchun decorator.
    
    Args:
        logger: Logger obyekti
    
    Returns:
        Decorator funksiya
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            # Request ma'lumotlari
            request = args[0] if args else None
            if request and hasattr(request, 'method'):
                func_logger.info(f"API {request.method} {func.__name__} - User: {getattr(request.user, 'username', 'Anonymous')}")
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                func_logger.info(f"API {func.__name__} completed in {execution_time:.2f}s")
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(f"API {func.__name__} failed in {execution_time:.2f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator


def log_celery_task(logger: Optional[logging.Logger] = None):
    """
    Celery task'larni log qilish uchun decorator.
    
    Args:
        logger: Logger obyekti
    
    Returns:
        Decorator funksiya
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            func_logger.info(f"Starting Celery task: {func.__name__}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                func_logger.info(f"Celery task {func.__name__} completed in {execution_time:.2f}s")
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(f"Celery task {func.__name__} failed in {execution_time:.2f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator


class LoggerMixin:
    """
    Logger mixin class - barcha class'lar uchun logger qo'shish.
    """
    
    @property
    def logger(self) -> logging.Logger:
        """Logger obyektini qaytaradi."""
        return get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")


def log_performance(logger: Optional[logging.Logger] = None, threshold: float = 1.0):
    """
    Performance log qilish uchun decorator.
    
    Args:
        logger: Logger obyekti
        threshold: Log qilish uchun minimal vaqt (sekund)
    
    Returns:
        Decorator funksiya
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            if execution_time >= threshold:
                func_logger.warning(f"Slow operation: {func.__name__} took {execution_time:.2f}s")
            else:
                func_logger.debug(f"Operation {func.__name__} took {execution_time:.2f}s")
            
            return result
        
        return wrapper
    return decorator
