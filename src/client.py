from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SonarError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class SonarClient:
    """Minimal pooled HTTP client for the SonarQube Web API."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        token_file: str | None = None,
        timeout: float = 20.0,
    ):
        self.base_url = (base_url or os.environ.get("SONAR_HOST_URL") or "").rstrip("/")
        self.token = token
        self.token_file = token_file
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    def check_credentials(self) -> None:
        if not self.base_url:
            raise SonarError(
                0,
                "SonarQube base URL is required: set SONAR_HOST_URL or base_url in the local credentials file.",
            )
        result = self.request("GET", "/api/authentication/validate")
        if not (isinstance(result, dict) and result.get("valid")):
            raise SonarError(0, "SonarQube token ditolak oleh /api/authentication/validate.")

    @staticmethod
    def _sanitize(text: str) -> str:
        text = re.sub(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?\S+", r"\1<redacted>", text)
        text = re.sub(r"(?i)(token\s*[:=]\s*)\S+", r"\1<redacted>", text)
        return text

    def _resolve_token(self) -> str:
        token = (self.token or os.environ.get("SONAR_TOKEN") or "").strip()
        if token:
            return token

        token_file = (self.token_file or os.environ.get("SONAR_TOKEN_FILE") or "").strip()
        if token_file:
            try:
                with open(token_file, encoding="utf-8") as handle:
                    file_token = handle.read().strip()
            except OSError as exc:
                raise SonarError(0, f"Cannot read SonarQube token file: {exc}") from exc
            if file_token:
                return file_token

        raise SonarError(
            0,
            "No SonarQube token found. Provide SONAR_TOKEN, SONAR_TOKEN_FILE, or token in "
            "~/.omp/sonar_credentials.json (USER token, bukan project token).",
        )

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/api/"):
            raise ValueError("path must start with /api/")
        if "://" in path or ".." in path or "//" in path[1:]:
            raise ValueError("path must not contain '://', '..' or '//'")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
    ) -> Any:
        self._validate_path(path)
        token = self._resolve_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = self.base_url + path

        for attempt in range(3):
            try:
                response = self._http.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise SonarError(0, self._sanitize(str(exc))) from exc

            if response.status_code in RETRYABLE_STATUS and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise SonarError(response.status_code, self._sanitize(response.text[:1000]))
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                return response.text

    def close(self) -> None:
        self._http.close()
