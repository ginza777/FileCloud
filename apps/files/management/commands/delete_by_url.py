from django.core.management.base import BaseCommand
from ...models import Document, Product

class Command(BaseCommand):
    help = 'Delete documents and products that have URL starting with https://soff.uz/api/v1/document/download/'

    def handle(self, *args, **options):
        target_url = 'https://soff.uz/api/v1/document/download/'

        # Get all documents with matching URL
        documents = Document.objects.filter(file_url__startswith=target_url)

        if documents.exists():
            # Get related products
            product_ids = documents.values_list('product_id', flat=True)
            products = Product.objects.filter(id__in=product_ids)

            # Delete products first (this will cascade delete documents)
            products_count = products.count()
            products.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {products_count} products and their related documents'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'No documents found with the specified URL pattern'
                )
            )
