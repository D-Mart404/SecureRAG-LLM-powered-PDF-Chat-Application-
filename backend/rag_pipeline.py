import os
import logging
import langchain
langchain.debug = True
from typing import Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.chains import create_retrieval_chain, create_history_aware_retriever
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.retrievers import EnsembleRetriever
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from config import MONGODB_VECTOR_COLLECTION, MONGODB_VECTOR_INDEX, MAX_IMAGES_PER_QUERY, COHERE_API_KEY
from database import get_db
from llm_factory import get_chat_llm
import logging
from vision import get_visual_insights

logger = logging.getLogger(__name__)

_cross_encoder = None
if not COHERE_API_KEY:
    try:
        from sentence_transformers import CrossEncoder
        # Only load it once into memory
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    except Exception as e:
        logging.warning("Could not load CrossEncoder: " + str(e))
else:
    logging.info("COHERE_API_KEY found, bypassing local CrossEncoder initialization.")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Use local embeddings to avoid 401 Unauthorized API issues
_embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-base-en-v1.5" # 768 dimensions
)

from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from typing import List

class RerankingRetriever(BaseRetriever):
    base_retriever: BaseRetriever
    top_k: int = 7  # Increased from 10 → 7 for cross-section financial questions

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        # ── Stage 1: Hybrid Retrieval ─────────────────────────────────────────
        docs = self.base_retriever.invoke(query, config={"callbacks": run_manager.get_child()})

        logger.info(
            "\n" + "="*60 +
            f"\n[RETRIEVAL] Hybrid BM25+Vector candidates: {len(docs)} docs" +
            "\n" + "="*60
        )
        for i, d in enumerate(docs):
            pg  = d.metadata.get("page", "?")
            sec = d.metadata.get("section_title", "?")[:60]
            src = d.metadata.get("source", "?") 
            logger.info(f"  [{i+1:02d}] p{pg} | {src} | {sec} | {len(d.page_content)}ch")

        if not docs:
            return []

        scored = []
        if COHERE_API_KEY:
            # ── Stage 2: Cohere API Reranking ────────────────────────────
            import cohere
            logger.info(f"[RERANK] Calling Cohere API for {len(docs)} docs...")
            try:
                co = cohere.Client(api_key=COHERE_API_KEY)
                docs_text = [doc.page_content for doc in docs]
                response = co.rerank(
                    model="rerank-english-v3.0",
                    query=query,
                    documents=docs_text,
                    top_n=len(docs),
                    return_documents=False
                )
                for res in response.results:
                    scored.append((docs[res.index], res.relevance_score))
            except Exception as e:
                logger.error(f"[RERANK] Cohere failed: {e}")
                
        elif _cross_encoder is not None:
            # ── Stage 2: CrossEncoder Reranking ──────────────────────────────
            pairs = [[query, doc.page_content] for doc in docs]
            scores = _cross_encoder.predict(pairs)
            scored = list(zip(docs, scores))
            scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            final_docs = docs[:self.top_k]
            logger.info(f"[RETRIEVAL] Reranking skipped or failed — truncated to top {len(final_docs)}")
            for idx, doc in enumerate(final_docs):
                doc.metadata["score"] = float(max(len(final_docs) - idx, 1))
        else:
            logger.info(
                "\n" + "-"*60 +
                f"\n[RERANK] Reranker scores (sorted desc, top 20 shown):" +
                "\n" + "-"*60
            )
            for i, (d, s) in enumerate(scored[:20]):
                pg  = d.metadata.get("page", "?")
                sec = d.metadata.get("section_title", "?")[:55]
                logger.info(f"  [{i+1:02d}] score={s:+.4f} | p{pg} | {sec}")

            import numpy as np
            def cosine_sim(a, b):
                if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0: return 0
                return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

            # Semantic Deduplication — relaxed threshold (0.92) to preserve
            # multiple rows from the same Markdown table that are similar but
            # each carry a distinct data point (e.g. different EBITDA rows).
            final_docs = []
            selected_embeddings = []
            dedup_log = []

            for d, s in scored:
                if len(final_docs) >= self.top_k:
                    break

                # Table chunks from the SAME page are always kept together —
                # splitting an intra-page table breaks numeric cross-references.
                d_page = d.metadata.get("page")
                d_type = d.metadata.get("type", "text")
                if d_type == "table" and any(
                    fd.metadata.get("page") == d_page and
                    fd.metadata.get("type") == "table"
                    for fd in final_docs
                ):
                    # Same-page table chunk: always include, skip cosine check
                    final_docs.append(d)
                    selected_embeddings.append(
                        np.array(_embeddings.embed_query(d.page_content))
                    )
                    dedup_log.append((d, s, "KEEP (same-page table)"))
                    continue

                # Embed the chunk to check similarity with already-selected chunks
                doc_emb = np.array(_embeddings.embed_query(d.page_content))

                is_duplicate = False
                for sel_emb in selected_embeddings:
                    if cosine_sim(doc_emb, sel_emb) > 0.92:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    final_docs.append(d)
                    selected_embeddings.append(doc_emb)
                    d.metadata["score"] = float(s)
                    dedup_log.append((d, s, "KEEP"))
                else:
                    dedup_log.append((d, s, "DROPPED (cosine dup)"))

            logger.info(
                "\n" + "-"*60 +
                f"\n[DEDUP] Semantic deduplication results ({len(scored)} → {len(final_docs)} kept):" +
                "\n" + "-"*60
            )
            for d, s, decision in dedup_log:
                pg  = d.metadata.get("page", "?")
                sec = d.metadata.get("section_title", "?")[:50]
                logger.info(f"  {decision:<26} | score={s:+.4f} | p{pg} | {sec}")

        # Add chunk numbers to metadata and ensure metadata keys exist
        for i, doc in enumerate(final_docs):
            doc.metadata["chunk_number"] = i + 1
            doc.metadata["page"] = doc.metadata.get("page", "?")
            doc.metadata["section_title"] = doc.metadata.get("section_title", "Unknown Section")
            doc.metadata["type"] = doc.metadata.get("type", "text")
            if "score" not in doc.metadata:
                doc.metadata["score"] = None

        logger.info(
            "\n" + "="*60 +
            f"\n[FINAL DOCS] {len(final_docs)} chunks sent to LLM:" +
            "\n" + "="*60
        )
        for doc in final_docs:
            pg   = doc.metadata.get("page", "?")
            sec  = doc.metadata.get("section_title", "?")[:55]
            typ  = doc.metadata.get("type", "text")
            cnum = doc.metadata.get("chunk_number", "?")
            logger.info(
                f"  [q{cnum}] p{pg} | type={typ:<6} | {sec}\n"
                f"          preview: {doc.page_content[:120].replace(chr(10),' ')}..."
            )

        return final_docs

