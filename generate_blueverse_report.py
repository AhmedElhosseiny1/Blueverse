#!/usr/bin/env python3
"""
Generate the comprehensive Blueverse paid-media report.

Inputs:
- ~/Downloads/Blueverse/{keywords,months,ad,heat map,Day Report}.csv
- ~/Downloads/blueverse meta ads june.xlsx
- ./june_paid_media_contacts.csv

Output:
- ./outputs/google_ads_report.html
"""

from __future__ import annotations

import html
import json
import math
import base64
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path.home() / "Downloads" / "Blueverse"
META_XLSX = Path.home() / "Downloads" / "blueverse meta ads june.xlsx"
RESPOND_CSV = ROOT / "june_paid_media_contacts.csv"
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)
OUT_HTML = OUT_DIR / "google_ads_report.html"
OUT_JSON = OUT_DIR / "blueverse_paid_media_data.json"
LOGO_PATH = ROOT / "assets" / "blueverse-logo.png"

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
GOOGLE_METRICS = ["Cost", "Impressions", "Clicks", "Conversions", "CTR", "CPC", "CPL", "CPM", "CVR"]
META_METRICS = ["Spend", "Impressions", "Reach", "Conversations", "CPM", "CPMC", "Frequency"]
LIFECYCLE_ORDER = [
    "New Lead",
    "Hot Lead",
    "Quotation",
    "Show Up",
    "Customer",
    "Won",
    "Cold Lead",
    "Lost",
    "NaN",
    "Not set",
]


