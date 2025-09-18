import os
import sys
import shutil

# Django sozlamalarini o'rnatish
# Skriptni loyiha papkasidan ishga tushirishingiz kerak
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django

django.setup()

from django.conf import settings
# DIQQAT: Bu yerdagi 'apps.files.models' yo'lini o'zingizning app nomingizga moslang
# Masalan: 'apps.multiparser.models'
from apps.files.models import Document, Product


def main():
    """
    Barcha Document, Product yozuvlarini va media papkasini butunlay o'chiradi.
    Bu amalni QAYTARIB BO'LMAYDI.
    """

    confirmation_phrase = 'y'

    print("\n" + "=" * 60)
    print("!!! DIQQAT: O'TA XAVFLI AMAL !!!")
    print("=" * 60)
    print("Ushbu skript quyidagilarni bajaradi:")
    print(f"  1. Barcha fayllar joylashgan '{settings.MEDIA_ROOT}' papkasini butunlay o'chiradi.")
    print("  2. Ma'lumotlar bazasidagi BARCHA `Product` yozuvlarini o'chiradi.")
    print("  3. Ma'lumotlar bazasidagi BARCHA `Document` yozuvlarini o'chiradi.")
    print("\nBU AMALNI ORTGA QAYTARIB BO'LMAYDI.")
    print("=" * 60)

    response = input(f"Davom etish uchun '{confirmation_phrase}' deb yozing va Enter bosing: ")

    if response != confirmation_phrase:
        print("\nNoto'g'ri tasdiqlash. Amal bekor qilindi.")
        return

    print("\nTasdiqlandi. O'chirish jarayoni boshlandi...")

    # 1. Media papkasini o'chirish
    media_path = settings.MEDIA_ROOT
    try:
        if os.path.exists(media_path):
            shutil.rmtree(media_path)
            print(f"✅ Media papkasi '{media_path}' muvaffaqiyatli o'chirildi.")
        else:
            print(f"INFO: Media papkasi '{media_path}' mavjud emas.")
    except Exception as e:
        print(f"❌ Media papkasini o'chirishda xatolik: {e}")
        return

    # 2. Product yozuvlarini o'chirish
    try:
        deleted_products_count, _ = Product.objects.all().delete()
        print(f"✅ {deleted_products_count} ta `Product` yozuvi muvaffaqiyatli o'chirildi.")
    except Exception as e:
        print(f"❌ Product yozuvlarini o'chirishda xatolik: {e}")
        return

    # 3. Document yozuvlarini o'chirish
    # Odatda Product o'chirilganda CASCADE tufayli Document ham o'chiriladi,
    # lekin 100% ishonch hosil qilish uchun alohida o'chiramiz.
    try:
        deleted_docs_count, _ = Document.objects.all().delete()
        print(f"✅ {deleted_docs_count} ta `Document` yozuvi muvaffaqiyatli o'chirildi.")
    except Exception as e:
        print(f"❌ Document yozuvlarini o'chirishda xatolik: {e}")
        return

    print("\n--- BARCHA MA'LUMOTLAR MUOFFAQIYATLI O'CHIRILDI! ---")


if __name__ == "__main__":
    main()