# Lazy-loaded vector store
_vector_store: MongoDBAtlasVectorSearch | None = None
_retrievers: dict[str, Any] = {}
_qa_chains: dict[str, Any] = {}
_sum_chains: dict[str, Any] = {}
EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"


def get_vector_store() -> MongoDBAtlasVectorSearch:
    global _vector_store
    if _vector_store is None:
        db = get_db()
        if db is None:
            raise RuntimeError("MongoDB is not connected. Vector search unavailable.")
        _collection = db[MONGODB_VECTOR_COLLECTION]
        _vector_store = MongoDBAtlasVectorSearch(
            collection=_collection,
            embedding=_embeddings,
            index_name=MONGODB_VECTOR_INDEX,
            relevance_score_fn="cosine",
        )
    return _vector_store


def invalidate_rag_cache() -> None:
    _retrievers.clear()
    _qa_chains.clear()
    _sum_chains.clear()


def _get_all_docs(username: str, limit: int = 4000) -> list[Document]:
    """Fetch all documents for a user from MongoDB to build BM25 index."""
    db = get_db()
    if db is None:
        logger.error("[RETRIEVAL] MongoDB is NOT connected!")
        return []
    coll = db[MONGODB_VECTOR_COLLECTION]
    # Check both top-level and metadata nested field to be absolutely sure
    cursor = coll.find({
        "$or": [
            {"metadata.uploaded_by": username},
            {"uploaded_by": username}
        ]
    }).limit(limit)
    out: list[Document] = []
    for doc in cursor:
        # Check both LangChain standard 'text' field and our custom metadata.text
        text = doc.get("text") or doc.get("page_content") or doc.get("metadata", {}).get("text")
        if text and str(text).strip():
            # Get the full metadata dictionary so we don't lose page numbers, block_ids, and types
            full_metadata = doc.get("metadata", {})

            # MongoDB Atlas Vector Search might flatten metadata to the top level.
            # We must pull these fields back into full_metadata for LangChain to use them.
            for key in ["page", "source", "section_title", "type", "block_id", "uploaded_by", "score"]:
                if key in doc and key not in full_metadata:
                    full_metadata[key] = doc[key]

            # Ensure essential keys exist
            if "uploaded_by" not in full_metadata:
                full_metadata["uploaded_by"] = username
            if "source" not in full_metadata:
                full_metadata["source"] = "Unknown"

            out.append(Document(page_content=str(text), metadata=full_metadata))

    logger.info(f"[RETRIEVAL] _get_all_docs for user '{username}': found {len(out)} documents in MongoDB")
    return out


