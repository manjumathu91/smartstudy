

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import pymupdf

from documents.models import Document, DocumentPage
from documents.ocr_utils import extract_page_text_with_ocr


class Command(BaseCommand):
    help = "Re-extract and repair text for existing PDF documents"

    def add_arguments(self, parser):
        parser.add_argument(
            "--document-id",
            type=int,
            help="Process only one document by its ID",
        )

    def handle(self, *args, **options):
        document_id = options.get("document_id")

        documents = Document.objects.all().order_by("id")

        if document_id is not None:
            documents = documents.filter(id=document_id)

            if not documents.exists():
                raise CommandError(
                    f"Document ID {document_id} was not found."
                )

        for document in documents:
            self.stdout.write(
                f"Processing document {document.id}: {document.title}"
            )

            try:
                with document.file.open("rb") as pdf_file:
                    pdf_bytes = pdf_file.read()

                page_records = []
                ocr_pages = []

                with pymupdf.open(
                    stream=pdf_bytes,
                    filetype="pdf",
                ) as pdf:

                    if pdf.needs_pass:
                        self.stderr.write(
                            f"Skipped password-protected PDF: "
                            f"{document.title}"
                        )
                        continue

                    for page_number, page in enumerate(pdf, start=1):
                        native_text = page.get_text("text").strip()
                        text = native_text

                        native_errors = native_text.count("\ufffd")
                        should_try_ocr = (
                            not native_text or native_errors > 0
                        )

                        if should_try_ocr:
                            try:
                                ocr_text = extract_page_text_with_ocr(
                                    page,
                                    languages="tam+eng",
                                ).strip()

                                ocr_errors = ocr_text.count("\ufffd")

                                if ocr_text and (
                                    not native_text
                                    or ocr_errors < native_errors
                                ):
                                    text = ocr_text
                                    ocr_pages.append(page_number)

                            except Exception as exc:
                                self.stderr.write(
                                    f"OCR failed on page {page_number}: "
                                    f"{exc}"
                                )

                        page_records.append(
                            {
                                "page_number": page_number,
                                "extracted_text": text,
                                "needs_ocr": (
                                    not bool(text)
                                    or "\ufffd" in text
                                ),
                            }
                        )

                combined_text = "\n\n".join(
                    record["extracted_text"]
                    for record in page_records
                    if record["extracted_text"]
                ).strip()

                with transaction.atomic():
                    DocumentPage.objects.filter(
                        document=document
                    ).delete()

                    DocumentPage.objects.bulk_create(
                        [
                            DocumentPage(
                                document=document,
                                page_number=record["page_number"],
                                extracted_text=record["extracted_text"],
                                needs_ocr=record["needs_ocr"],
                            )
                            for record in page_records
                        ]
                    )

                    document.extracted_text = combined_text
                    document.save(update_fields=["extracted_text"])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Saved {len(page_records)} pages for "
                        f"document {document.id}. "
                        f"OCR used on pages: {ocr_pages}"
                    )
                )

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to process document {document.id}: {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS("Document reprocessing finished.")
        )
