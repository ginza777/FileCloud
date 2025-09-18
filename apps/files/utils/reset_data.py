import os
import sys
import shutil

# Django setup
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.conf import settings
from files.models import Document, Product


def main():
    print("\nDIQQAT! BU AMAL QUYIDAGILARNI BAJARADI:")
    print(f"  - Barcha fayllar joylashgan '{settings.MEDIA_ROOT}' papkasini butunlay o'chiradi.")
    print("  - Barcha hujjatlarning qayta ishlash statuslarini boshlang'ich holatga qaytaradi.")
    print("  - Barcha mahsulotlarning parse qilingan kontentini tozalaydi.")


    # 1. Media papkasini o'chirish
    media_path = settings.MEDIA_ROOT
    try:
        if os.path.exists(media_path):
            shutil.rmtree(media_path)
            print(f"✅ Media papkasi '{media_path}' muvaffaqiyatli o'chirildi.")
        else:
            print(f"Papkasi '{media_path}' mavjud emas, o'tkazib yuborildi.")
    except Exception as e:
        print(f"Media papkasini o'chirishda xatolik: {e}")
        return

    # Debug: Show counts before update
    doc_count_before = Document.objects.count()
    prod_count_before = Product.objects.count()
    print(f"Documentlar soni (oldin): {doc_count_before}")
    print(f"Productlar soni (oldin): {prod_count_before}")

    # 2. Document statuslarini va maydonlarini tozalash
    print("Hujjatlar statuslari tozalanmoqda...")
    try:
        updated_docs_count = Document.objects.all().update(
            download_status='pending',
            parse_status='pending',
            index_status='pending',
            telegram_status='pending',
            delete_status='pending',
            file_path=None,  # Fayl manzili ham tozalanadi
            telegram_file_id=None  # Telegram file_id ham tozalanadi
        )
        print(f"✅ {updated_docs_count} ta hujjatning statuslari boshlang'ich holatga qaytarildi.")
        # Debug: Show a sample Document after update
        sample_doc = Document.objects.first()
        if sample_doc:
            print(f"Namuna Document: {sample_doc.id}, download_status={sample_doc.download_status}, file_path={sample_doc.file_path}")
    except Exception as e:
        print(f"Hujjatlarni yangilashda xatolik: {e}")
        return

    # 3. Product'ning parse qilingan kontentini tozalash
    print("Mahsulotlarning parse qilingan kontenti tozalanmoqda...")
    try:
        updated_products_count = Product.objects.all().update(
            parsed_content=None
        )
        print(f"✅ {updated_products_count} ta mahsulotning kontenti tozalandi.")
        # Debug: Show a sample Product after update
        sample_prod = Product.objects.first()
        if sample_prod:
            print(f"Namuna Product: {sample_prod.id}, parsed_content={sample_prod.parsed_content}")
    except Exception as e:
        print(f"Mahsulotlarni yangilashda xatolik: {e}")
        return

    # Debug: Show counts after update
    doc_count_after = Document.objects.count()
    prod_count_after = Product.objects.count()
    print(f"Documentlar soni (keyin): {doc_count_after}")
    print(f"Productlar soni (keyin): {prod_count_after}")

    # Verification: Print Documents not fully reset
    not_pending_docs = Document.objects.exclude(
        download_status='pending',
    ).union(
        Document.objects.exclude(parse_status='pending')
    ).union(
        Document.objects.exclude(index_status='pending')
    ).union(
        Document.objects.exclude(telegram_status='pending')
    ).union(
        Document.objects.exclude(delete_status='pending')
    )
    if not_pending_docs.exists():
        print("Quyidagi Documentlar to'liq 'pending' holatiga o'tmadi:")
        for doc in not_pending_docs:
            print(f"ID: {doc.id}, download_status={doc.download_status}, parse_status={doc.parse_status}, index_status={doc.index_status}, telegram_status={doc.telegram_status}, delete_status={doc.delete_status}")
    else:
        print("Barcha Document statuslari to'g'ri 'pending' holatida!")

    print("\n--- Barcha ma'lumotlar muvaffaqiyatli boshlang'ich holatga qaytarildi! ---")
    print("Endi `dparse` komandasini ishga tushirib, barcha fayllarni qaytadan ishlashingiz mumkin.")

if __name__ == "__main__":
    main()

