"""
Cleanup Tasks
=============

Bu modul tizimni tozalash bilan bog'liq task'larni o'z ichiga oladi:
- Temporary files cleanup
- File system cleanup
- Disk space management

Bu task'lar tizimni toza saqlash va disk to'lib qolishini oldini olish uchun ishlatiladi.
"""

import logging
import os
import shutil
from celery import shared_task
from django.conf import settings
from django.db import transaction

from ..models import Document, DocumentError

# Logger
logger = logging.getLogger(__name__)


@shared_task(name="apps.files.tasks.cleanup_temp_files_task")
def cleanup_temp_files_task():
    """
    Temporary fayllarni tozalaydi va disk to'lib qolishini oldini oladi.
    
    Bu task:
    - Temporary papkalardagi eski fayllarni o'chiradi
    - Disk hajmini tekshiradi
    - Disk to'lib qolishini oldini oladi
    
    Returns:
        str: Tozalash natijasi xabari
    """
    logger.info("========= TEMPORARY FAYLLARNI TOZALASH BOSHLANDI =========")
    
    temp_dirs = ['/tmp/downloads', '/tmp', '/app/media/downloads']
    total_freed = 0
    total_files = 0
    
    for temp_dir in temp_dirs:
        if not os.path.exists(temp_dir):
            continue
            
        logger.info(f"Tozalash: {temp_dir}")
        
        # Fayllarni yoshi bo'yicha tekshirish (24 soatdan eski)
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    # Fayl yoshini tekshirish
                    file_age_hours = (os.path.getctime(file_path) - os.path.getctime('/')) / 3600
                    
                    if file_age_hours > 24:  # 24 soatdan eski
                        file_size = os.path.getsize(file_path)
                        total_freed += file_size
                        total_files += 1
                        
                        os.remove(file_path)
                        logger.info(f"✅ O'chirildi: {file_path} ({file_size} bytes)")
                        
                except Exception as e:
                    logger.warning(f"❌ Xatolik: {file_path} - {e}")
    
    # Disk hajmini ko'rsatish
    try:
        disk_usage = shutil.disk_usage('/tmp')
        free_gb = disk_usage.free / (1024**3)
        
        if free_gb < 1.0:  # 1 GB dan kam bo'sh joy
            logger.warning("⚠️  DIQQAT: Disk to'lib qolmoqda!")
        elif free_gb < 2.0:  # 2 GB dan kam bo'sh joy
            logger.warning("⚠️  Ogoh: Disk to'lib qolish arafasida")
        else:
            logger.info("✅ Disk holati yaxshi")
            
    except Exception as e:
        logger.error(f"❌ Disk hajmini o'qishda xatolik: {e}")
    
    logger.info(f"✅ Tozalash yakunlandi: {total_files} ta fayl, {total_freed / (1024**2):.1f} MB bo'shatildi")
    return f"Cleaned {total_files} files, freed {total_freed / (1024**2):.1f} MB"


