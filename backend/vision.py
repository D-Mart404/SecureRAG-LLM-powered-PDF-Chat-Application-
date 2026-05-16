"""
vision.py — Visual Retrieval Pipeline for VisDoM-style Multimodal RAG.

Responsibilities:
  1. extract_page_images(pdf_bytes, doc_id) → writes JPG images to IMAGE_STORE_DIR
  2. get_image_path(doc_id, page_number) → resolves the cached image path
  3. analyze_page_image(image_path, query) → calls Groq Vision API, returns structured insights
  4. All vision API responses are cached by (image_hash, query_hash) to minimise API calls.

Design principles (from spec):
  - Retrieval first, vision second — this module is ONLY called after textual retrieval.
  - Vision calls ≤ MAX_IMAGES_PER_QUERY per query.
  - No GPU required — uses hosted Groq Vision API (Llama 4 Scout).
  - Pure-Python PDF→image via PyMuPDF (no Poppler required).
  - Graceful fallback: if the vision call fails, falls back to text-only description.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from config import IMAGE_STORE_DIR, VISION_MODEL_NAME, VISION_FALLBACK_MODEL

logger = logging.getLogger(__name__)

# ─── In-memory response cache: {(image_hash, query_hash): insight_text} ───────
# Prevents redundant vision API calls for the same page+query combo.
_vision_cache: dict[tuple[str, str], str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# 1. PDF → Image Extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_page_images(pdf_bytes: bytes, doc_id: str, dpi: int = 150) -> dict[int, Path]:
    """
    Convert every page of a PDF to a JPEG image and save to IMAGE_STORE_DIR.
    Uses PyMuPDF (fitz) and parallelizes the extraction using ThreadPoolExecutor.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
        return {}

    page_image_map: dict[int, Path] = {}

    try:
        import concurrent.futures
        
        # Get total pages quickly
        temp_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(temp_doc)
        temp_doc.close()

        def _process_single_page(page_idx):
            page_num = page_idx + 1  # 1-indexed to match LlamaParse metadata
            out_path = IMAGE_STORE_DIR / f"{doc_id}_page_{page_num}.jpg"

            # Skip re-rendering if already cached on disk (idempotent)
            if out_path.exists():
                return page_num, out_path

            # Open a thread-local document instance from bytes
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                page = doc[page_idx]

                # ── Relevance Heuristic: Skip pure-text pages ─────────────────────
                is_visually_heavy = False
                drawings = page.get_drawings()
                if len(drawings) >= 10:
                    is_visually_heavy = True

                if not is_visually_heavy:
                    images = page.get_images()
                    page_area = page.rect.width * page.rect.height
                    for img in images:
                        xref = img[0]
                        for r in page.get_image_rects(xref):
                            if (r.width * r.height) > (page_area * 0.05):
                                is_visually_heavy = True
                                break
                        if is_visually_heavy:
                            break

                if not is_visually_heavy:
                    logger.info(f"[Vision] ⏭️ Skipping page {page_num} — mostly text (drawings: {len(drawings)})")
                    return page_num, None

                # ───────────────────────────────────────────────────────────────────
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pix.save(str(out_path), jpg_quality=85)
                logger.debug(f"[Vision] Saved page {page_num} → {out_path.name}")
                return page_num, out_path
            finally:
                doc.close()

        # Run extraction in parallel (max 8 workers to not overwhelm CPU/Memory)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_process_single_page, i): i for i in range(total_pages)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    p_num, path = future.result()
                    if path is not None:
                        page_image_map[p_num] = path
                except Exception as e:
                    logger.error(f"[Vision] Error processing page: {e}")

        logger.info(f"[Vision] Extracted {len(page_image_map)} images for '{doc_id}'")

    except Exception as exc:
        logger.error(f"[Vision] PDF→image failed for '{doc_id}': {exc}")

    return page_image_map


# ─────────────────────────────────────────────────────────────────────────────
# 2. Image Path Resolver
# ─────────────────────────────────────────────────────────────────────────────

def get_image_path(doc_id: str, page_number: int | str) -> Optional[Path]:
    """
    Resolve the stored image path for a given (doc_id, page_number) pair.
    Returns None if the image has not been extracted yet.
    """
    try:
        page_num = int(page_number)
    except (TypeError, ValueError):
        return None

    candidate = IMAGE_STORE_DIR / f"{doc_id}_page_{page_num}.jpg"
    if candidate.exists():
        return candidate

    # Fuzzy match for minor casing differences
    pattern = f"{doc_id}_page_{page_num}.jpg"
    for f in IMAGE_STORE_DIR.glob(f"*_page_{page_num}.jpg"):
        if f.name.lower() == pattern.lower():
            return f

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Groq Vision API Call (Llama 4 Scout)
# ─────────────────────────────────────────────────────────────────────────────

