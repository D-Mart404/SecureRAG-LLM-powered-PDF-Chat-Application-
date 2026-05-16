import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))

from database import get_db
from config import MONGODB_VECTOR_COLLECTION

db = get_db()
coll = db[MONGODB_VECTOR_COLLECTION]

# Test counts
print("Total count:", coll.count_documents({}))
print("Count with metadata.uploaded_by:", coll.count_documents({"metadata.uploaded_by": {"$exists": True}}))
print("Count with uploaded_by:", coll.count_documents({"uploaded_by": {"$exists": True}}))

print("Count with metadata.source:", coll.count_documents({"metadata.source": {"$exists": True}}))
print("Count with source:", coll.count_documents({"source": {"$exists": True}}))
