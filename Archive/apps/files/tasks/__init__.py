# apps/files/tasks/__init__.py (To'g'rilangan versiya)

# 1. Asosiy pipeline (document_processing.py dan)
from .document_processing import (
    process_document_pipeline,
    log_document_error,
)

# 2. Rasm generatsiya qilish (image_processing.py dan)
from .image_processing import (
    generate_document_previews,
)

# 3. Parsing (parsing_tasks.py dan)
from .parsing_tasks import (
    soft_uz_process_documents,
    arxiv_uz_parse,
)

# 4. Tozalash (cleanup_tasks.py dan)
# Eslatma: Siz yuborgan fayllarga asoslanib, bu task'lar mavjud deb hisoblaymiz.
from .cleanup_tasks import (
    cleanup_temp_files_task,
)

# 5. Telegram (telegram_tasks.py dan)
from .telegram_tasks import (
    wait_for_telegram_rate_limit,
)

# Barcha task'larni Celery'ga ko'rsatish
__all__ = [
    # document_processing
    'process_document_pipeline',
    'log_document_error',

    # image_processing
    'generate_document_previews',

    # parsing_tasks
    'soft_uz_process_documents',
    'arxiv_uz_parse',

    # cleanup_tasks
    'cleanup_temp_files_task',


    # telegram_tasks
    'wait_for_telegram_rate_limit',

    # utility_tasks.py va backup_tasks.py dan xato importlar olib tashlandi
]