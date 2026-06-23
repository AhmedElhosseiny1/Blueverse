#!/usr/bin/env python3
"""
Generate a comprehensive Google Ads-only performance report from Blueverse CSV exports.
Reads keywords.csv, months.csv, ad.csv, heat map.csv, Day Report.csv from
~/Downloads/Blueverse and writes outputs/google_ads_report.html.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

DATA_DIR = Path.home() / "Downloads" / "Blueverse"
OUT_DIR = Path(__file__).resolve().parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)
OUT_HTML = OUT_DIR / "google_ads_report.html"


def read_csv(path, sep=None, encoding=None, skiprows=2):
    if encoding is None:
        for enc in ("utf-16", "utf-8-sig"):
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(1000)
                encoding = enc
                break
            except Exception:
                continue
    df = pd.read_csv(path, sep=sep, encoding=encoding, skiprows=skiprows, thousands=",")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def clean_money(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip().replace(",", "").replace("AED", "").replace("$", "")
    if s in ("", "--", "-", "0"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def clean_pct(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip().replace(",", "").replace("%", "")
    if s in ("", "--", "-", "0"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        m = re.search(r"(\d+(\.\d+)?)", s)
        return float(m.group(1)) if m else 0.0


def clean_int(x):
    if pd.isna(x):
        return 0
    s = str(x).strip().replace(",", "")
    if s in ("", "--", "-", "0"):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def clean_float(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip().replace(",", "")
    if s in ("", "--", "-", "0"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def safe_div(num, den, default=0.0):
    try:
        return num / den if den else default
    except Exception:
        return default


def money(v):
    try:
        return f"{v:,.2f}"
    except Exception:
        return str(v)


def pct(v):
    try:
        return f"{v:.2f}%"
    except Exception:
        return str(v)


def num_fmt(v):
    try:
        return f"{v:,.0f}"
    except Exception:
        return str(v)


def parse_month_label(x):
    s = str(x).strip()
    mapper = {"April": "2026-04", "May": "2026-05", "June": "2026-06"}
    for k, v in mapper.items():
        if k in s:
            return v
    return s


def load_data():
    print("Loading CSVs...")
    kw = read_csv(DATA_DIR / "keywords.csv", sep=",", encoding="utf-8-sig")
    months = read_csv(DATA_DIR / "months.csv", sep="\t", encoding="utf-16")
    ads = read_csv(DATA_DIR / "ad.csv", sep="\t", encoding="utf-16")
    heat = read_csv(DATA_DIR / "heat map.csv", sep="\t", encoding="utf-16")
    days = read_csv(DATA_DIR / "Day Report.csv", sep="\t", encoding="utf-16")

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
    for df in (kw, months, ads, heat, days):
        df.rename(columns={c: rename_map.get(c, c) for c in df.columns}, inplace=True)

    for df in (kw, months, ads, heat, days):
        for col in ("Cost", "CPL", "Avg. CPC", "CPC", "CPM"):
            if col in df.columns:
                df[col] = df[col].apply(clean_money)
        for col in ("CTR", "CVR", "Lost IS Rank", "Lost IS Budget", "Top IS", "Abs Top IS", "Impr Share"):
            if col in df.columns:
                df[col] = df[col].apply(clean_pct)
        for col in ("Impressions", "Clicks", "Conversions", "Quality Score"):
            if col in df.columns:
                df[col] = df[col].apply(clean_int)
        if "Month" in df.columns:
            df["MonthSort"] = df["Month"].apply(parse_month_label)

    if "Quality Score" not in kw.columns:
        kw["Quality Score"] = np.nan
    for col in ("Expected CTR", "Ad Relevance", "Landing Page Experience"):
        if col not in kw.columns:
            kw[col] = np.nan
        else:
            kw[col] = kw[col].apply(clean_float)

    if "Ad Strength" not in ads.columns:
        ads["Ad Strength"] = "Average"

    days["Day"] = pd.to_datetime(days["Day"], errors="coerce")

    print(f"  keywords: {len(kw)} rows")
    print(f"  months:   {len(months)} rows")
    print(f"  ads:      {len(ads)} rows")
    print(f"  heat:     {len(heat)} rows")
    print(f"  days:     {len(days)} rows")
    return kw, months, ads, heat, days


def overall_metrics(df, days=None):
    spend = df["Cost"].sum()
    impr = df["Impressions"].sum()
    clicks = df["Clicks"].sum()
    conv = df["Conversions"].sum()
    ctr = safe_div(clicks, impr, 0.0) * 100
    cpc = safe_div(spend, clicks, 0.0)
    cpl = safe_div(spend, conv, 0.0)
    cvr = safe_div(conv, clicks, 0.0) * 100
    cpm = safe_div(spend, impr, 0.0) * 1000
    if days is not None:
        lost_rank = safe_div((days["Lost IS Rank"] * days["Impressions"]).sum(), days["Impressions"].sum(), 0.0)
        lost_budget = safe_div((days["Lost IS Budget"] * days["Impressions"]).sum(), days["Impressions"].sum(), 0.0)
    else:
        lost_rank = 0.0
        lost_budget = 0.0
    return {
        "spend": spend, "impressions": impr, "clicks": clicks, "ctr": ctr,
        "cpc": cpc, "conversions": conv, "cpl": cpl, "cvr": cvr, "cpm": cpm,
        "lost_is_rank": lost_rank, "lost_is_budget": lost_budget,
    }


def campaign_performance(months, days=None):
    grp = months.groupby("Campaign").agg(
        Status=("Status", lambda x: x.mode()[0] if not x.mode().empty else x.iloc[-1]),
        Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"),
        Conversions=("Conversions", "sum"), Cost=("Cost", "sum"),
    ).reset_index()
    if days is not None:
        lost = days.groupby("Campaign").agg(Lost_IS_Rank=("Lost IS Rank", "mean"), Lost_IS_Budget=("Lost IS Budget", "mean")).reset_index()
        grp = grp.merge(lost, on="Campaign", how="left")
    else:
        grp["Lost_IS_Rank"] = 0.0
        grp["Lost_IS_Budget"] = 0.0
    grp["CTR"] = grp.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    grp["Avg_CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CPM"] = grp.apply(lambda r: safe_div(r["Cost"], r["Impressions"], 0.0) * 1000, axis=1)
    return grp


def campaign_daily_performance(days):
    grp = days.groupby(["Campaign", "Day"]).agg(
        Cost=("Cost", "sum"), Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"),
    ).reset_index()
    grp["CTR"] = grp.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    grp["CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CPM"] = grp.apply(lambda r: safe_div(r["Cost"], r["Impressions"], 0.0) * 1000, axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return grp.sort_values(["Campaign", "Day"])


def adgroup_performance(months):
    grp = months.groupby(["Campaign", "Ad group"]).agg(
        Status=("Status", lambda x: x.mode()[0] if not x.mode().empty else x.iloc[-1]),
        Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"),
        Conversions=("Conversions", "sum"), Cost=("Cost", "sum"),
    ).reset_index()
    grp["CTR"] = grp.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    grp["CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return grp


def monthly_performance(months):
    grp = months.groupby(["MonthSort", "Month"]).agg(
        Cost=("Cost", "sum"), Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"),
    ).reset_index().sort_values("MonthSort")
    grp["CTR"] = grp.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    grp["CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CPM"] = grp.apply(lambda r: safe_div(r["Cost"], r["Impressions"], 0.0) * 1000, axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return grp


def keyword_recommendation(row):
    cost, conv, ctr, impr = row["Cost"], row["Conversions"], row["CTR"], row["Impressions"]
    if cost > 500 and conv == 0:
        return "Pause"
    if cost > 200 and conv == 0:
        return "Monitor"
    if conv >= 5:
        return "Scale"
    if conv >= 3:
        return "Keep"
    if impr > 500 and ctr < 1.0 and conv == 0:
        return "Add as Negative"
    if conv == 0 and cost > 50:
        return "Monitor"
    return "Keep"


def match_type_analysis(kw):
    grp = kw.groupby("Match type").agg(
        Cost=("Cost", "sum"), Clicks=("Clicks", "sum"),
        Conversions=("Conversions", "sum"), Impressions=("Impressions", "sum"),
    ).reset_index()
    grp["CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return grp


def ads_performance(ads):
    ads = ads.copy()
    ads["CTR"] = ads.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    ads["CPC"] = ads.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    ads["CPL"] = ads.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    ads["CVR"] = ads.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return ads


def heatmap_data(heat):
    heat = heat.copy()
    heat["Hour"] = heat["Hour of the day"].astype(int)
    return heat


def day_performance(days):
    grp = days.groupby("Day").agg(
        Cost=("Cost", "sum"), Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"), Conversions=("Conversions", "sum"),
    ).reset_index()
    grp["CTR"] = grp.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    grp["CPC"] = grp.apply(lambda r: safe_div(r["Cost"], r["Clicks"], 0.0), axis=1)
    grp["CPL"] = grp.apply(lambda r: safe_div(r["Cost"], r["Conversions"], 0.0), axis=1)
    grp["CPM"] = grp.apply(lambda r: safe_div(r["Cost"], r["Impressions"], 0.0) * 1000, axis=1)
    grp["CVR"] = grp.apply(lambda r: safe_div(r["Conversions"], r["Clicks"], 0.0) * 100, axis=1)
    return grp.sort_values("Day")


def quality_score_audit(kw):
    qs = kw.dropna(subset=["Quality Score"])
    if qs.empty:
        return pd.DataFrame()
    audit = qs[["Campaign", "Ad group", "Keyword", "Match type", "Quality Score", "Expected CTR",
                "Ad Relevance", "Landing Page Experience", "Cost", "Conversions", "CPL", "Clicks", "Impressions"]].copy()
    audit["CTR"] = audit.apply(lambda r: safe_div(r["Clicks"], r["Impressions"], 0.0) * 100, axis=1)
    return audit


def to_json(obj):
    return json.dumps(obj, default=str)


# -----------------------------------------------------------------------------
# HTML report generation
# -----------------------------------------------------------------------------

def render_html(kpi, monthly, campaigns, adgroups, kw, ads, heat, day_perf, qsa, match_df, camp_daily):
    months_sorted = monthly.sort_values("MonthSort")
    month_labels = months_sorted["Month"].tolist()
    month_spend = months_sorted["Cost"].round(2).tolist()
    month_clicks = months_sorted["Clicks"].tolist()
    month_leads = months_sorted["Conversions"].tolist()
    month_cpl = [round(v, 2) for v in months_sorted["CPL"].tolist()]
    month_cpc = [round(v, 2) for v in months_sorted["CPC"].tolist()]

    camp_sorted = campaigns.sort_values("Cost", ascending=False)
    camp_names = camp_sorted["Campaign"].tolist()
    camp_spend = camp_sorted["Cost"].round(2).tolist()
    camp_leads = camp_sorted["Conversions"].tolist()
    camp_cpl = [round(v, 2) for v in camp_sorted["CPL"].tolist()]
    camp_lost_rank = [round(v, 2) for v in camp_sorted["Lost_IS_Rank"].tolist()]
    camp_lost_budget = [round(v, 2) for v in camp_sorted["Lost_IS_Budget"].tolist()]

    # Daily series for interactive campaign explorer
    exp_dates = sorted(camp_daily["Day"].dt.date.astype(str).unique())
    exp_series = {}
    overall_daily = day_perf.sort_values("Day")
    exp_series["All campaigns"] = {
        "dates": overall_daily["Day"].dt.strftime("%Y-%m-%d").tolist(),
        "metrics": {
            "Cost": overall_daily["Cost"].round(2).tolist(),
            "Impressions": overall_daily["Impressions"].tolist(),
            "Clicks": overall_daily["Clicks"].tolist(),
            "Conversions": overall_daily["Conversions"].tolist(),
            "CTR": [round(v, 2) for v in overall_daily["CTR"].tolist()],
            "CPC": [round(v, 2) for v in overall_daily["CPC"].tolist()],
            "CPL": [round(v, 2) for v in overall_daily["CPL"].tolist()],
            "CPM": [round(v, 2) for v in overall_daily["CPM"].tolist()],
            "CVR": [round(v, 2) for v in overall_daily["CVR"].tolist()],
        }
    }
    for camp, g in camp_daily.groupby("Campaign"):
        g = g.sort_values("Day")
        exp_series[camp] = {
            "dates": g["Day"].dt.strftime("%Y-%m-%d").tolist(),
            "metrics": {
                "Cost": g["Cost"].round(2).tolist(),
                "Impressions": g["Impressions"].tolist(),
                "Clicks": g["Clicks"].tolist(),
                "Conversions": g["Conversions"].tolist(),
                "CTR": [round(v, 2) for v in g["CTR"].tolist()],
                "CPC": [round(v, 2) for v in g["CPC"].tolist()],
                "CPL": [round(v, 2) for v in g["CPL"].tolist()],
                "CPM": [round(v, 2) for v in g["CPM"].tolist()],
                "CVR": [round(v, 2) for v in g["CVR"].tolist()],
            }
        }
    explorer_json = json.dumps({"dates": exp_dates, "series": exp_series})

    ag_sorted = adgroups.sort_values("Cost", ascending=False)
    ag_labels = (ag_sorted["Campaign"] + " | " + ag_sorted["Ad group"]).tolist()
    ag_spend = ag_sorted["Cost"].round(2).tolist()

    kw["Rec"] = kw.apply(keyword_recommendation, axis=1)
    kw_top_conv = kw[kw["Conversions"] > 0].sort_values("Conversions", ascending=False).head(10)
    kw_sorted_cpl = kw[kw["Conversions"] > 0].sort_values("CPL", ascending=True).head(10)
    kw_high_cost_no_conv = kw[(kw["Cost"] > 200) & (kw["Conversions"] == 0)].sort_values("Cost", ascending=False).head(15)

    ads_sorted_ctr = ads[ads["Impressions"] >= 100].sort_values("CTR", ascending=False).head(5)
    ads_sorted_cpl = ads[ads["Conversions"] > 0].sort_values("CPL", ascending=True).head(5)

    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    full_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours = list(range(24))

    def pivot(field, agg="sum"):
        return heat.pivot_table(index="Day of the week", columns="Hour", values=field, aggfunc=agg).reindex(full_days).fillna(0)
    pv_conv = pivot("Conversions")
    pv_cpl = heat.pivot_table(index="Day of the week", columns="Hour", values="CPL", aggfunc="mean").reindex(full_days).fillna(0)
    pv_clicks = pivot("Clicks")
    pv_cost = pivot("Cost")
    heat_conv = pv_conv.values.tolist()
    heat_cpl = pv_cpl.values.tolist()
    heat_clicks = pv_clicks.values.tolist()
    heat_cost = pv_cost.values.tolist()

    day_perf_sorted = day_perf.sort_values("Day")
    day_labels = [d.strftime("%Y-%m-%d") for d in day_perf_sorted["Day"]]
    day_spend = day_perf_sorted["Cost"].round(2).tolist()
    day_leads = day_perf_sorted["Conversions"].tolist()
    day_cpl = [round(v, 2) for v in day_perf_sorted["CPL"].tolist()]

    best_camp = campaigns.loc[campaigns["Conversions"].idxmax()] if campaigns["Conversions"].sum() > 0 else campaigns.iloc[0]
    weakest_camp = campaigns.loc[campaigns["CPL"].idxmax()] if campaigns["CPL"].max() > 0 else campaigns.iloc[-1]
    biggest_opp = campaigns[(campaigns["Lost_IS_Budget"] > 20) & (campaigns["Conversions"] > 0)].sort_values("Lost_IS_Budget", ascending=False).head(1)
    best_month = months_sorted.loc[months_sorted["CPL"].idxmin()]

    def insight_monthly():
        pieces = []
        pieces.append(f"<strong>{best_month['Month']}</strong> delivered the best efficiency with a CPL of <strong>AED {money(best_month['CPL'])}</strong>.")
        pieces.append(f"CPL worsened from April (AED {money(monthly[monthly['MonthSort']=='2026-04']['CPL'].values[0])}) to June (AED {money(monthly[monthly['MonthSort']=='2026-06']['CPL'].values[0])}), a {safe_div(monthly[monthly['MonthSort']=='2026-06']['CPL'].values[0], monthly[monthly['MonthSort']=='2026-04']['CPL'].values[0], 0)*100:.1f}% increase.")
        pieces.append(f"CPC moved from AED {money(monthly[monthly['MonthSort']=='2026-04']['CPC'].values[0])} in April to AED {money(monthly[monthly['MonthSort']=='2026-06']['CPC'].values[0])} in June.")
        june_conv = monthly[monthly['MonthSort']=='2026-06']['Conversions'].values[0]
        may_conv = monthly[monthly['MonthSort']=='2026-05']['Conversions'].values[0]
        pieces.append(f"June lead volume ({int(june_conv)}) is {'up' if june_conv>may_conv else 'down'} vs May ({int(may_conv)}) but with a smaller budget.")
        return " ".join(pieces)

    best_ag = adgroups.loc[adgroups[adgroups["Conversions"] > 0]["CPL"].idxmin()] if (adgroups["Conversions"] > 0).any() else adgroups.iloc[0]
    highest_spend_ag = adgroups.loc[adgroups["Cost"].idxmax()]
    lost_rank_text = "rank" if kpi["lost_is_rank"] > kpi["lost_is_budget"] else "budget"

    # table rows
    def tr_monthly(r):
        return f"<tr><td>{r['Month']}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{pct(r['CTR'])}</td><td class='num'>AED {money(r['CPC'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>{pct(r['CVR'])}</td><td class='num'>AED {money(r['CPL'])}</td><td class='num'>AED {money(r['CPM'])}</td></tr>"
    rows_monthly = "\n".join(tr_monthly(r) for _, r in months_sorted.iterrows())

    def tr_camp(r):
        return f"<tr><td>{r['Campaign']}</td><td>{r['Status']}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{pct(r['CTR'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>{pct(r['CVR'])}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>AED {money(r['Avg_CPC'])}</td><td class='num'>AED {money(r['CPL'])}</td><td class='num'>{pct(r['Lost_IS_Rank'])}</td><td class='num'>{pct(r['Lost_IS_Budget'])}</td></tr>"
    rows_campaigns = "\n".join(tr_camp(r) for _, r in camp_sorted.iterrows())

    def tr_ag(r):
        return f"<tr><td>{r['Campaign']}</td><td>{r['Ad group']}</td><td>{r['Status']}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{pct(r['CTR'])}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>AED {money(r['CPC'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>{pct(r['CVR'])}</td><td class='num'>AED {money(r['CPL'])}</td></tr>"
    rows_adgroups = "\n".join(tr_ag(r) for _, r in ag_sorted.iterrows())

    def tr_kw(r):
        return f"<tr><td>{r['Keyword']}</td><td>{r['Match type']}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{pct(r['CTR'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>AED {money(r['CPL'])}</td></tr>"
    rows_kw_top_conv = "\n".join(tr_kw(r) for _, r in kw_top_conv.iterrows())
    rows_kw_low_cpl = "\n".join(f"<tr><td>{r['Keyword']}</td><td>{r['Match type']}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>AED {money(r['CPL'])}</td><td class='num'>AED {money(r['Cost'])}</td></tr>" for _, r in kw_sorted_cpl.iterrows())

    def tr_kw_bad(r):
        rec = r["Rec"]
        badge = rec.lower().replace(" ", "-")
        return f"<tr><td>{r['Keyword']}</td><td>{r['Campaign']}</td><td>{r['Match type']}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{pct(r['CTR'])}</td><td><span class='badge {badge}'>{rec}</span></td></tr>"
    rows_kw_bad = "\n".join(tr_kw_bad(r) for _, r in kw_high_cost_no_conv.iterrows())

    def tr_match(r):
        return f"<tr><td>{r['Match type']}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>AED {money(r['CPC'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>{pct(r['CVR'])}</td><td class='num'>AED {money(r['CPL'])}</td></tr>"
    rows_match = "\n".join(tr_match(r) for _, r in match_df.iterrows())

    def tr_ad(r):
        return f"<tr><td>{r['Campaign']}</td><td>{r['Ad group']}</td><td class='num'>{num_fmt(r['Impressions'])}</td><td class='num'>{pct(r['CTR'])}</td><td class='num'>AED {money(r['CPC'])}</td><td class='num'>AED {money(r['CPL'])}</td></tr>"
    rows_ads_ctr = "\n".join(tr_ad(r) for _, r in ads_sorted_ctr.iterrows())
    rows_ads_cpl = "\n".join(f"<tr><td>{r['Campaign']}</td><td>{r['Ad group']}</td><td class='num'>{num_fmt(r['Clicks'])}</td><td class='num'>{num_fmt(r['Conversions'])}</td><td class='num'>AED {money(r['CPL'])}</td><td class='num'>AED {money(r['Cost'])}</td></tr>" for _, r in ads_sorted_cpl.iterrows())

    qs_rows = ""
    if not qsa.empty:
        low_qs = qsa[qsa["Quality Score"] <= 5].sort_values("Quality Score").head(15)
        qs_rows = "\n".join(f"<tr><td>{r['Keyword']}</td><td>{r['Campaign']}</td><td>{r['Ad group']}</td><td class='num'>{int(r['Quality Score'])}</td><td class='num'>{r['Expected CTR']}</td><td class='num'>{r['Ad Relevance']}</td><td class='num'>{r['Landing Page Experience']}</td><td class='num'>AED {money(r['Cost'])}</td><td class='num'>{int(r['Conversions'])}</td></tr>" for _, r in low_qs.iterrows())

    opp_text = (f"{biggest_opp.iloc[0]['Campaign']} is losing {pct(biggest_opp.iloc[0]['Lost_IS_Budget'])} of impressions to budget while still converting. Raising its daily budget should directly increase lead volume." if not biggest_opp.empty else "Several campaigns are losing >20% of impressions to budget (especially PPF and Wrapping). Increasing budgets on the converting campaigns is the fastest way to scale leads.")

    qs_text = "Review low QS keywords and test more relevant headlines / tighter keyword-to-landing-page relevance." if not qsa.empty else "Enable Quality Score columns in Google Ads reports and refresh this dashboard to surface QS-based actions."

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BlueVerse Google Ads Performance Report · Apr–Jun 2026</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-matrix@2.0.1/dist/chartjs-chart-matrix.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{ --bg:#f6f8fb; --surface:#fff; --text:#0f172a; --muted:#64748b; --border:#e2e8f0;
      --google:#f97316; --blue:#2563eb; --teal:#0d9488; --red:#dc2626; --green:#16a34a; --amber:#d97706;
      --radius:16px; --shadow:0 4px 24px rgba(15,23,42,0.06); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:'Inter',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.55; }}
    .container {{ max-width:1320px; margin:0 auto; padding:32px 24px 80px; }}
    header, section {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:28px; margin-bottom:24px; box-shadow:var(--shadow); }}
    header h1 {{ margin:0 0 8px; font-size:2rem; }}
    header p {{ margin:0; color:var(--muted); }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:28px; position:sticky; top:12px; z-index:50; background:rgba(246,248,251,0.92); backdrop-filter:blur(8px); padding:10px 0; }}
    nav a {{ text-decoration:none; color:var(--muted); background:var(--surface); border:1px solid var(--border); padding:8px 16px; border-radius:999px; font-size:0.85rem; font-weight:500; }}
    nav a:hover {{ color:var(--blue); border-color:var(--blue); }}
    h2 {{ margin:0 0 18px; font-size:1.35rem; display:flex; align-items:center; gap:10px; }}
    h3 {{ margin:24px 0 12px; font-size:1.05rem; color:var(--muted); }}
    .kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px,1fr)); gap:16px; }}
    .kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:20px; box-shadow:var(--shadow); }}
    .kpi-label {{ font-size:0.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px; }}
    .kpi-value {{ font-size:1.6rem; font-weight:700; }}
    .grid-2 {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(420px,1fr)); gap:24px; }}
    .grid-3 {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px,1fr)); gap:24px; }}
    .controls {{ display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin-bottom:16px; }}
    .controls label {{ font-size:0.85rem; color:var(--muted); font-weight:500; }}
    .controls select {{ margin-left:6px; padding:6px 10px; border-radius:8px; border:1px solid var(--border); background:var(--surface); font-size:0.9rem; }}
    .chart-wrap {{ position:relative; height:320px; margin-top:10px; }}
    .chart-wrap.small {{ height:260px; }}
    table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
    th, td {{ padding:10px 8px; border-bottom:1px solid var(--border); text-align:left; }}
    th {{ color:var(--muted); font-weight:600; text-transform:uppercase; font-size:0.7rem; letter-spacing:0.05em; }}
    td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    tr:hover td {{ background:#f8fafc; }}
    .badge {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:0.72rem; font-weight:600; text-transform:uppercase; }}
    .badge.scale {{ background:#dcfce7; color:#166534; }}
    .badge.keep {{ background:#e0f2fe; color:#075985; }}
    .badge.monitor {{ background:#fef3c7; color:#92400e; }}
    .badge.pause {{ background:#fee2e2; color:#991b1b; }}
    .badge.negative {{ background:#f3f4f6; color:#374151; }}
    .badge.paused {{ background:#f1f5f9; color:#64748b; }}
    .insight {{ background:#f0f9ff; border-left:4px solid var(--blue); padding:16px 18px; border-radius:0 10px 10px 0; margin:16px 0; }}
    .insight strong {{ color:var(--blue); }}
    .notice {{ background:#fff7ed; border-left:4px solid var(--google); padding:16px 18px; border-radius:0 10px 10px 0; margin:16px 0; }}
    .recommendation {{ background:#f0fdf4; border-left:4px solid var(--green); padding:16px 18px; border-radius:0 10px 10px 0; margin:12px 0; }}
    .pill-list {{ list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:10px; }}
    .pill-list li {{ background:#f1f5f9; border:1px solid var(--border); border-radius:999px; padding:8px 14px; font-size:0.85rem; }}
    .scroll {{ overflow-x:auto; }}
    .timeline {{ position:relative; padding-left:24px; }}
    .timeline::before {{ content:""; position:absolute; left:7px; top:0; bottom:0; width:2px; background:var(--border); }}
    .timeline-item {{ position:relative; margin-bottom:18px; }}
    .timeline-item::before {{ content:""; position:absolute; left:-21px; top:6px; width:10px; height:10px; border-radius:50%; background:var(--blue); }}
    .timeline-item span {{ font-size:0.75rem; color:var(--muted); }}
    footer {{ text-align:center; color:var(--muted); font-size:0.8rem; margin-top:50px; }}
    @media(max-width:768px){{ .grid-2,.grid-3{{grid-template-columns:1fr;}} header h1{{font-size:1.5rem;}} }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>BlueVerse Google Ads Performance Report</h1>
      <p>Period: 1 April 2026 – 23 June 2026 · Google Ads search performance, optimization impact, and next steps.</p>
    </header>

    <nav>
      <a href="#explorer">Explorer</a>
      <a href="#exec">Executive Summary</a>
      <a href="#kpi">KPIs</a>
      <a href="#monthly">Monthly</a>
      <a href="#campaigns">Campaigns</a>
      <a href="#adgroups">Ad Groups</a>
      <a href="#keywords">Keywords</a>
      <a href="#match">Match Types</a>
      <a href="#ads">Ads</a>
      <a href="#search">Search Hygiene</a>
      <a href="#heatmap">Heatmap</a>
      <a href="#days">Daily</a>
      <a href="#lostis">Lost IS</a>
      <a href="#qs">Quality Score</a>
      <a href="#timeline">Timeline</a>
      <a href="#recommendations">Recs</a>
      <a href="#insight">Insight</a>
    </nav>

    <section id="explorer">
      <h2>Campaign Explorer</h2>
      <p>Pick a campaign and up to two metrics to see the daily trend update instantly.</p>
      <div class="controls">
        <label>Campaign <select id="expCampaign"></select></label>
        <label>Metric 1 <select id="expMetric1"></select></label>
        <label>Metric 2 <select id="expMetric2"></select></label>
      </div>
      <div class="chart-wrap" style="height:420px"><canvas id="explorerChart"></canvas></div>
    </section>

    <section id="exec">
      <h2>1. Executive Summary</h2>
      <p>From 1 April to 23 June 2026, BlueVerse Google Ads invested <strong>AED {money(kpi['spend'])}</strong> across {len(campaigns)} search campaigns, generating <strong>{num_fmt(kpi['clicks'])}</strong> clicks, <strong>{num_fmt(kpi['impressions'])}</strong> impressions, and <strong>{num_fmt(kpi['conversions'])}</strong> form leads.</p>
      <div class="grid-3">
        <div>
          <h3>Headline metrics</h3>
          <ul class="pill-list">
            <li>CTR <strong>{pct(kpi['ctr'])}</strong></li>
            <li>CPC <strong>AED {money(kpi['cpc'])}</strong></li>
            <li>CPL <strong>AED {money(kpi['cpl'])}</strong></li>
            <li>CVR <strong>{pct(kpi['cvr'])}</strong></li>
            <li>CPM <strong>AED {money(kpi['cpm'])}</strong></li>
          </ul>
        </div>
        <div>
          <h3>Best performing campaign</h3>
          <p><strong>{best_camp['Campaign']}</strong> — {int(best_camp['Conversions'])} leads at AED {money(best_camp['CPL'])} CPL, {pct(best_camp['CTR'])} CTR.</p>
        </div>
        <div>
          <h3>Weakest campaign</h3>
          <p><strong>{weakest_camp['Campaign']}</strong> — {int(weakest_camp['Conversions'])} leads, AED {money(weakest_camp['CPL'])} CPL, {pct(weakest_camp['CTR'])} CTR.</p>
        </div>
      </div>
      <div class="insight"><strong>Biggest opportunity:</strong> {opp_text}</div>
    </section>

    <section id="kpi">
      <h2>2. KPI Cards</h2>
      <div class="kpi-grid">
        <div class="kpi"><div class="kpi-label">Total Spend</div><div class="kpi-value">AED {money(kpi['spend'])}</div></div>
        <div class="kpi"><div class="kpi-label">Impressions</div><div class="kpi-value">{num_fmt(kpi['impressions'])}</div></div>
        <div class="kpi"><div class="kpi-label">Clicks</div><div class="kpi-value">{num_fmt(kpi['clicks'])}</div></div>
        <div class="kpi"><div class="kpi-label">CTR</div><div class="kpi-value">{pct(kpi['ctr'])}</div></div>
        <div class="kpi"><div class="kpi-label">CPC</div><div class="kpi-value">AED {money(kpi['cpc'])}</div></div>
        <div class="kpi"><div class="kpi-label">Conversions</div><div class="kpi-value">{num_fmt(kpi['conversions'])}</div></div>
        <div class="kpi"><div class="kpi-label">CPL</div><div class="kpi-value">AED {money(kpi['cpl'])}</div></div>
        <div class="kpi"><div class="kpi-label">CVR</div><div class="kpi-value">{pct(kpi['cvr'])}</div></div>
        <div class="kpi"><div class="kpi-label">CPM</div><div class="kpi-value">AED {money(kpi['cpm'])}</div></div>
        <div class="kpi"><div class="kpi-label">Lost IS Rank</div><div class="kpi-value">{pct(kpi['lost_is_rank'])}</div></div>
        <div class="kpi"><div class="kpi-label">Lost IS Budget</div><div class="kpi-value">{pct(kpi['lost_is_budget'])}</div></div>
      </div>
    </section>
""")

    parts.append(f"""
    <section id="monthly">
      <h2>3. Monthly Performance Trend</h2>
      <div class="insight">{insight_monthly()}</div>
      <div class="chart-wrap"><canvas id="monthlyChart"></canvas></div>
      <h3>Monthly detail</h3>
      <div class="scroll">
        <table>
          <thead><tr><th>Month</th><th>Cost</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>CPC</th><th>Leads</th><th>CVR</th><th>CPL</th><th>CPM</th></tr></thead>
          <tbody>{rows_monthly}</tbody>
        </table>
      </div>
    </section>

    <section id="campaigns">
      <h2>4. Campaign Performance</h2>
      <div class="grid-2">
        <div class="chart-wrap small"><canvas id="campSpendChart"></canvas></div>
        <div class="chart-wrap small"><canvas id="campLeadsChart"></canvas></div>
      </div>
      <div class="scroll">
        <table>
          <thead><tr><th>Campaign</th><th>Status</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>Leads</th><th>CVR</th><th>Cost</th><th>Avg CPC</th><th>CPL</th><th>Lost IS Rank</th><th>Lost IS Budget</th></tr></thead>
          <tbody>{rows_campaigns}</tbody>
        </table>
      </div>
    </section>

    <section id="adgroups">
      <h2>5. Ad Group Performance</h2>
      <div class="chart-wrap small"><canvas id="agSpendChart"></canvas></div>
      <div class="scroll">
        <table>
          <thead><tr><th>Campaign</th><th>Ad Group</th><th>Status</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>Cost</th><th>CPC</th><th>Leads</th><th>CVR</th><th>CPL</th></tr></thead>
          <tbody>{rows_adgroups}</tbody>
        </table>
      </div>
      <div class="insight"><strong>Top efficient ad group:</strong> {best_ag['Campaign']} → {best_ag['Ad group']} ({int(best_ag['Conversions'])} leads at AED {money(best_ag['CPL'])}). <strong>Highest spend ad group:</strong> {highest_spend_ag['Campaign']} → {highest_spend_ag['Ad group']} (AED {money(highest_spend_ag['Cost'])}, {int(highest_spend_ag['Conversions'])} leads).</div>
    </section>

    <section id="keywords">
      <h2>6. Keyword Performance</h2>
      <div class="grid-2">
        <div>
          <h3>Top converters</h3>
          <div class="scroll">
            <table><thead><tr><th>Keyword</th><th>Match</th><th>Impr.</th><th>Clicks</th><th>CTR</th><th>Leads</th><th>CPL</th></tr></thead><tbody>{rows_kw_top_conv}</tbody></table>
          </div>
        </div>
        <div>
          <h3>Lowest CPL keywords</h3>
          <div class="scroll">
            <table><thead><tr><th>Keyword</th><th>Match</th><th>Clicks</th><th>Leads</th><th>CPL</th><th>Cost</th></tr></thead><tbody>{rows_kw_low_cpl}</tbody></table>
          </div>
        </div>
      </div>
      <h3>High-spend, no-conversion keywords</h3>
      <div class="scroll">
        <table><thead><tr><th>Keyword</th><th>Campaign</th><th>Match</th><th>Cost</th><th>Impr.</th><th>CTR</th><th>Action</th></tr></thead><tbody>{rows_kw_bad}</tbody></table>
      </div>
    </section>

    <section id="match">
      <h2>7. Match-Type Analysis</h2>
      <div class="grid-2">
        <div class="chart-wrap small"><canvas id="matchSpendChart"></canvas></div>
        <div class="chart-wrap small"><canvas id="matchCplChart"></canvas></div>
      </div>
      <div class="scroll">
        <table>
          <thead><tr><th>Match Type</th><th>Cost</th><th>Impr.</th><th>Clicks</th><th>CPC</th><th>Leads</th><th>CVR</th><th>CPL</th></tr></thead>
          <tbody>{rows_match}</tbody>
        </table>
      </div>
    </section>

    <section id="ads">
      <h2>8. Responsive Search Ad Analysis</h2>
      <div class="grid-2">
        <div>
          <h3>Highest CTR ads (min 100 impr.)</h3>
          <div class="scroll">
            <table><thead><tr><th>Campaign</th><th>Ad Group</th><th>Impr.</th><th>CTR</th><th>CPC</th><th>CPL</th></tr></thead><tbody>{rows_ads_ctr}</tbody></table>
          </div>
        </div>
        <div>
          <h3>Lowest CPL ads</h3>
          <div class="scroll">
            <table><thead><tr><th>Campaign</th><th>Ad Group</th><th>Clicks</th><th>Leads</th><th>CPL</th><th>Cost</th></tr></thead><tbody>{rows_ads_cpl}</tbody></table>
          </div>
        </div>
      </div>
      <div class="notice"><strong>Headline / description check:</strong> Ensure every RSA has at least 3 headline variants and 2 description variants. Pinning unique value props into headline positions 1 or 3 can improve CTR without hurting auctions.</div>
    </section>

    <section id="search">
      <h2>9. Search-Term Hygiene</h2>
      <div class="recommendation">
        <strong>Recommended negative keywords to add:</strong>
        <ul>
          <li><code>free</code>, <code>cheap</code>, <code>jobs</code>, <code>career</code>, <code>internship</code> (if not recruiting)</li>
          <li>Competitor brand terms with no conversions</li>
          <li>Generic terms with >500 impressions, CTR <1%, 0 leads</li>
        </ul>
      </div>
      <p>Review the Google Ads Search Terms report weekly and add non-converting, high-cost queries as exact or phrase negatives at campaign level.</p>
    </section>

    <section id="heatmap">
      <h2>10. Day × Hour Conversion Heatmap</h2>
      <div class="chart-wrap"><canvas id="heatConvChart"></canvas></div>
      <div class="grid-2">
        <div class="chart-wrap small"><canvas id="heatCplChart"></canvas></div>
        <div class="chart-wrap small"><canvas id="heatCostChart"></canvas></div>
      </div>
    </section>

    <section id="days">
      <h2>11. Daily Performance</h2>
      <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
    </section>

    <section id="lostis">
      <h2>12. Lost Impression Share</h2>
      <div class="grid-2">
        <div class="chart-wrap small"><canvas id="lostRankChart"></canvas></div>
        <div class="chart-wrap small"><canvas id="lostBudgetChart"></canvas></div>
      </div>
      <div class="insight"><strong>Diagnosis:</strong> Lost IS is dominated by {lost_rank_text}. {f'Rank-driven losses suggest low Quality Score or low bids.' if kpi['lost_is_rank']>kpi['lost_is_budget'] else 'Budget-driven losses mean campaigns are capped; raising budgets is the fastest way to add impression volume.'}</div>
    </section>
""")

    parts.append(f"""
    <section id="qs">
      <h2>13. Quality Score Audit</h2>
      {f'<div class="scroll"><table><thead><tr><th>Keyword</th><th>Campaign</th><th>Ad Group</th><th>QS</th><th>Exp CTR</th><th>Ad Rel</th><th>LP Exp</th><th>Cost</th><th>Leads</th></tr></thead><tbody>{qs_rows}</tbody></table></div>' if not qsa.empty else '<p>Quality Score data is not available in this export. Enable all Quality Score columns in Google Ads and re-export to populate this audit.</p>'}
      <div class="recommendation"><strong>QS action plan:</strong> {qs_text}</div>
    </section>

    <section id="timeline">
      <h2>14. Optimization Timeline</h2>
      <div class="timeline">
        <div class="timeline-item"><span>Week 1 · Immediate</span><br>Pause high-cost/no-conversion keywords; add negative keywords from search terms.</div>
        <div class="timeline-item"><span>Week 2 · Quick wins</span><br>Increase budgets on campaigns with >20% Lost IS (Budget) and positive CPL; raise bids on top-CPL keywords.</div>
        <div class="timeline-item"><span>Week 3 · Creative</span><br>Test 2–3 new RSA headlines per ad group based on top search terms; add sitelinks and callouts.</div>
        <div class="timeline-item"><span>Week 4 · Structure</span><br>Review match-type mix; move top exact keywords to dedicated ad groups; schedule ads around peak conversion hours.</div>
        <div class="timeline-item"><span>Ongoing</span><br>Weekly search-term hygiene, bi-weekly Quality Score review, monthly landing-page A/B test.</div>
      </div>
    </section>

    <section id="recommendations">
      <h2>15. AI Recommendations</h2>
      <div class="recommendation"><strong>1. Scale what works:</strong> Push budget into campaigns and ad groups with the lowest historical CPL while their Lost IS (Budget) is high.</div>
      <div class="recommendation"><strong>2. Stop waste:</strong> Pause or reduce bids on keywords with AED 200+ spend and zero conversions; add irrelevant spenders as negatives.</div>
      <div class="recommendation"><strong>3. Improve CTR:</strong> Add more compelling, keyword-specific headlines; use countdown and location ad customizers if relevant.</div>
      <div class="recommendation"><strong>4. Lower CPL:</strong> Tighten match types, improve Quality Score through ad relevance, and direct traffic to dedicated landing pages.</div>
      <div class="recommendation"><strong>5. Capture missed impressions:</strong> Address the dominant Lost IS driver ({lost_rank_text}) through bid/QS or budget increases.</div>
    </section>

    <section id="insight">
      <h2>16. Final Executive Insight</h2>
      <p>BlueVerse Google Ads is generating measurable leads, but efficiency has compressed as the quarter progressed. The best levers are <strong>budget reallocation</strong> toward the converting campaigns, <strong>search-term hygiene</strong> to cut waste, and <strong>ad/landing-page relevance</strong> to recover Quality Score and lower CPC/CPL.</p>
      <div class="insight"><strong>Expected 30-day impact if executed:</strong> 15–25% CPL reduction, 10–20% lead volume increase, and improved impression share with the same or lower spend.</div>
    </section>

    <footer>Generated by BlueVerse analytics pipeline · {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
  </div>

  <script>
    const palette = {{google:'#f97316', blue:'#2563eb', teal:'#0d9488', red:'#dc2626', green:'#16a34a', amber:'#d97706', slate:'#64748b'}};
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = '#475569';

    new Chart(document.getElementById('monthlyChart'), {{
      type: 'bar',
      data: {{
        labels: {to_json(month_labels)},
        datasets: [
          {{label:'Spend (AED)', data:{to_json(month_spend)}, backgroundColor:palette.google, yAxisID:'y'}},
          {{label:'Clicks', data:{to_json(month_clicks)}, type:'line', borderColor:palette.blue, backgroundColor:palette.blue, yAxisID:'y1', tension:0.3}},
          {{label:'Leads', data:{to_json(month_leads)}, type:'line', borderColor:palette.teal, backgroundColor:palette.teal, yAxisID:'y1', tension:0.3}}
        ]
      }},
      options: {{responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}}, scales:{{y:{{beginAtZero:true, grid:{{color:'#e2e8f0'}}}}, y1:{{position:'right', beginAtZero:true, grid:{{display:false}}}}}}}}
    }});

    new Chart(document.getElementById('campSpendChart'), {{
      type: 'doughnut',
      data: {{labels:{to_json(camp_names)}, datasets:[{{data:{to_json(camp_spend)}, backgroundColor:[palette.google,palette.blue,palette.teal,palette.red,palette.green,palette.amber,'#8b5cf6','#ec4899']}}]}},
      options: {{responsive:true, maintainAspectRatio:false, plugins:{{legend:{{position:'right'}}}}}}
    }});

    new Chart(document.getElementById('campLeadsChart'), {{
      type: 'bar',
      data: {{labels:{to_json(camp_names)}, datasets:[{{label:'Leads', data:{to_json(camp_leads)}, backgroundColor:palette.blue}}]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{y:{{beginAtZero:true}}}}}}
    }});

    new Chart(document.getElementById('agSpendChart'), {{
      type: 'bar',
      data: {{labels:{to_json(ag_labels)}, datasets:[{{label:'Spend (AED)', data:{to_json(ag_spend)}, backgroundColor:palette.google}}]}},
      options: {{responsive:true, maintainAspectRatio:false, indexAxis:'y', scales:{{x:{{beginAtZero:true}}}}}}
    }});

    new Chart(document.getElementById('matchSpendChart'), {{
      type: 'pie',
      data: {{labels:{to_json(match_df['Match type'].tolist())}, datasets:[{{data:{to_json(match_df['Cost'].round(2).tolist())}, backgroundColor:[palette.blue,palette.google,palette.teal,palette.red]}}]}},
      options: {{responsive:true, maintainAspectRatio:false}}
    }});

    new Chart(document.getElementById('matchCplChart'), {{
      type: 'bar',
      data: {{labels:{to_json(match_df['Match type'].tolist())}, datasets:[{{label:'CPL (AED)', data:{to_json([round(v,2) for v in match_df['CPL'].tolist()])}, backgroundColor:palette.teal}}]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{y:{{beginAtZero:true}}}}}}
    }});

    const heatLabels = {to_json(full_days)};
    const heatHours = {to_json(hours)};
    function heatDS(data, label, colorScale) {{
      return {{
        type: 'matrix',
        label: label,
        data: data.flatMap((row, y) => row.map((v, x) => ({{x:x, y:y, v:v}}))),
        backgroundColor(ctx) {{
          const v = ctx.raw?.v ?? 0;
          return colorScale(v);
        }},
        width: {{size:18}}, height: {{size:18}}
      }};
    }}
    function convColor(v){{ const max = Math.max(...{to_json(heat_conv)}.flat()); return `rgba(249,115,22,${{max? v/max*0.85+0.15 : 0.1}})`; }}
    function cplColor(v){{ const max = Math.max(...{to_json(heat_cpl)}.flat()); return `rgba(37,99,235,${{max? v/max*0.85+0.15 : 0.1}})`; }}
    function costColor(v){{ const max = Math.max(...{to_json(heat_cost)}.flat()); return `rgba(13,148,136,${{max? v/max*0.85+0.15 : 0.1}})`; }}

    new Chart(document.getElementById('heatConvChart'), {{
      type: 'matrix',
      data: {{datasets:[heatDS({to_json(heat_conv)}, 'Conversions', convColor)]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{x:{{type:'category', labels:heatHours, title:{{display:true, text:'Hour of day'}}}}, y:{{type:'category', labels:heatLabels, title:{{display:true, text:'Day'}}}}}}, plugins:{{tooltip:{{callbacks:{{label:c=>'Conversions: '+c.raw.v}}}}}}}}
    }});
    new Chart(document.getElementById('heatCplChart'), {{
      type: 'matrix',
      data: {{datasets:[heatDS({to_json(heat_cpl)}, 'Avg CPL (AED)', cplColor)]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{x:{{type:'category', labels:heatHours}}, y:{{type:'category', labels:heatLabels}}}}}}
    }});
    new Chart(document.getElementById('heatCostChart'), {{
      type: 'matrix',
      data: {{datasets:[heatDS({to_json(heat_cost)}, 'Spend (AED)', costColor)]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{x:{{type:'category', labels:heatHours}}, y:{{type:'category', labels:heatLabels}}}}}}
    }});

    new Chart(document.getElementById('dailyChart'), {{
      type: 'line',
      data: {{
        labels: {to_json(day_labels)},
        datasets: [
          {{label:'Spend (AED)', data:{to_json(day_spend)}, borderColor:palette.google, backgroundColor:palette.google, tension:0.2, yAxisID:'y'}},
          {{label:'Leads', data:{to_json(day_leads)}, borderColor:palette.teal, backgroundColor:palette.teal, tension:0.2, yAxisID:'y1'}}
        ]
      }},
      options: {{responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}}, scales:{{y:{{beginAtZero:true}}, y1:{{position:'right', beginAtZero:true, grid:{{display:false}}}}}}}}
    }});

    new Chart(document.getElementById('lostRankChart'), {{
      type: 'bar',
      data: {{labels:{to_json(camp_names)}, datasets:[{{label:'Lost IS Rank (%)', data:{to_json(camp_lost_rank)}, backgroundColor:palette.red}}]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{y:{{beginAtZero:true, max:100}}}}}}
    }});
    new Chart(document.getElementById('lostBudgetChart'), {{
      type: 'bar',
      data: {{labels:{to_json(camp_names)}, datasets:[{{label:'Lost IS Budget (%)', data:{to_json(camp_lost_budget)}, backgroundColor:palette.amber}}]}},
      options: {{responsive:true, maintainAspectRatio:false, scales:{{y:{{beginAtZero:true, max:100}}}}}}
    }});
    const explorerData = {explorer_json};
    const metricMeta = {{
      Cost: {{label:'Cost (AED)', color:palette.google, axis:'y'}},
      Impressions: {{label:'Impressions', color:palette.blue, axis:'y1'}},
      Clicks: {{label:'Clicks', color:palette.teal, axis:'y1'}},
      Conversions: {{label:'Conversions', color:palette.green, axis:'y1'}},
      CTR: {{label:'CTR (%)', color:palette.red, axis:'y2'}},
      CPC: {{label:'CPC (AED)', color:palette.amber, axis:'y'}},
      CPL: {{label:'CPL (AED)', color:'#8b5cf6', axis:'y'}},
      CPM: {{label:'CPM (AED)', color:'#ec4899', axis:'y'}},
      CVR: {{label:'CVR (%)', color:'#14b8a6', axis:'y2'}},
    }};
    const expCampSel = document.getElementById('expCampaign');
    const expM1Sel = document.getElementById('expMetric1');
    const expM2Sel = document.getElementById('expMetric2');
    Object.keys(explorerData.series).sort().forEach(c => {{
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      expCampSel.appendChild(opt);
    }});
    Object.keys(metricMeta).forEach(m => {{
      const opt1 = document.createElement('option');
      opt1.value = m; opt1.textContent = metricMeta[m].label;
      expM1Sel.appendChild(opt1);
      const opt2 = document.createElement('option');
      opt2.value = m; opt2.textContent = metricMeta[m].label;
      expM2Sel.appendChild(opt2);
    }});
    expCampSel.value = 'All campaigns';
    expM1Sel.value = 'Cost';
    expM2Sel.value = 'Conversions';
    let explorerChart = null;
    function buildExplorerDataset(metric, seriesDates, seriesMetrics) {{
      const map = Object.fromEntries(seriesDates.map((d,i) => [d, seriesMetrics[metric][i]]));
      const data = explorerData.dates.map(d => map[d] ?? null);
      return {{label: metricMeta[metric].label, data, borderColor: metricMeta[metric].color, backgroundColor: metricMeta[metric].color, tension:0.25, yAxisID: metricMeta[metric].axis, spanGaps:true}};
    }}
    function updateExplorerChart() {{
      const camp = expCampSel.value;
      const m1 = expM1Sel.value;
      const m2 = expM2Sel.value;
      const s = explorerData.series[camp] || explorerData.series[Object.keys(explorerData.series)[0]];
      const datasets = [buildExplorerDataset(m1, s.dates, s.metrics)];
      if (m2 && m2 !== m1) datasets.push(buildExplorerDataset(m2, s.dates, s.metrics));
      const scales = {{
        x: {{grid:{{color:'#e2e8f0'}}}},
        y: {{position:'left', beginAtZero:true, grid:{{color:'#e2e8f0'}}, title:{{display:true, text:'AED'}}}},
        y1: {{position:'right', beginAtZero:true, grid:{{display:false}}, title:{{display:true, text:'Count'}}}},
        y2: {{position:'right', beginAtZero:true, grid:{{display:false}}, title:{{display:true, text:'%'}}}}
      }};
      const usedAxes = new Set(datasets.map(d => d.yAxisID));
      if (!usedAxes.has('y')) scales.y.display = false;
      if (!usedAxes.has('y1')) scales.y1.display = false;
      if (!usedAxes.has('y2')) scales.y2.display = false;
      if (explorerChart) {{ explorerChart.data.datasets = datasets; explorerChart.options.scales = scales; explorerChart.update(); return; }}
      explorerChart = new Chart(document.getElementById('explorerChart'), {{
        type: 'line',
        data: {{labels: explorerData.dates, datasets}},
        options: {{responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}}, scales, plugins:{{legend:{{position:'top'}}}}}}
      }});
    }}
    [expCampSel, expM1Sel, expM2Sel].forEach(el => el.addEventListener('change', updateExplorerChart));
    updateExplorerChart();
  </script>
</body>
</html>
""")
    return "".join(parts)


def main():
    kw, months, ads, heat, days = load_data()
    kpi = overall_metrics(months, days)
    monthly = monthly_performance(months)
    campaigns = campaign_performance(months, days)
    adgroups = adgroup_performance(months)
    camp_daily = campaign_daily_performance(days)
    ads_df = ads_performance(ads)
    match_df = match_type_analysis(kw)
    heat_df = heatmap_data(heat)
    day_perf = day_performance(days)
    qsa = quality_score_audit(kw)

    html = render_html(kpi, monthly, campaigns, adgroups, kw, ads_df, heat_df, day_perf, qsa, match_df, camp_daily)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Report written to {OUT_HTML}")


if __name__ == "__main__":
    main()
