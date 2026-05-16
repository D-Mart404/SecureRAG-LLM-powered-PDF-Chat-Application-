"""Input sanitization for query text."""
import re

_MAX_LEN = 500


def sanitize_input(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    t = re.sub(r"[;'\"]|--", "", t)
    t = re.sub(r"<[^>]*>", "", t)
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    return t[:_MAX_LEN]


def sanitize_filename(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        return "upload.pdf"
    base = name.replace("\\", "/").split("/")[-1]
    t = re.sub(r"[^a-zA-Z0-9._-]", "_", base)[:120]
    return t or "upload.pdf"
