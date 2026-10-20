"""Read MiaAI-Lab/sparkDash's UTC hourly token ledger, without modifying it."""
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

from .core import TZ, integer, text, validate

MAX_BYTES = 32 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect refused; configure the final sparkDash URL")


def endpoint(base):
    p = urllib.parse.urlsplit(base.strip())
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("Use a plain http(s) sparkDash base URL, without credentials/query/fragment")
    # The UI /tokens path is not the API base path. Reverse-proxy prefixes are supported.
    path = p.path.rstrip("/")
    if path.endswith("/tokens"):
        path = path[:-7]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path + "/api/llm-token-totals/history", "", ""))


def fetch_history(base, token=""):
    headers = {"Accept": "application/json", "User-Agent": "spark-arena/1.0"}
    if token:
        if "\r" in token or "\n" in token:
            raise ValueError("Invalid credential")
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(endpoint(base), headers=headers)
    try:
        # A local reporter connects directly. System proxies must not receive private
        # endpoint credentials or make an otherwise reachable private source fail.
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("sparkDash history is too large")
        result = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"sparkDash returned HTTP {exc.code}; check URL, version, and local token") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError("Cannot read sparkDash history; check local network/authentication") from None
    if not isinstance(result, dict):
        raise ValueError("Expected sparkDash history object")
    return result


def summarize(history, day, now=None):
    """24 UTC hour buckets spanning midnight-to-midnight at UTC+8.

    Missing traffic buckets are zero according to upstream, but upstream does not
    record monitoring uptime. 'recorded-window' never asserts full observability.
    """
    now = now or dt.datetime.now(TZ)
    start = dt.datetime.combine(day, dt.time(), TZ)
    end = start + dt.timedelta(days=1)
    if end > now:
        raise ValueError("Wait until this calendar day is complete")
    generated = history.get("generatedAt")
    if not isinstance(generated, (int, float)) or abs(now.timestamp() - generated / 1000) > 600:
        raise ValueError("sparkDash response is stale or has no generatedAt timestamp")
    hours = history.get("retention", {}).get("hours")
    if not isinstance(hours, (int, float)) or hours < 24 or start.timestamp() < generated / 1000 - hours * 3600:
        raise ValueError("Requested day is outside sparkDash hourly retention; daily UTC totals cannot substitute")
    rows = history.get("hour")
    if not isinstance(rows, list):
        raise ValueError("sparkDash version lacks hourly history")
    models, seen, first = {}, set(), None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed sparkDash history row")
        key = row.get("t", "")
        try:
            stamp = dt.datetime.strptime(key, "%Y-%m-%dT%H").replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            raise ValueError("Malformed UTC hour bucket") from None
        first = min(first, stamp) if first else stamp
        if not start <= stamp < end:
            continue
        model = text(row.get("modelId"), 200)
        identity = (key, row.get("sparkId"), row.get("port"), model)
        if identity in seen:
            raise ValueError("Duplicate sparkDash hour bucket")
        seen.add(identity)
        item = models.setdefault(model, {"model": model, "input_tokens": 0,
                                        "output_tokens": 0, "cached_input_tokens": 0})
        for dest, source in (("input_tokens", "promptTokens"), ("output_tokens", "completionTokens"),
                             ("cached_input_tokens", "cachedTokens")):
            item[dest] += integer(row.get(source, 0))
        if integer(row.get("cachedTokens", 0)) > integer(row.get("promptTokens", 0)):
            raise ValueError("Invalid sparkDash cache counters")
    payload = {"version": 1, "kind": "usage", "consent_public": True,
               "date": day.isoformat(), "timezone": "Asia/Shanghai",
               "coverage": "recorded-window" if first and first <= start else "partial",
               "models": list(models.values())}
    return validate(payload, now.date())
