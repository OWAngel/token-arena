"""Strict public wire format. Never include endpoint addresses or credentials."""
import datetime as dt
import json
import re

TZ = dt.timezone(dt.timedelta(hours=8))
COUNTERS = ("input_tokens", "output_tokens", "cached_input_tokens")


def today():
    return dt.datetime.now(TZ).date()


def text(value, limit=80):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError("Invalid text length")
    if any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f for c in value):
        raise ValueError("Control characters are not allowed")
    return value.strip()


def integer(value):
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("Token counters must be non-negative integers <= 1 trillion")
    return value


def validate(payload, now=None):
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload.get("version") != 1:
        raise ValueError("Unsupported report version")
    if payload.get("consent_public") is not True:
        raise ValueError("Explicit public consent is required")
    kind = payload.get("kind")
    if kind == "participant":
        return {"version": 1, "kind": kind, "consent_public": True,
                "wechat_name": text(payload.get("wechat_name"), 40)}
    if kind != "usage" or payload.get("timezone") != "Asia/Shanghai":
        raise ValueError("Expected usage report in Asia/Shanghai")
    day = dt.date.fromisoformat(payload.get("date", ""))
    if day.isoformat() != payload["date"] or not dt.date(2026, 1, 1) <= day < (now or today()):
        raise ValueError("Only completed days from 2026 onward are accepted")
    rows = payload.get("models")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Expected at most 100 models")
    models, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid model row")
        model = text(row.get("model"), 200)
        if model in seen:
            raise ValueError("Duplicate model")
        seen.add(model)
        item = {"model": model, **{k: integer(row.get(k)) for k in COUNTERS}}
        if item["cached_input_tokens"] > item["input_tokens"]:
            raise ValueError("Cached tokens must be a subset of input")
        item["total_tokens"] = item["input_tokens"] + item["output_tokens"]
        models.append(item)
    status = payload.get("coverage")
    if status not in ("partial", "recorded-window"):
        raise ValueError("Missing coverage status")
    return {"version": 1, "kind": "usage", "consent_public": True,
            "date": day.isoformat(), "timezone": "Asia/Shanghai",
            "coverage": status, "models": sorted(models, key=lambda x: x["model"])}


def issue_body(payload):
    clean = validate(payload)
    return ("Public opt-in sparkDash summary. No endpoint URL, token, or prompts.\n\n"
            "```json\n" + json.dumps(clean, ensure_ascii=False, indent=2) + "\n```\n")


def parse_body(body):
    if not isinstance(body, str) or len(body) > 60000:
        raise ValueError("Invalid issue body")
    match = re.search(r"```json\s*\n(.*?)\n```", body, re.S)
    if not match:
        raise ValueError("Expected one JSON code block")
    try:
        return validate(json.loads(match[1]))
    except RecursionError:
        raise ValueError("JSON nesting limit exceeded") from None
