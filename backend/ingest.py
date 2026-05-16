"""PDF extraction (LlamaParse if configured, else PyPDF) and Chroma ingest."""
import logging
import os
import re
import tempfile

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_pipeline import get_vector_store, invalidate_rag_cache
from security import sanitize_filename
from vision import extract_page_images, clear_vision_cache

logger = logging.getLogger(__name__)
_MAX_BYTES = 200 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# Page Number Mapping: LlamaParse logical page → PyMuPDF physical page
# ─────────────────────────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> set:
    """
    Extract distinctive numeric tokens from text.
    Financial figures like '2,276', '39%', '1,567.4' are unique per slide
    and are the most reliable signal for cross-system page matching.
    """
    # Match integers with optional thousands-comma, optional decimal, optional %
    return set(re.findall(r'\b[\d][\d,]*(?:\.\d+)?%?\b', text))


def _build_page_mapping(
    pdf_bytes: bytes,
    llama_docs: list,
) -> dict:
    """
    Build a mapping {llama_page_str -> physical_page_int} by finding which
    physical PDF page (rendered by PyMuPDF) contains the same content as
    each LlamaParse logical page.

    Strategy (in priority order):
      1. Number overlap — financial figures are unique per slide and match
         reliably even when text formatting differs between parsers.
      2. Token overlap — falls back to word-level overlap for non-numeric pages
         (e.g. title slides, section dividers).

    Returns the mapping dict. Pages with no confident match fall back to
    the LlamaParse page number unchanged (safe degradation).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("[PageMap] PyMuPDF not installed — skipping page mapping")
        return {}

    # ── Step 1: Extract text from every physical page via PyMuPDF ─────────────
    physical_texts: dict[int, str] = {}
    physical_numbers: dict[int, set] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            text = doc[page_idx].get_text("text")
            physical_texts[page_num] = text.lower()
            physical_numbers[page_num] = _extract_numbers(text)
        doc.close()
        logger.info(f"[PageMap] Extracted text from {len(physical_texts)} physical pages")
    except Exception as exc:
        logger.warning(f"[PageMap] PyMuPDF text extraction failed: {exc}")
        return {}

    # ── Step 2: For each LlamaParse page, find the best matching physical page ─
    mapping: dict[str, int] = {}
    for llama_doc in llama_docs:
        llama_page = str(llama_doc.metadata.get("page", ""))
        if llama_page in mapping:
            continue  # already resolved

        llama_text = llama_doc.page_content
        llama_numbers = _extract_numbers(llama_text)
        llama_tokens  = set(llama_text.lower().split())

        best_phys_page = int(llama_page) if llama_page.isdigit() else 1
        best_score     = -1
        method         = "fallback"

        if llama_numbers:
            # Primary: number overlap (most distinctive for financial docs)
            for phys_page, phys_nums in physical_numbers.items():
                score = len(llama_numbers & phys_nums)
                if score > best_score:
                    best_score     = score
                    best_phys_page = phys_page
                    method         = "number-overlap"
        else:
            # Secondary: token overlap for text-heavy / non-numeric pages
            for phys_page, phys_text in physical_texts.items():
                phys_tokens = set(phys_text.split())
                score = len(llama_tokens & phys_tokens)
                if score > best_score:
                    best_score     = score
                    best_phys_page = phys_page
                    method         = "token-overlap"

        mapping[llama_page] = best_phys_page
        logger.info(
            f"[PageMap] LlamaParse p{llama_page:>3} → physical p{best_phys_page:>3} "
            f"(method={method}, score={best_score})"
        )

    return mapping


def _header_level(line: str) -> int:
    """Return 1/2/3 for markdown headers, 0 for caps headings, -1 if not a header."""
    stripped = line.strip()
    if re.match(r'^# [^#]', stripped):   return 1
    if re.match(r'^## [^#]', stripped):  return 2
    if re.match(r'^### ', stripped):     return 3
    # ALL-CAPS line (≥6 chars) treated as H1-equivalent
    if re.match(r'^[A-Z][A-Z\s\-:,]{5,}$', stripped): return 1
    return -1


def split_by_structure(text: str) -> list[dict]:
    """
    Split page text by markdown / ALL-CAPS headers while propagating the full
    parent-header breadcrumb into every section.

    Returns a list of dicts:
        {
            'content':      str,   # raw section text
            'section_path': str,   # e.g. "Airports > TOTAL INCOME"
        }

    Why this matters
    ----------------
    LlamaParse produces markdown like:

        ## Airports
        ### TOTAL INCOME
        | H1-25 | H1-26 | YoY |
        | 4,453 | 5,882 | +32%|

    The old regex-split discarded the "## Airports" line and stored only
    "### TOTAL INCOME" as the section title, creating an orphaned chunk that
    the LLM could not attribute to any segment.  This version propagates
    "Airports" down so the injected header becomes:
        --- [Source: p24:q5] | [Section: Airports > TOTAL INCOME] | ...
    """
    h1 = h2 = h3 = ""
    current_lines: list[str] = []
    sections: list[dict] = []

    def _flush():
        content = "\n".join(current_lines).strip()
        if len(content) > 30:
            parts = [p for p in [h1, h2, h3] if p]
            path = " > ".join(parts) if parts else "Document"
            sections.append({"content": content, "section_path": path})

    for raw_line in text.split("\n"):
        lvl = _header_level(raw_line)
        label = re.sub(r'^#{1,3}\s*', '', raw_line).strip()

        if lvl == 1:
            _flush()
            current_lines = [raw_line]
            h1, h2, h3 = label, "", ""

        elif lvl == 2:
            _flush()
            # Prepend the H1 ancestor so the chunk TEXT reads:
            #   # AEL Consolidated
            #   ## IRM
            #   [content...]
            # The LLM then physically sees the parent segment name.
            context_prefix = ([f"# {h1}"] if h1 else [])
            current_lines = context_prefix + [raw_line]
            h2, h3 = label, ""

        elif lvl == 3:
            _flush()
            # Prepend BOTH parent ancestors so the chunk TEXT reads:
            #   ## IRM
            #   ### TOTAL INCOME
            #   Q2-25: 9,697 | Q2-26: 6,843 | -29%
            # Without this, "IRM" was absent from the chunk and the LLM
            # falsely attributed the 29% drop to the whole company.
            context_prefix = []
            if h1: context_prefix.append(f"# {h1}")
            if h2: context_prefix.append(f"## {h2}")
            current_lines = context_prefix + [raw_line]
            h3 = label

        else:
            current_lines.append(raw_line)

    _flush()  # flush last section
    return sections

def detect_type(text: str) -> str:
    import re
    digit_ratio = sum(c.isdigit() for c in text) / max(len(text), 1)
    if "|" in text or digit_ratio > 0.2:
        return "table"
    if "%" in text and digit_ratio > 0.1:
        return "chart"
    return "text"

def get_splitter(content_type: str):
    if content_type == "table":
        # Optimum: 1000 chars keeps a full financial Markdown table intact
        # (typically 8-12 rows × ~80 chars = ~960 chars per table block).
        # 700 was too small (split mid-row), 1500 was too large (Groq 413 error
        # because 15 chunks × ~375 tokens pushes over the 6000-token limit).
        return RecursiveCharacterTextSplitter(chunk_size=1100, chunk_overlap=150)
    elif content_type == "chart":
        return RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    else:
        return RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)




def _pypdf_text(path: str) -> list:
    return PyPDFLoader(path).load()


def _llama_parse_text(path: str) -> list | None:
    key = os.getenv("LLAMA_CLOUD_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests
        import time
        from langchain_core.documents import Document
        
        headers = {"Authorization": f"Bearer {key}", "accept": "application/json"}
        base_url = "https://api.cloud.llamaindex.ai/api/parsing"
        
        with requests.Session() as session:
            session.headers.update(headers)
            
            # 1. Upload to LlamaCloud with Premium Vision Mode Enabled
            with open(path, "rb") as f:
                upload_res = session.post(
                    f"{base_url}/upload",
                    data={
                        "premium_mode": "true",
                        "parsing_instruction": (
                            "Extract all text, tables, charts, and graphs perfectly. "
                            "Output all structured, tabular, and graphical data strictly in Markdown format (tables). "
                            "Do NOT generate conversational summaries or AI interpretations of the data. "
                            "Preserve exact numbers, distinct column headers, row labels, and axis labels exactly as they appear."
                        )
                    },
                    files={"file": (os.path.basename(path), f, "application/pdf")}
                )
            upload_res.raise_for_status()
            job_id = upload_res.json().get("id")
            if not job_id:
                return None
                
            # 2. Optimized Progressive Polling (Backoff)
            # Check fast initially for short PDFs, then slow down for massive PDFs
            # to avoid getting rate-limited or wasting API calls.
            sleep_time = 2
            max_sleep = 3 # Reduced from 10 to avoid oversleeping when the job is actually done
            max_duration = 300 # 5 minutes max total wait
            elapsed = 0
            
            while elapsed < max_duration:
                status_res = session.get(f"{base_url}/job/{job_id}")
                status_data = status_res.json()
                
                if status_data.get("status") == "SUCCESS":
                    break
                elif status_data.get("status") == "ERROR":
                    return None
                    
                time.sleep(sleep_time)
                elapsed += sleep_time
                # Gradually increase polling interval up to max_sleep
                sleep_time = min(sleep_time + 1, max_sleep)
            else:
                return None # Timeout
                
            # 3. Retrieve JSON Result
            res = session.get(f"{base_url}/job/{job_id}/result/json")
            res.raise_for_status()
            pages = res.json().get("pages", [])
            
        # 4. Map to Langchain Documents with Metadata
        docs: list[Document] = []
        for i,p in enumerate(pages):
            t = p.get("md") or p.get("text")
            if t:
                docs.append(Document(page_content=str(t), metadata={"page": p.get("page", i+1),"source": os.path.basename(path)}))#,"uploaded_by":username
                print(docs[-1].metadata)
                
        print(f"[SUCCESS] Successfully parsed {len(docs)} pages using LlamaParse API!")
        return docs if docs else None
        
    except Exception as e:
        # Safely capture the error string without crashing the Windows console
        err_msg = str(e).encode('ascii', 'replace').decode('ascii')
        print(f"[ERROR] LlamaParse HTTP API Error: {err_msg}")
        # If it's an HTTPError, we can extract the response text to see WHY it failed
        if hasattr(e, 'response') and e.response is not None:
            resp_text = e.response.text.encode('ascii', 'replace').decode('ascii')
            print(f"LlamaParse API Response: {resp_text}")
        return None


def extract_pdf_docs(raw: bytes) -> tuple[list, str]:
    if len(raw) > _MAX_BYTES:
        raise ValueError("PDF exceeds 200MB limit")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(raw)
        path = tmp.name

    parser_name = "LlamaParse API"
    try:
        docs = _llama_parse_text(path)
     
        if not docs:
            print("[FALLBACK] LlamaParse failed or returned nothing. Falling back to PyPDF for extraction...")
            parser_name = "PyPDF"
            docs = _pypdf_text(path)
    finally:
        if os.path.exists(path):
            os.remove(path)
            
    if not docs:
        raise ValueError("No extractable text from PDF")
    return docs, parser_name


def ingest_pdf_bytes(raw: bytes, original_name: str, username: str) -> tuple[int, str]:
    try:
        safe = sanitize_filename(original_name)
        # doc_id is the sanitised filename without extension (used as image filename prefix)
        doc_id = os.path.splitext(safe)[0]

        import concurrent.futures

        # ── MULTIMODAL: Run LlamaParse and Image Extraction CONCURRENTLY ──────
        print(f"[Ingest] Starting LlamaParse and local Image Extraction concurrently for '{doc_id}'...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_docs = executor.submit(extract_pdf_docs, raw)
            future_images = executor.submit(extract_page_images, raw, doc_id)
            
            docs, parser_name = future_docs.result()
            page_image_map = future_images.result()

        print(f"[Ingest] {len(page_image_map)} page image(s) stored for '{doc_id}'")

        # Build LlamaParse-page → physical-page mapping using content matching.
        # This corrects the mismatch between LlamaParse's logical page numbering
        # and PyMuPDF's physical page rendering positions.
        print(f"[Ingest] Building page number mapping for '{doc_id}'...")
        page_mapping = _build_page_mapping(raw, docs)
        mapped_count = sum(1 for lp, pp in page_mapping.items() if str(lp) != str(pp))
        print(f"[Ingest] Page mapping done — {mapped_count}/{len(page_mapping)} pages remapped")
        # ─────────────────────────────────────────────────────────────────────

        # Structure-Aware Pre-processing and Chunking
        # split_by_structure now returns list[dict] with 'content' + 'section_path'
        chunks = []
        for d in docs:
            section_dicts = split_by_structure(d.page_content)

            for sec in section_dicts:
                content      = sec["content"]
                section_path = sec["section_path"]  # e.g. "Airports > TOTAL INCOME"

                content_type = detect_type(content)
                splitter     = get_splitter(content_type)

                section_chunks = splitter.create_documents(
                    [content],
                    metadatas=[d.metadata]
                )

                for i, chunk in enumerate(section_chunks):
                    # LlamaParse returns 1-indexed page numbers.
                    # Do NOT add +1 — that was turning page 18 → "19", 23 → "24", etc.
                    llama_page = chunk.metadata.get("page", 1)
                    page_str   = str(llama_page) if llama_page else "1"

                    # Resolve the physical PyMuPDF page via content-matched mapping.
                    # Direct lookup works now that page_str is correct (no +1 offset).
                    physical_page = page_mapping.get(page_str, None)
                    if physical_page is None:
                        physical_page = int(page_str) if page_str.isdigit() else 1

                    chunk.metadata["type"]          = content_type
                    chunk.metadata["section_title"] = section_path[:120]
                    chunk.metadata["block_id"]      = f"{page_str}_{i}"
                    chunk.metadata["source"]        = safe
                    chunk.metadata["doc_id"]        = doc_id
                    chunk.metadata["uploaded_by"]   = username
                    chunk.metadata["text"]          = chunk.page_content
                    chunk.metadata["page"]          = page_str
                    # physical_page is the PyMuPDF page number used for image lookup
                    chunk.metadata["physical_page"] = physical_page

                chunks.extend(section_chunks)
        # Clear previous documents for this user to prevent duplicate bloat and slow BM25.
        # Uses get_db() + MONGODB_VECTOR_COLLECTION directly — same pattern as rag_pipeline.py.
        try:
            from database import get_db
            from config import MONGODB_VECTOR_COLLECTION
            db = get_db()
            if db is not None:
                coll = db[MONGODB_VECTOR_COLLECTION]
                # Delete under both top-level and nested metadata key (LangChain stores both)
                result1 = coll.delete_many({"uploaded_by": username})
                result2 = coll.delete_many({"metadata.uploaded_by": username})
                deleted = result1.deleted_count + result2.deleted_count
                print(f"[Ingest] Cleared {deleted} old chunk(s) for user '{username}'")
            else:
                print(f"[Ingest] MongoDB not connected — skipping old chunk cleanup for '{username}'")
        except Exception as e:
            print(f"Warning: Failed to clear old chunks for user {username}: {e}")

        # Batch insert to prevent OOM errors in local HuggingFace embeddings
        vs = get_vector_store()
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            vs.add_documents(chunks[i:i + batch_size])
            
        invalidate_rag_cache()
        # Flush vision response cache so stale page insights are not reused
        # after a document is replaced with a newer version.
        clear_vision_cache()
        return len(chunks), parser_name
    except Exception as e:
        import traceback
        with open("error_trace.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
