from __future__ import annotations

import hashlib
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from . import db as db_mod
from .auth import get_conn, get_current_agent
from .config import get_settings
from .schemas import FileOut

router = APIRouter()

_CHUNK_SIZE = 1024 * 1024


@router.post("/v1/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
) -> FileOut:
    settings = get_settings()
    files_dir = settings.resolved_files_dir
    files_dir.mkdir(parents=True, exist_ok=True)

    dest_name = f"{uuid.uuid4()}.bin"
    dest_path = files_dir / dest_name
    hasher = hashlib.sha256()
    size = 0

    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"file exceeds max upload size of {settings.max_upload_mb}MB",
                    )
                hasher.update(chunk)
                out.write(chunk)
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise

    row = db_mod.insert_file(
        conn,
        filename=file.filename or "upload.bin",
        uploader_id=agent["id"],
        size_bytes=size,
        content_type=file.content_type,
        storage_path=dest_name,
        sha256=hasher.hexdigest(),
    )
    return FileOut(
        id=row["id"],
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        content_type=row["content_type"],
        sha256=row["sha256"],
        created_at=row["created_at"],
    )


@router.get("/v1/files/{file_id}")
def download_file(
    file_id: int,
    agent: sqlite3.Row = Depends(get_current_agent),
    conn: sqlite3.Connection = Depends(get_conn),
):
    # 404 (not 403) whether the file doesn't exist or the agent can't see it —
    # avoids confirming to an unauthorized agent that a given file id exists.
    if not db_mod.can_access_file(conn, agent_id=agent["id"], agent_name=agent["name"], file_id=file_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")

    row = db_mod.get_file(conn, file_id)
    settings = get_settings()
    path = settings.resolved_files_dir / row["storage_path"]
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")

    return FileResponse(
        path=path,
        filename=row["filename"],
        media_type=row["content_type"] or "application/octet-stream",
    )
