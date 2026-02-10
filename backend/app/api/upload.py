"""Document upload and URL ingestion API endpoints."""
from fastapi import APIRouter, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from app.models.schema import (
    DocumentUploadResponse,
    URLRequest,
    URLIngestResponse,
    DocumentListResponse,
    DocumentDeleteResponse,
)
from app.services.rag_service import ingest_file, ingest_url, list_documents, delete_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile):
    """Upload and process a document file.

    Supports: .txt, .md, .html, .htm files

    Args:
        file: Uploaded file

    Returns:
        Document upload response with processing status
    """
    # Validate file type
    allowed_extensions = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Save file temporarily
    from pathlib import Path
    import tempfile

    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"upload_{file.filename}"

    try:
        # Write uploaded file
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Ingest file
        doc_id, chunk_count = await ingest_file(str(temp_path))

        return DocumentUploadResponse(
            document_id=doc_id,
            filename=file.filename,
            status="ready",
            chunk_count=chunk_count,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.post("/ingest-url", response_model=URLIngestResponse)
async def ingest_urls(request: URLRequest):
    """Ingest content from URLs.

    Args:
        request: URL list to ingest

    Returns:
        Ingestion results for all URLs
    """
    results = []
    total_chunks = 0

    for url in request.urls:
        try:
            doc_id, chunk_count = await ingest_url(url)
            results.append(
                DocumentUploadResponse(
                    document_id=doc_id,
                    filename=url,
                    status="ready",
                    chunk_count=chunk_count,
                )
            )
            total_chunks += chunk_count

        except Exception as e:
            results.append(
                DocumentUploadResponse(
                    document_id="",
                    filename=url,
                    status=f"failed: {str(e)}",
                    chunk_count=0,
                )
            )

    return URLIngestResponse(documents=results, total_chunks=total_chunks)


@router.get("/stats")
async def get_document_stats():
    """Get statistics about the document collection.

    Returns:
        Collection statistics
    """
    from app.services.rag_service import get_collection_stats

    stats = get_collection_stats()
    return {
        "total_documents": stats.get("count", 0),
        "collection_name": stats.get("name"),
    }


@router.delete("/clear")
async def clear_documents():
    """Clear all documents from the collection.

    Returns:
        Deletion confirmation
    """
    from app.services.rag_service import clear_collection

    clear_collection()
    return {"deleted": True, "message": "All documents cleared"}


@router.get("/list", response_model=DocumentListResponse)
async def list_document_collection():
    """Get list of all documents in the collection.

    Returns:
        List of documents with metadata
    """
    documents = list_documents()

    # Calculate totals
    total_chunks = sum(doc.get("chunk_count", 0) for doc in documents)

    return DocumentListResponse(
        documents=documents,
        total_count=len(documents),
        total_chunks=total_chunks,
    )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document_by_id(document_id: str):
    """Delete a specific document and all its chunks.

    Args:
        document_id: ID of the document to delete

    Returns:
        Deletion confirmation with chunks removed count
    """
    try:
        chunks_removed = delete_document(document_id)
        return DocumentDeleteResponse(
            deleted=True,
            document_id=document_id,
            chunks_removed=chunks_removed,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")
