"""
Files App Tasks Package
========================

Bu paket files app uchun barcha Celery task'larini o'z ichiga oladi.
Task'lar kategoriyalar bo'yicha bo'lingan:

- document_processing: Hujjatlar bilan ishlash task'lari
- telegram_tasks: Telegram bilan bog'liq task'lar
- cleanup_tasks: Tizimni tozalash task'lari
- parsing_tasks: Parsing task'lari
- utility_tasks: Yordamchi task'lar

Barcha task'lar Celery orqali ishlaydi va background'da bajariladi.
"""

# Import all tasks from submodules
from .document_processing import (
    generate_document_images_task,
    process_document_pipeline,
    log_document_error,
    add_watermark_to_image,
)

from .telegram_tasks import (
    wait_for_telegram_rate_limit,
)

from .cleanup_tasks import (
    cleanup_temp_files_task,
    cleanup_files_task,
)

from .parsing_tasks import (
    soft_uz_process_documents,
    soft_uz_parse,
    arxiv_uz_parse,
)

from .utility_tasks import (
    make_retry_session,
)

# Export all tasks for easy importing
__all__ = [
    # Document Processing Tasks
    'generate_document_images_task',
    'process_document_pipeline',
    'log_document_error',
    'add_watermark_to_image',
    
    # Telegram Tasks
    'wait_for_telegram_rate_limit',
    
    # Cleanup Tasks
    'cleanup_temp_files_task',
    'cleanup_files_task',
    
    # Parsing Tasks
    'soft_uz_process_documents',
    'soft_uz_parse',
    'arxiv_uz_parse',
    
    # Utility Tasks
    'make_retry_session',
]
