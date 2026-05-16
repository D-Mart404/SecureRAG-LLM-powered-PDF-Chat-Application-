import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))

from rag_pipeline import _cross_encoder

if _cross_encoder is None:
    print("CROSS ENCODER IS NONE!")
else:
    print("Cross Encoder loaded successfully!")
