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
    def __init__(self, status: int, where: str = "", *, limited: bool = False) -> None:
        self.status = status
        self.where = where
        self.limited = limited
        super().__init__(f"GitHub API error: HTTP {status}" + (f" ({where})" if where else ""))


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
            try:
                with self._open(request, timeout=30) as response:
                    return json.load(response), response.headers
            except urllib.error.HTTPError as err:
                status = err.code
                remaining = (err.headers or {}).get("x-ratelimit-remaining")
                limited = status == 429 or (status == 403 and remaining == "0")
                if not (status >= 500 or limited) or attempt == self._retries:
                    raise ApiError(status, limited=limited) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == self._retries:
                    raise ApiError(0) from None
            self._log(f"retry {attempt + 1}/{self._retries}")
            self._sleep(self._pause * (attempt + 1))
        raise AssertionError("unreachable")
