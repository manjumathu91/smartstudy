
from django.core.management.base import BaseCommand, CommandError

from learning.semantic_search import index_pdf_pages


class Command(BaseCommand):
    help = "Create semantic embeddings for uploaded PDF pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--document-id",
            type=int,
            default=None,
            help="Index only the specified document ID.",
        )

    def handle(self, *args, **options):
        document_id = options["document_id"]

        try:
            count = index_pdf_pages(document_id=document_id)
        except Exception as exc:
            raise CommandError(
                f"PDF indexing failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully indexed {count} PDF pages."
            )
        )
