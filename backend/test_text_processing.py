
from documents.text_processing import clean_text, split_into_chunks


sample_text = """
தமிழ்நாடு   அறிவியல்


அறிவியல் என்பது இயற்கையைப் பற்றிய
முறையான ஆய்வு ஆகும்.
"""

cleaned = clean_text(sample_text)
chunks = split_into_chunks(cleaned, chunk_size=40, overlap=10)

print("CLEANED TEXT:")
print(cleaned)

print("\nTOTAL CHUNKS:", len(chunks))

for index, chunk in enumerate(chunks, start=1):
    print(f"\nCHUNK {index}:")
    print(chunk)
