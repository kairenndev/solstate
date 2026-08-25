"""Minimal stdlib HTTP client for the off-chain data sources.

Kept as its own module rather than copy-pasted into each collector: politeness
rules (User-Agent, timeouts, honouring 429) should be identical everywhere.
Keyless public APIs tolerate us exactly as long as we behave, and working
without keys is a requirement here, not a preference.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "solstate/1.0 (+https://github.com/kairenndev/solstate)"
TIMEOUT = 25


class FetchError(RuntimeError):
    """Source did not return data after all attempts."""


def get_json(url: str, params: dict[str, Any] | None = None, *, retries: int = 2) -> Any:
    """GET and parse JSON, retrying and respecting rate limits.

    On 429 the server usually sends Retry-After. We follow it instead of
    guessing: a guessed delay is either too short (throttled again) or too long
    (the whole build stalls for minutes).
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    last_error: Exception | None = None

    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < retries:
                wait = exc.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.isdigit() else 5 * (attempt + 1))
                continue
            if exc.code >= 500 and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue

    raise FetchError(f"{url}: {last_error}")
