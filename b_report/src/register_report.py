"""생성된 PDF 경로를 b_gateway report 테이블에 등록."""

from __future__ import annotations

import os
from typing import Any

import requests

# b_gateway의 GATEWAY_API_KEY 환경변수와 같은 값이어야 함 (기본값은 서로 일치)
DEFAULT_API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")


def register_report(
    gateway_url: str,
    *,
    event_id: int,
    pdf_path: str,
    status: str = "GENERATED",
    timeout: float = 10.0,
    api_key: str = DEFAULT_API_KEY,
) -> dict[str, Any]:
    url = f"{gateway_url.rstrip('/')}/api/reports"
    payload = {
        "eventId": event_id,
        "pdfPath": pdf_path,
        "status": status,
    }
    resp = requests.post(url, json=payload, timeout=timeout, headers={"X-API-Key": api_key})
    resp.raise_for_status()
    return resp.json()