@shared_task(name="apps.files.tasks.cleanup_files_task")
def cleanup_files_task():
    """
    Fayl tizimini skanerlab, qolib ketgan fayllarni va nomuvofiq holatdagi
    hujjatlarni tozalaydi.
    
    Bu task:
    - Downloads papkasidagi fayllarni skanerlaydi
    - Hujjat holatlarini tekshiradi
    - Ideal holatdagi hujjatlarni yakunlaydi
    - Pending holatdagi hujjatlarni qayta tiklaydi
    
    Returns:
        str: Tozalash natijasi xabari
    """
    logger.info("========= FAYL TIZIMINI REJALI TOZALASH BOSHLANDI =========")

    # Check both 'downloads' and 'download' directories
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
    download_dir = os.path.join(settings.MEDIA_ROOT, 'download')

    directories_to_scan = []
    if os.path.exists(downloads_dir):
        directories_to_scan.append(downloads_dir)
        logger.info(f"📁 'downloads' papkasi topildi: {downloads_dir}")
    else:
        logger.warning(f"⚠️  'downloads' papkasi topilmadi: {downloads_dir}")

    if os.path.exists(download_dir):
        directories_to_scan.append(download_dir)
        logger.info(f"📁 'download' papkasi topildi: {download_dir}")
    else:
        logger.warning(f"⚠️  'download' papkasi topilmadi: {download_dir}")

    if not directories_to_scan:
        logger.warning("❌ Hech qanday tozalash papkasi topilmadi!")
        return

    deleted_files_count = 0
    updated_docs_count = 0
    reset_docs_count = 0

    # Process each directory
    for current_dir in directories_to_scan:
        logger.info(f"🔍 Papka skanerlanyapti: {current_dir}")

        for filename in os.listdir(current_dir):
            file_path = os.path.join(current_dir, filename)
            if not os.path.isfile(file_path): continue

            doc_id = os.path.splitext(filename)[0]

            try:
                with transaction.atomic():
                    doc = Document.objects.select_for_update().get(id=doc_id)

                    # Agar pipeline ishlayotgan bo'lsa, bu faylga tegmaymiz
                    if doc.pipeline_running:
                        logger.info(f"🔄 FAYL HIMOYALANGAN (pipeline ishlayapti): {filename}")
                        continue

                    # Debug: hujjat holatini ko'rsatish
                    has_parsed_content = (
                            hasattr(doc, 'product') and
                            doc.product is not None and
                            doc.product.parsed_content is not None and
                            doc.product.parsed_content.strip() != ''
                    )
                    logger.info(
                        f"🔍 HUJJAT HOLATI: {filename} - parse:{doc.parse_status}, index:{doc.index_status}, telegram_id:{bool(doc.telegram_file_id)}, parsed_content:{has_parsed_content}, pipeline:{doc.pipeline_running}")

                    # Ideal holatni tekshirish - faqat telegram_file_id va parsed_content ikkalasi ham bo'sh bo'lmasligi kerak
                    is_ideal_state = (
                            doc.telegram_file_id is not None and doc.telegram_file_id.strip() != '' and
                            has_parsed_content
                    )

                    if is_ideal_state:
                        # Hujjat ideal holatda, statuslarni to'liq 'completed' qilamiz
                        doc.download_status = 'completed'
                        doc.telegram_status = 'completed'
                        doc.delete_status = 'completed'
                        doc.completed = True
                        doc.save()
                        logger.info(f"✅ HUJJAT YAKUNLANDI: {doc.id} holati 'completed' ga o'rnatildi.")
                        updated_docs_count += 1

                        # Ideal holatda faylni o'chiramiz
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                logger.info(f"🗑️  FAYL O'CHIRILDI (ideal): {filename}")
                                deleted_files_count += 1
                            else:
                                logger.warning(f"⚠️  FAYL MAVJUD EMAS: {filename}")
                        except PermissionError as e:
                            error_msg = f"Fayl o'chirishda ruxsat xatosi: {filename} - {e}"
                            logger.error(f"❌ RUHSAT XATOSI: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)
                        except OSError as e:
                            error_msg = f"Fayl o'chirishda tizim xatosi: {filename} - {e}"
                            logger.error(f"❌ FAYL O'CHIRISH XATOSI: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)
                        except Exception as e:
                            error_msg = f"Fayl o'chirishda kutilmagan xato: {filename} - {e}"
                            logger.error(f"❌ KUTILMAGAN XATO: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)
                    else:
                        # Hujjat ideal holatda emas, statuslarni 'pending' qilamiz
                        doc.download_status = 'pending'
                        doc.parse_status = 'pending'
                        doc.index_status = 'pending'
                        doc.telegram_status = 'pending'
                        doc.delete_status = 'pending'
                        doc.completed = False
                        doc.save()
                        logger.warning(f"⚠️  HUJJAT QAYTA TIKLANDI: {doc.id} holati 'pending' ga o'rnatildi.")
                        reset_docs_count += 1

                        # Pending holatda ham faylni o'chiramiz (pipeline ishlamayapti)
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                logger.info(f"🗑️  FAYL O'CHIRILDI (pending): {filename}")
                                deleted_files_count += 1
                            else:
                                logger.warning(f"⚠️  FAYL MAVJUD EMAS: {filename}")
                        except PermissionError as e:
                            error_msg = f"Fayl o'chirishda ruxsat xatosi: {filename} - {e}"
                            logger.error(f"❌ RUHSAT XATOSI: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)
                        except OSError as e:
                            error_msg = f"Fayl o'chirishda tizim xatosi: {filename} - {e}"
                            logger.error(f"❌ FAYL O'CHIRISH XATOSI: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)
                        except Exception as e:
                            error_msg = f"Fayl o'chirishda kutilmagan xato: {filename} - {e}"
                            logger.error(f"❌ KUTILMAGAN XATO: {error_msg}")
                            log_document_error(doc, 'other', error_msg, 1)

            except Document.DoesNotExist:
                logger.warning(f"👻 YETIM FAYL (bazada yozuvi yo'q): {filename}. O'chirilmoqda...")
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"🗑️  YETIM FAYL O'CHIRILDI: {filename}")
                        deleted_files_count += 1
                    else:
                        logger.warning(f"⚠️  YETIM FAYL MAVJUD EMAS: {filename}")
                except PermissionError:
                    logger.error(f"❌ YETIM FAYL RUHSAT XATOSI: {filename} o'chirishga ruxsat yo'q")
                except OSError as e:
                    logger.error(f"❌ YETIM FAYL O'CHIRISH XATOSI: {filename} - {e}")
                except Exception as e:
                    logger.error(f"❌ YETIM FAYL KUTILMAGAN XATO: {filename} - {e}")
            except Exception as e:
                error_msg = f"Tozalashda kutilmagan xato: {filename} - {e}"
                logger.error(f"❌ {error_msg}")
                # Try to log to DocumentError if we can get the document
                try:
                    doc = Document.objects.get(id=doc_id)
                    log_document_error(doc, 'other', error_msg, 1)
                except Document.DoesNotExist:
                    # Document doesn't exist, can't log to DocumentError
                    pass

    logger.info("--- TOZALASH STATISTIKASI ---")
    logger.info(f"O'chirilgan fayllar: {deleted_files_count}")
    logger.info(f"Yakunlangan hujjatlar: {updated_docs_count}")
    logger.info(f"'Pending' qilingan hujjatlar: {reset_docs_count}")
    logger.info("========= FAYL TIZIMINI TOZALASH TUGADI =========")


def log_document_error(document, error_type, error_message, celery_attempt=1):
    """
    Tushunarli va chiroyli shaklda xatolik yozuvini DocumentError modeliga qo'shadi.
    
    Args:
        document: Document obyekti
        error_type: Xatolik turi (str)
        error_message: Xatolik xabari (str yoki Exception)
        celery_attempt: Celery urinish raqami (int)
    """
    try:
        # Xatolik matnini qisqartirish va formatlash
        if isinstance(error_message, Exception):
            error_text = f"{type(error_message).__name__}: {str(error_message)}"
        else:
            error_text = str(error_message)

        DocumentError.objects.create(
            document=document,
            error_type=error_type,
            error_message=error_text,
            celery_attempt=celery_attempt
        )
        logger.info(
            f"[ERROR LOGGED] DocID {document.id} - Type: {error_type} (Attempt: {celery_attempt}): {error_text}")
    except Exception as e:
        logger.error(f"[ERROR LOGGING FAILED] DocID {document.id} - {e}")
