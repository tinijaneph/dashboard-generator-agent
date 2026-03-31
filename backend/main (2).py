from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import vertexai
from vertexai.preview.generative_models import GenerativeModel
import os
import json
import pandas as pd
import io
from datetime import datetime
from google.cloud import storage

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type", "Authorization"], methods=["GET", "POST", "OPTIONS"])

# Initialize Vertex AI
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "molten-album-478703-d8")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
BUCKET_NAME = os.environ.get("GCS_BUCKET", "dashboard-generator-data")
DATA_FILE_GCS = os.environ.get("GCS_FILE", "nominative_list.csv")

vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.0-flash-001")

_df_cache = None

def load_dataset():
    """
    Load the workforce CSV from GCS.
    Cached in memory after first load — the dataset only changes when
    a new file is uploaded to the bucket, not between requests.
    To force a reload (e.g. after uploading new data), restart the Cloud Run instance
    or call the /api/reload endpoint.
    No local fallback — always use real data from GCS.
    """
    global _df_cache
    if _df_cache is not None:
        return _df_cache
    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(DATA_FILE_GCS)
        raw = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
        _df_cache = df
        print(f"Loaded {len(df):,} rows, {len(df.columns)} columns from gs://{BUCKET_NAME}/{DATA_FILE_GCS}")
        return df
    except Exception as e:
        print(f"ERROR loading dataset from GCS: {e}")
        return None


def get_latest_snapshot(df):
    """
    Isolate the most recent point-in-time snapshot from a longitudinal dataset.
    Tries three strategies in priority order so it works regardless of which
    snapshot column exists.
    """
    if "Is_Latest_Snapshot" in df.columns:
        mask = df["Is_Latest_Snapshot"].astype(str).str.lower().isin(["true", "1", "yes"])
        latest = df[mask]
        if len(latest) > 0:
            return latest, "Is_Latest_Snapshot=True"

    if "Snapshot_Month_Series" in df.columns:
        try:
            ts = pd.to_datetime(df["Snapshot_Month_Series"], errors="coerce")
            max_ts = ts.max()
            latest = df[ts == max_ts]
            if len(latest) > 0:
                return latest, f"Snapshot_Month_Series={max_ts}"
        except Exception:
            pass

    # Fallback: find any year+month column pair dynamically
    year_cols = [c for c in df.columns if "year" in c.lower() or "Year" in c]
    month_cols = [c for c in df.columns if "month" in c.lower() or "Month" in c]
    if year_cols and month_cols:
        try:
            ym = df[year_cols[0]].astype(str) + df[month_cols[0]].astype(str).str.zfill(2)
            latest = df[ym == ym.max()]
            if len(latest) > 0:
                return latest, f"Latest {year_cols[0]}+{month_cols[0]}: {ym.max()}"
        except Exception:
            pass

    return df, "full dataset"


def classify_columns(df):
    """
    Automatically classify every column into one of four categories.
    This is the core intelligence layer — it decides which fields have
    analytical value without any hardcoded column names.

    Returns a dict:
      categorical: {col: {value: count}}  — useful for groupby / charts
      numeric:     {col: {mean, ...}}     — useful for aggregations
      temporal:    [col, ...]             — date columns for time series
      identity:    [col, ...]             — IDs, emails — skip for charts
      constant:    {col: single_value}    — only 1 value, useless for charts
    """
    result = {"categorical": {}, "numeric": {}, "temporal": [], "identity": [], "constant": {}}
    n_rows = len(df)

    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        n_unique = series.nunique()

        # 1. Constants — single value, useless
        if n_unique == 1:
            result["constant"][col] = str(series.iloc[0])
            continue

        # 2. Identity — very high cardinality or known ID patterns
        id_signals = ["_id", "_ID", "Email", "email", "Unique", "SAP", "sap",
                      "Corporate_ID", "Employee_ID", "Manager_Corporate"]
        if any(sig in col for sig in id_signals) or n_unique > n_rows * 0.5:
            result["identity"].append(col)
            continue

        # 3. Numeric
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() / len(series) > 0.8 and n_unique > 10:
            result["numeric"][col] = {
                "mean": round(float(numeric.mean()), 2),
                "median": round(float(numeric.median()), 2),
                "min": round(float(numeric.min()), 2),
                "max": round(float(numeric.max()), 2),
                "n": int(numeric.notna().sum()),
            }
            continue

        # 4. Temporal — date-like column names or parseable as dates
        temporal_signals = ["date", "Date", "month", "Month", "year", "Year",
                            "series", "Series", "_Month", "_Year"]
        if any(sig in col for sig in temporal_signals):
            try:
                parsed = pd.to_datetime(series, errors="coerce")
                if parsed.notna().sum() / len(series) > 0.7:
                    result["temporal"].append(col)
                    continue
            except Exception:
                pass

        # 5. Categorical — 2 to 150 unique values = analytically useful
        if 2 <= n_unique <= 150:
            counts = series.astype(str).value_counts()
            result["categorical"][col] = {str(k): int(v) for k, v in counts.head(20).items()}

        # else: >150 unique and not numeric/temporal — free text, skip silently

    return result


