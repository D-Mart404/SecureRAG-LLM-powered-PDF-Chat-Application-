import requests
import os

key = "llx-iOu8tw2YHnBQFi0mBPIt5lRZFAzb0ItZz1zDFqSwmVycNJDo"
headers = {"Authorization": f"Bearer {key}", "accept": "application/json"}
base_url = "https://api.cloud.llamaindex.ai/api/parsing"

# Create a dummy pdf
with open("dummy.pdf", "wb") as f:
    f.write(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF")

with open("dummy.pdf", "rb") as f:
    upload_res = requests.post(
        f"{base_url}/upload",
        headers=headers,
        data={
            "premium_mode": "true",
            "parsing_instruction": "Describe all images and graphs.",
        },
        files={"file": ("dummy.pdf", f, "application/pdf")}
    )

print(upload_res.status_code)
print(upload_res.json())
