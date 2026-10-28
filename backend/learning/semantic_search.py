from functools import lru_cache

from django.conf import settings
from qdrant_client import QdrantClient, models as qdrant_models


from documents.models import Document, DocumentPage


COLLECTION_NAME = "pdf_pages"
VECTOR_SIZE = 384



@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


@lru_cache(maxsize=1)
def get_qdrant_client():
    storage_path = settings.BASE_DIR / "qdrant_storage"
    storage_path.mkdir(parents=True, exist_ok=True)

    return QdrantClient(path=str(storage_path))


def ensure_collection():
    client = get_qdrant_client()

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_SIZE,
                distance=qdrant_models.Distance.COSINE,
            ),
        )


def index_pdf_pages(document_id=None):
    """Create embeddings for saved PDF pages and store them in local Qdrant."""
    ensure_collection()

    pages = DocumentPage.objects.select_related("document").exclude(
        extracted_text=""
    )

    if document_id is not None:
        pages = pages.filter(document_id=document_id)

    model = get_embedding_model()
    client = get_qdrant_client()
    indexed_count = 0

    for page in pages.iterator():
        text = page.extracted_text.strip()

        if not text:
            continue

        vector = model.encode(
            text,
            normalize_embeddings=True,
        ).tolist()

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                qdrant_models.PointStruct(
                    id=page.id,
                    vector=vector,
                    payload={
                        "document_id": page.document_id,
                        "document_title": page.document.title,
                        "page_number": page.page_number,
                        "extracted_text": text,
                        "needs_ocr": page.needs_ocr,
                    },
                )
            ],
            wait=True,
        )

        indexed_count += 1

    return indexed_count






def search_pdf_pages(question, limit=5, document_id=None, owner_id=None):
    """Search PDF pages belonging to the specified user."""

    import re

    if not isinstance(question, str) or not question.strip():
        return []

    if owner_id is None:
        return []

    question = question.strip()

    try:
        owner_id = int(owner_id)

        if document_id is not None:
            document_id = int(document_id)
            if document_id <= 0:
                return []
    except (TypeError, ValueError):
        return []

    owned_document_ids = list(
        Document.objects.filter(
            owner_id=owner_id
        ).values_list("id", flat=True)
    )

    if not owned_document_ids:
        return []

    # Restrict every search to the user's selected/owned PDF.
    if document_id is not None:
        if document_id not in owned_document_ids:
            return []

        allowed_ids = [document_id]

        document_filter = qdrant_models.FieldCondition(
            key="document_id",
            match=qdrant_models.MatchValue(value=document_id),
        )
    else:
        allowed_ids = owned_document_ids

        document_filter = qdrant_models.FieldCondition(
            key="document_id",
            match=qdrant_models.MatchAny(any=allowed_ids),
        )

    def normalize_text(value):
        value = value or ""

        for char in ("\u200c", "\u200d", "\ufeff"):
            value = value.replace(char, "")

        return " ".join(value.split()).casefold()

    # --------------------------------------------------
    # 1. EXACT PAGE SEARCH
    # --------------------------------------------------
    # Examples: "page 6", "Explain page 25",
    # "பக்கம் 6-ஐ விளக்கு"
    page_match = re.search(
        r"\b(?:page|பக்கம்)\s*[-:#]?\s*(\d+)\b",
        question,
        re.IGNORECASE,
    )

    if page_match:
        requested_page = int(page_match.group(1))

        if requested_page <= 0:
            return []

        exact_pages = DocumentPage.objects.filter(
            document__owner_id=owner_id,
            page_number=requested_page,
            extracted_text__gt="",
        ).select_related("document")

        if document_id is not None:
            exact_pages = exact_pages.filter(
                document_id=document_id
            )

        results = []

        for page in exact_pages:
            results.append({
                "document_id": page.document_id,
                "title": page.document.title,
                "page_number": page.page_number,
                "extracted_text": page.extracted_text,
                "needs_ocr": page.needs_ocr,
                "score": 1.0,
            })

        # Do not replace a missing requested page with
        # unrelated pages from semantic search.
        return results

    # --------------------------------------------------
    # 2. KEYWORD SEARCH
    # --------------------------------------------------
    normalized_question = normalize_text(question)

    terms = [
        term
        for term in normalized_question.split()
        if len(term) >= 2
    ]

    combined = {}

    pages = DocumentPage.objects.filter(
        document__owner_id=owner_id,
        extracted_text__gt="",
    ).select_related("document")

    if document_id is not None:
        pages = pages.filter(document_id=document_id)

    for page in pages.iterator():
        text = normalize_text(page.extracted_text)

        exact_match = (
            bool(normalized_question)
            and normalized_question in text
        )

        matched_terms = sum(
            1 for term in terms if term in text
        )

        if exact_match or matched_terms:
            keyword_score = (
                1.0
                if exact_match
                else matched_terms / max(len(terms), 1)
            )

            combined[
                (page.document_id, page.page_number)
            ] = {
                "document_id": page.document_id,
                "title": page.document.title,
                "page_number": page.page_number,
                "extracted_text": page.extracted_text,
                "needs_ocr": page.needs_ocr,
                "score": keyword_score,
                "_keyword_score": keyword_score,
            }

    # --------------------------------------------------
    # 3. SEMANTIC SEARCH
    # --------------------------------------------------
    client = get_qdrant_client()

    if client.collection_exists(COLLECTION_NAME):
        model = get_embedding_model()

        query_vector = model.encode(
            question,
            normalize_embeddings=True,
        ).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=qdrant_models.Filter(
                must=[document_filter]
            ),
            limit=max(limit * 3, 15),
            with_payload=True,
        )

        for point in results.points:
            payload = point.payload or {}

            doc_id = payload.get("document_id")
            page_number = payload.get("page_number")

            if doc_id not in allowed_ids or page_number is None:
                continue

            try:
                doc_id = int(doc_id)
                page_number = int(page_number)
            except (TypeError, ValueError):
                continue

            if doc_id not in allowed_ids or page_number <= 0:
                continue

            # Verify the stored Qdrant page against the database.
            # This prevents returning stale or incorrect page text.
            db_page = DocumentPage.objects.filter(
                document_id=doc_id,
                document__owner_id=owner_id,
                page_number=page_number,
                extracted_text__gt="",
            ).select_related("document").first()

            if db_page is None:
                continue

            key = (doc_id, page_number)
            semantic_score = float(point.score or 0)

            if key not in combined:
                combined[key] = {
                    "document_id": db_page.document_id,
                    "title": db_page.document.title,
                    "page_number": db_page.page_number,
                    "extracted_text": db_page.extracted_text,
                    "needs_ocr": db_page.needs_ocr,
                    "score": semantic_score,
                    "_keyword_score": 0,
                }
            else:
                combined[key]["score"] = max(
                    combined[key]["score"],
                    semantic_score,
                )

    # --------------------------------------------------
    # 4. RANK AND RETURN RELEVANT PAGES
    # --------------------------------------------------
    def rank(item):
        text = normalize_text(item["extracted_text"])

        exact = (
            bool(normalized_question)
            and normalized_question in text
        )

        matched = sum(
            1 for term in terms if term in text
        )

        return (
            1 if exact else 0,
            matched,
            item.get("_keyword_score", 0),
            item["score"],
        )

    ranked_results = sorted(
        combined.values(),
        key=rank,
        reverse=True,
    )

    final_results = []

    for item in ranked_results:
        item.pop("_keyword_score", None)
        final_results.append(item)

    return final_results[:max(int(limit), 1)]