def score_field_relevance(field_name, field_stats, user_prompt):
    """
    Score how relevant a field is to the user's prompt.
    Pure keyword + structure analysis — no AI, fully deterministic.
    Returns a float 0.0–1.0.
    """
    prompt_lower = user_prompt.lower()
    field_lower = field_name.lower()
    score = 0.0

    # Direct name match in prompt
    if field_lower in prompt_lower:
        score += 0.8
    # Partial word match
    for word in field_lower.replace("_", " ").split():
        if len(word) > 3 and word in prompt_lower:
            score += 0.3

    # Semantic keyword groups — maps prompt concepts to likely field name fragments
    keyword_groups = [
        (["gender", "sex", "male", "female", "diversity"], ["gender"]),
        (["age", "young", "senior", "tenure", "experience"], ["age", "hire", "seniority", "service"]),
        (["band", "level", "grade", "seniority", "senior", "junior"], ["band", "level", "grade"]),
        (["function", "department", "team", "division", "unit"], ["function", "division", "department", "family"]),
        (["location", "city", "region", "country", "site", "office"], ["location", "city", "region", "country"]),
        (["contract", "employment", "permanent", "temporary", "type"], ["contract", "worker", "position"]),
        (["job", "role", "profile", "title", "position"], ["job", "profile", "position", "title"]),
        (["attrition", "turnover", "inactive", "active", "status", "workforce"], ["workforce", "staffing", "status"]),
        (["headcount", "count", "total", "employee", "workforce", "people"], ["workforce", "staffing", "status"]),
        (["time", "trend", "monthly", "over time", "history", "evolution"], ["month", "year", "snapshot", "date"]),
        (["cost", "center", "budget"], ["cost", "center"]),
        (["org", "organization", "supervisory", "hierarchy", "structure"], ["supervisory", "org"]),
        (["fte", "full time", "part time", "hours"], ["fte"]),
        (["collar", "blue", "white", "category"], ["collar", "category"]),
    ]

    for prompt_keywords, field_fragments in keyword_groups:
        prompt_match = any(kw in prompt_lower for kw in prompt_keywords)
        field_match = any(frag in field_lower for frag in field_fragments)
        if prompt_match and field_match:
            score += 0.5

    # Structural bonuses: binary fields are great for comparison charts
    if field_stats.get("type") == "categorical":
        n_unique = field_stats.get("n_unique", 0)
        if n_unique == 2:
            score += 0.1  # binary = very clean donut or grouped bar
        elif 3 <= n_unique <= 6:
            score += 0.05  # small cardinality = readable chart

    return min(score, 1.0)


def select_chart_type(field1_stats, field2_stats=None):
    """
    Deterministically select the best chart type based on field structure.
    Rules derived from data visualization best practices:

    Single field:
      - 2 values      → donut (proportions)
      - 3-6 values    → bar (readable columns)
      - 7-15 values   → horizontal_bar (long labels)
      - numeric       → histogram (use bar with binning)
      - temporal      → line

    Two fields:
      - cat × cat (both ≤ 6 values) → grouped_bar or stacked_bar
      - cat × binary                → stacked_bar (shows composition)
      - cat × numeric               → composed (bar count + line avg)
      - temporal × cat              → line (multi-series)
      - high cardinality primary    → horizontal_bar
    """
    t1 = field1_stats.get("type")
    n1 = field1_stats.get("n_unique", 0)
    is_temporal1 = field1_stats.get("is_temporal", False)

    if field2_stats is None:
        # Single field
        if is_temporal1:
            return "line"
        if t1 == "numeric":
            return "bar"  # backend will bin it
        if n1 == 2:
            return "donut"
        if n1 <= 6:
            return "bar"
        if n1 <= 20:
            return "horizontal_bar"
        return "table"

    t2 = field2_stats.get("type")
    n2 = field2_stats.get("n_unique", 0)
    is_temporal2 = field2_stats.get("is_temporal", False)

    # Time series with secondary breakdown
    if is_temporal1 or is_temporal2:
        return "line"

    # Numeric secondary = composed (count bar + metric line)
    if t2 == "numeric":
        return "composed"

    # Both categorical
    if t1 == "categorical" and t2 == "categorical":
        if n2 == 2:
            return "stacked_bar"   # binary secondary = perfect for stacked composition
        if n1 > 8:
            return "horizontal_bar"  # long primary labels
        if n2 <= 5:
            return "grouped_bar"
        return "stacked_bar"

    return "bar"