def _image_hash(image_path: Path) -> str:
    h = hashlib.md5()
    with open(image_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _query_hash(query: str) -> str:
    return hashlib.md5(query.strip().lower().encode()).hexdigest()[:16]


def _encode_image_b64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _call_groq(api_key: str, model: str, messages: list, max_tokens: int = 1024) -> str:
    """Low-level Groq API call. Returns the content string or raises."""
    import httpx
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _vision_fallback(api_key: str, image_path: Path, query: str) -> str:
    """
    Text-only fallback when the primary vision model fails.
    Describes the page by its filename context and asks the LLM to note the limitation.
    This ensures the pipeline always returns a response, never crashes silently.
    """
    try:
        messages = [
            {
                "role": "user",
                "content": (
                    f"A document page image (file: {image_path.name}) could not be analyzed "
                    f"visually due to an API limitation. Based on the filename context only, "
                    f"acknowledge this limitation and state that visual analysis of this page "
                    f"is unavailable. The user asked: '{query}'"
                ),
            }
        ]
        return _call_groq(api_key, VISION_FALLBACK_MODEL, messages, max_tokens=256)
    except Exception as e:
        return f"[Visual analysis unavailable for {image_path.name}: {str(e)[:150]}]"


def analyze_page_image(image_path: Path, query: str, hint: Optional[str] = None) -> str:
    """
    Send a document page image to the Groq Vision API (Llama 4 Scout) and return
    structured insights. Cached by (image_hash, query_hash). Falls back gracefully.

    Args:
        image_path: Path to the JPEG image to analyze.
        query:      The user's original question to focus the visual analysis.
        hint:       Optional context text from the same page to aid analysis.

    Returns:
        Structured string of visual insights extracted from the page.
    """
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        logger.warning("[Vision] GROQ_API_KEY not set — skipping visual analysis.")
        return "[Visual analysis unavailable: GROQ_API_KEY not configured]"

    if not image_path.exists():
        logger.warning(f"[Vision] Image not found: {image_path}")
        return f"[Visual analysis unavailable: {image_path.name} not found]"

    # ── Cache check ────────────────────────────────────────────────────────────
    img_h = _image_hash(image_path)
    qry_h = _query_hash(query)
    cache_key = (img_h, qry_h)

    if cache_key in _vision_cache:
        logger.info(
            f"[Vision] Cache HIT  ─ {image_path.name} | query_hash={qry_h}\n"
            f"         Returning cached insight ({len(_vision_cache[cache_key])} chars)"
        )
        return _vision_cache[cache_key]

    # ── Build Llama 4 Scout vision prompt ─────────────────────────────────────
    b64_image = _encode_image_b64(image_path)
    hint_section = f"\n\nTEXT RETRIEVAL HINTS (from this page):\n{hint}\n" if hint else ""

    vision_prompt = (
        "You are a precise document analyst. Analyze this document page image carefully.\n\n"
        f"User Question: {query}\n"
        f"{hint_section}\n"
        "Instructions:\n"
        "1. TEMPORAL IDENTIFICATION (CRITICAL): Before extracting any data, identify the "
        "EXACT time period shown (e.g., Q2-25, H1-26, FY25). Look for headers like 'Q2' or 'H1'.\n"
        "2. Identify ALL charts, graphs, tables, diagrams, and figures on this page.\n"
        "3. Extract EXACT values, labels, axes, and data points from any charts/graphs.\n"
        "4. Reconstruct any tables as structured text with headers and row labels intact.\n"
        "5. Focus ONLY on information relevant to the user's question above.\n"
        "6. If TEXT RETRIEVAL HINTS are provided, use them to cross-reference and verify "
        "any values you see in charts or tables. If there is a conflict, note it.\n"
        # """A “business segment” is a distinct operational unit of the company for which
        # separate financial metrics (such as EBITDA or Total Income) are explicitly reported.

        # A valid segment MUST:
        # 1. Have its own financial values (e.g., EBITDA, Total Income) shown separately.
        # 2. Appear as an individual line item in financial tables or charts.
        # 3. Represent an operational business unit (e.g., Airports, IRM, ANIL Ecosystem).

        # A segment MUST NOT:
        # 1. Be an aggregate/grouping (e.g., Consolidated, Established, Incubating).
        # 2. Be a thematic/portfolio category (e.g., Infrastructure, Energy & Utility).
        # 3. Be a generic label without separate financial data."""
        "'No relevant visual content found on this page.'\n\n"
        "Provide a structured, factual response. Do NOT speculate or hallucinate values."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}",
                    },
                },
                {"type": "text", "text": vision_prompt},
            ],
        }
    ]

    # ── Primary: Llama 4 Scout (vision) ───────────────────────────────────────
    try:
        logger.info(
            f"[Vision] ► Calling Llama 4 Scout ─ {image_path.name}\n"
            f"         Model : {VISION_MODEL_NAME}\n"
            f"         Query : {query[:120]}"
        )
        insight = _call_groq(groq_api_key, VISION_MODEL_NAME, messages, max_tokens=1024)
        logger.info(
            "\n" + "="*60 +
            f"\n[Vision] Llama 4 Scout RESULT ─ {image_path.name} ({len(insight)} chars)" +
            "\n" + "="*60 +
            "\n" + insight +
            "\n" + "="*60
        )
        _vision_cache[cache_key] = insight
        return insight

    except Exception as exc:
        err_msg = str(exc).encode("ascii", "replace").decode("ascii")
        logger.warning(
            f"[Vision] ⚠ Primary vision model FAILED ─ {image_path.name}\n"
            f"         Error: {err_msg[:200]}"
        )

    # ── Fallback: text-only model ──────────────────────────────────────────────
    logger.info(f"[Vision] ↳ Using text-only fallback ({VISION_FALLBACK_MODEL}) for {image_path.name}")
    fallback_result = _vision_fallback(groq_api_key, image_path, query)
    _vision_cache[cache_key] = fallback_result
    return fallback_result