def _build_retriever(username: str):
    # Vector Search with pre-filter for user isolation
    vs = get_vector_store()
    # Try multiple common metadata filter patterns for MongoDBAtlasVectorSearch
    base = vs.as_retriever(
        search_kwargs={
            "k": 35,
            "pre_filter": {
                "$or": [
                    {"uploaded_by": {"$eq": username}},
                    {"metadata.uploaded_by": {"$eq": username}}
                ]
            }
        }
    )
    
    # Optional Hybrid BM25 fallback
    docs = _get_all_docs(username, limit=10000)
    if len(docs) >= 1: # Always try to use BM25 if there's at least 1 doc
        logger.info(f"[RETRIEVAL] Building hybrid BM25+Vector retriever for user '{username}' with {len(docs)} docs")
        bm25 = BM25Retriever.from_documents(docs)
        bm25.k = 35  # Retrieve 35 from BM25
        # Vector gets higher weight (0.6) — better at finding dense semantic tables
        # (e.g. EBITDA comparison tables) than pure keyword BM25 matching.
        ensemble = EnsembleRetriever(retrievers=[bm25, base], weights=[0.4, 0.6])
        return RerankingRetriever(base_retriever=ensemble, top_k=7)
    
    logger.warning(f"[RETRIEVAL] No documents found for user '{username}' — using vector-only retriever")
    return RerankingRetriever(base_retriever=base, top_k=7)


def _get_retriever(username: str):
    if username not in _retrievers:
        _retrievers[username] = _build_retriever(username)
    return _retrievers[username]