def plan_dashboard_charts(df, classified, user_prompt, n_charts=7):
    """
    The core chart planning engine. Runs entirely in Python on real data.
    No AI involved — chart type and field selection are deterministic.

    Steps:
    1. Score every field for relevance to the user's prompt
    2. Always include 1 overview chart (overall distribution of key status field)
    3. Always include 1 time-series if temporal data exists
    4. Fill remaining slots with the highest-scoring field pairs
    5. Select chart type based on field structure (not AI guessing)
    6. Compute real data for every chart right here

    Returns a list of chart specs with real computed_data already attached.
    """
    plans = []

    # Build field info lookup
    field_info = {}
    for col, stats in classified["categorical"].items():
        n_unique = len(stats)
        field_info[col] = {"type": "categorical", "n_unique": n_unique,
                           "is_temporal": False, "stats": stats}
    for col, stats in classified["numeric"].items():
        field_info[col] = {"type": "numeric", "n_unique": 999,
                           "is_temporal": False, "stats": stats}
    for col in classified["temporal"]:
        n_ts = df[col].nunique() if col in df.columns else 1
        field_info[col] = {"type": "temporal", "n_unique": n_ts,
                           "is_temporal": True, "stats": {}}

    # Score all categorical + temporal fields
    scores = {}
    for col, info in field_info.items():
        scores[col] = score_field_relevance(col, info, user_prompt)

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_fields = [f for f, s in ranked if s > 0 or len(plans) < 3]

    used_combos = set()

    def add_chart(f1, f2=None, override_type=None, is_overview=False, is_timeseries=False):
        combo = tuple(sorted([f1] + ([f2] if f2 else [])))
        if combo in used_combos:
            return False
        used_combos.add(combo)

        info1 = field_info.get(f1, {"type": "categorical", "n_unique": 5, "is_temporal": False})
        info2 = field_info.get(f2) if f2 else None

        chart_type = override_type or select_chart_type(info1, info2)
        fields = [f1] + ([f2] if f2 else [])

        # Compute real data
        computed = compute_chart_data(df, chart_type, fields)
        if not computed and chart_type != "table":
            return False

        plans.append({
            "fields": fields,
            "type": chart_type,
            "computed_data": computed,
            "is_overview": is_overview,
            "is_timeseries": is_timeseries,
        })
        return True

    # 1. Overview chart: find the most relevant single field for a donut/bar
    if top_fields:
        best = top_fields[0]
        info = field_info.get(best, {})
        n = info.get("n_unique", 5)
        t = "donut" if n <= 6 else "bar"
        add_chart(best, override_type=t, is_overview=True)

    # 2. Time series if temporal data exists
    for col in classified["temporal"]:
        if len(plans) < n_charts:
            add_chart(col, override_type="line", is_timeseries=True)
            break

    # 3. Best cross-field combinations
    for i, f1 in enumerate(top_fields[:8]):
        if len(plans) >= n_charts:
            break
        for f2 in top_fields[i+1:9]:
            if len(plans) >= n_charts:
                break
            if field_info.get(f1, {}).get("is_temporal") or field_info.get(f2, {}).get("is_temporal"):
                continue  # already handled time series
            add_chart(f1, f2)

    # 4. Fill remaining slots with single-field charts from top ranked
    for f in top_fields:
        if len(plans) >= n_charts:
            break
        add_chart(f)

    # 5. Always end with a summary table
    if len(plans) < n_charts and top_fields:
        f1 = top_fields[0]
        f2 = top_fields[1] if len(top_fields) > 1 else None
        add_chart(f1, f2, override_type="table")

    return plans


def compute_chart_data(df, chart_type, fields, active_filters=None):
    """
    Compute real aggregated data for a chart from the DataFrame.
    This is the single source of truth — no fake data anywhere.
    active_filters: {field: [values]} applied before aggregation.
    """
    if active_filters:
        for field, values in active_filters.items():
            if field in df.columns and values:
                df = df[df[field].astype(str).isin([str(v) for v in values])]

    if len(df) == 0:
        return []

    f1 = fields[0] if fields else None
    f2 = fields[1] if len(fields) > 1 else None

    try:
        if chart_type == "table":
            if f1 and f1 in df.columns:
                counts = df[f1].astype(str).value_counts().reset_index()
                counts.columns = [f1, "Count"]
                total = counts["Count"].sum()
                counts["Share %"] = (counts["Count"] / total * 100).round(1).astype(str) + "%"
                if f2 and f2 in df.columns:
                    # Add breakdown by f2 as columns
                    pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
                    pivot["Total"] = pivot.sum(axis=1)
                    pivot = pivot.sort_values("Total", ascending=False).head(10).reset_index()
                    return [{str(k): (int(v) if isinstance(v, (int, float)) else str(v))
                             for k, v in row.items()} for _, row in pivot.iterrows()]
                return counts.head(10).to_dict("records")

        elif chart_type in ("donut", "pie"):
            if f1 and f1 in df.columns:
                counts = df[f1].astype(str).value_counts().head(8)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        elif chart_type == "bar":
            if f1 and f1 in df.columns:
                # Check if numeric — bin it
                numeric = pd.to_numeric(df[f1], errors="coerce")
                if numeric.notna().sum() / len(df) > 0.8:
                    bins = pd.cut(numeric.dropna(), bins=8)
                    counts = bins.value_counts().sort_index()
                    return [{"name": str(k), "value": int(v)} for k, v in counts.items()]
                counts = df[f1].astype(str).value_counts().head(12)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        elif chart_type == "horizontal_bar":
            if f1 and f1 in df.columns:
                if f2 and f2 in df.columns:
                    pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
                    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index[:10]]
                    result = []
                    for idx, row in pivot.iterrows():
                        entry = {"name": str(idx)}
                        for col in pivot.columns:
                            entry[str(col)] = int(row[col])
                        result.append(entry)
                    return result
                counts = df[f1].astype(str).value_counts().head(12)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        elif chart_type == "grouped_bar":
            if f1 and f2 and f1 in df.columns and f2 in df.columns:
                pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
                # Keep top 8 by total
                pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index[:8]]
                result = []
                for idx, row in pivot.iterrows():
                    entry = {"name": str(idx)}
                    for col in pivot.columns:
                        entry[str(col)] = int(row[col])
                    result.append(entry)
                return result

        elif chart_type == "stacked_bar":
            if f1 and f2 and f1 in df.columns and f2 in df.columns:
                pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
                pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index[:8]]
                result = []
                for idx, row in pivot.iterrows():
                    entry = {"name": str(idx)}
                    for col in pivot.columns:
                        entry[str(col)] = int(row[col])
                    result.append(entry)
                return result

        elif chart_type == "composed":
            if f1 and f1 in df.columns:
                counts = df[f1].astype(str).value_counts().head(8)
                result = []
                for k, v in counts.items():
                    subset = df[df[f1].astype(str) == k]
                    entry = {"name": str(k), "Count": int(v)}
                    if f2 and f2 in df.columns:
                        num = pd.to_numeric(subset[f2], errors="coerce").mean()
                        entry[f"Avg {f2}"] = round(float(num), 2) if not pd.isna(num) else 0
                    else:
                        # Find the best binary field for rate computation
                        for col in df.columns:
                            if col == f1:
                                continue
                            vc = df[col].astype(str).value_counts()
                            if len(vc) == 2:
                                minority_val = vc.index[-1]
                                n_minority = len(subset[subset[col].astype(str) == minority_val])
                                rate = round(n_minority / v * 100, 1) if v > 0 else 0
                                entry[f"{minority_val} Rate %"] = rate
                                break
                    result.append(entry)
                return result

        elif chart_type == "line":
            # Use full longitudinal data for time series
            if f1 and f1 in df.columns:
                try:
                    ts_col = f1
                    df_copy = df.copy()
                    df_copy["_ts"] = pd.to_datetime(df_copy[ts_col], errors="coerce")
                    df_copy = df_copy.dropna(subset=["_ts"])
                    df_copy["_ts_str"] = df_copy["_ts"].dt.strftime("%Y-%m")
                    if f2 and f2 in df.columns:
                        top_vals = df[f2].astype(str).value_counts().head(4).index.tolist()
                        pivot = df_copy[df_copy[f2].astype(str).isin(top_vals)].groupby(
                            ["_ts_str", f2]).size().unstack(fill_value=0).reset_index()
                        result = []
                        for _, row in pivot.sort_values("_ts_str").iterrows():
                            entry = {"name": row["_ts_str"]}
                            for col in pivot.columns:
                                if col != "_ts_str":
                                    entry[str(col)] = int(row[col])
                            result.append(entry)
                        return result
                    else:
                        ts = df_copy.groupby("_ts_str").size().reset_index(name="value")
                        return [{"name": r["_ts_str"], "value": int(r["value"])}
                                for _, r in ts.sort_values("_ts_str").iterrows()]
                except Exception as e:
                    print(f"Line chart error: {e}")

    except Exception as e:
        import traceback
        print(f"compute_chart_data error ({chart_type}, {fields}): {e}")
        traceback.print_exc()

    return []




