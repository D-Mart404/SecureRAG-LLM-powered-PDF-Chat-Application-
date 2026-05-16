import sys
import os

# Append backend to path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__)))

from database import get_db
from config import MONGODB_VECTOR_COLLECTION

db = get_db()
coll = db[MONGODB_VECTOR_COLLECTION]
count = coll.count_documents({})
print(f"Total documents in DB: {count}")

docs = list(coll.find({}, {"metadata.source": 1, "metadata.page": 1, "_id": 0}))
sources = {}
for d in docs:
    src = d.get("metadata", {}).get("source", "Unknown")
    sources[src] = sources.get(src, 0) + 1

print("Sources in DB:")
for k, v in sources.items():
    print(f"  {k}: {v} chunks")
