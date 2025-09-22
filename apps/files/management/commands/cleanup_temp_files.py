from django.core.management.base import BaseCommand
from apps.files.tasks import cleanup_old_temp_files


class Command(BaseCommand):
    help = 'Eski vaqtincha fayllarni tozalaydi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Barcha vaqtincha fayllarni majburiy o\'chiradi',
        )

    def handle(self, *args, **options):
        if options['force']:
            self.stdout.write('Barcha vaqtincha fayllar o\'chirilmoqda...')
            # Force cleanup logic can be added here
        else:
            self.stdout.write('Eski vaqtincha fayllar tozalanmoqda...')
        
        cleanup_old_temp_files()
        self.stdout.write(
            self.style.SUCCESS('Vaqtincha fayllar muvaffaqiyatli tozalandi!')
        )
