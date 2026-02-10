"""RAG (Retrieval-Augmented Generation) Service.

Handles document ingestion, chunking, embedding, and retrieval using ChromaDB.
"""
import uuid
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import chromadb
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.core.config import settings, CHROMA_DIR
from app.services.embedding_service import embed_texts, embed_query
from app.models.schema import SourceDocument


# Global ChromaDB client and collection
_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def get_collection() -> chromadb.Collection:
    """Get or initialize the ChromaDB collection."""
    global _chroma_client, _collection

    if _collection is None:
        _chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
        )
        _collection = _chroma_client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    return _collection


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """Split text into chunks for embedding with semantic awareness for Chinese.

    Uses a hybrid approach:
    1. First tries to split by natural boundaries (paragraphs, sections)
    2. Then merges smaller chunks to reach target size
    3. Finally splits oversized chunks at semantic boundaries

    Args:
        text: Input text to chunk
        chunk_size: Maximum chunk size (default from settings)
        overlap: Overlap between chunks (default from settings)

    Returns:
        List of text chunks
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    # Clean the text but preserve structure
    text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces and tabs
    text = re.sub(r'\n{3,}', '\n\n', text)  # Normalize multiple newlines

    # Step 1: Split by paragraphs first (natural boundaries)
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""
    current_length = 0

    # Step 2: Merge paragraphs into chunks
    for para in paragraphs:
        para_length = len(para)

        # If paragraph alone exceeds chunk size, need to split it
        if para_length > chunk_size:
            # Save current chunk if any
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
                current_length = 0

            # Split large paragraph at semantic boundaries
            sub_chunks = _split_large_chunk(para, chunk_size)
            chunks.extend(sub_chunks)
            continue

        # Check if adding this paragraph would exceed chunk size
        if current_length + para_length + 2 > chunk_size:  # +2 for "\n\n"
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Add overlap from previous chunk's end
            if chunks and overlap > 0:
                last_chunk = chunks[-1]
                overlap_text = last_chunk[-overlap:] if len(last_chunk) > overlap else last_chunk
                current_chunk = overlap_text + "\n\n" + para
                current_length = len(overlap_text) + 2 + para_length
            else:
                current_chunk = para
                current_length = para_length
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
                current_length += 2 + para_length
            else:
                current_chunk = para
                current_length = para_length

    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def _split_large_chunk(text: str, max_size: int) -> List[str]:
    """Split a large text chunk at semantic boundaries.

    Args:
        text: Large text to split
        max_size: Maximum size for each chunk

    Returns:
        List of split chunks
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + max_size

        if end >= text_length:
            chunks.append(text[start:].strip())
            break

        # Find best break point
        break_point = _find_semantic_break_point(text, start, end, max_size)

        chunk = text[start:break_point].strip()
        if chunk:
            chunks.append(chunk)

        start = break_point

    return chunks


def _find_semantic_break_point(text: str, start: int, end: int, max_size: int) -> int:
    """Find the best semantic break point between start and end.

    Priority: Paragraph > Sentence > Clause
    """
    min_acceptable = start + max_size // 3

    # Try different break points in order of preference
    break_candidates = [
        ('\n\n', 2),   # Paragraph break
        ('\n', 1),     # Line break
        ('。', 1),     # Chinese period
        ('？', 1),     # Chinese question mark
        ('！', 1),     # Chinese exclamation
        ('；', 1),     # Chinese semicolon
        ('，', 1),     # Chinese comma
        ('. ', 2),     # English period
        ('? ', 2),     # English question
        ('! ', 2),     # English exclamation
        ('; ', 2),     # English semicolon
        (', ', 2),     # English comma
    ]

    for marker, offset in break_candidates:
        pos = text.rfind(marker, min_acceptable, end)
        if pos > min_acceptable:
            return pos + offset

    # No good break point found, use hard limit
    return end


