from django.core.management.base import BaseCommand
from ...models import Document

class Command(BaseCommand):
    help = 'Delete documents and related products that have a URL starting with https://soff.uz/api/v1/document/download/'

    def handle(self, *args, **options):
        target_url = 'https://soff.uz/api/v1/document/download/'

        # Find all documents with a URL that starts with the target URL.
        # We select the related 'product' to avoid extra database queries later,
        # although it's not strictly necessary for the delete operation itself.
        documents_to_delete = Document.objects.filter(parse_file_url__startswith=target_url)

        if not documents_to_delete.exists():
            self.stdout.write(
                self.style.WARNING('No documents found with the specified URL pattern.')
            )
            return

        # The count of documents to be deleted.
        document_count = documents_to_delete.count()

        # Deleting the documents will automatically trigger the deletion of related
        # products because of the `on_delete=models.CASCADE` setting on the
        # `OneToOneField` in the `Product` model.
        documents_to_delete.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully deleted {document_count} documents and their associated products.'
            )
        )