# ─────────────────────────────────────────────────────────────────────────────
# 4. Batch Visual Analysis (primary entry-point for rag_pipeline.py)
# ─────────────────────────────────────────────────────────────────────────────

def get_visual_insights(
    page_refs: list[tuple[str, str | int]],
    query: str,
    max_images: int = 3,
    text_hints: Optional[list] = None,
) -> list[dict]:
    """
    Analyze up to `max_images` document pages visually and return structured insights.

    Called by rag_pipeline.py AFTER textual retrieval. Implements the core
    VisDoM principle: retrieval first, vision second — never on all pages.

    Args:
        page_refs:  List of (doc_id, page_number) tuples from retrieved text chunks.
                    Duplicates are deduplicated; order is preserved (most-relevant first).
        query:      The user's original query.
        max_images: Hard cap on the number of vision API calls per query.

    Returns:
        List of dicts, one per analyzed page:
            {
                "doc_id":      str,
                "page_number": int,
                "image_path":  str,
                "insight":     str,
            }
    """
    # Deduplicate while preserving order
    seen: set[tuple[str, int]] = set()
    unique_refs: list[tuple[str, int]] = []
    for doc_id, page_num in page_refs:
        try:
            pn = int(page_num)
        except (TypeError, ValueError):
            continue
        key = (str(doc_id), pn)
        if key not in seen:
            seen.add(key)
            unique_refs.append(key)
        if len(unique_refs) >= max_images:
            break

    logger.info(
        "\n" + "-"*60 +
        f"\n[Vision] get_visual_insights: {len(page_refs)} raw refs → "
        f"{len(unique_refs)} unique (cap={max_images}) → will analyze: "
        + str([(d, p) for d, p in unique_refs]) +
        "\n" + "-"*60
    )

    import concurrent.futures

    results = []
    filtered_count = 0

    def _process_page(ref):
        doc_id, page_num = ref
        img_path = get_image_path(doc_id, page_num)
        if img_path is None:
            logger.info(f"[Vision] ✗ No cached image for {doc_id} p{page_num} — skipping visual analysis.")
            return "skip"

        # Extract hints for THIS specific page from the provided text_hints
        hint_text = ""
        if text_hints:
            page_chunks = []
            for doc in text_hints:
                # physical_page or page metadata
                d_id = doc.metadata.get("doc_id")
                p_num = doc.metadata.get("physical_page") or doc.metadata.get("page")
                if str(d_id) == str(doc_id) and str(p_num) == str(page_num):
                    page_chunks.append(doc.page_content)
            if page_chunks:
                hint_text = "--- TEXT CHUNKS FROM THIS PAGE ---\n" + "\n".join(page_chunks)

        cache_key_check = (_image_hash(img_path), _query_hash(query))
        is_cached = cache_key_check in _vision_cache
        insight = analyze_page_image(img_path, query, hint=hint_text)

        # Relevance filter: Drop pages that Scout determined had no useful data
        if "no relevant visual content found" in insight.lower():
            logger.info(f"[Vision] ✂️ Filtered out {doc_id} p{page_num} (no relevant visual content)")
            return "filtered"

        return {
            "doc_id":      doc_id,
            "page_number": page_num,
            "image_path":  str(img_path),
            "insight":     insight,
            "cached":      is_cached,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_images) as executor:
        for res in executor.map(_process_page, unique_refs):
            if res == "filtered":
                filtered_count += 1
            elif res != "skip":
                results.append(res)

    logger.info(f"[Vision] ✔ Returned {len(results)} visual insight(s) for this query ({filtered_count} filtered out).")
    return results


def clear_vision_cache() -> None:
    """Flush in-memory vision response cache (called on document re-upload)."""
    _vision_cache.clear()
    logger.info("[Vision] Response cache cleared.")
