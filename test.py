import requests
from math import ceil
import time
import logging
import os  # 'os' modulini import qilish

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Asosiy URL'lar (API uchun /uz/ siz)
base_urls = [
    "https://arxiv.uz/documents/dars-ishlanmalar/",
    "https://arxiv.uz/documents/diplom-ishlar/",
    "https://arxiv.uz/documents/darsliklar/",
    "https://arxiv.uz/documents/slaydlar/",
    "https://arxiv.uz/documents/referatlar/",
    "https://arxiv.uz/documents/kurs-ishlari/",
]

# Sub-kataloglar
sub_categories = [
    "adabiyot", "algebra", "anatomiya", "arxitektura", "astronomiya", "biologiya",
    "biotexnologiya", "botanika", "chizmachilik", "chqbt", "davlat-tilida-ish-yuritish",
    "dinshunoslik-asoslari", "ekologiya", "energetika", "falsafa", "fizika",
    "fransuz-tili", "geodeziya", "geografiya", "geologiya", "geometriya", "huquqshunoslik",
    "informatika-va-at", "ingliz-tili", "iqtisodiyot", "issiqlik-texnikasi", "jismoniy-tarbiya",
    "kimyo", "konchilik-ishi", "madaniyatshunoslik", "maktabgacha-va-boshlang-ich-ta-lim",
    "manaviyat-asoslari", "mashinasozlik", "materialshunoslik", "mehnat", "melioratsiya",
    "metrologiya", "mexanika", "milliy-istiqlol-g-oyasi", "musiqa", "nemis-tili",
    "o-qish", "odam-va-uning-salomatligi", "odobnoma", "oziq-ovqat-texnologiyasi",
    "pedagogik-psixologiya", "prezident-asarlari", "psixologiya", "psixologiya-1",
    "qishloq-va-o-rmon-xo-jaligi", "radiotexnika", "rus-tili-va-adabiyoti", "san-at",
    "siyosatshunoslik", "sotsiologiya", "suv-xo-jaligi", "tabiatshunoslik", "tarix",
    "tasviriy-san-at", "texnika-va-texnologiya", "tibbiyot", "tilshunoslik",
    "to-qimachilik", "transport", "valeologiya", "xayot-faoliyati-xavfsizligi", "zoologiya"
]

# Header'lar
headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'priority': 'u=1, i',
    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
}

# Cookies (foydalanuvchi sessiyasi)
cookies = {
    '_gcl_au': '1.1.790518223.1758657252',
    '_ga': 'GA1.1.1764259932.1758657252',
    '_ym_uid': '175865725312197865',
    '_ym_d': '1758657253',
    '_ym_isad': '2',
    'PHPSESSID': 'fc33f22ec66a83cbcdc3ba6a8c37e80e',
    '_ga_WCY75STCX9': 'GS2.1.s1758662533$o2$g0$t1758662533$j60$l0$h0',
}


# ---
## Faylni yuklab olish funksiyasi
# ---

def download_file(url, file_path):
    """
    Berilgan URL'dagi faylni yuklab oladi va saqlaydi.
    """
    try:
        logger.info(f"Yuklab olinmoqda: {url}")
        # Faylning hajmi katta bo'lishi mumkinligi sababli stream=True ishlatiladi
        with requests.get(url, headers=headers, cookies=cookies, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Fayl saqlandi: {file_path}")
    except requests.RequestException as e:
        logger.error(f"Faylni yuklab olishda xato yuz berdi ({url}): {e}")


# ---
## Har bir sahifani aylanib chiqish va fayllarni yuklab olish
# ---

def scrape_category(base_url, sub_category):
    page = 1
    page_size = 10
    # Referer'ni dinamik sozlash
    headers['referer'] = f"https://arxiv.uz/uz/documents/{sub_category.split('/')[-1]}/{sub_category.split('/')[-1]}"

    # Yuklab olinadigan papka nomini aniqlash
    save_directory = "arxiv"

    while True:
        api_url = f"{base_url}{sub_category}?page={page}&pageSize={page_size}"
        try:
            logger.info(f"So'rov yuborilmoqda: {api_url}")
            response = requests.get(api_url, headers=headers, cookies=cookies, timeout=10)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"JSON xatosi ({api_url}): {e}. Javob matni: {response.text[:100]}")
                break

            documents = data.get("documents", [])
            if not documents:
                logger.info(f"Kategoriyada hujjatlar yo'q: {api_url}")
                break

            for doc in documents:
                slug = doc.get("slug")
                category_slug = doc.get("category", {}).get("slug")
                subject_slug = doc.get("subject", {}).get("slug")
                title = doc.get("title", slug).replace("/", "-")  # Sarlavhadagi ' / ' belgilarini o'zgartirish

                if slug and category_slug and subject_slug:
                    download_url = f"https://arxiv.uz/uz/download/{category_slug}/{subject_slug}/{slug}"

                    # Fayl nomini sarlavha va slug asosida belgilash
                    file_name = f"{title}-{slug}.pdf"
                    file_path = os.path.join(save_directory, file_name)

                    # Faylni yuklab olish funksiyasini chaqirish
                    download_file(download_url, file_path)

            total = data.get("total", 0)
            total_pages = ceil(total / page_size)
            logger.info(f"Sahifa {page}/{total_pages}, Jami hujjatlar: {total}")
            if page >= total_pages:
                break

            page += 1
            time.sleep(1)  # Serverga yukni kamaytirish uchun pauza

        except requests.RequestException as e:
            logger.error(
                f"Xato yuz berdi ({api_url}): {e}. Status kodi: {response.status_code if 'response' in locals() else 'N/A'}")
            break


# ---
## Asosiy funksiya
# ---

def main():
    # Fayllarni saqlash uchun "arxiv" papkasini yaratish
    save_directory = "arxiv"
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)
        logger.info(f"'{save_directory}' papkasi yaratildi.")

    for base_url in base_urls:
        for sub_category in sub_categories:
            logger.info(f"\nKategoriya: {base_url}{sub_category}")
            scrape_category(base_url, sub_category)


if __name__ == "__main__":
    main()