import json
import subprocess
import urllib.parse
import os
import sys

API_KEY = os.environ.get("RESPONDIO_API_KEY", "").strip()
if not API_KEY:
    try:
        out = subprocess.check_output(
            "ps eww -p $(pgrep -f respond-io-mcp/dist/index.js) | tr ' ' '\n' | grep RESPONDIO_API_KEY",
            shell=True, text=True
        )
        API_KEY = out.strip().split("=", 1)[1]
    except Exception:
        pass
if not API_KEY:
    print("No RESPONDIO_API_KEY", file=sys.stderr)
    sys.exit(1)

MCP_BIN = "/Users/ahmedelhosseiny/Library/pnpm/bin/node"
MCP_SCRIPT = "/Users/ahmedelhosseiny/Documents/Neo/mcps/respond-io-mcp/dist/index.js"

JUNE_2026_START = 1780272000  # 2026-06-01 00:00 UTC
JUNE_2026_END = 1782864000    # 2026-07-01 00:00 UTC

SOURCE_NORMALIZE = {
    "google ads": "Google Ads",
    "meta ads": "Meta Ads",
}


def call_list_contacts(cursor_id=None, limit=100):
    args = {"limit": limit}
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
        env={"RESPONDIO_API_KEY": API_KEY, "MCP_SERVER_MODE": "stdio"},
        timeout=60,
    )
    if proc.returncode != 0:
        raise Exception(f"MCP server error: {proc.stderr[:1000]}")
    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    if not lines:
        raise Exception("Empty MCP response")
    resp = json.loads(lines[-1])
    if resp.get("result", {}).get("isError"):
        raise Exception(resp["result"]["content"][0]["text"])
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def extract_field(contact, name):
    for field in contact.get("custom_fields", []):
        if field.get("name") == name:
            return field.get("value")
    return None


def to_float(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        # handle strings like "AED 1234.5" or "1,234"
        cleaned = str(value).replace(",", "").replace("AED", "").replace("$", "").strip()
        return float(cleaned)
    except Exception:
        return None


def main():
    cursor = None
    page = 0
    total_contacts = 0
    june_records = []

    while True:
        page += 1
        data = call_list_contacts(cursor_id=cursor, limit=100)
        items = data.get("items", [])
        if not items:
            break
        total_contacts += len(items)

        for c in items:
            created_at = c.get("created_at")
            if created_at is None:
                continue
            if not (JUNE_2026_START <= created_at < JUNE_2026_END):
                continue
            source = (extract_field(c, "source") or "").strip()
            medium = (extract_field(c, "medium") or "").strip()
            if not source:
                continue
            key = source.lower()
            if key not in ("google ads", "meta ads"):
                continue
            normalized = SOURCE_NORMALIZE[key]
            revenue_raw = extract_field(c, "final_sale_value")
            revenue = to_float(revenue_raw)
            quoted_raw = extract_field(c, "quoted_value")
            quoted = to_float(quoted_raw)
            lifecycle = c.get("lifecycle") or ""
            service = extract_field(c, "service") or ""
            june_records.append({
                "id": c.get("id"),
                "source": normalized,
                "medium": medium,
                "service": service,
                "lifecycle": lifecycle,
                "final_sale_value_raw": revenue_raw,
                "final_sale_value": revenue,
                "quoted_value": quoted,
                "created_at": created_at,
            })

        next_url = data.get("pagination", {}).get("next")
        if not next_url:
            break
        parsed = urllib.parse.urlparse(next_url)
        qs = urllib.parse.parse_qs(parsed.query)
        new_cursor = qs.get("cursorId", [None])[0]
        if new_cursor is None or int(new_cursor) == int(cursor or 0):
            break
        cursor = new_cursor
        if page % 5 == 0:
            print(f"Fetched {page} pages, {total_contacts} contacts...", file=sys.stderr)

    print(f"\nTotal contacts scanned: {total_contacts}")
    print(f"June 2026 paid-media contacts: {len(june_records)}\n")

    by_source = {}
    for r in june_records:
        by_source.setdefault(r["source"], {"leads": 0, "revenue": 0.0, "quoted": 0.0, "records": []})
        by_source[r["source"]]["leads"] += 1
        if r["final_sale_value"] is not None:
            by_source[r["source"]]["revenue"] += r["final_sale_value"]
        if r["quoted_value"] is not None:
            by_source[r["source"]]["quoted"] += r["quoted_value"]
        by_source[r["source"]]["records"].append(r)

    for src, agg in by_source.items():
        print(f"--- {src} ---")
        print(f"Leads: {agg['leads']}")
        print(f"Final sale revenue (AED): {agg['revenue']:,.2f}")
        print(f"Quoted value (AED): {agg['quoted']:,.2f}")
        non_zero = [r for r in agg["records"] if r["final_sale_value"] and r["final_sale_value"] > 0]
        print(f"Contacts with non-zero revenue: {len(non_zero)}")
        print()

    # output detailed CSV for inspection
    import csv
    csv_path = "/Users/ahmedelhosseiny/Documents/Blueverse/june_paid_media_contacts.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "source", "medium", "service", "lifecycle", "final_sale_value_raw", "final_sale_value", "quoted_value", "created_at"])
        writer.writeheader()
        writer.writerows(june_records)
    print(f"Wrote details to {csv_path}")


if __name__ == "__main__":
    main()
