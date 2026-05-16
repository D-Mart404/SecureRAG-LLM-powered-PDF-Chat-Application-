import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))

from database import get_db
from config import MONGODB_VECTOR_COLLECTION

db = get_db()
coll = db[MONGODB_VECTOR_COLLECTION]

# Delete all documents in the collection to give a 100% clean slate
result = coll.delete_many({})
print(f"Successfully deleted {result.deleted_count} chunks from the MongoDB database.")