def get_data_summary():
    """
    Produces a 100% data-driven summary injected into every AI prompt.

    Design principles:
    - No field names, category values, or counts are hardcoded anywhere
    - Scopes to the latest snapshot (point-in-time accuracy)
    - Skips constants, IDs, and high-cardinality free text automatically
    - Any schema change (new columns, renamed columns, new category values,
      more/fewer employees) reflects automatically without code changes
    - Loads from GCS only — no local fallback to avoid stale data
    """
    df_raw = load_dataset()
    if df_raw is None:
        return "Dataset not available — check GCS bucket and file path."

    df, snapshot_label = get_latest_snapshot(df_raw)

    # Distinct employee count using best available ID column
    id_col = next(
        (c for c in ["Corporate_ID", "Employee_ID", "Nominative_List_Unique_ID"]
         if c in df.columns), None
    )
    distinct_employees = int(df[id_col].nunique()) if id_col else len(df)

    # Time coverage — detect temporal columns dynamically
    date_range = ""
    snapshot_months = []
    classified_raw = classify_columns(df_raw)
    for tcol in classified_raw["temporal"]:
        try:
            ts = pd.to_datetime(df_raw[tcol], errors="coerce").dropna()
            if len(ts) > 0:
                date_range = f"{ts.min().strftime('%Y-%m')} to {ts.max().strftime('%Y-%m')}"
                snapshot_months = sorted(ts.dt.strftime("%Y-%m").unique().tolist())
                break
        except Exception:
            continue
    if not date_range:
        # Try any column with "month" or "year" in name that has low cardinality
        for col in df_raw.columns:
            if any(kw in col.lower() for kw in ["month", "year", "snapshot"]):
                vals = df_raw[col].dropna().astype(str).unique()
                if 1 < len(vals) <= 60:
                    snapshot_months = sorted(vals.tolist())
                    date_range = f"{snapshot_months[0]} to {snapshot_months[-1]}"
                    break

    classified = classify_columns(df)

    lines = [
        "=== WORKFORCE DATASET ===",
        f"Snapshot: {snapshot_label}",
        f"Distinct employees (latest snapshot): {distinct_employees:,}",
        f"Total rows in full dataset: {len(df_raw):,} (longitudinal — NOT employee count)",
        f"All columns ({len(df.columns)}): {', '.join(df.columns.tolist())}",
    ]
    if date_range:
        lines.append(f"Date range covered: {date_range}")
    if snapshot_months:
        lines.append(f"Available snapshot months: {snapshot_months}")

    if classified["categorical"]:
        lines.append("")
        lines.append("=== CATEGORICAL FIELDS — use these for charts and groupby ===")
        for col, counts in classified["categorical"].items():
            total = sum(counts.values())
            lines.append(f'{col} (n={total:,}): {json.dumps(counts)}')

    if classified["numeric"]:
        lines.append("")
        lines.append("=== NUMERIC FIELDS ===")
        for col, s in classified["numeric"].items():
            lines.append(
                f'{col}: mean={s["mean"]}, median={s["median"]}, '
                f'min={s["min"]}, max={s["max"]}, n={s["n"]:,}'
            )

    if classified["temporal"]:
        lines.append("")
        lines.append("=== TEMPORAL FIELDS — use for time-series ===")
        lines.append(", ".join(classified["temporal"]))

    if classified["constant"]:
        lines.append("")
        lines.append("=== CONSTANT FIELDS — DO NOT use for charts (single value, no analytical value) ===")
        for col, val in classified["constant"].items():
            lines.append(f'  {col} = "{val}"')

    lines += [
        "",
        "=== RULES FOR AI ===",
        "1. Use ONLY column names from 'All columns' list.",
        "2. Charts must use ONLY fields from CATEGORICAL or NUMERIC sections.",
        "3. Category names in insights must EXACTLY match values shown above.",
        "4. KPI values must come from the numbers above — never invent counts.",
        "5. Constant fields have zero analytical value — never use for groupby.",
        "6. Distinct employees = headcount. Total rows = longitudinal history.",
    ]

    return "\n".join(lines)