def ingest_text(
    text: str,
    source: str,
    metadata: Optional[Dict] = None,
) -> List[str]:
    """Ingest text into the vector database.

    Args:
        text: Text content to ingest
        source: Source identifier (filename, URL, etc.)
        metadata: Additional metadata to attach

    Returns:
        List of chunk IDs created
    """
    collection = get_collection()

    # Chunk the text
    chunks = chunk_text(text)

    if not chunks:
        return []

    # Generate embeddings
    embeddings = embed_texts(chunks)

    # Prepare metadata for each chunk
    chunk_metadata = []
    for i, chunk in enumerate(chunks):
        meta = {
            "source": source,
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        if metadata:
            meta.update(metadata)
        chunk_metadata.append(meta)

    # Generate IDs
    chunk_ids = [f"{source}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]

    # Add to collection
    collection.add(
        documents=chunks,
        embeddings=embeddings,
        metadatas=chunk_metadata,
        ids=chunk_ids,
    )

    return chunk_ids


async def ingest_file(file_path: str) -> Tuple[str, int]:
    """Ingest a local file into the vector database.

    Supports text files, PDF files, and HTML files.

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (document_id, chunk_count)
    """
    path = Path(file_path)
    doc_id = str(uuid.uuid4())

    # Read file content based on file type
    if path.suffix.lower() == ".pdf":
        # Handle PDF files using pypdf
        try:
            reader = PdfReader(path)
            content_parts = []

            # Extract text from all pages
            for page in reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        content_parts.append(page_text)
                except Exception as e:
                    # Skip pages that fail to extract
                    continue

            content = "\n\n".join(content_parts)

            # If no content was extracted, raise error
            if not content or not content.strip():
                raise ValueError("无法从 PDF 中提取文本内容。PDF 可能是扫描版图片格式。")

        except Exception as e:
            raise ValueError(f"PDF 解析失败: {str(e)}")

    elif path.suffix in [".html", ".htm"]:
        # Handle HTML files
        with open(path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove scripts and styles
        for script in soup(["script", "style"]):
            script.decompose()
        content = soup.get_text(separator='\n', strip=True)

    else:
        # Handle text files (txt, md, etc.)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(path, 'r', encoding='gbk') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()

    # Validate content
    if not content or not content.strip():
        raise ValueError(f"文件内容为空: {path.name}")

    # Ingest
    chunk_ids = ingest_text(
        text=content,
        source=f"file://{path.name}",
        metadata={
            "document_id": doc_id,
            "file_path": str(path),
            "file_type": path.suffix,
        },
    )

    return doc_id, len(chunk_ids)


async def ingest_url(url: str) -> Tuple[str, int]:
    """Ingest content from a URL into the vector database.

    Args:
        url: URL to ingest

    Returns:
        Tuple of (document_id, chunk_count)
    """
    doc_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    # Parse HTML content
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    text = soup.get_text(separator='\n', strip=True)

    # Clean up text
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join([line for line in lines if line])

    # Ingest
    chunk_ids = ingest_text(
        text=text,
        source=url,
        metadata={
            "document_id": doc_id,
            "url": url,
            "type": "web",
        },
    )

    return doc_id, len(chunk_ids)


def retrieve(query: str, k: int = None, min_score: float = None) -> List[SourceDocument]:
    """Retrieve relevant documents for a query with relevance filtering and reranking.

    Args:
        query: Search query
        k: Number of documents to retrieve (default from settings)
        min_score: Minimum relevance score threshold (default from settings)

    Returns:
        List of retrieved source documents filtered by relevance
    """
    k = k or settings.RETRIEVAL_K
    min_score = min_score or settings.MIN_RELEVANCE_SCORE
    collection = get_collection()

    # Generate query embedding
    query_embedding = embed_query(query)

    # Search - retrieve more than k to allow for filtering and reranking
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k * 3,  # Retrieve 3x more for better filtering
    )

    # Format results with relevance filtering
    documents = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            # Skip None documents
            if doc is None:
                continue

            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            # Calculate relevance score (cosine similarity)
            score = (
                1 - results["distances"][0][i]
                if results.get("distances")
                else 0.0
            )

            # Only include documents above relevance threshold
            if score >= min_score:
                documents.append(
                    SourceDocument(
                        content=doc,
                        metadata=metadata or {},
                        score=score,
                    )
                )

        # Rerank by content relevance (boost exact keyword matches)
        documents = _rerank_documents(query, documents)

        # Sort by final score and limit to k results
        documents = sorted(documents, key=lambda x: x.score or 0, reverse=True)[:k]

    return documents


def _rerank_documents(query: str, documents: List[SourceDocument]) -> List[SourceDocument]:
    """Rerank documents based on query-content keyword overlap.

    This boosts documents that contain exact terms from the query.

    Args:
        query: User's query
        documents: Retrieved documents

    Returns:
        Reranked documents with updated scores
    """
    if not documents:
        return documents

    # Extract key terms from query (remove stopwords)
    stop_words = {
        "的", "是", "在", "了", "和", "与", "或", "但", "如果",
        "什么", "哪里", "谁", "如何", "为什么", "怎样", "几", "多少",
        "the", "is", "a", "an", "of", "to", "in", "for", "on", "at",
    }

    # Get meaningful terms (2+ characters for Chinese, 3+ for English)
    key_terms = set()
    for i in range(len(query)):
        # Extract 2-char Chinese terms
        if i < len(query) - 1:
            term = query[i:i+2]
            if term not in stop_words and '\u4e00' <= term[0] <= '\u9fff':
                key_terms.add(term)

    # Rerank with keyword boost
    for doc in documents:
        keyword_score = 0
        content_lower = doc.content.lower()

        # Count keyword matches
        for term in key_terms:
            if term in content_lower:
                keyword_score += 0.05  # Boost for each keyword match

        # Combine original score with keyword boost
        if doc.score:
            doc.score = min(1.0, doc.score + keyword_score)

    return documents


def get_context(documents: List[SourceDocument]) -> str:
    """Format retrieved documents into context string with clear markers.

    Args:
        documents: List of source documents

    Returns:
        Formatted context string with clear delimiters
    """
    if not documents:
        return ""

    context_parts = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source", "Unknown").replace("file://", "")
        score_str = f" (相关度: {doc.score:.1%})" if doc.score else ""
        context_parts.append(f"【参考文档{i} 来源: {source}{score_str}】\n{doc.content}")

    return "\n\n".join(context_parts)


def verify_content_relevance(query: str, documents: List[SourceDocument]) -> bool:
    """Verify that the retrieved documents actually contain relevant information.

    This is a secondary filter that checks if key terms from the query
    actually appear in the retrieved content, reducing false positives.

    Args:
        query: The user's question
        documents: Retrieved documents

    Returns:
        True if documents are likely to contain the answer
    """
    if not documents:
        return False

    # Extract key terms from the query (remove common stop words)
    stop_words = {
        "的", "是", "在", "了", "和", "与", "或", "但", "如果",
        "什么", "哪里", "谁", "如何", "为什么", "怎样", "几", "多少",
        "the", "is", "a", "an", "of", "to", "in", "for", "on", "at",
        "what", "where", "who", "how", "why", "when", "which"
    }

    # Combine all document content
    all_content = " ".join(doc.content for doc in documents)

    # For Chinese text, check each character/term
    # Split by common delimiters and also check individual Chinese characters
    query_terms = set()

    # Split by common Chinese delimiters
    for delimiter in ['的', '是', '在', '了', '和', '或', ' ', '?', '？', '的', '一个', '这个']:
        parts = query.split(delimiter)
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                query_terms.add(part)

    # Also add individual meaningful 2+ character substrings
    for i in range(len(query) - 1):
        substr = query[i:i+2]
        if substr not in stop_words:
            query_terms.add(substr)

    if not query_terms:
        return True  # No meaningful terms to check, pass through

    # Check if at least some key terms appear in the content
    matches = sum(1 for term in query_terms if term in all_content)

    # Require at least 20% of terms to match (lowered threshold for Chinese)
    return matches >= max(1, len(query_terms) * 0.2)


def get_collection_stats() -> Dict:
    """Get statistics about the vector collection.

    Returns:
        Dictionary with collection stats
    """
    collection = get_collection()
    return {
        "name": collection.name,
        "count": collection.count(),
        "metadata": collection.metadata,
    }


def clear_collection():
    """Clear all documents from the collection."""
    global _collection
    collection = get_collection()
    # Delete and recreate
    client = collection._client
    client.delete_collection(settings.COLLECTION_NAME)
    _collection = None


def list_documents() -> List[Dict]:
    """List all documents in the collection.

    Returns:
        List of document information dictionaries
    """
    collection = get_collection()

    # Get all data from collection
    result = collection.get()

    if not result or not result.get("metadatas"):
        return []

    # Group chunks by document_id
    documents = {}
    for metadata in result["metadatas"]:
        doc_id = metadata.get("document_id")
        if not doc_id:
            continue

        if doc_id not in documents:
            documents[doc_id] = {
                "document_id": doc_id,
                "source": metadata.get("source", "Unknown"),
                "chunk_count": 0,
                "file_type": metadata.get("file_type") or metadata.get("type", "unknown"),
            }
        documents[doc_id]["chunk_count"] += 1

    return list(documents.values())


def delete_document(document_id: str) -> int:
    """Delete a specific document and all its chunks from the collection.

    Args:
        document_id: ID of the document to delete

    Returns:
        Number of chunks removed

    Raises:
        ValueError: If document_id is not found
    """
    collection = get_collection()

    # Get all data to find chunks belonging to this document
    result = collection.get()

    if not result or not result.get("metadatas"):
        raise ValueError(f"Document {document_id} not found")

    # Find all chunk IDs for this document
    chunk_ids_to_delete = []
    for i, metadata in enumerate(result["metadatas"]):
        if metadata.get("document_id") == document_id:
            chunk_ids_to_delete.append(result["ids"][i])

    if not chunk_ids_to_delete:
        raise ValueError(f"Document {document_id} not found")

    # Delete the chunks
    collection.delete(ids=chunk_ids_to_delete)

    return len(chunk_ids_to_delete)
