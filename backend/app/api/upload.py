"""Document upload and URL ingestion API endpoints."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, HTTPException, File

from app.models.schema import (
    DocumentUploadResponse,
    DocumentBatchUploadResponse,
    URLRequest,
    URLIngestResponse,
    DocumentListResponse,
    DocumentDeleteResponse,
)
from app.core.config import settings
from app.services.rag_service import ingest_file, ingest_url, list_documents, delete_document

router = APIRouter(prefix="/documents", tags=["documents"])


def _allowed_extensions() -> set[str]:
    """Parse allowed file extensions from settings."""
    extensions: set[str] = set()
    for item in settings.UPLOAD_ALLOWED_EXTENSIONS.split(","):
        value = item.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        extensions.add(value)
    return extensions


def _resolve_extension(filename: str) -> str:
    """Resolve extension from file name."""
    return Path(filename).suffix.lower()


async def _process_upload(file: UploadFile) -> DocumentUploadResponse:
    """Validate, store temporarily, and ingest an uploaded file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    allowed_extensions = _allowed_extensions()
    file_ext = _resolve_extension(file.filename)
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    max_bytes = settings.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"文件内容为空: {file.filename}")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"文件过大: {file.filename} ({len(content) / 1024 / 1024:.2f}MB), "
                f"限制 {settings.MAX_UPLOAD_FILE_SIZE_MB}MB"
            ),
        )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="upload_",
            suffix=file_ext,
            delete=False,
        ) as tmp_file:
            tmp_file.write(content)
            temp_path = Path(tmp_file.name)

        doc_id, chunk_count = await ingest_file(str(temp_path))

        return DocumentUploadResponse(
            document_id=doc_id,
            filename=file.filename,
            status="ready",
            chunk_count=chunk_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}") from e

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        await file.close()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a single document."""
    return await _process_upload(file)


@router.post("/upload-batch", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch(files: list[UploadFile] = File(...)):
    """Upload and process multiple documents in one request."""
    if not files:
        raise HTTPException(status_code=400, detail="至少上传一个文件")
    if len(files) > settings.MAX_BATCH_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"单次最多上传 {settings.MAX_BATCH_UPLOAD_FILES} 个文件，"
                f"当前为 {len(files)} 个"
            ),
        )

    results: list[DocumentUploadResponse] = []
    total_chunks = 0
    success_count = 0

    for file in files:
        try:
            result = await _process_upload(file)
            success_count += 1
            total_chunks += result.chunk_count
            results.append(result)
        except HTTPException as exc:
            results.append(
                DocumentUploadResponse(
                    document_id="",
                    filename=file.filename or "unknown",
                    status=f"failed: {exc.detail}",
                    chunk_count=0,
                )
            )
        except Exception as exc:
            results.append(
                DocumentUploadResponse(
                    document_id="",
                    filename=file.filename or "unknown",
                    status=f"failed: {str(exc)}",
                    chunk_count=0,
                )
            )

    return DocumentBatchUploadResponse(
        documents=results,
        total_files=len(files),
        success_count=success_count,
        failed_count=len(files) - success_count,
        total_chunks=total_chunks,
    )


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
