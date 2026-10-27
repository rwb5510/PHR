"""Document file serving and household-scoped lookups.

Phase 9 lands inline Content-Disposition for previewable types so the review
inbox iframe can render PDFs and images. Phase 10 extends the mime matrix.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .auth import AUTH_DISABLED
from .models import Document, Profile, User

SUFFIX_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".xml": "application/xml",
}

INLINE_BASE_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "text/plain",
    "text/markdown",
    "application/xml",
    "text/xml",
}


def session_household_id(request: Request, db: Session) -> Optional[int]:
    user = getattr(request.state, "user", None)
    if user is not None:
        return int(user.household_id)
    if AUTH_DISABLED:
        row = db.query(User).first()
        if row:
            return int(row.household_id)
        return None
    raise HTTPException(401, "login required")


def profile_in_household(db: Session, profile_id: int, household_id: Optional[int]) -> Profile:
    q = db.query(Profile).filter(Profile.id == profile_id)
    if household_id is not None:
        q = q.filter(Profile.household_id == household_id)
    profile = q.first()
    if not profile:
        raise HTTPException(404)
    return profile


def document_in_household(db: Session, document_id: int, household_id: Optional[int]) -> Document:
    q = db.query(Document).join(Profile, Document.profile_id == Profile.id).filter(Document.id == document_id)
    if household_id is not None:
        q = q.filter(Profile.household_id == household_id)
    doc = q.first()
    if not doc:
        raise HTTPException(404)
    return doc


def resolve_media_type(filename: str, stored_mime: Optional[str]) -> str:
    stored = (stored_mime or "").strip()
    stored_base = stored.split(";")[0].strip().lower()
    suffix = os.path.splitext(filename or "")[1].lower()
    suffix_type = SUFFIX_TO_MIME.get(suffix)
    if stored_base and stored_base != "application/octet-stream":
        mime = stored
    elif suffix_type:
        mime = suffix_type
    else:
        mime = stored or "application/octet-stream"
    base = mime.split(";")[0].strip().lower()
    if base in ("text/plain", "text/markdown", "text/xml") and "charset=" not in mime.lower():
        return f"{base}; charset=utf-8"
    return mime


def content_disposition_type(media_type: str) -> str:
    base = media_type.split(";")[0].strip().lower()
    if base in INLINE_BASE_TYPES or base.startswith("image/") or base.startswith("text/"):
        return "inline"
    return "attachment"


def file_response_for_document(path: str, doc: Document) -> FileResponse:
    media_type = resolve_media_type(doc.filename, doc.mime_type)
    return FileResponse(
        path,
        filename=doc.filename,
        media_type=media_type,
        content_disposition_type=content_disposition_type(media_type),
    )
