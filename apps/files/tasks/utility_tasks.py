"""
Utility Tasks
=============

Bu modul yordamchi task'larni o'z ichiga oladi:
- HTTP session creation
- Retry mechanisms
- Common utilities

Bu task'lar boshqa task'lar uchun yordamchi funksiyalar va umumiy utility'larni taqdim etadi.
"""

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Logger
logger = logging.getLogger(__name__)


def make_retry_session():
    """
    Qayta urinishlar bilan mustahkam HTTP session yaratadi.
    
    Bu funksiya:
    - HTTP session yaratadi
    - Retry mexanizmini sozlaydi
    - HTTP va HTTPS adapter'larni mount qiladi
    
    Returns:
        requests.Session: Retry mexanizmi bilan HTTP session
    """
    session = requests.Session()
    retry = Retry(
        total=5, read=5, connect=5, backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