SYSTEM_PROMPT = """You are an expert HR Analytics AI. Generate data-driven dashboards using ONLY the statistics provided.

{data_summary}

=== YOUR TASK ===
Read the CATEGORICAL FIELDS section above carefully.
Those are the ONLY fields with analytical value in this dataset.
Select fields most relevant to the user's request.
Every chart, KPI, and insight must reflect the actual numbers shown — never invent values.

=== OUTPUT RULES ===
OVERVIEW: 1-2 sentences. What the dashboard analyzes and why it matters.

OVERALL_INSIGHTS: Exactly 5 bullets. Each must:
  - Quote a real number from the statistics
  - Be under 20 words
  - State a finding + what it implies

METRICS: 3-5 KPI cards. Values must come from the statistics.

VISUALIZATIONS: 6-8 charts. For each:
  - "fields": column names that exist in the data (check All columns list)
  - "key_insights": 2-3 bullets under 15 words each with real numbers
  - Never use category values not listed in the statistics

CHART TYPES:
  bar           — single categorical field, simple counts
  grouped_bar   — two categorical fields compared side by side
  stacked_bar   — two categorical fields, stacked composition
  horizontal_bar — when category label names are long strings
  composed      — bar (count) + line (rate) dual axis
  donut         — overall proportions, max 6 slices
  line          — temporal fields for time series
  table         — multi-column detail with real numbers

SUGGESTIONS: 5 specific follow-up ideas using real field names from the data.

=== RESPONSE (valid JSON only, no markdown fences) ===
{{
  "message": "One sentence confirming what was built.",
  "analysis_type": "workforce|attrition|headcount|demographics|org|custom",
  "suggestions": ["...", "...", "...", "...", "..."],
  "dashboard": {{
    "title": "Short descriptive title",
    "overview": "1-2 sentences.",
    "overall_insights": ["insight with real number", "...x5"],
    "metrics": [
      {{"label": "...", "value": "real number from stats", "trend": "up|down|stable", "change": "...", "insight": "..."}}
    ],
    "visualizations": [
      {{
        "id": "viz-1",
        "type": "chart_type",
        "title": "Chart title",
        "description": "One sentence.",
        "fields": ["RealColumnName"],
        "data_hint": "descriptive_hint",
        "key_insights": ["finding with real number", "what it implies"]
      }}
    ],
    "recommendations": ["actionable recommendation"]
  }}
}}

If modifying an existing dashboard: keep all visualizations, only add/change what was requested.
"""




