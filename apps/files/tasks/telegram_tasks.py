"""
Telegram Tasks
==============

Bu modul Telegram bilan bog'liq task'larni o'z ichiga oladi:
- Rate limiting
- Message sending
- File uploads

Bu task'lar Telegram API bilan ishlash va rate limiting'ni boshqarish uchun ishlatiladi.
"""

import logging
import time

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Logger
logger = logging.getLogger(__name__)


def wait_for_telegram_rate_limit():
    """
    Redis yordamida markazlashtirilgan (distributed) rate limiting uchun kutish funksiyasi.
    Barcha worker'lar uchun umumiy bo'lgan qulf yordamida bir vaqtda faqat bitta
    worker Telegramga so'rov yuborishini ta'minlaydi.
    
    Bu funksiya:
    - Redis orqali distributed lock yaratadi
    - Rate limiting qoidalarini boshqaradi
    - Barcha worker'lar uchun umumiy bo'lgan qulf mexanizmini ta'minlaydi
    """
    if not REDIS_AVAILABLE:
        logger.warning("Redis topilmadi, rate limit uchun 5 soniya kutamiz.")
        time.sleep(5)
        return
    
    try:
        # Redis connection
        r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
        
        # Telegram rate limit key
        lock_key = "telegram_rate_limit_lock"
        last_send_key = "telegram_last_send_time"
        
        # 1 soniya kutish intervali
        min_interval = 1.0
        
        while True:
            # Lock olishga harakat qilamiz
            if r.set(lock_key, "locked", nx=True, ex=30):  # 30 soniya timeout
                try:
                    # Oxirgi yuborish vaqtini olamiz
                    last_send = r.get(last_send_key)
                    current_time = time.time()
                    
                    if last_send:
                        time_since_last = current_time - float(last_send)
                        if time_since_last < min_interval:
                            wait_time = min_interval - time_since_last
                            logger.info(f"Rate limit: {wait_time:.2f} soniya kutamiz")
                            time.sleep(wait_time)
                    
                    # Yuborish vaqtini yangilaymiz
                    r.set(last_send_key, str(current_time))
                    logger.info("Rate limit lock olindi, Telegram yuborish mumkin")
                    break
                    
                finally:
                    # Lock ni ochamiz
                    r.delete(lock_key)
            else:
                # Boshqa worker ishlayapti, kichik kutamiz
                time.sleep(0.1)
                
    except Exception as e:
        logger.warning(f"Redis rate limiting xatosi: {e}, 5 soniya kutamiz")
        time.sleep(5)
