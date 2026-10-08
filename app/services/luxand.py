from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

BASE_URL = "https://api.luxand.cloud"
TIMEOUT = httpx.Timeout(60.0, connect=20.0)


def _token() -> str:
    token = settings.LUXAND_API_TOKEN.strip()
    if not token:
        raise RuntimeError("LUXAND_API_TOKEN is not configured")
    return token


def _headers() -> dict[str, str]:
    return {"token": _token()}


def _raise_api_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("detail") or payload.get("message") or str(payload)
    else:
        message = str(payload)
    raise RuntimeError(f"Luxand API error ({response.status_code}): {message}")


def _json(response: httpx.Response) -> Any:
    _raise_api_error(response)
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError("Luxand returned an invalid JSON response") from exc


async def enroll_person(name: str, photo: bytes, filename: str = "face.jpg") -> str:
    data = {"name": name, "store": "1"}
    if settings.LUXAND_COLLECTION.strip():
        data["collections"] = settings.LUXAND_COLLECTION.strip()

    files = {"photos": (filename, photo, "image/jpeg")}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/v2/person",
            headers=_headers(),
            data=data,
            files=files,
        )

    payload = _json(response)
    person_id = payload.get("uuid") or payload.get("id")
    if not person_id:
        raise RuntimeError(f"Luxand enrollment succeeded but no person id was returned: {payload}")
    return str(person_id)


async def add_face(person_id: str, photo: bytes, filename: str = "face.jpg") -> dict[str, Any]:
    data = {"store": "1"}
    files = {"photos": (filename, photo, "image/jpeg")}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/v2/person/{person_id}",
            headers=_headers(),
            data=data,
            files=files,
        )

    return _json(response)


async def verify_person(person_id: str, photo: bytes, filename: str = "verify.jpg") -> dict[str, Any]:
    files = {"photo": (filename, photo, "image/jpeg")}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/photo/verify/{person_id}",
            headers=_headers(),
            files=files,
        )

    return _json(response)


def verification_passed(payload: dict[str, Any]) -> bool:
    # Luxand's official sample returns the JSON body directly. Prefer an
    # explicit boolean when the response provides one; otherwise accept the
    # documented success status. Never let an explicit false be overridden by
    # a generic success field.
    for key in ("verified", "match", "success"):
        if key in payload and isinstance(payload[key], bool):
            return payload[key]

    return str(payload.get("status", "")).lower() == "success"


async def recognize_all(photo: bytes, filename: str = "attendance.jpg") -> list[dict[str, Any]]:
    files = {"photo": (filename, photo, "image/jpeg")}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/photo/search/v2",
            headers=_headers(),
            files=files,
        )

    payload = _json(response)

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("faces")
            or payload.get("results")
            or payload.get("data")
            or []
        )

        # Some Luxand endpoints return one result instead of an array.
        if not items and (payload.get("id") or payload.get("uuid")):
            items = [payload]
    else:
        items = []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        person_id = (
            item.get("uuid")
            or item.get("person_uuid")
            or item.get("person_id")
            or item.get("id")
        )
        if not person_id:
            continue

        confidence = item.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        normalized.append(
            {
                "luxand_person_id": str(person_id),
                "name": item.get("name"),
                "confidence": confidence,
                "raw": item,
            }
        )

    return normalized
