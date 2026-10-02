from __future__ import annotations

import httpx
from app.core.config import settings


def upload_bytes(bucket: str, path: str, data: bytes, content_type: str = "application/octet-stream") -> str | None:
    """Upload to a private Supabase Storage bucket using the backend service-role key."""
    if not settings.SUPABASE_STORAGE_ENABLED:
        return None
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase Storage is enabled but SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY is missing")
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, content=data, headers=headers)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Supabase Storage upload failed ({response.status_code}): {response.text[:300]}")
    return path
