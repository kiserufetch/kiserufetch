"""Minimal GitHub REST client. Error messages never include URLs: Action logs are public."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

API = "https://api.github.com"
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


class ApiError(Exception):
    def __init__(self, status: int, where: str = "", *, limited: bool = False, blocked: bool = False) -> None:
        self.status = status
        self.where = where
        self.limited = limited
        self.blocked = blocked
        super().__init__(f"GitHub API error: HTTP {status}" + (f" ({where})" if where else ""))


def _error_body(err: urllib.error.HTTPError) -> dict:
    """Parsed JSON error body, or {}. Never logged: a block notice can name the repository."""
    try:
        data = json.loads(err.read() or b"{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def next_link(header: str | None) -> str | None:
    if not header:
        return None
    match = _NEXT.search(header)
    return match.group(1) if match else None


class GitHubClient:
    def __init__(self, token: str, *, opener=urllib.request.urlopen, sleep=time.sleep,
                 retries: int = 3, pause: float = 5.0, log=print) -> None:
        self._token = token
        self._open = opener
        self._sleep = sleep
        self._retries = retries
        self._pause = pause
        self._log = log

    def get(self, path: str, params: dict | None = None) -> Any:
        data, _ = self._request(self._url(path, params))
        return data

    def list(self, path: str, params: dict | None = None, key: str | None = None) -> list:
        url: str | None = self._url(path, params)
        items: list = []
        while url:
            data, headers = self._request(url)
            items.extend(data[key] if key else data)
            url = next_link(headers.get("Link"))
        return items

    @staticmethod
    def _url(path: str, params: dict | None) -> str:
        return API + path + ("?" + urlencode(params) if params else "")

    def _request(self, url: str):
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kiserufetch-dossier",
        })
        for attempt in range(self._retries + 1):
            wait = self._pause * (attempt + 1)
            try:
                with self._open(request, timeout=30) as response:
                    return json.load(response), response.headers
            except urllib.error.HTTPError as err:
                status = err.code
                headers = err.headers or {}
                body = _error_body(err) if status in (403, 451) else {}
                message = str(body.get("message", "")).lower()
                retry_after = headers.get("retry-after")
                limited = status == 429 or (status == 403 and (
                    headers.get("x-ratelimit-remaining") == "0" or retry_after is not None or "rate limit" in message))
                blocked = not limited and ("block" in body or "access blocked" in message)
                if not (status >= 500 or limited) or attempt == self._retries:
                    raise ApiError(status, limited=limited, blocked=blocked) from None
                if retry_after and retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), 120))
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == self._retries:
                    raise ApiError(0) from None
            self._log(f"retry {attempt + 1}/{self._retries}")
            self._sleep(wait)
        raise AssertionError("unreachable")
