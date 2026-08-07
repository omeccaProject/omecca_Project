"""생성된 PDF 경로를 b_gateway report 테이블에 등록."""

from __future__ import annotations

from typing import Any

import requests


def register_report(
    gateway_url: str,
    *,
    event_id: int,
    pdf_path: str,
    status: str = "GENERATED",
    timeout: float = 10.0,
) -> dict[str, Any]:
    url = f"{gateway_url.rstrip('/')}/api/reports"
    payload = {
        "eventId": event_id,
        "pdfPath": pdf_path,
        "status": status,
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
