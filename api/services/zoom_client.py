"""
Клиент для работы с Zoom Recording API.
Использует account_credentials grant для получения access_token.
"""
import base64
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ZoomClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.zoom_base_url,
                timeout=30.0,
            )
        return self._client

    def _auth_header_basic(self) -> str:
        auth_str = f"{settings.zoom_client_id}:{settings.zoom_client_secret}"
        return "Basic " + base64.b64encode(auth_str.encode()).decode()

    async def _refresh_token(self) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                settings.zoom_auth_url,
                headers={
                    "Authorization": self._auth_header_basic(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "account_credentials",
                    "account_id": settings.zoom_account_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 3600) - 30
            logger.info("Zoom access token obtained")

    async def _get_access_token(self) -> str:
        if not self._access_token or time.time() >= self._expires_at:
            await self._refresh_token()
        return self._access_token

    async def list_recordings(self) -> List[Dict[str, Any]]:
        token = await self._get_access_token()
        client = await self._get_client()

        params = {
            "from": None,
            "page_size": 100,
        }
        if settings.zoom_recording_days_back:
            # Zoom expects YYYY-MM-DD; берем диапазон по дням назад
            import datetime as dt

            from_date = (dt.datetime.utcnow() - dt.timedelta(days=settings.zoom_recording_days_back)).strftime(
                "%Y-%m-%d"
            )
            params["from"] = from_date

        resp = await client.get(
            f"/v2/users/{settings.zoom_user_id}/recordings",
            headers={"Authorization": f"Bearer {token}"},
            params={k: v for k, v in params.items() if v is not None},
        )
        resp.raise_for_status()
        data = resp.json()

        recordings: List[Dict[str, Any]] = []
        for meeting in data.get("meetings", []):
            topic = meeting.get("topic") or "Zoom Meeting"
            duration_minutes = meeting.get("duration") or 0
            for f in meeting.get("recording_files", []):
                download_url = f.get("download_url")
                if not download_url:
                    continue
                rec = {
                    "id": f.get("id") or f.get("file_path") or download_url,
                    "meeting_id": meeting.get("id") or meeting.get("uuid"),
                    "topic": topic,
                    "duration_seconds": (duration_minutes or 0) * 60,
                    "download_url": download_url,
                    "file_extension": f.get("file_extension"),
                    "recording_start": f.get("recording_start"),
                    "recording_type": f.get("recording_type"),
                }
                recordings.append(rec)
        return recordings

    async def download_recording(self, download_url: str, destination_path: str) -> bool:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                download_url,
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status_code >= 400:
                    logger.error(f"Failed to download zoom file: {resp.status_code}")
                    return False
                with open(destination_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
        return True

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


_zoom_client: Optional[ZoomClient] = None


def get_zoom_client() -> ZoomClient:
    global _zoom_client
    if _zoom_client is None:
        _zoom_client = ZoomClient()
    return _zoom_client