def calculate_actual_data(viz_type, fields, data_hint="", active_filters=None):
    """
    Compute real chart data from the dataset.

    Always scopes to the LATEST SNAPSHOT for point-in-time accuracy.
    For line/trend charts, uses the FULL longitudinal dataset grouped by snapshot.

    active_filters: dict of {field_name: [selected_values]} — applied before aggregation.
    This is how the UI filter bar actually changes chart data.
    """
    df_raw = load_dataset()
    if df_raw is None:
        return []

    try:
        hint = (data_hint or "").lower()
        primary_field = fields[0] if fields else None
        secondary_field = fields[1] if len(fields) > 1 else None

        # Line/trend charts need the full longitudinal data grouped by snapshot
        is_time_series = viz_type == "line" or "trend" in hint or "time" in hint or "month" in hint

        if is_time_series:
            df = df_raw.copy()
        else:
            # All other charts: scope to latest snapshot only
            df, _ = get_latest_snapshot(df_raw)

        # Apply active UI filters (this is what makes filter chips actually work)
        if active_filters:
            for filter_field, selected_values in active_filters.items():
                if filter_field in df.columns and selected_values:
                    df = df[df[filter_field].astype(str).isin([str(v) for v in selected_values])]

        if len(df) == 0:
            return []

        # ── TABLE ─────────────────────────────────────────────────────────────
        if viz_type == "table":
            valid_fields = [f for f in fields if f in df.columns]
            if not valid_fields:
                return []
            group_col = valid_fields[0]

            # Try to build a rich table: headcount + breakdown by second field if available
            if secondary_field and secondary_field in df.columns:
                grp = df.groupby([group_col, secondary_field]).size().reset_index(name="Count")
                # Pivot so each value of secondary becomes a column
                pivoted = grp.pivot_table(index=group_col, columns=secondary_field, values="Count", fill_value=0)
                pivoted["Total"] = pivoted.sum(axis=1)
                pivoted = pivoted.sort_values("Total", ascending=False).head(10)
                pivoted = pivoted.reset_index()
                # Round and convert
                result = []
                for _, row in pivoted.iterrows():
                    result.append({str(k): (int(v) if isinstance(v, (int, float)) else str(v)) for k, v in row.items()})
                return result
            else:
                # Simple count table
                counts = df[group_col].value_counts().head(10).reset_index()
                counts.columns = [group_col, "Count"]
                # Add percentage column
                counts["Rate %"] = (counts["Count"] / counts["Count"].sum() * 100).round(1).astype(str) + "%"
                return counts.to_dict("records")

        # ── GROUPED / STACKED BAR — requires two fields ───────────────────────
        elif viz_type in ("grouped_bar", "stacked_bar"):
            if primary_field and secondary_field and primary_field in df.columns and secondary_field in df.columns:
                grp = df.groupby([primary_field, secondary_field]).size().reset_index(name="count")
                pivoted = grp.pivot_table(index=primary_field, columns=secondary_field, values="count", fill_value=0)
                # Sort by total descending, keep top 8 categories
                pivoted["_total"] = pivoted.sum(axis=1)
                pivoted = pivoted.sort_values("_total", ascending=False).head(8).drop(columns=["_total"])
                result = []
                for idx, row in pivoted.iterrows():
                    entry = {"name": str(idx)}
                    for col in pivoted.columns:
                        entry[str(col)] = int(row[col])
                    result.append(entry)
                return result
            elif primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(8)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        # ── SIMPLE BAR ────────────────────────────────────────────────────────
        elif viz_type == "bar":
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(10)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        # ── HORIZONTAL BAR ───────────────────────────────────────────────────
        elif viz_type == "horizontal_bar":
            if primary_field and secondary_field and primary_field in df.columns and secondary_field in df.columns:
                grp = df.groupby([primary_field, secondary_field]).size().reset_index(name="count")
                pivoted = grp.pivot_table(index=primary_field, columns=secondary_field, values="count", fill_value=0)
                pivoted["_total"] = pivoted.sum(axis=1)
                pivoted = pivoted.sort_values("_total", ascending=False).head(10).drop(columns=["_total"])
                result = []
                for idx, row in pivoted.iterrows():
                    entry = {"name": str(idx)}
                    for col in pivoted.columns:
                        entry[str(col)] = int(row[col])
                    result.append(entry)
                return result
            elif primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(10)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        # ── LINE / TIME SERIES — uses full longitudinal data ─────────────────
        elif viz_type == "line":
            if "Snapshot_Month_Series" in df.columns:
                try:
                    df["_ts"] = pd.to_datetime(df["Snapshot_Month_Series"], errors="coerce")
                    grp = df.dropna(subset=["_ts"]).groupby("_ts")
                    if secondary_field and secondary_field in df.columns:
                        # Multi-series: one line per value of secondary_field
                        pivoted = df.dropna(subset=["_ts"]).groupby(["_ts", secondary_field]).size().reset_index(name="count")
                        top_vals = df[secondary_field].value_counts().head(4).index.tolist()
                        pivoted = pivoted[pivoted[secondary_field].isin(top_vals)]
                        piv = pivoted.pivot_table(index="_ts", columns=secondary_field, values="count", fill_value=0).reset_index()
                        piv = piv.sort_values("_ts")
                        result = []
                        for _, row in piv.iterrows():
                            entry = {"name": str(row["_ts"])[:7]}
                            for col in piv.columns:
                                if col != "_ts":
                                    entry[str(col)] = int(row[col])
                            result.append(entry)
                        return result
                    else:
                        ts = grp.size().reset_index(name="value").sort_values("_ts")
                        return [{"name": str(r["_ts"])[:7], "value": int(r["value"])} for _, r in ts.iterrows()]
                except Exception as e:
                    print(f"Time series error: {e}")
            else:
                # No Snapshot_Month_Series — find any temporal column dynamically
                classified = classify_columns(df)
                for tcol in classified["temporal"]:
                    try:
                        ts = df.groupby(tcol).size().reset_index(name="value")
                        ts = ts.sort_values(tcol)
                        return [{"name": str(r[tcol]), "value": int(r["value"])} for _, r in ts.iterrows()]
                    except Exception:
                        continue

        # ── COMPOSED — bar + line (e.g. count bar + rate line) ───────────────
        elif viz_type == "composed":
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(8)
                result = []

                # Dynamically find the best secondary metric:
                # Priority 1 — if a secondary field is specified, use it
                # Priority 2 — find any binary/low-cardinality status column
                #              and compute a non-dominant-value rate (e.g. inactive %)
                # This works regardless of what the status column is called
                status_col = None
                status_minority = None
                if secondary_field and secondary_field in df.columns:
                    pass  # handled per-row below
                else:
                    # Find a binary-ish column (2-5 unique values) that could be a status
                    for col in df.columns:
                        if col == primary_field:
                            continue
                        vc = df[col].astype(str).value_counts()
                        if 2 <= len(vc) <= 5:
                            # The minority value is likely the "attrition/inactive" signal
                            status_col = col
                            status_minority = vc.index[-1]  # least common value
                            break

                for k, v in counts.items():
                    subset = df[df[primary_field] == k]
                    entry = {"name": str(k), "Count": int(v)}
                    if secondary_field and secondary_field in df.columns:
                        try:
                            val = pd.to_numeric(subset[secondary_field], errors="coerce").mean()
                            entry[secondary_field] = round(float(val), 2) if not pd.isna(val) else 0
                        except Exception:
                            pass
                    elif status_col:
                        n_minority = len(subset[subset[status_col].astype(str) == status_minority])
                        rate = round(n_minority / v * 100, 1) if v > 0 else 0
                        entry[f"{status_minority} Rate %"] = rate
                    result.append(entry)
                return result

        # ── PIE / DONUT ───────────────────────────────────────────────────────
        elif viz_type in ("pie", "donut"):
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(6)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

    except Exception as e:
        import traceback
        print(f"Data calculation error: {e}")
        traceback.print_exc()

    return []


@app.route("/health", methods=["GET"])
def health_check():
    df = load_dataset()
    distinct = 0
    snapshot = "unknown"
    if df is not None:
        id_col = next((c for c in ["Corporate_ID", "Employee_ID"] if c in df.columns), None)
        if id_col:
            df_latest, snapshot = get_latest_snapshot(df)
            distinct = int(df_latest[id_col].nunique())
    return jsonify({
        "status": "healthy",
        "project_id": PROJECT_ID,
        "model": "gemini-2.0-flash-001",
        "dataset_loaded": df is not None,
        "total_rows": len(df) if df is not None else 0,
        "distinct_employees_latest_snapshot": distinct,
        "snapshot": snapshot,
        "gcs": f"gs://{BUCKET_NAME}/{DATA_FILE_GCS}",
    })


