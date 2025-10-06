"""
Files App Utility Functions
==========================

Bu modul files app uchun yordamchi funksiyalarni o'z ichiga oladi.
Asosan SOFF sayti bilan ishlash va HTTP so'rovlarini boshqarish uchun ishlatiladi.

Funksiyalar:
- make_retry_session: HTTP so'rovlar uchun qayta urinish mexanizmi
- refresh_soff_token: SOFF saytidan yangi token olish
- get_valid_soff_token: Haqiqiy SOFF tokenini olish yoki yangilash

Ishlatish:
    from apps.files.utils import make_retry_session, get_valid_soff_token
    
    # HTTP sessiya yaratish
    session = make_retry_session(retries=5)
    
    # SOFF token olish
    token = get_valid_soff_token()
"""

import logging
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apps.files.models import SiteToken

logger = logging.getLogger(__name__)


def make_retry_session(
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504),
        session=None,
):
    """
    HTTP so'rovlar uchun qayta urinish mexanizmi bilan sessiya yaratadi.
    
    Bu funksiya:
    - HTTP so'rovlar uchun avtomatik qayta urinish mexanizmini qo'shadi
    - Server xatolari paytida qayta urinish qiladi
    - Exponential backoff strategiyasini qo'llab-quvvatlaydi
    
    Args:
        retries (int): Qayta urinishlar soni (default: 3)
        backoff_factor (float): Qayta urinishlar orasidagi kutish koeffitsienti (default: 0.3)
        status_forcelist (tuple): Qayta urinish kerak bo'lgan HTTP status kodlari (default: 500, 502, 504)
        session (requests.Session, optional): Mavjud sessiyaga qayta urinish mexanizmini qo'shish
    
    Returns:
        requests.Session: Qayta urinish mexanizmi bilan sessiya
    
    Ishlatish:
        # Oddiy sessiya
        session = make_retry_session()
        
        # Maxsus parametrlar bilan
        session = make_retry_session(retries=5, backoff_factor=0.5)
        
        # Mavjud sessiyaga qo'shish
        existing_session = requests.Session()
        session = make_retry_session(session=existing_session)
    """
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def refresh_soff_token():
    """
    SOFF saytidan yangi token (buildId) olish va bazaga saqlash.
    
    Bu funksiya:
    - SOFF saytining asosiy sahifasini yuklaydi
    - HTML dan buildId ni topadi
    - Yangi token ni bazaga saqlaydi
    - Xatoliklar paytida log yozadi
    
    Returns:
        str: Yangi token muvaffaqiyatli bo'lsa, None xatolik paytida
    
    Raises:
        requests.RequestException: Tarmoq xatolari
        Exception: Boshqa kutilmagan xatoliklar
    
    Ishlatish:
        token = refresh_soff_token()
        if token:
            print(f"Yangi token: {token}")
        else:
            print("Token olishda xatolik")
    """
    try:
        page_url = "https://soff.uz/scientific-resources/all?slug=all&search="
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        # Get the page
        r = session.get(page_url)
        r.raise_for_status()
        html = r.text

        # Find buildId
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if not m:
            m = re.search(r'"buildId":"([^"]+)"', html)

        if not m:
            logger.error("Failed to find buildId in the page content")
            return None

        build_id = m.group(1)

        # Update or create token in database
        site_token, created = SiteToken.objects.update_or_create(
            name='soff',  # Changed from site_name to name
            defaults={'token': build_id}
        )

        logger.info(f"Successfully {'created' if created else 'updated'} SOFF token: {build_id}")
        return build_id

    except requests.RequestException as e:
        logger.error(f"Network error while refreshing SOFF token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while refreshing SOFF token: {str(e)}")
        return None


def get_valid_soff_token():
    """
    Haqiqiy SOFF tokenini olish. Agar token eskirgan bo'lsa, yangilaydi.
    
    Bu funksiya:
    - Bazadan mavjud token ni qidiradi
    - Token ning haqiqiyligini tekshiradi
    - Agar token eskirgan bo'lsa, yangi token olishga chaqiradi
    - Avtomatik token yangilash mexanizmini ta'minlaydi
    
    Returns:
        str: Haqiqiy token muvaffaqiyatli bo'lsa, None xatolik paytida
    
    Raises:
        Exception: Token tekshirish yoki olishda xatoliklar
    
    Ishlatish:
        token = get_valid_soff_token()
        if token:
            # Token bilan API so'rov yuborish
            api_url = f"https://soff.uz/_next/data/{token}/..."
        else:
            print("Token olishda xatolik")
    """
    try:
        # Try to get existing token
        site_token = SiteToken.objects.filter(name='soff').first()  # Changed from site_name to name

        if site_token:
            # Verify token is still valid
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})

            json_url = f"https://soff.uz/_next/data/{site_token.token}/scientific-resources/all.json?slug=all&search="
            resp = session.get(json_url)

            if resp.status_code == 200:
                return site_token.token

        # If we get here, either there's no token or it's invalid
        return refresh_soff_token()

    except Exception as e:
        logger.error(f"Error checking/getting SOFF token: {str(e)}")
        return None
