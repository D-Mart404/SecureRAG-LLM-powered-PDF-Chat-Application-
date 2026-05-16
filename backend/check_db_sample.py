import sys
import os
import pprint

sys.path.append(os.path.join(os.path.dirname(__file__)))

from database import get_db
from config import MONGODB_VECTOR_COLLECTION

db = get_db()
coll = db[MONGODB_VECTOR_COLLECTION]

sample = coll.find_one({})
print("Sample Document:")
pprint.pprint(sample)