@app.route("/api/reload", methods=["POST"])
def reload_data():
    """Force reload the dataset from GCS — call this after uploading new data."""
    global _df_cache
    _df_cache = None
    df = load_dataset()
    if df is None:
        return jsonify({"error": "Failed to load dataset from GCS"}), 500
    df_latest, snapshot = get_latest_snapshot(df)
    id_col = next((c for c in ["Corporate_ID", "Employee_ID"] if c in df_latest.columns), None)
    distinct = int(df_latest[id_col].nunique()) if id_col else len(df_latest)
    return jsonify({
        "status": "reloaded",
        "total_rows": len(df),
        "distinct_employees": distinct,
        "snapshot": snapshot,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        conversation_history = data.get("history", [])
        current_dashboard = data.get("current_dashboard", None)

        active_filters = data.get("active_filters", {})

        df_raw = load_dataset()
        if df_raw is None:
            return jsonify({"error": "Dataset not available"}), 503

        df_latest, snapshot_label = get_latest_snapshot(df_raw)

        # Apply active filters to the planning dataset
        df_filtered = df_latest.copy()
        if active_filters:
            for field, values in active_filters.items():
                if field in df_filtered.columns and values:
                    df_filtered = df_filtered[
                        df_filtered[field].astype(str).isin([str(v) for v in values])
                    ]

        classified = classify_columns(df_filtered)

        # ── STEP 1: Python plans the charts deterministically ─────────────────
        # If new dashboard: plan from scratch using field relevance scoring
        # If modifying: keep existing plans, just add what was requested
        if not current_dashboard:
            chart_plans = plan_dashboard_charts(
                df_raw, classified, user_message, n_charts=7
            )
        else:
            # Modification — re-compute data for existing charts with new filters
            chart_plans = []
            for viz in current_dashboard.get("visualizations", []):
                fields = viz.get("fields", [])
                chart_type = viz.get("type", "bar")
                computed = compute_chart_data(df_filtered, chart_type, fields, {})
                chart_plans.append({
                    "fields": fields,
                    "type": chart_type,
                    "computed_data": computed,
                    "existing_title": viz.get("title", ""),
                    "existing_description": viz.get("description", ""),
                    "existing_insights": viz.get("key_insights", []),
                })

        # ── STEP 2: Build the prompt — Gemini only writes narrative ───────────
        data_summary = get_data_summary()

        # Serialize chart plans for Gemini (without the bulk computed_data)
        chart_specs_for_prompt = []
        for i, plan in enumerate(chart_plans):
            # Give Gemini a compact data preview — first 8 rows only
            data_preview = plan.get("computed_data", [])[:8]
            spec = {
                "chart_index": i + 1,
                "chart_type": plan["type"],
                "fields": plan["fields"],
                "data_preview": data_preview,
            }
            if plan.get("existing_title"):
                spec["existing_title"] = plan["existing_title"]
            chart_specs_for_prompt.append(spec)

        id_col = next((c for c in ["Corporate_ID", "Employee_ID"] if c in df_filtered.columns), None)
        distinct_n = int(df_filtered[id_col].nunique()) if id_col else len(df_filtered)

        prompt = f"""{SYSTEM_PROMPT.format(data_summary=data_summary)}

=== PRE-COMPUTED CHART PLANS ===
The Python backend has already selected the chart types and computed real data.
Your ONLY job is to write the narrative: title, description, key_insights for each chart.

TOTAL EMPLOYEES IN VIEW: {distinct_n:,} (snapshot: {snapshot_label})
{"ACTIVE FILTERS: " + json.dumps(active_filters) if active_filters else "No filters active."}

CHART PLANS (use these exact types and fields — do NOT change them):
{json.dumps(chart_specs_for_prompt, indent=2)}

USER REQUEST: {user_message}

{f'EXISTING DASHBOARD (modify mode — keep structure, update narrative only):\n{json.dumps(current_dashboard, indent=2)[:2000]}' if current_dashboard else ''}

CONVERSATION CONTEXT:
{chr(10).join([f"{'User' if m['role']=='user' else 'AI'}: {m['content']}" for m in conversation_history[-4:]])}

Respond with valid JSON only. The "visualizations" array must have exactly {len(chart_plans)} entries,
one per chart plan above, in the same order.
Each visualization must include: id, type (MUST match chart_type from plan), fields (MUST match),
title, description, key_insights (2-3 bullets with real numbers from data_preview).
"""

        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": 6000, "temperature": 0.2, "top_p": 0.9},
        )

        raw = response.text.strip()
        for fence in ["```json", "```"]:
            if fence in raw:
                start = raw.find(fence) + len(fence)
                end = raw.rfind("```")
                raw = raw[start:end].strip()
                break

        try:
            parsed = json.loads(raw)
        except Exception as e:
            print(f"JSON parse error: {e}\nRaw: {raw[:400]}")
            parsed = {
                "message": "Dashboard generated.",
                "dashboard": current_dashboard,
                "suggestions": [],
            }

        # ── STEP 3: Attach real computed_data to every visualization ─────────
        # The computed data from chart_plans is the source of truth —
        # overrides anything Gemini may have invented
        dashboard = parsed.get("dashboard")
        if dashboard and "visualizations" in dashboard:
            vizs = dashboard["visualizations"]
            for i, plan in enumerate(chart_plans):
                if i < len(vizs):
                    # Enforce correct type and fields from the plan
                    vizs[i]["type"] = plan["type"]
                    vizs[i]["fields"] = plan["fields"]
                    vizs[i]["computed_data"] = plan.get("computed_data", [])
                    if "id" not in vizs[i]:
                        vizs[i]["id"] = f"viz-{i+1}"

        return jsonify({
            "response": parsed.get("message", "Dashboard generated."),
            "dashboard": dashboard,
            "suggestions": parsed.get("suggestions", []),
            "analysis_type": parsed.get("analysis_type", "custom"),
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "message": "Error processing request."}), 500


@app.route("/api/chart-data", methods=["POST"])
def get_chart_data():
    """
    Recompute chart data for a specific visualization — used when filters change.
    Uses compute_chart_data which is the same engine as the planner.
    """
    try:
        req = request.json
        viz_type = req.get("type", "bar")
        fields = req.get("fields", [])
        active_filters = req.get("active_filters", {})

        df_raw = load_dataset()
        if df_raw is None:
            return jsonify({"data": []})

        df, _ = get_latest_snapshot(df_raw)
        computed = compute_chart_data(df, viz_type, fields, active_filters)
        return jsonify({"data": computed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/deeper-insights", methods=["POST"])
def deeper_insights():
    """
    Generate richer analyst-quality insights for a specific visualization.
    This is called when user clicks "Generate deeper insights" — it returns
    enhanced key_insights for each chart based on the actual computed data.
    """
    try:
        req = request.json
        dashboard = req.get("dashboard", {})
        active_filters = req.get("active_filters", {})

        if not dashboard:
            return jsonify({"error": "No dashboard provided"}), 400

        # Build a data-rich context for each visualization
        viz_data_context = []
        for viz in dashboard.get("visualizations", []):
            fields = viz.get("fields", [])
            hint = viz.get("data_hint", "")
            computed = calculate_actual_data(viz["type"], fields, hint, active_filters)
            if computed:
                viz_data_context.append({
                    "id": viz.get("id", ""),
                    "title": viz.get("title", ""),
                    "type": viz.get("type", ""),
                    "actual_data": computed[:10]  # first 10 rows/entries
                })

        filter_desc = f"Active filters: {active_filters}" if active_filters else "No active filters — full dataset"
        data_summary = get_data_summary()

        prompt = f"""You are an expert HR data analyst. Based on the actual computed data below, 
generate sharper, more specific key insights for each visualization.

DATASET CONTEXT:
{data_summary}

{filter_desc}

VISUALIZATIONS WITH ACTUAL DATA:
{json.dumps(viz_data_context, indent=2)}

CURRENT DASHBOARD TITLE: {dashboard.get("title", "")}

For each visualization, return 2-3 insights that:
1. Quote specific numbers directly from the actual_data provided
2. Make an interpretation (not just describe — explain what it means for the business)
3. Are concise — under 20 words each

Respond ONLY with valid JSON, no markdown:
{{
  "enhanced_insights": {{
    "<viz_id>": ["insight 1 with real number", "interpretation of why it matters", "optional third insight"],
    ...
  }},
  "overall_insights": [
    "5 updated overall insights based on actual data with real numbers"
  ]
}}"""

        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": 4096, "temperature": 0.2, "top_p": 0.9},
        )

        raw = response.text.strip()
        for fence in ["```json", "```"]:
            if fence in raw:
                start = raw.find(fence) + len(fence)
                end = raw.rfind("```")
                raw = raw[start:end].strip()
                break

        parsed = json.loads(raw)

        # Merge enhanced insights back into the dashboard visualizations
        enhanced = parsed.get("enhanced_insights", {})
        updated_vizs = []
        for viz in dashboard.get("visualizations", []):
            viz_id = viz.get("id", "")
            if viz_id in enhanced:
                viz = {**viz, "key_insights": enhanced[viz_id]}
            updated_vizs.append(viz)

        updated_dashboard = {
            **dashboard,
            "visualizations": updated_vizs,
            "overall_insights": parsed.get("overall_insights", dashboard.get("overall_insights", [])),
        }

        return jsonify({
            "dashboard": updated_dashboard,
            "message": "Insights refreshed with actual data.",
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/schema", methods=["GET"])
def get_schema():
    """
    Returns columns, row counts, and real distinct values for key categorical fields.
    Used by the frontend to populate filter dropdowns with actual data values.
    Always scoped to the latest snapshot so filter options match what users see.
    """
    df_raw = load_dataset()
    if df_raw is None:
        return jsonify({"columns": [], "sample": {}, "distinct_values": {}})

    df, snapshot_label = get_latest_snapshot(df_raw)

    # Dynamically detect filterable fields using classify_columns
    # Only categorical fields (2-150 unique values) are useful as filters
    classified = classify_columns(df)

    distinct_values = {}
    for col, counts in classified["categorical"].items():
        # Return sorted list of all unique values for this field (for filter dropdowns)
        distinct_values[col] = sorted(counts.keys())

    id_col = next((c for c in ["Corporate_ID", "Employee_ID", "Nominative_List_Unique_ID"]
                   if c in df.columns), None)
    distinct_employees = int(df[id_col].nunique()) if id_col else len(df)

    return jsonify({
        "columns": list(df.columns),
        "total_rows": len(df_raw),
        "snapshot_rows": len(df),
        "distinct_employees": distinct_employees,
        "snapshot_label": snapshot_label,
        "categorical_fields": list(classified["categorical"].keys()),
        "numeric_fields": list(classified["numeric"].keys()),
        "temporal_fields": classified["temporal"],
        "constant_fields": list(classified["constant"].keys()),
        "distinct_values": distinct_values,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
