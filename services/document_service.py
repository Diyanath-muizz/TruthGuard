"""
services/document_service.py
────────────────────────────
Document processing and ingestion pipeline.
Coordinates parsing, metadata validation, chunking, embedding generation,
ChromaDB indexing, BM25 indexing, SQLite persistence, and proactive conflict scans.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import settings
from database import repository
from database.models import Document, DocumentChunk
from documents.chunking import DocumentChunker, TextChunk
from documents.metadata import DocumentMetadata, extract_metadata_from_text, validate_metadata
from documents.parsers import DocumentParser, ParseResult
from retrieval.bm25_retriever import BM25Retriever
from retrieval.embedding_service import EmbeddingService
from retrieval.vector_store import VectorStore
from services.audit_service import AuditService
from services.conflict_service import ConflictService

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """
    Detailed outcome of ingesting a document.
    """
    doc_id: Optional[int]
    success: bool
    filename: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    chunk_count: int = 0
    conflict_count: int = 0


class DocumentService:
    """
    Service coordinating document ingestion, indexing synchronization,
    and metadata updates.
    """

    def __init__(self) -> None:
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.bm25_retriever = BM25Retriever()

    def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        user_metadata: Optional[Dict[str, Any]] = None,
        db_session=None,
    ) -> ProcessResult:
        warnings: List[str] = []
        errors: List[str] = []

        # 1. Size Validation
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        if len(file_bytes) > max_bytes:
            return ProcessResult(
                doc_id=None,
                success=False,
                filename=filename,
                errors=[f"File size exceeds maximum permitted limit ({settings.max_file_size_mb} MB)."],
            )

        # 2. Duplicate Detection via SHA-256 Content Hash
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        if db_session:
            existing = repository.get_document_by_hash(db_session, content_hash)
            if existing:
                return ProcessResult(
                    doc_id=existing.id,
                    success=False,
                    filename=filename,
                    errors=[f"Duplicate document detected: exactly matches existing document '{existing.filename}' (ID: {existing.id})."],
                )

        # 3. Document Parsing
        parse_result: ParseResult = self.parser.parse(file_bytes, filename)
        if not parse_result.success or not parse_result.text.strip():
            return ProcessResult(
                doc_id=None,
                success=False,
                filename=filename,
                errors=[parse_result.error or "Failed to extract usable text from uploaded file."],
            )
        warnings.extend(parse_result.warnings)

        # 4. Metadata Extraction & Merging
        # Extract from text headers
        auto_meta = extract_metadata_from_text(parse_result.text)

        # Combine: user_metadata > auto_meta
        combined_meta = dict(auto_meta)
        if user_metadata:
            for k, v in user_metadata.items():
                if v is not None and str(v).strip():
                    combined_meta[k] = v

        combined_meta["metadata_source"] = "user" if user_metadata else ("auto" if auto_meta else "inferred")

        # Fallback title to filename if not found
        if not combined_meta.get("title"):
            combined_meta["title"] = filename

        val_meta, val_warnings = validate_metadata(combined_meta)
        warnings.extend(val_warnings)

        # 5. Persist Document in SQLite
        doc = None
        if db_session:
            doc_data = {
                "filename": filename,
                "original_filename": filename,
                "content_hash": content_hash,
                "title": val_meta.title,
                "doc_type": val_meta.doc_type,
                "authority_level": val_meta.authority_level,
                "version": val_meta.version,
                "department": val_meta.department,
                "publication_date": val_meta.publication_date,
                "effective_date": val_meta.effective_date,
                "expiration_date": val_meta.expiration_date,
                "status": val_meta.status,
                "supersedes": val_meta.supersedes,
                "metadata_source": val_meta.metadata_source,
                "raw_text": parse_result.text,
            }
            doc = repository.create_document(db_session, doc_data)
            db_session.flush()

        doc_id = doc.id if doc else 1

        # 6. Text Chunking with Provenance
        chunks: List[TextChunk] = self.chunker.chunk_document(
            text=parse_result.text,
            document_id=doc_id,
            pages=parse_result.pages,
        )

        # 7. Generate Embeddings & Store in ChromaDB
        chunk_texts = [c.text for c in chunks]
        embeddings = self.embedding_service.embed_batch(chunk_texts)

        chunk_metadatas = [
            {
                "doc_id": doc_id,
                "filename": filename,
                "doc_type": val_meta.doc_type,
                "version": val_meta.version or "",
                "effective_date": val_meta.effective_date or "",
                "authority_level": val_meta.authority_level,
                "page_number": c.page_number or 1,
            }
            for c in chunks
        ]

        self.vector_store.add_chunks(
            chunks=chunks,
            embeddings=embeddings,
            metadatas=chunk_metadatas,
        )

        # 8. Persist Chunks in SQLite
        if db_session and doc:
            for c in chunks:
                repository.create_chunk(
                    db_session,
                    {
                        "document_id": doc.id,
                        "chunk_index": c.chunk_index,
                        "text": c.text,
                        "page_number": c.page_number,
                        "char_start": c.char_start,
                        "char_end": c.char_end,
                        "chroma_chunk_id": c.chunk_id,
                    },
                )
            doc.total_chunks = len(chunks)
            db_session.commit()

        # 9. Update BM25 Index
        bm25_chunk_dicts = [
            {
                "chunk_id": c.chunk_id,
                "doc_id": doc_id,
                "text": c.text,
                "metadata": chunk_metadatas[i],
            }
            for i, c in enumerate(chunks)
        ]
        self.bm25_retriever.add_documents(bm25_chunk_dicts)

        # 10. Audit Event
        if db_session:
            AuditService.log_upload(str(doc_id), filename, db_session)

        # 11. Proactive Conflict Scan
        conflict_count = 0
        if db_session and doc:
            reports = ConflictService.scan_new_document(doc.id, db_session)
            conflict_count = len(reports)

        return ProcessResult(
            doc_id=doc_id,
            success=True,
            filename=filename,
            warnings=warnings,
            chunk_count=len(chunks),
            conflict_count=conflict_count,
        )

    def delete_document(self, doc_id: int, db_session) -> bool:
        doc = repository.get_document(db_session, doc_id)
        if not doc:
            return False

        filename = doc.filename
        # Remove from vector store
        self.vector_store.delete_document(str(doc_id))

        # Remove from SQLite (cascades to chunks)
        repository.delete_document(db_session, doc_id)

        # Rebuild BM25 index from remaining documents
        all_chunks = repository.get_all_chunks(db_session)
        bm25_docs = [
            {
                "chunk_id": str(c.chroma_chunk_id or c.id),
                "doc_id": c.document_id,
                "text": c.text,
                "metadata": {"doc_id": c.document_id},
            }
            for c in all_chunks
        ]
        self.bm25_retriever.build_index(bm25_docs)

        # Audit event
        AuditService.log_delete(str(doc_id), filename, db_session)
        db_session.commit()
        return True

    def rebuild_index(self, db_session) -> Dict[str, Any]:
        """
        Re-synchronizes vector store and BM25 index completely from SQLite.
        """
        all_chunks = repository.get_all_chunks(db_session)
        all_docs = {d.id: d for d in repository.get_all_documents(db_session)}

        # Clear vector store
        self.vector_store.reset()

        # Re-embed and re-index
        texts = [c.text for c in all_chunks]
        if texts:
            embeddings = self.embedding_service.embed_batch(texts)
            fake_chunks = [
                TextChunk(
                    chunk_id=str(c.chroma_chunk_id or c.id),
                    document_id=c.document_id,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    page_number=c.page_number,
                )
                for c in all_chunks
            ]
            metas = []
            for c in all_chunks:
                d = all_docs.get(c.document_id)
                metas.append({
                    "doc_id": c.document_id,
                    "filename": d.filename if d else "",
                    "doc_type": d.doc_type if d else "Policy",
                    "authority_level": d.authority_level if d else 1,
                    "version": d.version if d else "",
                    "effective_date": d.effective_date if d else "",
                    "page_number": c.page_number or 1,
                })
            self.vector_store.add_chunks(fake_chunks, embeddings, metas)

            bm25_docs = [
                {
                    "chunk_id": str(c.chroma_chunk_id or c.id),
                    "doc_id": c.document_id,
                    "text": c.text,
                    "metadata": metas[i],
                }
                for i, c in enumerate(all_chunks)
            ]
            self.bm25_retriever.build_index(bm25_docs)

        return {"total_chunks": len(all_chunks), "total_documents": len(all_docs)}