VISDOM_SYSTEM_PROMPT = """<system_policy>
<role_persona>
You are an elite Financial and Multimodal Document Analyst. Your objective is to provide
high-fidelity, grounded answers based EXCLUSIVELY on the provided TEXT EVIDENCE and
VISUAL EVIDENCE from documents. You integrate insights from both textual chunks and
visual analysis of charts, tables, and diagrams to deliver comprehensive answers.
You operate with zero internal knowledge and prioritize factual accuracy above all.
</role_persona>

<grounding_rules>
    1. STRICT GROUNDING: Use only the TEXT EVIDENCE and VISUAL EVIDENCE provided below.
       If the answer is not explicitly stated in either, reply exactly with:
       'Not found in the documents.'
    2. NO HALLUCINATION: Do not guess, speculate, or use external data not present in
       the provided evidence.
    3. METRIC INTEGRITY: Quotes, numbers, and financial metrics must be extracted verbatim.
       Never paraphrase a value.
    4. TABLE PROTOCOL: Treat Markdown tables as structured row-by-row data. Match row
       labels to correct column headers.
    5. STRICT TEMPORAL MATCHING: Never mix Q2 and H1 metrics in the same comparison.
    6. NO METRIC SUBSTITUTION: Only answer using the exact metric requested.
    8. VISUAL EVIDENCE PRIORITY: When textual and visual evidence conflict, note BOTH
       and explain the discrepancy. Never silently prefer one over the other.
    9. LOGICAL AGGREGATE EXCLUSION: When asked about "segments", "divisions", or "business units", you must strictly exclude aggregate totals (the sum of the whole company). THIS RULE OVERRIDES ALL EVIDENCE. Even if the text or visual evidence explicitly refers to "Consolidated" or "Total" as a "segment", you MUST logically recognize it is a total and EXCLUDE IT.
    10. MATHEMATICAL VERIFICATION: You must independently verify any mathematical claims made in the evidence. If the visual evidence claims that a number X is greater than Y (e.g., claiming 3,199 is greater than 6,843), you MUST check the math yourself. If the evidence's math is wrong, OVERRIDE the evidence and output the mathematically correct answer.
    11. CONVERSATIONAL AWARENESS: If the user asks about the conversation itself (e.g., "What did I just ask?" or "What sentence did you use?"), prioritize the Chat History. Do NOT confuse the provided TEXT/VISUAL EVIDENCE with your own previous responses.
</grounding_rules>

<corporate_glossary>
    - "H" or "Half" = Half-Year (e.g., H1, H2, H1-25, H1-26)
    - "Q" = Quarter (e.g., Q1, Q2, Q2-26)
    - "Cr" = Crore
    - "YoY" = Year over Year
</corporate_glossary>

<citation_protocol>
    - Every claim must be followed by a citation.
    - For text evidence: [p{{page}}:q{{chunk_number}}] format.
    - For visual evidence: [visual:p{{page}}:{{doc_id}}] format.
    - Insert citation immediately after the relevant sentence or data point.
</citation_protocol>

<response_format>
You MUST wrap all of your logical deduction, math verification, and evidence filtering inside `<think>` XML tags at the very beginning of your response. This section is hidden from the user, so use it as your internal scratchpad.

Inside the `<think>` tags:
- If the question requires math/filtering, strip all commas from the numbers (e.g. convert "3,199" to 3199).
- Explicitly write out your logic (e.g. "Is 3199 > 6843? No. Discarding").
- Explicitly enforce the rule to exclude aggregate totals (like "Consolidated").

After closing the `</think>` tag, provide the final answer to the user.
Do NOT use sections like "Section A" or "Final Answer". Just write a clear, concise, and direct answer to the user's question. Use markdown formatting (bolding, lists) to make the answer easy to read. Include citations natively in your text.
</response_format>

</system_policy>
"""


def assemble_multimodal_context(
    text_docs: list[Document],
    visual_insights: list[dict],
) -> str:
    """
    Combine textual chunks and visual insights into a single structured context string.

    Format:
        TEXT EVIDENCE:
          <document_chunk ...>...</document_chunk>
          ...

        VISUAL EVIDENCE:
          [Page X of doc_id]: <insight>
          ...
    """
    parts = ["=== TEXT EVIDENCE ==="]
    for i, doc in enumerate(text_docs):
        page = doc.metadata.get("page", "?")
        chunk_num = doc.metadata.get("chunk_number", i + 1)
        source = doc.metadata.get("source", "unknown")
        parts.append(
            f"<document_chunk source='p{page}:q{chunk_num}' doc='{source}'>\n"
            f"{doc.page_content}\n"
            f"</document_chunk>"
        )

    if visual_insights:
        parts.append("\n=== VISUAL EVIDENCE ===")
        for vi in visual_insights:
            doc_id = vi.get("doc_id", "unknown")
            pg = vi.get("page_number", "?")
            insight = vi.get("insight", "")
            parts.append(f"[visual:p{pg}:{doc_id}]:\n{insight}")
    else:
        parts.append("\n=== VISUAL EVIDENCE ===\n[No visual evidence retrieved for this query]")

    return "\n\n".join(parts)

def get_rag_chain(username: str, user_query: str):
    retriever = _get_retriever(username)
    llm = get_chat_llm(0.0)  # Zero temperature for maximum factual accuracy

    system = VISDOM_SYSTEM_PROMPT + "\n\n<context>\n{context}\n</context>"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Question: {input}")
    ])

    # CRITICAL FIX: Forces LangChain to inject page number from database metadata
    # into the LLM's readable context for correct citation generation.
    document_prompt = PromptTemplate.from_template(
        "<document_chunk source='p{page}:q{chunk_number}'>\n{page_content}\n</document_chunk>"
    )

    combine = create_stuff_documents_chain(
        llm=llm, 
        prompt=prompt,
        document_prompt=document_prompt
    )
    
    history_prompt = ChatPromptTemplate.from_messages([
        ("system", "Given the above conversation and a follow up question, rephrase the follow up question to be a standalone question. Do NOT answer the question, just reformulate it."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}")
    ])
    
    history_aware_retriever = create_history_aware_retriever(llm, retriever, history_prompt)
    
    return create_retrieval_chain(history_aware_retriever, combine)


