"""RAG Service — Report chunk storage and retrieval using FAISS.

Provides:
  1. Indexing report text chunks with metadata
  2. Semantic search over indexed chunks (for future AI chat features)
  3. Gemini Embedding API as the embedder (Phase 1)

The FAISS index is persisted to disk so it survives server restarts.
Each call to `index_report_chunks` is idempotent (existing chunks for a
report_id are removed before re-indexing).
"""
from __future__ import annotations

import os
import json
import pickle
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Optional dependencies (graceful degradation) ────────────────────────────
try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

try:
    import faiss
    _FAISS_OK = True
except ImportError:
    _FAISS_OK = False

# ─── Config ───────────────────────────────────────────────────────────────────

_EMBED_DIM = 768          # Gemini embedding-001 dimension
_INDEX_DIR = Path(__file__).parent.parent / "rag_store"
_INDEX_PATH = _INDEX_DIR / "faiss_index.bin"
_META_PATH  = _INDEX_DIR / "chunk_metadata.json"


# ─── Embedding ────────────────────────────────────────────────────────────────

def _get_gemini_embedding(text: str) -> Optional[list[float]]:
    """Call Gemini Embedding API to get a vector for `text`."""
    import requests as _req
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"embedding-001:embedContent?key={api_key}"
    )
    payload = {
        "model": "models/embedding-001",
        "content": {"parts": [{"text": text[:2000]}]},   # Token limit
    }
    try:
        resp = _req.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            values = resp.json()["embedding"]["values"]
            return values
        else:
            print(f"[rag_service] Embedding API error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"[rag_service] Embedding request failed: {e}")
        return None


# ─── Index Management ─────────────────────────────────────────────────────────

class _RAGStore:
    """Singleton in-memory + on-disk FAISS index."""

    def __init__(self):
        self._index = None          # faiss.IndexFlatIP
        self._metadata: list[dict] = []   # Parallel to FAISS rows
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if not _FAISS_OK or not _NUMPY_OK:
            print("[rag_service] faiss/numpy not available — RAG disabled")
            self._loaded = True
            return

        _INDEX_DIR.mkdir(parents=True, exist_ok=True)

        if _INDEX_PATH.exists() and _META_PATH.exists():
            try:
                self._index = faiss.read_index(str(_INDEX_PATH))
                with open(_META_PATH, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)
                print(f"[rag_service] Loaded index ({self._index.ntotal} vectors)")
            except Exception as e:
                print(f"[rag_service] Failed to load existing index: {e}")
                self._index = None
                self._metadata = []

        if self._index is None:
            self._index = faiss.IndexFlatIP(_EMBED_DIM)
            self._metadata = []

        self._loaded = True

    def _save(self):
        if not _FAISS_OK or self._index is None:
            return
        try:
            faiss.write_index(self._index, str(_INDEX_PATH))
            with open(_META_PATH, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, ensure_ascii=False, indent=2,
                          default=str)
        except Exception as e:
            print(f"[rag_service] Failed to save index: {e}")

    def remove_report_chunks(self, report_id: int):
        """Remove all previously indexed chunks for a report (before re-indexing)."""
        self._ensure_loaded()
        if not _FAISS_OK or not _NUMPY_OK or self._index is None:
            return
        # FAISS FlatIP doesn't support selective delete, so we rebuild
        keep_idx = [i for i, m in enumerate(self._metadata)
                    if m.get("report_id") != report_id]
        if len(keep_idx) == len(self._metadata):
            return  # Nothing to remove

        vectors = np.array(
            [self._index.reconstruct(i) for i in keep_idx],
            dtype="float32",
        ) if keep_idx else np.empty((0, _EMBED_DIM), dtype="float32")

        new_index = faiss.IndexFlatIP(_EMBED_DIM)
        if vectors.size > 0:
            new_index.add(vectors)
        self._index = new_index
        self._metadata = [self._metadata[i] for i in keep_idx]
        print(f"[rag_service] Removed {len(self._metadata) + (len(self._metadata) - len(keep_idx))} chunks for report {report_id}")

    def add_chunks(self, chunks: list[dict]) -> int:
        """Add a list of chunk dicts to the index.
        
        Each chunk must have: text, report_id, care_recipient_id, section_type, chunk_type
        Returns number of chunks successfully embedded and indexed.
        """
        self._ensure_loaded()
        if not _FAISS_OK or not _NUMPY_OK or self._index is None:
            return 0

        added = 0
        for chunk in chunks:
            text = chunk.get("text", "").strip()
            if not text:
                continue
            vec = _get_gemini_embedding(text)
            if vec is None or len(vec) != _EMBED_DIM:
                continue
            vec_np = np.array([vec], dtype="float32")
            # L2 normalise so Inner Product ≈ cosine similarity
            faiss.normalize_L2(vec_np)
            self._index.add(vec_np)
            self._metadata.append({
                "text":             text[:500],
                "report_id":        chunk.get("report_id"),
                "care_recipient_id": chunk.get("care_recipient_id"),
                "section_type":     chunk.get("section_type", "GENERAL"),
                "chunk_type":       chunk.get("chunk_type", "text"),  # "text" | "table_row"
                "indexed_at":       str(datetime.utcnow()),
            })
            added += 1

        if added:
            self._save()
        return added

    def search(
        self,
        query: str,
        care_recipient_id: int,
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search for the most relevant chunks.
        
        Returns list of {text, section_type, report_id, score}.
        """
        self._ensure_loaded()
        if not _FAISS_OK or not _NUMPY_OK or self._index is None or self._index.ntotal == 0:
            return []

        vec = _get_gemini_embedding(query)
        if vec is None or len(vec) != _EMBED_DIM:
            return []

        vec_np = np.array([vec], dtype="float32")
        faiss.normalize_L2(vec_np)
        scores, indices = self._index.search(vec_np, min(top_k * 3, self._index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self._metadata[idx]
            # Filter to this patient
            if meta.get("care_recipient_id") != care_recipient_id:
                continue
            results.append({
                "text":          meta["text"],
                "section_type":  meta["section_type"],
                "report_id":     meta["report_id"],
                "score":         float(score),
            })
            if len(results) >= top_k:
                break

        return results


# ─── Global Singleton ─────────────────────────────────────────────────────────

_store = _RAGStore()


# ─── Public API ───────────────────────────────────────────────────────────────

def index_report_chunks(
    report_id: int,
    care_recipient_id: int,
    cleaned_lines: list[str],
    extracted_rows: list[dict],
) -> int:
    """Index a report's content into the RAG store.

    Creates two types of chunks:
      - "text": 5-line sliding windows of cleaned document text
      - "table_row": individual extracted lab rows (with source_text)

    Returns total chunks indexed.
    """
    # Remove stale chunks for this report first
    _store.remove_report_chunks(report_id)

    chunks: list[dict] = []
    base = {"report_id": report_id, "care_recipient_id": care_recipient_id}

    # Type 1: Sliding window text chunks (for open-ended retrieval)
    window = 5
    for i in range(0, len(cleaned_lines), window // 2):
        block = " ".join(cleaned_lines[i : i + window]).strip()
        if len(block) < 20:
            continue
        chunks.append({
            **base,
            "text":         block,
            "section_type": "TEXT",
            "chunk_type":   "text",
        })

    # Type 2: Extracted lab rows (for metric-specific retrieval)
    for row in extracted_rows:
        src = row.get("source_text") or row.get("raw_name", "")
        if not src:
            continue
        label = f"{row.get('raw_name', '')} {row.get('value', '')} {row.get('unit', '')}"
        chunks.append({
            **base,
            "text":         label.strip(),
            "section_type": row.get("section", "GENERAL"),
            "chunk_type":   "table_row",
        })

    indexed = _store.add_chunks(chunks)
    print(f"[rag_service] Indexed {indexed}/{len(chunks)} chunks for report {report_id}")
    return indexed


def search_patient_history(
    query: str,
    care_recipient_id: int,
    top_k: int = 5,
) -> list[dict]:
    """Search the RAG store for relevant historical information about a patient.
    
    Returns list of {text, section_type, report_id, score}.
    """
    return _store.search(query, care_recipient_id, top_k)
