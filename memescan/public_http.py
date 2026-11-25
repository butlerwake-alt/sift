"""Public read-only HTTP. Backs off on 429. Never fabricates a body."""

import json
import time
import urllib.error
import urllib.request

UA = "sift-memescan-paper/1.0 (read-only; no wallet)"


class SourceUnavailable(Exception):
    """A public read failed. Callers must skip or mark n/a. Never invent a value."""


def fetch_bytes(url, method="GET", body=None, headers=None, timeout=25, attempts=4):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers
        except urllib.error.HTTPError as err:
            last = err
            if err.code == 429 or 500 <= err.code < 600:
                wait = 2 ** attempt
                retry = err.headers.get("Retry-After") if err.headers else None
                if retry and str(retry).isdigit():
                    wait = min(int(retry), 30)
                time.sleep(wait)
                continue
            raise SourceUnavailable("HTTP %s for %s" % (err.code, url)) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last = err
            time.sleep(2 ** attempt)
    raise SourceUnavailable("unavailable %s: %s" % (url, last))


def fetch_json(url, method="GET", body=None, headers=None, timeout=25, attempts=4):
    raw, _headers = fetch_bytes(url, method=method, body=body, headers=headers, timeout=timeout, attempts=attempts)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise SourceUnavailable("not json %s" % url) from err