def multimodal_rag_query(
    username: str,
    query: str,
    chat_history: list,
    max_images: int = MAX_IMAGES_PER_QUERY,
) -> dict:
    """
    Full VisDoM-style Multimodal RAG pipeline.

    Pipeline stages:
      1. Textual retrieval (vector + BM25 ensemble → CrossEncoder rerank)
      2. Page image identification from retrieved chunk metadata
      3. Visual analysis of identified pages via Groq Vision API
      4. Evidence aggregation (TEXT EVIDENCE + VISUAL EVIDENCE)
      5. Three-step prompted generation (Evidence Curation → CoT → Final Answer)

    Returns:
        {
            "answer":          str,
            "text_sources":    list[dict],  # page + chunk + snippet
            "visual_sources":  list[dict],  # doc_id + page + insight snippet
            "source_pages":    list[dict],  # deduplicated (doc, page) pairs
        }
    """
    from langchain_core.messages import HumanMessage, AIMessage

    # ── Stage 0: Standalone Question Generation ──────────────────────────────
    # If there is chat history, we MUST rephrase the query to be standalone.
    # Otherwise, the Vision model (which is stateless) won't know what "it" or
    # "the increase" refers to.
    standalone_query = query
    if chat_history:
        from langchain_core.prompts import ChatPromptTemplate
        rephrase_llm = get_chat_llm(0.0)
        rephrase_prompt = ChatPromptTemplate.from_messages([
            ("system", "Given the following conversation and a follow-up question, rephrase the question to be a standalone search query. Do NOT answer it. If the question is already standalone, return it as is."),
            MessagesPlaceholder("history"),
            ("human", "{input}")
        ])
        # Convert dict history to LangChain messages
        history_msgs = []
        for m in chat_history:
            if m.get("role") == "user": history_msgs.append(HumanMessage(content=m.get("content", "")))
            else: history_msgs.append(AIMessage(content=m.get("content", "")))
        
        rephrased = rephrase_llm.invoke(rephrase_prompt.format_messages(history=history_msgs, input=query))
        standalone_query = rephrased.content if hasattr(rephrased, "content") else str(rephrased)
        logger.info(f"[QUERY] Rephrased '{query}' → '{standalone_query}'")

    # ── Stage 1: Textual Retrieval ─────────────────────────────────────────────
    retriever = _get_retriever(username)
    text_docs = retriever.invoke(standalone_query)

    # ── Stage 2: Identify Relevant Pages ──────────────────────────────────────
    # physical_page = PyMuPDF page number (content-matched at ingest time).
    # Falls back to LlamaParse page for legacy chunks without physical_page.
    import os as _os
    page_refs: list[tuple[str, str]] = []
    for doc in text_docs:
        meta   = doc.metadata
        doc_id = meta.get("doc_id") or _os.path.splitext(meta.get("source", "unknown"))[0]
        physical = meta.get("physical_page")   # set at ingest time via content-matching
        llama_p  = meta.get("page", "1")
        image_page = str(physical) if physical is not None else str(llama_p)
        page_refs.append((str(doc_id), image_page))

    logger.info(
        "\n" + "="*60 +
        f"\n[PAGE REFS] {len(page_refs)} physical page refs for visual lookup:" +
        "\n" + "="*60 +
        "\n  " + ", ".join(f"{d}:p{p}" for d, p in page_refs[:10]) +
        (" ..." if len(page_refs) > 10 else "")
    )

    # ── Stage 3: Visual Analysis ───────────────────────────────────────────────
    # Pass text_docs as hints so the Vision model can cross-reference OCR text 
    # with charts to prevent hallucinations (e.g. misreading 7,233 as 9,906).
    visual_insights = get_visual_insights(page_refs, standalone_query, max_images=max_images, text_hints=text_docs)

    logger.info(
        "\n" + "="*60 +
        f"\n[VISUAL] Llama 4 Scout analyzed {len(visual_insights)} page image(s):" +
        "\n" + "="*60
    )
    for vi in visual_insights:
        pg     = vi.get("page_number", "?")
        did    = vi.get("doc_id", "?")
        chars  = len(vi.get("insight", ""))
        cached = "(cached)" if vi.get("cached") else ""
        insight_preview = vi.get("insight", "")[:300].replace("\n", " ")
        logger.info(
            f"  [visual:p{pg}:{did}] {chars} chars {cached}\n"
            f"  Preview: {insight_preview}..."
        )
    if not visual_insights:
        logger.info("  (no page images found for retrieved pages)")

    # ── Stage 4: Evidence Aggregation ─────────────────────────────────────────
    combined_context = assemble_multimodal_context(text_docs, visual_insights)

    logger.info(
        "\n" + "="*60 +
        f"\n[CONTEXT] Assembled evidence ({len(combined_context)} total chars):" +
        "\n" + "="*60 +
        f"\n  Text chunks : {len(text_docs)}" +
        f"\n  Visual pages: {len(visual_insights)}" +
        f"\n  Context preview (first 800 chars):\n" +
        combined_context[:800].replace("\n", "\n  ") +
        "\n  ..."
    )

    # ── Stage 5: Three-Step Prompted Generation ────────────────────────────────
    # IMPORTANT: We build message objects directly (SystemMessage / HumanMessage /
    # AIMessage) and pass them straight to llm.invoke().  We deliberately avoid
    # ChatPromptTemplate.from_messages() + .format_messages() here because
    # combined_context can contain arbitrary '{...}' patterns from document
    # content (JSON, code, financial tables) that would cause a KeyError.
    from langchain_core.messages import SystemMessage
    llm = get_chat_llm(0.0)
    system_content = VISDOM_SYSTEM_PROMPT + f"\n\n<context>\n{combined_context}\n</context>"

    lc_messages = [SystemMessage(content=system_content)]
    for msg in chat_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
    lc_messages.append(HumanMessage(content=f"Question: {query}"))

    response = llm.invoke(lc_messages)
    answer = response.content if hasattr(response, "content") else str(response)
    
    # Strip <think> tags from the final answer so they are hidden from the user UI
    import re
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

    # ── Build Response ─────────────────────────────────────────────────────────
    text_sources = []
    for doc in text_docs:
        text_sources.append({
            "page":    doc.metadata.get("page", "?"),
            "chunk":   doc.metadata.get("chunk_number", "?"),
            "source":  doc.metadata.get("source", "unknown"),
            "snippet": doc.page_content[:250],
            "type":    doc.metadata.get("type", "text"),
            "section": doc.metadata.get("section_title", ""),
        })

    visual_sources = []
    for vi in visual_insights:
        visual_sources.append({
            "doc_id":       vi["doc_id"],
            "page_number":  vi["page_number"],
            "image_path":   vi["image_path"],
            "insight_snippet": vi["insight"][:300],
        })

    # Deduplicated source page list for UI display
    seen_pages: set[tuple] = set()
    source_pages = []
    for s in text_sources:
        key = (s["source"], s["page"])
        if key not in seen_pages:
            seen_pages.add(key)
            source_pages.append({"doc": s["source"], "page": s["page"]})

    return {
        "answer":         answer,
        "text_sources":   text_sources,
        "visual_sources": visual_sources,
        "source_pages":   source_pages,
    }


def get_summarize_chain(username: str):
    if username not in _sum_chains:
        retriever = _get_retriever(username)
        llm = get_chat_llm(0.0)
        
        # FIX: Removed "lab assignments" and adapted for corporate data
        system = (
            "You are a financial assistant summarizing corporate documents. "
            "Base your summary ONLY on the provided context.\n"
            "Start with a high-level overview, then break down the details by specific business segments or categories.\n"
            "If the provided context is empty or missing, DO NOT imagine content; instead, "
            "say exactly: 'Error: Context is missing or empty. Please ensure documents are uploaded.'"
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system), 
            ("human", "Context:\n{context}\n\nRequest: {input}")
        ])

        document_prompt = PromptTemplate.from_template("Source [Page {page}]:\n{page_content}")

        combine = create_stuff_documents_chain(
            llm=llm, 
            prompt=prompt,
            document_prompt=document_prompt
        )
        
        _sum_chains[username] = create_retrieval_chain(retriever, combine)
        
    return _sum_chains[username]



