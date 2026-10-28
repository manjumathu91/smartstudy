
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from documents.models import Document
from documents.text_processing import clean_text, split_into_chunks

document = Document.objects.order_by("-uploaded_at").first()

if document is None:
    print("No uploaded documents found.")
else:
    cleaned_text = clean_text(document.extracted_text)
    chunks = split_into_chunks(cleaned_text)

    print("Document:", document.title)
    print("Original characters:", len(document.extracted_text))
    print("Cleaned characters:", len(cleaned_text))
    print("Total chunks:", len(chunks))
    print("\nFirst 1000 characters:")
    print(cleaned_text[:1000])

    print("\nFirst chunk:")
    print(chunks[0] if chunks else "No text chunks found.")
