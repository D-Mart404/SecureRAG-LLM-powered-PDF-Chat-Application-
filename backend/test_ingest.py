import traceback
from ingest import ingest_pdf_bytes

raw = b"%PDF-1.4\n" + b"test"*1000

try:
    ingest_pdf_bytes(raw, "lab2.pdf", "01")
except Exception as e:
    traceback.print_exc()
