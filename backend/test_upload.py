
import requests

url = "http://127.0.0.1:8000/api/documents/upload/"

pdf_path = r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"

with open(pdf_path, "rb") as pdf:
    response = requests.post(
        url,
        files={"file": ("sample.pdf", pdf, "application/pdf")},
    )

print("Status Code:", response.status_code)
print("Response:", response.text)