def clean_number(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("AED", "").replace("$", "")
    if text in {"", "--", "-", "nan", "None"}:
        return 0.0
    text = text.replace(">", "").replace("<", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0


def clean_percent(value: Any) -> float:
    return clean_number(str(value).replace("%", ""))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    try:
        if den in (0, 0.0) or pd.isna(den):
            return default
        return float(num) / float(den)
    except Exception:
        return default


def fmt_money(value: float, digits: int = 0) -> str:
    if digits:
        return f"AED {value:,.{digits}f}"
    return f"AED {value:,.0f}"


def fmt_num(value: float, digits: int = 0) -> str:
    if digits:
        return f"{value:,.{digits}f}"
    return f"{value:,.0f}"


def fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}%"


def esc(value: Any) -> str:
    if pd.isna(value):
        return ""
    return html.escape(str(value), quote=True)


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def image_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    if isinstance(value, tuple):
        return [json_ready(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return 0.0
    return value


def read_google_csv(name: str, sep: str | None = None, encoding: str | None = None) -> pd.DataFrame:
    path = DATA_DIR / name
    attempts = []
    if encoding:
        attempts.append((encoding, sep))
    attempts.extend([("utf-16", sep or "\t"), ("utf-8-sig", sep or ","), ("utf-16", ","), ("utf-8-sig", "\t")])
    last_error = None
    for enc, delimiter in attempts:
        try:
            df = pd.read_csv(path, encoding=enc, sep=delimiter, skiprows=2, thousands=",")
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not read {path}: {last_error}")


def normalize_google(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename_map = {
        "Search keyword": "Keyword",
        "Search terms match type": "Match type",
        "Ad state": "Status",
        "Cost / conv.": "CPL",
        "Conv. rate": "CVR",
        "Impr.": "Impressions",
        "Search lost IS (rank)": "Lost IS Rank",
        "Search lost IS (budget)": "Lost IS Budget",
        "Search top IS": "Top IS",
        "Search abs. top IS": "Abs Top IS",
        "Search impression share": "Impr Share",
    }
    df.rename(columns={col: rename_map.get(col, col) for col in df.columns}, inplace=True)
    for col in ("Cost", "CPL", "Avg. CPC", "CPC", "CPM"):
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
    for col in ("CTR", "CVR", "Lost IS Rank", "Lost IS Budget", "Top IS", "Abs Top IS", "Impr Share"):
        if col in df.columns:
            df[col] = df[col].apply(clean_percent)
    for col in ("Impressions", "Clicks", "Conversions", "Reach"):
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
    if "Day" in df.columns:
        df["Day"] = pd.to_datetime(df["Day"], errors="coerce")
    if "Month" in df.columns:
        df["MonthDate"] = pd.to_datetime(df["Month"], format="%B %Y", errors="coerce")
        df["MonthKey"] = df["MonthDate"].dt.strftime("%Y-%m")
    return df


def add_rate_columns(df: pd.DataFrame, cost_col: str = "Cost", lead_col: str = "Conversions") -> pd.DataFrame:
    df = df.copy()
    if "CTR" not in df.columns and {"Clicks", "Impressions"}.issubset(df.columns):
        df["CTR"] = df.apply(lambda r: safe_div(r["Clicks"], r["Impressions"]) * 100, axis=1)
    if "CPC" not in df.columns and {cost_col, "Clicks"}.issubset(df.columns):
        df["CPC"] = df.apply(lambda r: safe_div(r[cost_col], r["Clicks"]), axis=1)
    if "CPL" not in df.columns and {cost_col, lead_col}.issubset(df.columns):
        df["CPL"] = df.apply(lambda r: safe_div(r[cost_col], r[lead_col]), axis=1)
    if "CPM" not in df.columns and {cost_col, "Impressions"}.issubset(df.columns):
        df["CPM"] = df.apply(lambda r: safe_div(r[cost_col], r["Impressions"]) * 1000, axis=1)
    if "CVR" not in df.columns and {"Clicks", lead_col}.issubset(df.columns):
        df["CVR"] = df.apply(lambda r: safe_div(r[lead_col], r["Clicks"]) * 100, axis=1)
    return df


def weighted_mean(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    if value_col not in df.columns or weight_col not in df.columns:
        return 0.0
    return safe_div((df[value_col] * df[weight_col]).sum(), df[weight_col].sum())


@dataclass
class SourceData:
    keywords: pd.DataFrame
    months: pd.DataFrame
    ads: pd.DataFrame
    heat: pd.DataFrame
    days: pd.DataFrame
    meta_raw: pd.DataFrame
    contacts: pd.DataFrame


def load_data() -> SourceData:
    keywords = normalize_google(read_google_csv("keywords.csv", sep=",", encoding="utf-8-sig"))
    months = normalize_google(read_google_csv("months.csv", sep="\t", encoding="utf-16"))
    ads = normalize_google(read_google_csv("ad.csv", sep="\t", encoding="utf-16"))
    heat = normalize_google(read_google_csv("heat map.csv", sep="\t", encoding="utf-16"))
    days = normalize_google(read_google_csv("Day Report.csv", sep="\t", encoding="utf-16"))

    meta = pd.read_excel(META_XLSX, sheet_name=0)
    meta.columns = [str(c).strip() for c in meta.columns]
    meta.rename(
        columns={
            "Campaign name": "Campaign",
            "Ad name": "Ad",
            "Amount spent (AED)": "Spend",
            "Messaging conversations started": "Conversations",
            "Cost per messaging conversation started": "CPMC",
            "Reporting starts": "Start",
            "Reporting ends": "End",
        },
        inplace=True,
    )
    for col in ("Spend", "Impressions", "Reach", "Conversations", "CPMC"):
        meta[col] = pd.to_numeric(meta[col], errors="coerce").fillna(0.0)
    meta["Start"] = pd.to_datetime(meta["Start"], errors="coerce")
    meta["End"] = pd.to_datetime(meta["End"], errors="coerce")
    meta["CPM"] = meta.apply(lambda r: safe_div(r["Spend"], r["Impressions"]) * 1000, axis=1)
    meta["Frequency"] = meta.apply(lambda r: safe_div(r["Impressions"], r["Reach"]), axis=1)

    contacts = pd.read_csv(RESPOND_CSV)
    contacts.columns = [str(c).strip() for c in contacts.columns]
    for col in ("final_sale_value", "quoted_value"):
        if col not in contacts.columns:
            contacts[col] = 0.0
        contacts[col] = pd.to_numeric(contacts[col], errors="coerce").fillna(0.0)
    contacts["source"] = contacts.get("source", "Not set").fillna("Not set").astype(str).replace({"nan": "Not set", "NaN": "Not set"})
    contacts["service"] = contacts.get("service", "Not set").fillna("Not set").astype(str).replace({"nan": "Not set", "NaN": "Not set", "": "Not set"})
    contacts["lifecycle"] = contacts.get("lifecycle", "Not set").fillna("Not set").astype(str).replace({"nan": "NaN", "": "Not set"})
    if "created_at" in contacts.columns:
        contacts["created_dt"] = pd.to_datetime(pd.to_numeric(contacts["created_at"], errors="coerce"), unit="s", errors="coerce")
    else:
        contacts["created_dt"] = pd.NaT

    return SourceData(keywords=keywords, months=months, ads=ads, heat=heat, days=days, meta_raw=meta, contacts=contacts)


def summarize_google(data: SourceData) -> dict[str, Any]:
    months = data.months
    days = data.days
    campaigns = (
        months.groupby("Campaign", dropna=False)
        .agg(
            Status=("Status", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
            Cost=("Cost", "sum"),
            Impressions=("Impressions", "sum"),
            Clicks=("Clicks", "sum"),
            Conversions=("Conversions", "sum"),
        )
        .reset_index()
    )
    campaigns = add_rate_columns(campaigns)
    lost = (
        days.groupby("Campaign", dropna=False)
        .apply(
            lambda g: pd.Series(
                {
                    "Lost IS Rank": weighted_mean(g, "Lost IS Rank", "Impressions"),
                    "Lost IS Budget": weighted_mean(g, "Lost IS Budget", "Impressions"),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    campaigns = campaigns.merge(lost, on="Campaign", how="left").fillna({"Lost IS Rank": 0, "Lost IS Budget": 0})

    adgroups = (
        months.groupby(["Campaign", "Ad group"], dropna=False)
        .agg(
            Status=("Status", lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown"),
            Cost=("Cost", "sum"),
            Impressions=("Impressions", "sum"),
            Clicks=("Clicks", "sum"),
            Conversions=("Conversions", "sum"),
        )
        .reset_index()
    )
    adgroups = add_rate_columns(adgroups)

    monthly = (
        months.groupby(["MonthKey", "Month"], dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
        .sort_values("MonthKey")
    )
    monthly = add_rate_columns(monthly)

    daily = (
        days.groupby("Day", dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
        .sort_values("Day")
    )
    daily = add_rate_columns(daily)
    daily["Week"] = daily["Day"].dt.to_period("W-MON").apply(lambda p: p.start_time.date().isoformat() if not pd.isna(p) else "")
    weekly = (
        daily.groupby("Week", dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
    )
    weekly = add_rate_columns(weekly)

    camp_daily = (
        days.groupby(["Campaign", "Day"], dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
        .sort_values(["Campaign", "Day"])
    )
    camp_daily = add_rate_columns(camp_daily)

    camp_weekly = camp_daily.copy()
    camp_weekly["Week"] = camp_weekly["Day"].dt.to_period("W-MON").apply(lambda p: p.start_time.date().isoformat() if not pd.isna(p) else "")
    camp_weekly = (
        camp_weekly.groupby(["Campaign", "Week"], dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
    )
    camp_weekly = add_rate_columns(camp_weekly)

    camp_monthly = months.groupby(["Campaign", "MonthKey", "Month"], dropna=False).agg(
        Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum")
    ).reset_index()
    camp_monthly = add_rate_columns(camp_monthly)

    keywords = data.keywords.copy()
    keywords = add_rate_columns(keywords)
    keywords["Recommendation"] = keywords.apply(keyword_recommendation, axis=1)

    ads = add_rate_columns(data.ads.copy())
    match_types = (
        keywords.groupby("Match type", dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reset_index()
    )
    match_types = add_rate_columns(match_types)

    heat = data.heat.copy()
    heat["Hour"] = pd.to_numeric(heat["Hour of the day"], errors="coerce").fillna(0).astype(int)
    weekday = (
        heat.groupby("Day of the week", dropna=False)
        .agg(Cost=("Cost", "sum"), Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"))
        .reindex(DAY_ORDER)
        .fillna(0)
        .reset_index()
    )
    weekday = add_rate_columns(weekday)

    totals = {
        "spend": months["Cost"].sum(),
        "impressions": months["Impressions"].sum(),
        "clicks": months["Clicks"].sum(),
        "conversions": months["Conversions"].sum(),
    }
    totals["ctr"] = safe_div(totals["clicks"], totals["impressions"]) * 100
    totals["cpc"] = safe_div(totals["spend"], totals["clicks"])
    totals["cpl"] = safe_div(totals["spend"], totals["conversions"])
    totals["cpm"] = safe_div(totals["spend"], totals["impressions"]) * 1000
    totals["cvr"] = safe_div(totals["conversions"], totals["clicks"]) * 100
    totals["lost_is_rank"] = weighted_mean(days, "Lost IS Rank", "Impressions")
    totals["lost_is_budget"] = weighted_mean(days, "Lost IS Budget", "Impressions")
    totals["date_start"] = days["Day"].min().date().isoformat()
    totals["date_end"] = days["Day"].max().date().isoformat()

    return {
        "totals": totals,
        "campaigns": campaigns.sort_values("Cost", ascending=False),
        "active_campaigns": campaigns[campaigns["Status"].str.lower().eq("enabled")].sort_values("Cost", ascending=False),
        "paused_campaigns": campaigns[~campaigns["Status"].str.lower().eq("enabled")].sort_values("Cost", ascending=False),
        "adgroups": adgroups.sort_values("Cost", ascending=False),
        "monthly": monthly,
        "daily": daily,
        "weekly": weekly,
        "camp_daily": camp_daily,
        "camp_weekly": camp_weekly,
        "camp_monthly": camp_monthly,
        "keywords": keywords.sort_values("Cost", ascending=False),
        "ads": ads.sort_values("Cost", ascending=False),
        "match_types": match_types.sort_values("Cost", ascending=False),
        "heat": heat,
        "weekday": weekday,
    }


def keyword_recommendation(row: pd.Series) -> str:
    cost = row.get("Cost", 0.0)
    conversions = row.get("Conversions", 0.0)
    ctr = row.get("CTR", 0.0)
    impressions = row.get("Impressions", 0.0)
    if conversions >= 5 and safe_div(cost, conversions) <= 250:
        return "Scale"
    if conversions >= 2:
        return "Keep"
    if cost >= 300 and conversions == 0:
        return "Pause"
    if impressions >= 500 and ctr < 1 and conversions == 0:
        return "Negative candidate"
    if cost >= 100 and conversions == 0:
        return "Monitor"
    return "Keep"


def summarize_meta(meta: pd.DataFrame) -> dict[str, Any]:
    by_campaign = meta.groupby("Campaign", dropna=False).agg(
        Spend=("Spend", "sum"),
        Impressions=("Impressions", "sum"),
        Reach=("Reach", "sum"),
        Conversations=("Conversations", "sum"),
    ).reset_index()
    by_campaign["CPMC"] = by_campaign.apply(lambda r: safe_div(r["Spend"], r["Conversations"]), axis=1)
    by_campaign["CPM"] = by_campaign.apply(lambda r: safe_div(r["Spend"], r["Impressions"]) * 1000, axis=1)
    by_campaign["Frequency"] = by_campaign.apply(lambda r: safe_div(r["Impressions"], r["Reach"]), axis=1)

    by_platform = meta.groupby("Platform", dropna=False).agg(
        Spend=("Spend", "sum"),
        Impressions=("Impressions", "sum"),
        Reach=("Reach", "sum"),
        Conversations=("Conversations", "sum"),
    ).reset_index()
    by_platform["CPMC"] = by_platform.apply(lambda r: safe_div(r["Spend"], r["Conversations"]), axis=1)
    by_platform["CPM"] = by_platform.apply(lambda r: safe_div(r["Spend"], r["Impressions"]) * 1000, axis=1)
    by_platform["Frequency"] = by_platform.apply(lambda r: safe_div(r["Impressions"], r["Reach"]), axis=1)

    by_ad = meta.groupby(["Campaign", "Ad"], dropna=False).agg(
        Spend=("Spend", "sum"),
        Impressions=("Impressions", "sum"),
        Reach=("Reach", "sum"),
        Conversations=("Conversations", "sum"),
    ).reset_index()
    by_ad["CPMC"] = by_ad.apply(lambda r: safe_div(r["Spend"], r["Conversations"]), axis=1)
    by_ad["CPM"] = by_ad.apply(lambda r: safe_div(r["Spend"], r["Impressions"]) * 1000, axis=1)
    by_ad["Frequency"] = by_ad.apply(lambda r: safe_div(r["Impressions"], r["Reach"]), axis=1)

    totals = {
        "spend": meta["Spend"].sum(),
        "impressions": meta["Impressions"].sum(),
        "reach": meta["Reach"].sum(),
        "conversations": meta["Conversations"].sum(),
        "date_start": meta["Start"].min().date().isoformat(),
        "date_end": meta["End"].max().date().isoformat(),
    }
    totals["cpmc"] = safe_div(totals["spend"], totals["conversations"])
    totals["cpm"] = safe_div(totals["spend"], totals["impressions"]) * 1000
    totals["frequency"] = safe_div(totals["impressions"], totals["reach"])
    return {
        "totals": totals,
        "campaigns": by_campaign.sort_values("Spend", ascending=False),
        "platforms": by_platform.sort_values("Spend", ascending=False),
        "ads": by_ad.sort_values("Spend", ascending=False),
    }


def summarize_respond(contacts: pd.DataFrame) -> dict[str, Any]:
    source = contacts.groupby("source", dropna=False).agg(
        Contacts=("id", "count"),
        QuotedValue=("quoted_value", "sum"),
        Revenue=("final_sale_value", "sum"),
    ).reset_index()
    lifecycle = contacts.groupby("lifecycle", dropna=False).agg(Contacts=("id", "count")).reset_index()
    lifecycle["order"] = lifecycle["lifecycle"].apply(lambda v: LIFECYCLE_ORDER.index(v) if v in LIFECYCLE_ORDER else 999)
    lifecycle = lifecycle.sort_values(["order", "Contacts"], ascending=[True, False]).drop(columns="order")
    service = contacts.groupby("service", dropna=False).agg(
        Contacts=("id", "count"),
        QuotedValue=("quoted_value", "sum"),
        Revenue=("final_sale_value", "sum"),
    ).reset_index().sort_values("Contacts", ascending=False)
    source_lifecycle = contacts.groupby(["source", "lifecycle"], dropna=False).agg(Contacts=("id", "count")).reset_index()
    source_service = contacts.groupby(["source", "service"], dropna=False).agg(Contacts=("id", "count")).reset_index().sort_values("Contacts", ascending=False)
    daily = contacts.dropna(subset=["created_dt"]).copy()
    if daily.empty:
        by_day = pd.DataFrame(columns=["Day", "Contacts"])
    else:
        daily["Day"] = daily["created_dt"].dt.strftime("%Y-%m-%d")
        by_day = daily.groupby("Day", dropna=False).agg(Contacts=("id", "count")).reset_index()

    totals = {
        "contacts": len(contacts),
        "quoted_value": contacts["quoted_value"].sum(),
        "revenue": contacts["final_sale_value"].sum(),
        "contacts_with_quote": int((contacts["quoted_value"] > 0).sum()),
        "contacts_with_sale": int((contacts["final_sale_value"] > 0).sum()),
    }
    return {
        "totals": totals,
        "source": source.sort_values("Contacts", ascending=False),
        "lifecycle": lifecycle,
        "service": service,
        "source_lifecycle": source_lifecycle,
        "source_service": source_service,
        "daily": by_day,
    }


def df_records(df: pd.DataFrame, cols: list[str], limit: int | None = None) -> list[dict[str, Any]]:
    src = df[cols].copy()
    if limit is not None:
        src = src.head(limit)
    records = src.replace({np.nan: None}).to_dict(orient="records")
    return records


def table(headers: list[str], rows: list[list[str]], class_name: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = []
        for idx, value in enumerate(row):
            cls = "num" if idx and is_numeric_text(value) else ""
            cells.append(f"<td class=\"{cls}\">{value}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<div class=\"table-wrap {class_name}\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def is_numeric_text(value: str) -> bool:
    return bool(re.match(r"^(AED |[-+]?[\d,.]+|[-+]?[\d,.]+%|--)", re.sub("<[^>]+>", "", str(value)).strip()))


def render_campaign_table(df: pd.DataFrame) -> str:
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                esc(r["Campaign"]),
                status_badge(r["Status"]),
                fmt_money(r["Cost"]),
                fmt_num(r["Impressions"]),
                fmt_num(r["Clicks"]),
                fmt_pct(r["CTR"]),
                fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
                fmt_pct(r["CVR"]),
                fmt_money(r["CPL"]),
                fmt_pct(r["Lost IS Rank"]),
                fmt_pct(r["Lost IS Budget"]),
            ]
        )
    return table(["Campaign", "Status", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CVR", "CPL", "Lost Rank", "Lost Budget"], rows)


def render_adgroup_table(df: pd.DataFrame, limit: int | None = None) -> str:
    rows = []
    for _, r in (df.head(limit) if limit else df).iterrows():
        rows.append(
            [
                esc(r["Campaign"]),
                esc(r["Ad group"]),
                status_badge(r["Status"]),
                fmt_money(r["Cost"]),
                fmt_num(r["Impressions"]),
                fmt_num(r["Clicks"]),
                fmt_pct(r["CTR"]),
                fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
                fmt_money(r["CPL"]),
            ]
        )
    return table(["Campaign", "Ad group", "Status", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CPL"], rows)


def render_keyword_table(df: pd.DataFrame, limit: int | None = None) -> str:
    rows = []
    for _, r in (df.head(limit) if limit else df).iterrows():
        rows.append(
            [
                esc(r["Keyword"]),
                esc(r["Campaign"]),
                esc(r["Match type"]),
                fmt_money(r["Cost"]),
                fmt_num(r["Impressions"]),
                fmt_num(r["Clicks"]),
                fmt_pct(r["CTR"]),
                fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
                fmt_money(r["CPL"]),
                rec_badge(r["Recommendation"]),
            ]
        )
    return table(["Keyword", "Campaign", "Match", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CPL", "Action"], rows)


def render_meta_table(df: pd.DataFrame, kind: str) -> str:
    label = {"campaign": "Campaign", "platform": "Platform", "ad": "Ad"}.get(kind, "Name")
    first_cols = {"campaign": ["Campaign"], "platform": ["Platform"], "ad": ["Campaign", "Ad"]}[kind]
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [esc(r[col]) for col in first_cols]
            + [
                fmt_money(r["Spend"]),
                fmt_num(r["Impressions"]),
                fmt_num(r["Reach"]),
                fmt_num(r["Conversations"]),
                fmt_money(r["CPMC"], 2),
                fmt_money(r["CPM"], 2),
                fmt_num(r["Frequency"], 2),
            ]
        )
    headers = first_cols + ["Spend", "Impr.", "Reach", "Msg starts", "Cost/msg", "CPM", "Freq."]
    headers[0] = label
    return table(headers, rows)


def status_badge(status: str) -> str:
    key = str(status).lower()
    cls = "good" if key == "enabled" else "muted"
    return f"<span class=\"badge {cls}\">{esc(status)}</span>"


def rec_badge(rec: str) -> str:
    key = str(rec).lower().replace(" ", "-")
    return f"<span class=\"badge action-{key}\">{esc(rec)}</span>"


def build_explorer_payload(google: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    def series_from(df: pd.DataFrame, label_col: str, period_col: str, metrics: list[str], all_label: str) -> dict[str, Any]:
        periods = sorted(str(v) for v in df[period_col].dropna().unique())
        result: dict[str, Any] = {}
        total = df.groupby(period_col).agg(
            Cost=("Cost", "sum"),
            Impressions=("Impressions", "sum"),
            Clicks=("Clicks", "sum"),
            Conversions=("Conversions", "sum"),
        ).reset_index() if "Cost" in df.columns else None
        if total is not None:
            total = add_rate_columns(total)
            result[all_label] = {
                "periods": [str(v) for v in total[period_col].tolist()],
                "metrics": {m: [round(float(x), 3) for x in total[m].tolist()] for m in metrics if m in total.columns},
            }
        for name, group in df.groupby(label_col, dropna=False):
            group = group.sort_values(period_col)
            result[str(name)] = {
                "periods": [str(v) for v in group[period_col].tolist()],
                "metrics": {m: [round(float(x), 3) for x in group[m].tolist()] for m in metrics if m in group.columns},
            }
        return {"periods": periods, "series": result}

    daily = google["camp_daily"].copy()
    daily["Day"] = daily["Day"].dt.strftime("%Y-%m-%d")
    google_day = series_from(daily, "Campaign", "Day", GOOGLE_METRICS, "All Google campaigns")
    google_week = series_from(google["camp_weekly"], "Campaign", "Week", GOOGLE_METRICS, "All Google campaigns")
    cm = google["camp_monthly"].copy()
    google_month = series_from(cm.rename(columns={"MonthKey": "Period"}), "Campaign", "Period", GOOGLE_METRICS, "All Google campaigns")

    meta_campaign = meta["campaigns"].copy()
    meta_campaign["Campaign"] = meta_campaign["Campaign"].astype(str)
    meta_campaign["Period"] = "2026-06"
    meta_campaign["Cost"] = meta_campaign["Spend"]
    meta_campaign["Conversions"] = meta_campaign["Conversations"]
    meta_campaign["CPL"] = meta_campaign["CPMC"]
    meta_campaign["Clicks"] = 0
    meta_total = pd.DataFrame(
        [
            {
                "Campaign": "All Meta campaigns",
                "Period": "2026-06",
                "Cost": meta_campaign["Cost"].sum(),
                "Impressions": meta_campaign["Impressions"].sum(),
                "Reach": meta_campaign["Reach"].sum(),
                "Conversions": meta_campaign["Conversions"].sum(),
            }
        ]
    )
    meta_total["CPM"] = meta_total.apply(lambda r: safe_div(r["Cost"], r["Impressions"]) * 1000, axis=1)
    meta_total["CPL"] = meta_total.apply(lambda r: safe_div(r["Cost"], r["Conversions"]), axis=1)
    meta_total["Frequency"] = meta_total.apply(lambda r: safe_div(r["Impressions"], r["Reach"]), axis=1)
    meta_explorer = pd.concat([meta_total, meta_campaign], ignore_index=True)

    def meta_series_payload(df: pd.DataFrame) -> dict[str, Any]:
        series = {}
        for _, row in df.iterrows():
            series[row["Campaign"]] = {
                "periods": [row["Period"]],
                "metrics": {
                    "Cost": [round(float(row["Cost"]), 3)],
                    "Impressions": [round(float(row["Impressions"]), 3)],
                    "Reach": [round(float(row["Reach"]), 3)],
                    "Conversions": [round(float(row["Conversions"]), 3)],
                    "CPM": [round(float(row["CPM"]), 3)],
                    "CPL": [round(float(row["CPL"]), 3)],
                    "Frequency": [round(float(row["Frequency"]), 3)],
                },
            }
        return {"periods": ["2026-06"], "series": series}

    meta_month = meta_series_payload(meta_explorer)

    return {"google": {"day": google_day, "week": google_week, "month": google_month}, "meta": {"month": meta_month}}


def build_chart_payloads(google: dict[str, Any], meta: dict[str, Any], respond: dict[str, Any]) -> dict[str, Any]:
    monthly = google["monthly"].copy()
    campaigns = google["campaigns"].copy()
    adgroups = google["adgroups"].copy()
    keywords = google["keywords"].copy()
    heat = google["heat"].copy()
    weekday = google["weekday"].copy()

    heat_conv = (
        heat.pivot_table(index="Day of the week", columns="Hour", values="Conversions", aggfunc="sum")
        .reindex(DAY_ORDER)
        .fillna(0)
    )
    heat_cost = (
        heat.pivot_table(index="Day of the week", columns="Hour", values="Cost", aggfunc="sum")
        .reindex(DAY_ORDER)
        .fillna(0)
    )
    heat_cpl = (
        heat.pivot_table(index="Day of the week", columns="Hour", values="CPL", aggfunc="mean")
        .reindex(DAY_ORDER)
        .fillna(0)
    )

    return {
        "explorer": build_explorer_payload(google, meta),
        "googleMonthly": {
            "labels": monthly["Month"].tolist(),
            "spend": [round(x, 2) for x in monthly["Cost"].tolist()],
            "conversions": [round(x, 2) for x in monthly["Conversions"].tolist()],
            "cpl": [round(x, 2) for x in monthly["CPL"].tolist()],
        },
        "googleCampaigns": {
            "labels": campaigns["Campaign"].tolist(),
            "spend": [round(x, 2) for x in campaigns["Cost"].tolist()],
            "conversions": [round(x, 2) for x in campaigns["Conversions"].tolist()],
            "cpl": [round(x, 2) for x in campaigns["CPL"].tolist()],
            "lostRank": [round(x, 2) for x in campaigns["Lost IS Rank"].tolist()],
            "lostBudget": [round(x, 2) for x in campaigns["Lost IS Budget"].tolist()],
        },
        "adgroupSpend": {
            "labels": (adgroups["Campaign"] + " | " + adgroups["Ad group"]).head(12).tolist(),
            "values": [round(x, 2) for x in adgroups["Cost"].head(12).tolist()],
        },
        "keywordActions": keywords["Recommendation"].value_counts().to_dict(),
        "weekday": {
            "labels": DAY_SHORT,
            "spend": [round(x, 2) for x in weekday["Cost"].tolist()],
            "conversions": [round(x, 2) for x in weekday["Conversions"].tolist()],
            "cpl": [round(x, 2) for x in weekday["CPL"].tolist()],
        },
        "heatmap": {
            "days": DAY_SHORT,
            "hours": list(range(24)),
            "conversions": heat_conv.values.tolist(),
            "cost": heat_cost.values.tolist(),
            "cpl": heat_cpl.values.tolist(),
        },
        "metaCampaigns": {
            "labels": meta["campaigns"]["Campaign"].tolist(),
            "spend": [round(x, 2) for x in meta["campaigns"]["Spend"].tolist()],
            "conversations": [round(x, 2) for x in meta["campaigns"]["Conversations"].tolist()],
            "cpmc": [round(x, 2) for x in meta["campaigns"]["CPMC"].tolist()],
        },
        "metaPlatforms": {
            "labels": meta["platforms"]["Platform"].tolist(),
            "spend": [round(x, 2) for x in meta["platforms"]["Spend"].tolist()],
            "conversations": [round(x, 2) for x in meta["platforms"]["Conversations"].tolist()],
        },
        "respondLifecycle": {
            "labels": respond["lifecycle"]["lifecycle"].tolist(),
            "values": [int(x) for x in respond["lifecycle"]["Contacts"].tolist()],
        },
        "respondSource": {
            "labels": respond["source"]["source"].tolist(),
            "values": [int(x) for x in respond["source"]["Contacts"].tolist()],
        },
        "respondService": {
            "labels": respond["service"]["service"].head(8).tolist(),
            "values": [int(x) for x in respond["service"]["Contacts"].head(8).tolist()],
        },
    }


def kpi_card(label: str, value: str, note: str = "", accent: str = "") -> str:
    return f"""
      <article class="kpi {accent}">
        <span>{esc(label)}</span>
        <strong>{value}</strong>
        <small>{esc(note)}</small>
      </article>
    """


def insight_card(title: str, body: str, tone: str = "") -> str:
    return f"<article class=\"insight-card {tone}\"><h3>{esc(title)}</h3><p>{body}</p></article>"


def render_report(data: SourceData, google: dict[str, Any], meta: dict[str, Any], respond: dict[str, Any]) -> str:
    gt = google["totals"]
    mt = meta["totals"]
    rt = respond["totals"]
    total_spend = gt["spend"] + mt["spend"]
    total_impressions = gt["impressions"] + mt["impressions"]
    total_platform_events = gt["conversions"] + mt["conversations"]
    blended_cpl_event = safe_div(total_spend, total_platform_events)
    total_respond_contacts = rt["contacts"]
    platform_to_crm = safe_div(total_respond_contacts, total_platform_events) * 100
    customer_like = int(
        data.contacts["lifecycle"].str.lower().isin(["customer", "won", "show up"]).sum()
        if not data.contacts.empty
        else 0
    )
    hot_or_quote = int(data.contacts["lifecycle"].str.lower().isin(["hot lead", "quotation"]).sum())

    best_google_campaign = google["campaigns"].sort_values(["Conversions", "CPL"], ascending=[False, True]).iloc[0]
    most_efficient_keyword = google["keywords"][google["keywords"]["Conversions"] > 0].sort_values("CPL").head(1)
    most_efficient_keyword_text = (
        f"{esc(most_efficient_keyword.iloc[0]['Keyword'])} at {fmt_money(most_efficient_keyword.iloc[0]['CPL'])} CPL"
        if not most_efficient_keyword.empty
        else "No converting keyword rows in export"
    )
    best_meta_campaign = meta["campaigns"].sort_values(["Conversations", "CPMC"], ascending=[False, True]).iloc[0]
    top_service = respond["service"].iloc[0] if not respond["service"].empty else None
    top_service_text = f"{esc(top_service['service'])}: {int(top_service['Contacts'])} contacts" if top_service is not None else "No service data"
    logo_src = image_data_uri(LOGO_PATH)
    logo_html = (
        f'<img class="brand-logo" src="{logo_src}" alt="BlueVerse logo">'
        if logo_src
        else '<div class="brand-mark">B</div>'
    )

    chart_payload = build_chart_payloads(google, meta, respond)
    source_rows = [
        [esc(r["source"]), fmt_num(r["Contacts"]), fmt_money(r["QuotedValue"]), fmt_money(r["Revenue"])]
        for _, r in respond["source"].iterrows()
    ]
    lifecycle_rows = [[esc(r["lifecycle"]), fmt_num(r["Contacts"])] for _, r in respond["lifecycle"].iterrows()]
    service_rows = [
        [esc(r["service"]), fmt_num(r["Contacts"]), fmt_money(r["QuotedValue"]), fmt_money(r["Revenue"])]
        for _, r in respond["service"].iterrows()
    ]
    source_service_rows = [
        [esc(r["source"]), esc(r["service"]), fmt_num(r["Contacts"])]
        for _, r in respond["source_service"].head(12).iterrows()
    ]

    monthly_rows = [
        [
            esc(r["Month"]),
            fmt_money(r["Cost"]),
            fmt_num(r["Impressions"]),
            fmt_num(r["Clicks"]),
            fmt_pct(r["CTR"]),
            fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
            fmt_pct(r["CVR"]),
            fmt_money(r["CPL"]),
        ]
        for _, r in google["monthly"].iterrows()
    ]
    match_rows = [
        [
            esc(r["Match type"]),
            fmt_money(r["Cost"]),
            fmt_num(r["Impressions"]),
            fmt_num(r["Clicks"]),
            fmt_pct(r["CTR"]),
            fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
            fmt_pct(r["CVR"]),
            fmt_money(r["CPL"]),
        ]
        for _, r in google["match_types"].iterrows()
    ]
    ad_rows = []
    for _, r in google["ads"].head(14).iterrows():
        headline = next((r.get(f"Headline {i}") for i in range(1, 16) if str(r.get(f"Headline {i}", "")).strip() not in {"", "--", "nan"}), "")
        ad_rows.append(
            [
                esc(r["Campaign"]),
                esc(r["Ad group"]),
                esc(headline),
                status_badge(r["Status"]),
                fmt_money(r["Cost"]),
                fmt_num(r["Impressions"]),
                fmt_num(r["Clicks"]),
                fmt_pct(r["CTR"]),
                fmt_num(r["Conversions"], 1 if r["Conversions"] % 1 else 0),
                fmt_money(r["CPL"]),
            ]
        )

    no_conversion_keywords = google["keywords"][(google["keywords"]["Conversions"] == 0) & (google["keywords"]["Cost"] >= 100)].sort_values("Cost", ascending=False)
    top_keywords = google["keywords"][google["keywords"]["Conversions"] > 0].sort_values(["Conversions", "CPL"], ascending=[False, True])

    active_adgroups = google["adgroups"][google["adgroups"]["Status"].str.lower().eq("enabled")]
    paused_adgroups = google["adgroups"][~google["adgroups"]["Status"].str.lower().eq("enabled")]

    meta_campaign_rows = render_meta_table(meta["campaigns"], "campaign")
    meta_platform_rows = render_meta_table(meta["platforms"], "platform")
    meta_ad_rows = render_meta_table(meta["ads"].head(14), "ad")

    data_gaps = [
        "Age / demographic performance is not present in the shared Google CSVs or Meta workbook. Export age, gender, and age × gender breakdowns from both ad platforms to populate this section.",
        "Respond.io contact export has source, service, and lifecycle, but not campaign, ad, keyword, UTM, or conversation-owner fields. Campaign-level CRM quality will require those fields or a fresh API pull with custom fields.",
        "Respond.io quoted value and final sale value are all zero in the current CSV, so ROI/revenue and customer-value analysis are shown as data gaps rather than estimated.",
        "Meta export is June 1-22 only; Google daily export runs April 15-June 23 and monthly export covers April-June. Combined totals therefore label their periods explicitly.",
    ]

    funnel_steps = [
        ("Paid spend", fmt_money(total_spend), "Google + Meta spend"),
        ("Platform lead events", fmt_num(total_platform_events, 1 if total_platform_events % 1 else 0), "Google conversions + Meta message starts"),
        ("Respond.io contacts", fmt_num(total_respond_contacts), f"{fmt_pct(platform_to_crm)} of platform events"),
        ("Hot / quotation", fmt_num(hot_or_quote), "CRM quality signal available now"),
        ("Customer / show up", fmt_num(customer_like), "Needs richer lifecycle hygiene"),
    ]

    sections = f"""
    <header class="hero">
      <div class="brand-row">
        {logo_html}
        <div>
          <p class="eyeline">Blueverse performance command center</p>
          <h1>Paid Media + Respond.io Report</h1>
        </div>
      </div>
      <p class="hero-copy">Comprehensive Google Ads, Meta Ads, and CRM quality dashboard generated from the source files in this repo. Periods: Google {gt['date_start']} to {gt['date_end']}; Meta {mt['date_start']} to {mt['date_end']}; Respond.io June paid-media contacts.</p>
      <div class="hero-grid">
        {kpi_card("Total paid spend", fmt_money(total_spend), "Google + Meta", "blue")}
        {kpi_card("Total impressions", fmt_num(total_impressions), "Cross-channel reach signal", "cyan")}
        {kpi_card("Platform lead events", fmt_num(total_platform_events, 1 if total_platform_events % 1 else 0), "Google conv. + Meta msg starts", "green")}
        {kpi_card("Respond.io contacts", fmt_num(total_respond_contacts), f"{fmt_pct(platform_to_crm)} event-to-CRM ratio", "orange")}
        {kpi_card("Blended cost / event", fmt_money(blended_cpl_event), "Spend divided by platform lead events", "violet")}
      </div>
    </header>

    <nav class="toc">
      <a href="#explorer">Explorer</a>
      <a href="#overview">Overview</a>
      <a href="#funnel">Funnel</a>
      <a href="#google">Google Ads</a>
      <a href="#keywords">Keywords</a>
      <a href="#meta">Meta Ads</a>
      <a href="#respond">Respond.io</a>
      <a href="#insights">Insights</a>
      <a href="#gaps">Data gaps</a>
    </nav>

    <section id="explorer" class="panel primary-panel">
      <div class="section-head">
        <div>
          <p class="label">Interactive chart</p>
          <h2>Performance Explorer</h2>
          <p>Choose channel, period, campaign, and metrics. Google supports daily, weekly, and monthly breakdowns from the exports; Meta supports the June campaign export.</p>
        </div>
      </div>
      <div class="control-grid">
        <label>Channel<select id="explorerChannel"><option value="google">Google Ads</option><option value="meta">Meta Ads</option></select></label>
        <label>Breakdown<select id="explorerGranularity"><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select></label>
        <label>Campaign<select id="explorerCampaign"></select></label>
        <label>Metric 1<select id="explorerMetric1"></select></label>
        <label>Metric 2<select id="explorerMetric2"></select></label>
      </div>
      <div class="chart-shell tall"><svg id="explorerChart" role="img" aria-label="Interactive performance chart"></svg></div>
    </section>

    <section id="overview" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Executive overview</p>
          <h2>Combined Paid-Media Numbers</h2>
        </div>
      </div>
      <div class="split">
        {insight_card("Best Google signal", f"<strong>{esc(best_google_campaign['Campaign'])}</strong> leads Google volume with {fmt_num(best_google_campaign['Conversions'], 1 if best_google_campaign['Conversions'] % 1 else 0)} conversions at {fmt_money(best_google_campaign['CPL'])} CPL.")}
        {insight_card("Best Meta signal", f"<strong>{esc(best_meta_campaign['Campaign'])}</strong> generated {fmt_num(best_meta_campaign['Conversations'])} messaging starts at {fmt_money(best_meta_campaign['CPMC'], 2)} per start.")}
        {insight_card("Respond.io quality", f"Top captured service is <strong>{top_service_text}</strong>. Quotation/customer movement is low in the current lifecycle export and should be audited.")}
      </div>
      <div class="kpi-grid compact">
        {kpi_card("Google spend", fmt_money(gt['spend']), f"{fmt_num(gt['conversions'], 1 if gt['conversions'] % 1 else 0)} conversions; {fmt_money(gt['cpl'])} CPL")}
        {kpi_card("Meta spend", fmt_money(mt['spend']), f"{fmt_num(mt['conversations'])} msg starts; {fmt_money(mt['cpmc'], 2)} cost/msg")}
        {kpi_card("CRM quoted value", fmt_money(rt['quoted_value']), f"{fmt_num(rt['contacts_with_quote'])} contacts with quote value")}
        {kpi_card("CRM final sale value", fmt_money(rt['revenue']), f"{fmt_num(rt['contacts_with_sale'])} contacts with sale value")}
      </div>
    </section>

    <section id="funnel" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Funnel</p>
          <h2>Paid Ads to Respond.io</h2>
        </div>
      </div>
      <div class="funnel">
        {''.join(f'<div class="funnel-step" style="--w:{max(18, 100 - i * 13)}%"><span>{esc(label)}</span><strong>{value}</strong><small>{esc(note)}</small></div>' for i, (label, value, note) in enumerate(funnel_steps))}
      </div>
      <div class="grid-two">
        <div>
          <h3>Contacts by source</h3>
          {table(["Source", "Contacts", "Quoted value", "Final sale"], source_rows)}
        </div>
        <div>
          <h3>Lifecycle distribution</h3>
          <div class="chart-shell"><svg id="respondLifecycleChart"></svg></div>
        </div>
      </div>
    </section>

    <section id="google" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Google Ads</p>
          <h2>Campaign, Ad Group, and Time Performance</h2>
        </div>
      </div>
      <div class="kpi-grid compact">
        {kpi_card("Spend", fmt_money(gt['spend']), f"{fmt_money(gt['cpc'], 2)} avg CPC")}
        {kpi_card("Clicks", fmt_num(gt['clicks']), f"{fmt_pct(gt['ctr'])} CTR")}
        {kpi_card("Conversions", fmt_num(gt['conversions'], 1 if gt['conversions'] % 1 else 0), f"{fmt_pct(gt['cvr'])} CVR")}
        {kpi_card("Cost / conversion", fmt_money(gt['cpl']), f"{fmt_pct(gt['lost_is_budget'])} lost IS budget")}
      </div>
      <div class="grid-two">
        <div class="chart-shell"><svg id="googleMonthlyChart"></svg></div>
        <div class="chart-shell"><svg id="googleCampaignChart"></svg></div>
      </div>
      <h3>Monthly detail</h3>
      {table(["Month", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CVR", "CPL"], monthly_rows)}
      <h3>Campaign detail</h3>
      {render_campaign_table(google['campaigns'])}
      <div class="grid-two">
        <div>
          <h3>Active ad groups</h3>
          {render_adgroup_table(active_adgroups, 12)}
        </div>
        <div>
          <h3>Paused / non-active ad groups</h3>
          {render_adgroup_table(paused_adgroups, 12)}
        </div>
      </div>
      <div class="grid-two">
        <div>
          <h3>Weekday performance</h3>
          <div class="chart-shell"><svg id="weekdayChart"></svg></div>
        </div>
        <div>
          <h3>Day × hour conversions</h3>
          <div class="heatmap" id="conversionHeatmap"></div>
        </div>
      </div>
    </section>

    <section id="keywords" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Google keywords</p>
          <h2>Best Keywords, Waste, and Match Types</h2>
          <p>Best keyword signal: <strong>{most_efficient_keyword_text}</strong>.</p>
        </div>
      </div>
      <div class="grid-two">
        <div>
          <h3>Top converting keywords</h3>
          {render_keyword_table(top_keywords, 12)}
        </div>
        <div>
          <h3>High-spend no-conversion keywords</h3>
          {render_keyword_table(no_conversion_keywords, 12)}
        </div>
      </div>
      <h3>Match type performance</h3>
      {table(["Match type", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CVR", "CPL"], match_rows)}
      <h3>Ad performance</h3>
      {table(["Campaign", "Ad group", "Primary headline", "Status", "Spend", "Impr.", "Clicks", "CTR", "Conv.", "CPL"], ad_rows)}
    </section>

    <section id="meta" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Meta Ads</p>
          <h2>Campaign, Platform, and Creative Performance</h2>
        </div>
      </div>
      <div class="kpi-grid compact">
        {kpi_card("Spend", fmt_money(mt['spend']), f"{fmt_money(mt['cpm'], 2)} CPM")}
        {kpi_card("Reach", fmt_num(mt['reach']), f"{fmt_num(mt['frequency'], 2)} frequency")}
        {kpi_card("Message starts", fmt_num(mt['conversations']), f"{fmt_money(mt['cpmc'], 2)} cost/message")}
        {kpi_card("Impressions", fmt_num(mt['impressions']), "Facebook + Instagram + WhatsApp rows")}
      </div>
      <div class="grid-two">
        <div class="chart-shell"><svg id="metaCampaignChart"></svg></div>
        <div class="chart-shell"><svg id="metaPlatformChart"></svg></div>
      </div>
      <h3>Campaign detail</h3>
      {meta_campaign_rows}
      <h3>Platform detail</h3>
      {meta_platform_rows}
      <h3>Creative detail</h3>
      {meta_ad_rows}
    </section>

    <section id="respond" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Respond.io</p>
          <h2>Lead Quality and CRM Breakdown</h2>
        </div>
      </div>
      <div class="kpi-grid compact">
        {kpi_card("Paid-media contacts", fmt_num(rt['contacts']), f"{fmt_num(respond['source'].shape[0])} sources")}
        {kpi_card("Hot / quotation", fmt_num(hot_or_quote), f"{fmt_pct(safe_div(hot_or_quote, rt['contacts']) * 100)} of contacts")}
        {kpi_card("Customer / show up", fmt_num(customer_like), f"{fmt_pct(safe_div(customer_like, rt['contacts']) * 100)} of contacts")}
        {kpi_card("Top service", esc(top_service['service']) if top_service is not None else "N/A", f"{fmt_num(top_service['Contacts']) if top_service is not None else '0'} contacts")}
      </div>
      <div class="grid-two">
        <div>
          <h3>Lifecycle counts</h3>
          {table(["Lifecycle", "Contacts"], lifecycle_rows)}
        </div>
        <div>
          <h3>Service counts</h3>
          {table(["Service", "Contacts", "Quoted value", "Final sale"], service_rows)}
        </div>
      </div>
      <h3>Source × service mix</h3>
      {table(["Source", "Service", "Contacts"], source_service_rows)}
    </section>

    <section id="insights" class="panel">
      <div class="section-head">
        <div>
          <p class="label">Actions</p>
          <h2>Useful Insights From the Current Files</h2>
        </div>
      </div>
      <div class="split">
        {insight_card("Scale the best Google pockets", f"Prioritize budget and bid reviews for <strong>{esc(best_google_campaign['Campaign'])}</strong>, then protect low-CPL converting keywords from budget loss.")}
        {insight_card("Fix CRM attribution", "Respond.io currently proves source-level volume, but the decisive report needs campaign/ad/keyword or UTM custom fields. Add those fields to forms and chat entry points so CRM quality can be tied back to spend.")}
        {insight_card("Clean low-intent Google spend", f"There are <strong>{len(no_conversion_keywords)}</strong> keywords with AED 100+ spend and zero conversions. Review them as pause, bid-down, or negative-keyword candidates.")}
        {insight_card("Meta is the volume engine", f"Meta produced <strong>{fmt_num(mt['conversations'])}</strong> message starts at {fmt_money(mt['cpmc'], 2)} per start, but Respond.io lifecycle hygiene should prove how many become hot leads, quotations, show-ups, or customers.")}
      </div>
    </section>

    <section id="gaps" class="panel warning-panel">
      <div class="section-head">
        <div>
          <p class="label">Data quality</p>
          <h2>Known Gaps Before Final Board-Ready Version</h2>
        </div>
      </div>
      <ul class="gap-list">
        {''.join(f'<li>{esc(gap)}</li>' for gap in data_gaps)}
      </ul>
    </section>
    """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blueverse Paid Media + Respond.io Report</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --surface: #ffffff;
      --surface-2: #eef5ff;
      --ink: #102033;
      --muted: #66758b;
      --line: #d8e2ee;
      --blue: #0867c9;
      --cyan: #0a9bb0;
      --green: #11845b;
      --orange: #d46b08;
      --violet: #6b4fd8;
      --red: #c43d3d;
      --shadow: 0 18px 46px rgba(15, 37, 66, 0.09);
      --radius: 8px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .page {{ width: min(1440px, calc(100% - 36px)); margin: 0 auto; padding: 24px 0 60px; }}
    .hero, .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 26px;
      min-height: 440px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background:
        linear-gradient(118deg, rgba(8,103,201,0.11), rgba(10,155,176,0.05) 42%, rgba(255,255,255,0.94) 70%),
        var(--surface);
    }}
    .brand-row {{ display: flex; align-items: flex-start; gap: 18px; flex-direction: column; }}
    .brand-mark {{
      width: 54px; height: 54px; border-radius: 14px;
      display: grid; place-items: center;
      background: linear-gradient(135deg, var(--blue), var(--cyan));
      color: white; font-weight: 800; font-size: 26px;
      box-shadow: 0 12px 28px rgba(8,103,201,0.24);
    }}
    .brand-logo {{
      display: block;
      width: min(330px, 72vw);
      height: auto;
      object-fit: contain;
      margin-bottom: 2px;
    }}
    .eyeline, .label {{
      margin: 0 0 5px;
      color: var(--blue);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    h1, h2, h3 {{ letter-spacing: 0; }}
    h1 {{ margin: 0; font-size: clamp(34px, 5vw, 64px); line-height: .98; max-width: 980px; }}
    .hero-copy {{ max-width: 960px; color: #40516a; font-size: 18px; margin: 18px 0 28px; }}
    .hero-grid, .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .kpi {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      background: rgba(255,255,255,.84);
      min-width: 0;
    }}
    .kpi span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .kpi strong {{ display: block; margin-top: 5px; font-size: clamp(20px, 2.4vw, 31px); line-height: 1.05; word-break: break-word; }}
    .kpi small {{ display: block; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .kpi.blue {{ border-top: 4px solid var(--blue); }}
    .kpi.cyan {{ border-top: 4px solid var(--cyan); }}
    .kpi.green {{ border-top: 4px solid var(--green); }}
    .kpi.orange {{ border-top: 4px solid var(--orange); }}
    .kpi.violet {{ border-top: 4px solid var(--violet); }}
    .toc {{
      position: sticky; top: 10px; z-index: 10;
      display: flex; flex-wrap: wrap; gap: 8px;
      padding: 10px 0 18px;
      background: rgba(244,247,251,.92);
      backdrop-filter: blur(10px);
    }}
    .toc a {{
      text-decoration: none;
      color: #33445c;
      background: var(--surface);
      border: 1px solid var(--line);
      padding: 8px 12px;
      border-radius: 7px;
      font-size: 13px;
      font-weight: 700;
    }}
    .toc a:hover {{ border-color: var(--blue); color: var(--blue); }}
    .panel {{ padding: 24px; margin-top: 18px; }}
    .primary-panel {{ border-top: 4px solid var(--blue); }}
    .warning-panel {{ border-top: 4px solid var(--orange); }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 20px;
      margin-bottom: 18px;
    }}
    h2 {{ margin: 0; font-size: clamp(24px, 3vw, 38px); line-height: 1.08; }}
    h3 {{ margin: 22px 0 10px; font-size: 16px; }}
    .section-head p:not(.label), .panel > p {{ color: var(--muted); margin: 8px 0 0; max-width: 880px; }}
    .compact {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 16px 0; }}
    .split {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
    .hero-grid > *, .kpi-grid > *, .split > *, .grid-two > *, .control-grid > * {{ min-width: 0; }}
    .insight-card {{
      background: #f8fbff;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      min-width: 0;
    }}
    .insight-card h3 {{ margin: 0 0 8px; }}
    .insight-card p {{ margin: 0; color: #40516a; }}
    .grid-two {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }}
    .control-grid {{
      display: grid;
      grid-template-columns: 1fr 150px 1.4fr 160px 160px;
      gap: 10px;
      margin: 12px 0 16px;
    }}
    label {{ color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    select {{
      display: block;
      width: 100%;
      margin-top: 5px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px;
      background: white;
      color: var(--ink);
      font: inherit;
      font-size: 14px;
      text-transform: none;
    }}
    .chart-shell {{
      width: 100%;
      min-height: 310px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, #fff, #f9fbfe);
      border-radius: var(--radius);
      padding: 12px;
      overflow: hidden;
    }}
    .chart-shell.tall {{ min-height: 430px; }}
    svg {{ display: block; width: 100%; height: 100%; min-height: 280px; }}
    .chart-shell.tall svg {{ min-height: 390px; }}
    .table-wrap {{ width: 100%; max-width: 100%; min-width: 0; overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: white; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 760px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e8eef5; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; background: #f7faff; white-space: nowrap; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    tbody tr:hover td {{ background: #f8fbff; }}
    .badge {{
      display: inline-flex; align-items: center;
      min-height: 22px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .badge.good, .action-scale {{ background: #dcf7eb; color: #096344; }}
    .badge.muted {{ background: #eef2f6; color: #576679; }}
    .action-keep {{ background: #e5f1ff; color: #08539b; }}
    .action-monitor {{ background: #fff2d8; color: #805002; }}
    .action-pause {{ background: #ffe1e1; color: #982626; }}
    .action-negative-candidate {{ background: #f0e9ff; color: #5634aa; }}
    .funnel {{ display: grid; gap: 10px; margin: 10px 0 22px; }}
    .funnel-step {{
      width: var(--w);
      min-width: min(100%, 320px);
      background: linear-gradient(90deg, rgba(8,103,201,.12), rgba(10,155,176,.08));
      border: 1px solid var(--line);
      border-left: 5px solid var(--blue);
      border-radius: var(--radius);
      padding: 12px 16px;
    }}
    .funnel-step span {{ color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .funnel-step strong {{ display: block; font-size: 26px; line-height: 1.1; }}
    .funnel-step small {{ color: var(--muted); }}
    .heatmap {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px;
      background: white;
      min-height: 310px;
      display: grid;
      align-content: center;
      overflow-x: auto;
    }}
    .heat-row {{ display: grid; grid-template-columns: 44px repeat(24, 24px); gap: 3px; align-items: center; margin-bottom: 4px; }}
    .heat-label {{ color: var(--muted); font-size: 11px; font-weight: 800; }}
    .heat-cell {{ width: 24px; height: 20px; border-radius: 4px; background: rgba(8,103,201,.1); }}
    .heat-axis {{ display: grid; grid-template-columns: 44px repeat(24, 24px); gap: 3px; margin-top: 8px; color: var(--muted); font-size: 9px; }}
    .gap-list {{ margin: 0; padding-left: 20px; color: #3e4e64; }}
    .gap-list li {{ margin-bottom: 10px; }}
    .tooltip {{
      position: fixed;
      pointer-events: none;
      z-index: 50;
      background: #0f2035;
      color: white;
      padding: 7px 9px;
      border-radius: 6px;
      font-size: 12px;
      opacity: 0;
      transform: translate(-50%, -120%);
      transition: opacity .12s ease;
      max-width: 260px;
    }}
    @media (max-width: 1120px) {{
      .hero-grid, .kpi-grid, .compact {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .split {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .control-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 760px) {{
      .page {{ width: min(100% - 20px, 1440px); padding-top: 10px; }}
      .hero, .panel {{ padding: 16px; }}
      .hero {{ min-height: auto; }}
      .hero-grid, .kpi-grid, .compact, .split, .grid-two, .control-grid {{ grid-template-columns: 1fr; }}
      .brand-mark {{ width: 46px; height: 46px; }}
      .toc {{ top: 0; padding-bottom: 10px; }}
      .chart-shell, .chart-shell.tall {{ min-height: 340px; }}
      .funnel-step {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    {sections}
  </main>
  <div class="tooltip" id="tooltip"></div>
  <script>
    const REPORT_DATA = {as_json(chart_payload)};
    const COLORS = {{
      blue: '#0867c9',
      cyan: '#0a9bb0',
      green: '#11845b',
      orange: '#d46b08',
      violet: '#6b4fd8',
      red: '#c43d3d',
      muted: '#66758b',
      line: '#d8e2ee'
    }};
  </script>
  <script>
    const tooltip = document.getElementById('tooltip');
    const money = value => 'AED ' + Number(value || 0).toLocaleString(undefined, {{maximumFractionDigits: 0}});
    const num = (value, digits = 0) => Number(value || 0).toLocaleString(undefined, {{maximumFractionDigits: digits}});

    function showTip(event, text) {{
      tooltip.textContent = text;
      tooltip.style.left = event.clientX + 'px';
      tooltip.style.top = event.clientY + 'px';
      tooltip.style.opacity = '1';
    }}
    function hideTip() {{ tooltip.style.opacity = '0'; }}

    function svgEl(name, attrs = {{}}, parent) {{
      const el = document.createElementNS('http://www.w3.org/2000/svg', name);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      if (parent) parent.appendChild(el);
      return el;
    }}

    function clearSvg(id, height = 300) {{
      const svg = document.getElementById(id);
      svg.innerHTML = '';
      const width = Math.max(svg.clientWidth || 700, 420);
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      return {{svg, width, height}};
    }}

    function drawAxes(svg, width, height, pad, maxY, labels) {{
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      for (let i = 0; i <= 4; i++) {{
        const y = pad.top + plotH * i / 4;
        svgEl('line', {{x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}}, svg);
        const value = maxY * (1 - i / 4);
        svgEl('text', {{x: pad.left - 8, y: y + 4, 'text-anchor': 'end', fill: COLORS.muted, 'font-size': 11}}, svg).textContent = num(value);
      }}
      labels.forEach((label, i) => {{
        if (labels.length > 12 && i % Math.ceil(labels.length / 8) !== 0) return;
        const x = pad.left + plotW * (labels.length <= 1 ? 0.5 : i / (labels.length - 1));
        svgEl('text', {{x, y: height - 12, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10}}, svg).textContent = String(label).slice(5);
      }});
    }}

    function drawLineChart(id, config) {{
      const {{svg, width, height}} = clearSvg(id, config.height || 360);
      const pad = {{left: 58, right: 24, top: 24, bottom: 46}};
      const labels = config.labels || [];
      const datasets = (config.datasets || []).filter(ds => ds.data && ds.data.length);
      const allValues = datasets.flatMap(ds => ds.data.map(v => Number(v || 0))).filter(Number.isFinite);
      const maxY = Math.max(1, ...allValues) * 1.12;
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      drawAxes(svg, width, height, pad, maxY, labels);
      datasets.forEach((ds, dsIndex) => {{
        const points = ds.data.map((v, i) => {{
          const x = pad.left + plotW * (labels.length <= 1 ? 0.5 : i / (labels.length - 1));
          const y = pad.top + plotH * (1 - Number(v || 0) / maxY);
          return [x, y, v, labels[i]];
        }});
        const path = points.map((p, i) => `${{i ? 'L' : 'M'}}${{p[0]}},${{p[1]}}`).join(' ');
        svgEl('path', {{d: path, fill: 'none', stroke: ds.color, 'stroke-width': 3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}}, svg);
        points.forEach(p => {{
          const dot = svgEl('circle', {{cx: p[0], cy: p[1], r: 4, fill: ds.color, stroke: '#fff', 'stroke-width': 2}}, svg);
          dot.addEventListener('mousemove', ev => showTip(ev, `${{ds.label}} · ${{p[3]}}: ${{num(p[2], 2)}}`));
          dot.addEventListener('mouseleave', hideTip);
        }});
        const lx = pad.left + dsIndex * 160;
        svgEl('circle', {{cx: lx, cy: 12, r: 5, fill: ds.color}}, svg);
        svgEl('text', {{x: lx + 10, y: 16, fill: COLORS.muted, 'font-size': 12, 'font-weight': 700}}, svg).textContent = ds.label;
      }});
    }}

    function drawBarChart(id, config) {{
      const {{svg, width, height}} = clearSvg(id, config.height || 320);
      const horizontal = !!config.horizontal;
      const labels = config.labels || [];
      const values = (config.values || []).map(v => Number(v || 0));
      const max = Math.max(1, ...values) * 1.12;
      const pad = horizontal ? {{left: 170, right: 32, top: 28, bottom: 34}} : {{left: 54, right: 22, top: 28, bottom: 70}};
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      svgEl('text', {{x: pad.left, y: 16, fill: COLORS.muted, 'font-size': 12, 'font-weight': 800}}, svg).textContent = config.title || '';
      if (horizontal) {{
        const barH = Math.max(12, Math.min(26, plotH / Math.max(1, labels.length) - 6));
        labels.forEach((label, i) => {{
          const y = pad.top + i * (plotH / Math.max(1, labels.length)) + 4;
          const w = plotW * values[i] / max;
          svgEl('text', {{x: pad.left - 10, y: y + barH * .75, 'text-anchor': 'end', fill: COLORS.muted, 'font-size': 11}}, svg).textContent = String(label).slice(0, 24);
          const rect = svgEl('rect', {{x: pad.left, y, width: Math.max(2, w), height: barH, rx: 4, fill: config.color || COLORS.blue}}, svg);
          rect.addEventListener('mousemove', ev => showTip(ev, `${{label}}: ${{num(values[i], 2)}}`));
          rect.addEventListener('mouseleave', hideTip);
        }});
      }} else {{
        const gap = 8;
        const barW = Math.max(12, (plotW - gap * (labels.length - 1)) / Math.max(1, labels.length));
        values.forEach((value, i) => {{
          const h = plotH * value / max;
          const x = pad.left + i * (barW + gap);
          const y = pad.top + plotH - h;
          svgEl('rect', {{x, y, width: barW, height: Math.max(2, h), rx: 4, fill: config.color || COLORS.blue}}, svg)
            .addEventListener('mousemove', ev => showTip(ev, `${{labels[i]}}: ${{num(value, 2)}}`));
          svgEl('text', {{x: x + barW / 2, y: height - 18, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10, transform: `rotate(-28 ${{x + barW / 2}} ${{height - 18}})`}}, svg).textContent = String(labels[i]).slice(0, 18);
        }});
        for (let i = 0; i <= 4; i++) {{
          const y = pad.top + plotH * i / 4;
          svgEl('line', {{x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}}, svg);
        }}
      }}
    }}

    function drawGroupedBars(id, config) {{
      const {{svg, width, height}} = clearSvg(id, config.height || 330);
      const labels = config.labels || [];
      const datasets = config.datasets || [];
      const all = datasets.flatMap(ds => ds.values.map(v => Number(v || 0)));
      const max = Math.max(1, ...all) * 1.14;
      const pad = {{left: 56, right: 26, top: 28, bottom: 72}};
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const groupW = plotW / Math.max(1, labels.length);
      const barW = Math.max(8, (groupW - 12) / Math.max(1, datasets.length));
      for (let i = 0; i <= 4; i++) {{
        const y = pad.top + plotH * i / 4;
        svgEl('line', {{x1: pad.left, y1: y, x2: width - pad.right, y2: y, stroke: COLORS.line, 'stroke-width': 1}}, svg);
      }}
      datasets.forEach((ds, di) => {{
        labels.forEach((label, i) => {{
          const value = Number(ds.values[i] || 0);
          const h = plotH * value / max;
          const x = pad.left + i * groupW + 6 + di * barW;
          const y = pad.top + plotH - h;
          const rect = svgEl('rect', {{x, y, width: barW - 2, height: Math.max(2, h), rx: 4, fill: ds.color}}, svg);
          rect.addEventListener('mousemove', ev => showTip(ev, `${{ds.label}} · ${{label}}: ${{num(value, 2)}}`));
          rect.addEventListener('mouseleave', hideTip);
        }});
        const lx = pad.left + di * 140;
        svgEl('rect', {{x: lx, y: 10, width: 10, height: 10, rx: 3, fill: ds.color}}, svg);
        svgEl('text', {{x: lx + 15, y: 19, fill: COLORS.muted, 'font-size': 12, 'font-weight': 700}}, svg).textContent = ds.label;
      }});
      labels.forEach((label, i) => {{
        const x = pad.left + i * groupW + groupW / 2;
        svgEl('text', {{x, y: height - 18, 'text-anchor': 'middle', fill: COLORS.muted, 'font-size': 10, transform: `rotate(-28 ${{x}} ${{height - 18}})`}}, svg).textContent = String(label).slice(0, 18);
      }});
    }}

    function drawHeatmap() {{
      const box = document.getElementById('conversionHeatmap');
      const data = REPORT_DATA.heatmap.conversions;
      const max = Math.max(1, ...data.flat().map(Number));
      box.innerHTML = '';
      REPORT_DATA.heatmap.days.forEach((day, y) => {{
        const row = document.createElement('div');
        row.className = 'heat-row';
        row.innerHTML = `<span class="heat-label">${{day}}</span>`;
        data[y].forEach((value, hour) => {{
          const cell = document.createElement('span');
          cell.className = 'heat-cell';
          const alpha = .08 + .86 * Number(value || 0) / max;
          cell.style.background = `rgba(8,103,201,${{alpha}})`;
          cell.addEventListener('mousemove', ev => showTip(ev, `${{day}} ${{hour}}:00 · Conversions: ${{num(value, 1)}}`));
          cell.addEventListener('mouseleave', hideTip);
          row.appendChild(cell);
        }});
        box.appendChild(row);
      }});
      const axis = document.createElement('div');
      axis.className = 'heat-axis';
      axis.innerHTML = '<span></span>' + REPORT_DATA.heatmap.hours.map(h => `<span>${{h % 3 === 0 ? h : ''}}</span>`).join('');
      box.appendChild(axis);
    }}

    function initExplorer() {{
      const channelSel = document.getElementById('explorerChannel');
      const granSel = document.getElementById('explorerGranularity');
      const campSel = document.getElementById('explorerCampaign');
      const m1Sel = document.getElementById('explorerMetric1');
      const m2Sel = document.getElementById('explorerMetric2');
      const metricLabels = {{
        Cost: 'Spend / cost', Spend: 'Spend', Impressions: 'Impressions', Clicks: 'Clicks',
        Conversions: 'Conversions / msg starts', CTR: 'CTR %', CPC: 'CPC', CPL: 'CPL / cost per event',
        CPM: 'CPM', CVR: 'CVR %', Reach: 'Reach', CPMC: 'Cost per message', Frequency: 'Frequency'
      }};

      function activePayload() {{
        const channel = channelSel.value;
        let granularity = granSel.value;
        if (channel === 'meta') granularity = 'month';
        return REPORT_DATA.explorer[channel][granularity] || REPORT_DATA.explorer[channel].month;
      }}

      function refill() {{
        const channel = channelSel.value;
        [...granSel.options].forEach(opt => opt.disabled = channel === 'meta' && opt.value !== 'month');
        if (channel === 'meta') granSel.value = 'month';
        const payload = activePayload();
        const names = Object.keys(payload.series);
        campSel.innerHTML = names.map(name => `<option value="${{name.replace(/"/g, '&quot;')}}">${{name}}</option>`).join('');
        const first = payload.series[names[0]];
        const metrics = Object.keys(first.metrics || {{}});
        m1Sel.innerHTML = metrics.map(m => `<option value="${{m}}">${{metricLabels[m] || m}}</option>`).join('');
        m2Sel.innerHTML = metrics.map(m => `<option value="${{m}}">${{metricLabels[m] || m}}</option>`).join('');
        m1Sel.value = metrics.includes('Cost') ? 'Cost' : metrics[0];
        m2Sel.value = metrics.includes('Conversions') ? 'Conversions' : metrics[1] || metrics[0];
        update();
      }}

      function update() {{
        const payload = activePayload();
        const name = campSel.value || Object.keys(payload.series)[0];
        const s = payload.series[name];
        const periods = payload.periods;
        const metric1 = m1Sel.value;
        const metric2 = m2Sel.value;
        const periodMap = Object.fromEntries((s.periods || []).map((p, i) => [p, i]));
        const valuesFor = metric => periods.map(period => {{
          const idx = periodMap[period];
          return idx === undefined ? 0 : Number((s.metrics[metric] || [])[idx] || 0);
        }});
        const datasets = [
          {{label: metricLabels[metric1] || metric1, data: valuesFor(metric1), color: COLORS.blue}},
        ];
        if (metric2 && metric2 !== metric1) datasets.push({{label: metricLabels[metric2] || metric2, data: valuesFor(metric2), color: COLORS.orange}});
        drawLineChart('explorerChart', {{labels: periods, datasets, height: 390}});
      }}

      channelSel.addEventListener('change', refill);
      granSel.addEventListener('change', refill);
      campSel.addEventListener('change', update);
      m1Sel.addEventListener('change', update);
      m2Sel.addEventListener('change', update);
      refill();
    }}

    function renderAll() {{
      initExplorer();
      drawGroupedBars('googleMonthlyChart', {{
        labels: REPORT_DATA.googleMonthly.labels,
        datasets: [
          {{label: 'Spend', values: REPORT_DATA.googleMonthly.spend, color: COLORS.blue}},
          {{label: 'Conversions', values: REPORT_DATA.googleMonthly.conversions, color: COLORS.green}}
        ]
      }});
      drawBarChart('googleCampaignChart', {{labels: REPORT_DATA.googleCampaigns.labels, values: REPORT_DATA.googleCampaigns.spend, horizontal: true, color: COLORS.blue, title: 'Spend by campaign'}});
      drawGroupedBars('weekdayChart', {{
        labels: REPORT_DATA.weekday.labels,
        datasets: [
          {{label: 'Spend', values: REPORT_DATA.weekday.spend, color: COLORS.blue}},
          {{label: 'Conversions', values: REPORT_DATA.weekday.conversions, color: COLORS.green}}
        ]
      }});
      drawHeatmap();
      drawGroupedBars('metaCampaignChart', {{
        labels: REPORT_DATA.metaCampaigns.labels,
        datasets: [
          {{label: 'Spend', values: REPORT_DATA.metaCampaigns.spend, color: COLORS.cyan}},
          {{label: 'Msg starts', values: REPORT_DATA.metaCampaigns.conversations, color: COLORS.orange}}
        ]
      }});
      drawGroupedBars('metaPlatformChart', {{
        labels: REPORT_DATA.metaPlatforms.labels,
        datasets: [
          {{label: 'Spend', values: REPORT_DATA.metaPlatforms.spend, color: COLORS.cyan}},
          {{label: 'Msg starts', values: REPORT_DATA.metaPlatforms.conversations, color: COLORS.orange}}
        ]
      }});
      drawBarChart('respondLifecycleChart', {{labels: REPORT_DATA.respondLifecycle.labels, values: REPORT_DATA.respondLifecycle.values, horizontal: true, color: COLORS.green, title: 'Contacts by lifecycle'}});
    }}
    window.addEventListener('resize', () => window.requestAnimationFrame(renderAll));
    renderAll();
  </script>
</body>
</html>"""


def build_report() -> dict[str, Any]:
    data = load_data()
    google = summarize_google(data)
    meta = summarize_meta(data.meta_raw)
    respond = summarize_respond(data.contacts)
    html_report = render_report(data, google, meta, respond)
    OUT_HTML.write_text(html_report, encoding="utf-8")
    data_out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "google_totals": google["totals"],
        "meta_totals": meta["totals"],
        "respond_totals": respond["totals"],
    }
    data_out = json_ready(data_out)
    OUT_JSON.write_text(json.dumps(data_out, indent=2, ensure_ascii=False), encoding="utf-8")
    return data_out


def main() -> None:
    data_out = build_report()
    print(f"Wrote {OUT_HTML}")
    print(json.dumps(data_out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
