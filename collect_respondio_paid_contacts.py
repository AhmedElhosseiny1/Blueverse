#!/usr/bin/env python3
"""Collect aggregate paid-contact counts from Respond.io through the local MCP server.

This script intentionally writes aggregate counts only. It does not persist names,
phones, emails, or full raw contact payloads.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)
OUT_JSON = OUT_DIR / "respondio_paid_contacts_summary.json"
OUT_AUDIT_CSV = OUT_DIR / "respondio_paid_contacts_audit_counts.csv"

MCP_BIN = os.environ.get("RESPONDIO_MCP_NODE", "/Users/ahmedelhosseiny/Library/pnpm/bin/node")
MCP_SCRIPT = os.environ.get(
    "RESPONDIO_MCP_SCRIPT",
    "/Users/ahmedelhosseiny/Documents/New project/tools/respond-io-mcp-server.mjs",
)

JUNE_2026_START = 1780272000
JUNE_2026_END = 1782864000


def get_api_key() -> str:
    key = os.environ.get("RESPONDIO_API_KEY") or os.environ.get("RESPONDIO_API_TOKEN")
    if key:
        return key.strip()
    config_path = Path.home() / ".codex" / "config.toml"
    try:
        config_text = config_path.read_text(encoding="utf-8")
        match = re.search(
            r"(?s)\[mcp_servers\.respond_io\.env\].*?RESPONDIO_API_KEY\s*=\s*[\"']([^\"']+)",
            config_text,
        )
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            "ps eww -p $(pgrep -f respond-io-mcp/dist/index.js) | tr ' ' '\\n' | grep RESPONDIO_API_KEY",
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip().split("=", 1)[1]
    except Exception:
        return ""


def call_list_contacts(api_key: str, cursor_id: int | None = None, limit: int = 100) -> dict[str, Any]:
    args: dict[str, Any] = {"limit": limit, "timezone": "UTC"}
    if cursor_id is not None:
        args["cursorId"] = int(cursor_id)
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_contacts", "arguments": args},
    }
    proc = subprocess.run(
        [MCP_BIN, MCP_SCRIPT],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        env={"RESPONDIO_API_KEY": api_key, "MCP_SERVER_MODE": "stdio"},
        timeout=90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"MCP server error: {proc.stderr[:1000]}")
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Empty MCP response")
    resp = json.loads(lines[-1])
    if resp.get("result", {}).get("isError"):
        raise RuntimeError(resp["result"]["content"][0]["text"])
    text = resp["result"]["content"][0]["text"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected MCP response: {text[:500]}") from exc
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def next_cursor(data: dict[str, Any], current: int | None) -> int | None:
    next_url = data.get("pagination", {}).get("next") or data.get("next")
    if not next_url:
        return None
    parsed = urllib.parse.urlparse(next_url)
    cursor = urllib.parse.parse_qs(parsed.query).get("cursorId", [None])[0]
    if cursor is None:
        match = re.search(r"cursorId=([0-9]+)", str(next_url))
        cursor = match.group(1) if match else None
    if cursor is None:
        return None
    try:
        cursor_int = int(cursor)
    except ValueError:
        return None
    if current is not None and cursor_int == int(current):
        return None
    return cursor_int


def field(contact: dict[str, Any], name: str) -> Any:
    for custom_field in contact.get("custom_fields", []) or []:
        if custom_field.get("name") == name:
            return custom_field.get("value")
    return None


def tag_names(contact: dict[str, Any]) -> list[str]:
    """Return a sorted list of tag names attached to a contact."""
    tags = contact.get("tags") or []
    names = []
    for tag in tags:
        if isinstance(tag, dict):
            name = tag.get("name")
        else:
            name = str(tag)
        if name:
            names.append(str(name))
    return sorted(set(names))


def clean_text(value: Any, fallback: str = "Not set") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "null"} else fallback


def normalize_medium(value: Any) -> str:
    """Return a canonical medium label, case-normalized to avoid duplicate buckets."""
    text = clean_text(value, "Not set")
    if text.lower() == "not set":
        return "Not set"
    return text.title()


def _canonical_tokens(value: Any) -> str:
    """Return a compact lower-case token string suitable for alias matching."""
    text = clean_text(value, "").strip()
    # Remove common separators, then strip trailing "ad" / "ads" so
    # "Google Ads", "google_ads", "googel-ad" etc. collapse to the same token.
    text = re.sub(r"[\s_\-]+", "", text.lower())
    text = re.sub(r"ads?$", "", text)
    return text


def _matches_any(text: str, tokens: tuple[str, ...]) -> bool:
    normalized = _canonical_tokens(text)
    return any(token in normalized for token in tokens)


def normalize_source(value: Any) -> str:
    text = clean_text(value).strip()
    google_tokens = (
        "google", "googel", "goolge", "googl", "gclid",
        "paidsearch", "cpc", "searchads",
    )
    meta_tokens = (
        "meta", "facebook", "instagram", "fb", "ig", "fbclid",
        "paidsocial", "socialads",
    )
    if _matches_any(text, google_tokens):
        return "Google Ads"
    if _matches_any(text, meta_tokens):
        return "Meta Ads"
    return text


def source_from_medium(medium: Any) -> str | None:
    """Infer a canonical source from the medium when the source field is ambiguous."""
    text = clean_text(medium, "").strip()
    if _matches_any(text, ("paidsearch", "cpc", "searchads", "gclid")):
        return "Google Ads"
    if _matches_any(text, ("paidsocial", "socialads", "fbclid")):
        return "Meta Ads"
    return None


def is_paid_medium(value: Any) -> bool:
    lower = clean_text(value, "").lower()
    paid_markers = ("paid", "cpc", "ppc", "sem", "search ads", "social ads")
    return any(marker in lower for marker in paid_markers)


def is_paid_source(value: Any) -> bool:
    normalized = normalize_source(value)
    return normalized in {"Google Ads", "Meta Ads"}


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace("AED", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_source = Counter(r["source"] for r in records)
    by_medium = Counter(r["medium"] for r in records)
    by_lifecycle = Counter(r["lifecycle"] for r in records)
    by_service = Counter(r["service"] for r in records)
    contact_summaries = [
        {
            "id": r.get("id"),
            "created_at": r.get("created_at"),
            "source": r.get("source"),
            "source_raw": r.get("source_raw"),
            "medium": r.get("medium"),
            "lifecycle": r.get("lifecycle"),
            "service": r.get("service"),
            "quoted_value": r.get("quoted_value"),
            "final_sale_value": r.get("final_sale_value"),
            "tags": r.get("tags") or [],
        }
        for r in records
    ]
    source_financials: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"quoted_value": 0.0, "final_sale_value": 0.0, "contacts_with_quote": 0, "contacts_with_sale": 0}
    )
    service_financials: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"quoted_value": 0.0, "final_sale_value": 0.0, "contacts_with_quote": 0, "contacts_with_sale": 0}
    )
    source_lifecycle: dict[str, Counter[str]] = defaultdict(Counter)
    source_medium: dict[str, Counter[str]] = defaultdict(Counter)
    source_service: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        source_lifecycle[record["source"]][record["lifecycle"]] += 1
        source_medium[record["source"]][record["medium"]] += 1
        source_service[record["source"]][record["service"]] += 1
        for bucket, key in ((source_financials, record["source"]), (service_financials, record["service"])):
            bucket[key]["quoted_value"] += record["quoted_value"]
            bucket[key]["final_sale_value"] += record["final_sale_value"]
            bucket[key]["contacts_with_quote"] += int(record["quoted_value"] > 0)
            bucket[key]["contacts_with_sale"] += int(record["final_sale_value"] > 0)
    return {
        "total": len(records),
        "quoted_value": round(sum(r["quoted_value"] for r in records), 2),
        "final_sale_value": round(sum(r["final_sale_value"] for r in records), 2),
        "contacts_with_quote": sum(1 for r in records if r["quoted_value"] > 0),
        "contacts_with_sale": sum(1 for r in records if r["final_sale_value"] > 0),
        "by_source": dict(by_source.most_common()),
        "by_medium": dict(by_medium.most_common()),
        "by_lifecycle": dict(by_lifecycle.most_common()),
        "by_service": dict(by_service.most_common()),
        "source_financials": {
            key: {
                "quoted_value": round(value["quoted_value"], 2),
                "final_sale_value": round(value["final_sale_value"], 2),
                "contacts_with_quote": int(value["contacts_with_quote"]),
                "contacts_with_sale": int(value["contacts_with_sale"]),
            }
            for key, value in source_financials.items()
        },
        "service_financials": {
            key: {
                "quoted_value": round(value["quoted_value"], 2),
                "final_sale_value": round(value["final_sale_value"], 2),
                "contacts_with_quote": int(value["contacts_with_quote"]),
                "contacts_with_sale": int(value["contacts_with_sale"]),
            }
            for key, value in service_financials.items()
        },
        "source_lifecycle": {k: dict(v.most_common()) for k, v in sorted(source_lifecycle.items())},
        "source_medium": {k: dict(v.most_common()) for k, v in sorted(source_medium.items())},
        "source_service": {k: dict(v.most_common()) for k, v in sorted(source_service.items())},
        "contacts": contact_summaries,
    }


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        print("No RESPONDIO_API_KEY found in environment or running MCP process", file=sys.stderr)
        raise SystemExit(1)

    total_scanned = 0
    cursor: int | None = None
    page = 0
    paid_records: list[dict[str, Any]] = []
    medium_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    all_source_medium_counts: Counter[tuple[str, str]] = Counter()

    while True:
        page += 1
        data = call_list_contacts(api_key, cursor_id=cursor, limit=100)
        items = data.get("items", []) or []
        if not items:
            break
        total_scanned += len(items)
        for contact in items:
            source_raw = clean_text(field(contact, "source"))
            medium = clean_text(field(contact, "medium"))
            source = normalize_source(source_raw)
            # If the source custom field is not set but the medium clearly
            # identifies a paid channel, infer the source bucket from medium.
            if source not in {"Google Ads", "Meta Ads"}:
                inferred = source_from_medium(medium)
                if inferred:
                    source = inferred
            lifecycle = clean_text(contact.get("lifecycle"))
            service = clean_text(field(contact, "service"))
            medium = normalize_medium(medium)
            created_at = contact.get("created_at")
            source_counts[source] += 1
            medium_counts[medium] += 1
            all_source_medium_counts[(source, medium)] += 1
            if not (is_paid_medium(medium) or is_paid_source(source_raw) or source in {"Google Ads", "Meta Ads"}):
                continue
            paid_records.append(
                {
                    "id": contact.get("id"),
                    "source": source,
                    "source_raw": source_raw,
                    "medium": medium,
                    "lifecycle": lifecycle,
                    "service": service,
                    "created_at": int(created_at) if created_at else 0,
                    "quoted_value": to_float(field(contact, "quoted_value")),
                    "final_sale_value": to_float(field(contact, "final_sale_value")),
                    "tags": tag_names(contact),
                    "paid_by_medium": is_paid_medium(medium),
                    "paid_by_source": is_paid_source(source_raw),
                }
            )

        new_cursor = next_cursor(data, cursor)
        if new_cursor is None:
            break
        cursor = new_cursor
        if page % 10 == 0:
            print(f"Fetched {page} pages, scanned {total_scanned} contacts...", file=sys.stderr)
        time.sleep(0.15)

    june_paid = [
        r for r in paid_records if JUNE_2026_START <= int(r.get("created_at") or 0) < JUNE_2026_END
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mcp_tool": "respond-io-mcp:list_contacts",
        "filter_definition": {
            "paid_contact": "custom field medium contains paid/cpc/ppc/sem/search ads/social ads OR source normalizes to Google Ads / Meta Ads",
            "source_field": "custom_fields.source",
            "medium_field": "custom_fields.medium",
        },
        "total_contacts_scanned": total_scanned,
        "all_contacts_source_counts_top": dict(source_counts.most_common(25)),
        "all_contacts_medium_counts_top": dict(medium_counts.most_common(25)),
        "all_contacts_source_medium_top": [
            {"source": source, "medium": medium, "count": count}
            for (source, medium), count in all_source_medium_counts.most_common(50)
        ],
        "paid_all_time": summarize_records(paid_records),
        "paid_june_2026": summarize_records(june_paid),
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with OUT_AUDIT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scope", "dimension", "value_1", "value_2", "count"])
        for source, count in summary["paid_all_time"]["by_source"].items():
            writer.writerow(["paid_all_time", "source", source, "", count])
        for medium, count in summary["paid_all_time"]["by_medium"].items():
            writer.writerow(["paid_all_time", "medium", medium, "", count])
        for row in summary["all_contacts_source_medium_top"]:
            writer.writerow(["all_contacts", "source_medium", row["source"], row["medium"], row["count"]])

    print(json.dumps({
        "total_contacts_scanned": total_scanned,
        "paid_all_time": summary["paid_all_time"]["total"],
        "paid_june_2026": summary["paid_june_2026"]["total"],
        "paid_by_source": summary["paid_all_time"]["by_source"],
        "top_mediums": summary["paid_all_time"]["by_medium"],
        "output": str(OUT_JSON),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
