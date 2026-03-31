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

        # 2. Identity — high cardinality, known ID patterns, or personal name columns
        id_signals = ["_id", "_ID", "Email", "email", "Unique", "SAP", "sap",
                      "Corporate_ID", "Employee_ID", "Manager_Corporate",
                      "First_Name", "Last_Name", "Position_Title",  # personal identifiers
                      "Work_Email", "Legacy_SAP", "HRBP_Corporate", "Operational_Manager"]
        is_name_col = any(sig in col for sig in id_signals)
        # Also skip if values look like personal names (contain spaces and mixed case)
        sample_vals = series.astype(str).head(5).tolist()
        looks_like_names = sum(1 for v in sample_vals if ' ' in v and not v.isupper()) >= 3
        if is_name_col or looks_like_names or n_unique > n_rows * 0.5:
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


def score_field_relevance(field_name, user_prompt):
    """
    Score how relevant a field is to the user's prompt.
    Pure keyword + structural analysis — fully deterministic, no AI.
    """
    prompt_lower = user_prompt.lower()
    field_lower = field_name.lower().replace("_", " ")
    score = 0.0

    # Direct name match
    if field_lower in prompt_lower:
        score += 0.9
    for word in field_lower.split():
        if len(word) > 3 and word in prompt_lower:
            score += 0.3

    # Semantic groups: prompt keywords → field name fragments
    groups = [
        (["gender","sex","male","female","diversity","inclusion"],          ["gender"]),
        (["age","young","senior","junior","generation"],                    ["age","birth"]),
        (["band","level","grade","seniority","rank"],                       ["band","level","grade"]),
        (["function","department","team","division","unit","org"],          ["function","division","department"]),
        (["location","city","region","country","site","office","place"],    ["location","city","region","country","establishment"]),
        (["contract","employment","type","permanent","temporary","fixed"],  ["contract","worker","position","employment"]),
        (["job","role","profile","title","position"],                       ["job","profile","position","title"]),
        (["attrition","turnover","inactive","active","status","leave"],     ["workforce","staffing","status"]),
        (["headcount","count","total","employee","people","workforce"],     ["workforce","staffing","status","function","band"]),
        (["time","trend","monthly","history","evolution","over time"],      ["month","year","snapshot","date","series"]),
        (["cost","center","budget","finance"],                              ["cost","center","financial","division"]),
        (["org","organization","supervisory","hierarchy","structure"],      ["supervisory","org"]),
        (["fte","full time","part time","hours"],                           ["fte"]),
        (["collar","blue","white","category"],                              ["collar","category"]),
        (["family","group","category","classification"],                    ["family","group","category"]),
        (["worker","category","regular","intern","limited"],                ["worker","category","contract"]),
    ]
    for prompt_kws, field_frags in groups:
        if any(kw in prompt_lower for kw in prompt_kws):
            if any(frag in field_lower for frag in field_frags):
                score += 0.5

    return min(score, 1.0)


def select_chart_type_for_pair(f1_n, f2_n, f2_is_numeric=False, f1_is_temporal=False, f2_is_temporal=False):
    """
    Given two fields and their cardinalities, choose the best chart type.
    Rules based on data visualization theory, not AI.
    """
    if f1_is_temporal or f2_is_temporal:
        return "line"
    if f2_is_numeric:
        return "composed"          # bar (count) + line (avg metric)
    # Both categorical
    if f2_n == 2:
        return "stacked_bar"       # binary secondary = composition view
    if f1_n <= 6 and f2_n <= 5:
        return "grouped_bar"       # small × small = side by side
    if f1_n > 8:
        return "horizontal_bar"    # many primary categories = horizontal
    return "stacked_bar"


def select_chart_type_for_single(n_unique, is_temporal=False, is_numeric=False):
    """Chart type for a single field."""
    if is_temporal:
        return "line"
    if is_numeric:
        return "bar"       # will be binned
    if n_unique == 2:
        return "donut"
    if n_unique <= 5:
        return "donut"     # few categories look better as donut than bar
    if n_unique <= 12:
        return "bar"
    if n_unique <= 30:
        return "horizontal_bar"
    return "table"


def compute_chart_data(df, chart_type, fields, active_filters=None):
    """
    Compute real aggregated data for any chart type from a DataFrame.
    This is the single data computation function used everywhere:
    the planner, filter recomputation, and the /api/chart-data endpoint.

    df            — already scoped to the right snapshot by the caller
    chart_type    — bar, donut, grouped_bar, stacked_bar, horizontal_bar,
                    composed, line, table
    fields        — list of column names [primary] or [primary, secondary]
    active_filters — {field: [values]} applied before aggregation
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
        # ── TABLE ────────────────────────────────────────────────────────────
        if chart_type == "table":
            if not f1 or f1 not in df.columns:
                return []
            if f2 and f2 in df.columns:
                pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
                pivot["Total"] = pivot.sum(axis=1)
                pivot = pivot.sort_values("Total", ascending=False).head(12).reset_index()
                return [{str(k): (int(v) if hasattr(v, "item") else v)
                         for k, v in row.items()} for _, row in pivot.iterrows()]
            counts = df[f1].astype(str).value_counts().reset_index()
            counts.columns = [f1, "Count"]
            total = counts["Count"].sum()
            counts["Share %"] = (counts["Count"] / total * 100).round(1).astype(str) + "%"
            return counts.head(12).to_dict("records")

        # ── DONUT / PIE ───────────────────────────────────────────────────────
        elif chart_type in ("donut", "pie"):
            if not f1 or f1 not in df.columns:
                return []
            counts = df[f1].astype(str).value_counts().head(8)
            return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        # ── BAR (single field, optionally binned if numeric) ──────────────────
        elif chart_type == "bar":
            if not f1 or f1 not in df.columns:
                return []
            numeric = pd.to_numeric(df[f1], errors="coerce")
            if numeric.notna().sum() / len(df) > 0.8:
                bins = pd.cut(numeric.dropna(), bins=8)
                counts = bins.value_counts().sort_index()
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]
            counts = df[f1].astype(str).value_counts().head(12)
            return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        # ── HORIZONTAL BAR ────────────────────────────────────────────────────
        elif chart_type == "horizontal_bar":
            if not f1 or f1 not in df.columns:
                return []
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

        # ── GROUPED BAR ───────────────────────────────────────────────────────
        elif chart_type == "grouped_bar":
            if not f1 or not f2 or f1 not in df.columns or f2 not in df.columns:
                # Fall back to single-field bar
                if f1 and f1 in df.columns:
                    counts = df[f1].astype(str).value_counts().head(10)
                    return [{"name": str(k), "value": int(v)} for k, v in counts.items()]
                return []
            pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
            pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index[:8]]
            result = []
            for idx, row in pivot.iterrows():
                entry = {"name": str(idx)}
                for col in pivot.columns:
                    entry[str(col)] = int(row[col])
                result.append(entry)
            return result

        # ── STACKED BAR ───────────────────────────────────────────────────────
        elif chart_type == "stacked_bar":
            if not f1 or not f2 or f1 not in df.columns or f2 not in df.columns:
                if f1 and f1 in df.columns:
                    counts = df[f1].astype(str).value_counts().head(10)
                    return [{"name": str(k), "value": int(v)} for k, v in counts.items()]
                return []
            pivot = df.groupby([f1, f2]).size().unstack(fill_value=0)
            pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index[:8]]
            result = []
            for idx, row in pivot.iterrows():
                entry = {"name": str(idx)}
                for col in pivot.columns:
                    entry[str(col)] = int(row[col])
                result.append(entry)
            return result

        # ── COMPOSED (bar count + line avg metric) ────────────────────────────
        elif chart_type == "composed":
            if not f1 or f1 not in df.columns:
                return []
            counts = df[f1].astype(str).value_counts().head(8)
            result = []
            for k, v in counts.items():
                subset = df[df[f1].astype(str) == k]
                entry = {"name": str(k), "Count": int(v)}
                if f2 and f2 in df.columns:
                    numeric = pd.to_numeric(subset[f2], errors="coerce").mean()
                    entry[f"Avg {f2}"] = round(float(numeric), 2) if not pd.isna(numeric) else 0
                else:
                    # Find the best binary field to compute a rate
                    for col in df.columns:
                        if col == f1:
                            continue
                        vc = df[col].astype(str).value_counts()
                        if len(vc) == 2:
                            minority = vc.index[-1]
                            n_minority = len(subset[subset[col].astype(str) == minority])
                            entry[f"{minority} Rate %"] = round(n_minority / v * 100, 1) if v > 0 else 0
                            break
                result.append(entry)
            return result

        # ── LINE / TIME SERIES ────────────────────────────────────────────────
        elif chart_type == "line":
            if not f1 or f1 not in df.columns:
                return []
            try:
                df_copy = df.copy()
                df_copy["_ts"] = pd.to_datetime(df_copy[f1], errors="coerce")
                df_copy = df_copy.dropna(subset=["_ts"])
                df_copy["_ts_str"] = df_copy["_ts"].dt.strftime("%Y-%m")
                if f2 and f2 in df.columns:
                    top_vals = df[f2].astype(str).value_counts().head(4).index.tolist()
                    pivot = (df_copy[df_copy[f2].astype(str).isin(top_vals)]
                             .groupby(["_ts_str", f2]).size().unstack(fill_value=0).reset_index())
                    result = []
                    for _, row in pivot.sort_values("_ts_str").iterrows():
                        entry = {"name": row["_ts_str"]}
                        for col in pivot.columns:
                            if col != "_ts_str":
                                entry[str(col)] = int(row[col])
                        result.append(entry)
                    return result
                ts = df_copy.groupby("_ts_str").size().reset_index(name="value")
                return [{"name": r["_ts_str"], "value": int(r["value"])}
                        for _, r in ts.sort_values("_ts_str").iterrows()]
            except Exception as e:
                print(f"Line chart error: {e}")
                return []

    except Exception as e:
        import traceback
        print(f"compute_chart_data error ({chart_type}, {fields}): {e}")
        traceback.print_exc()

    return []


def plan_dashboard_charts(df_raw, classified, user_prompt, n_charts=7):
    """
    Deterministic chart planning engine. Runs entirely in Python on real data.

    Key design principles:
    1. ALWAYS prefer two-field cross-tabulations over single-field counts
       Single-field bar charts are the last resort, not the default
    2. Enforce chart type DIVERSITY — never repeat the same chart type
       more than twice in a row
    3. Use the longitudinal (full) dataset for time-series,
       latest snapshot for everything else
    4. Score fields by relevance to user prompt, then build combinations
    5. Computed data is attached here — Gemini only writes titles/insights
    """
    plans = []
    used_combos = set()
    type_counts = {}  # track how many of each type we've used

    # Build metadata for every field
    field_meta = {}
    for col, counts in classified["categorical"].items():
        field_meta[col] = {
            "type": "categorical", "n": len(counts),
            "is_temporal": False, "is_numeric": False
        }
    for col, stats in classified["numeric"].items():
        field_meta[col] = {
            "type": "numeric", "n": int(stats["max"] - stats["min"]),
            "is_temporal": False, "is_numeric": True
        }
    for col in classified["temporal"]:
        n_ts = df_raw[col].nunique() if col in df_raw.columns else 1
        field_meta[col] = {
            "type": "temporal", "n": n_ts,
            "is_temporal": True, "is_numeric": False
        }

    # Filter out identity-like and low-value fields from planning
    skip_patterns = ["_id", "email", "first_name", "last_name", "work_email",
                     "legacy", "siglum", "code", "_iso", "unique_id"]
    planning_fields = [
        col for col in field_meta
        if not any(p in col.lower() for p in skip_patterns)
    ]

    # Score every field for relevance
    scores = {col: score_field_relevance(col, user_prompt) for col in planning_fields}

    # Sort by score descending
    ranked = sorted(planning_fields, key=lambda c: scores[c], reverse=True)

    def can_add_type(chart_type):
        """Enforce diversity — max 2 of any one type, except table (max 1)."""
        limit = 1 if chart_type == "table" else 2
        return type_counts.get(chart_type, 0) < limit

    def add_plan(fields, chart_type, source=""):
        combo = tuple(sorted(fields))
        if combo in used_combos:
            return False
        if not can_add_type(chart_type):
            return False
        data = compute_chart_data(
            df_raw if chart_type == "line" else
            df_raw[df_raw["Is_Latest_Snapshot"].astype(str).str.lower().isin(["true","1","yes"])]
            if "Is_Latest_Snapshot" in df_raw.columns else df_raw,
            chart_type, fields
        )
        if not data and chart_type != "table":
            return False
        used_combos.add(combo)
        type_counts[chart_type] = type_counts.get(chart_type, 0) + 1
        plans.append({"fields": fields, "type": chart_type, "computed_data": data})
        return True

    # ── Phase 1: Time series (always include if temporal data exists) ─────────
    for col in classified["temporal"]:
        if len(plans) >= n_charts:
            break
        add_plan([col], "line", "temporal_single")

    # ── Phase 2: Cross-field combinations — PRIORITISED over single fields ────
    # Build all possible pairs from top-ranked fields, score each pair
    pair_candidates = []
    for i, f1 in enumerate(ranked[:10]):
        m1 = field_meta[f1]
        if m1["is_temporal"]:
            continue
        for f2 in ranked[i+1:11]:
            m2 = field_meta[f2]
            if m2["is_temporal"]:
                continue
            # Combined score = sum of individual scores + cross-relevance bonus
            pair_score = scores[f1] + scores[f2]
            # Bonus: numeric secondary creates a composed chart (most visually rich)
            if m2["is_numeric"]:
                pair_score += 0.3
            # Bonus: binary secondary creates clean stacked bar
            if m2["n"] == 2:
                pair_score += 0.2
            # Penalty: redundant fields (Job_Profile vs Job_Family — same information)
            if (("job_profile" in f1.lower() and "job_family" in f2.lower()) or
                ("job_family" in f1.lower() and "job_profile" in f2.lower()) or
                ("location" in f1.lower() and "city" in f2.lower()) or
                ("city" in f1.lower() and "location" in f2.lower())):
                pair_score -= 0.5

            chart_type = select_chart_type_for_pair(
                m1["n"], m2["n"],
                f2_is_numeric=m2["is_numeric"],
                f1_is_temporal=m1["is_temporal"],
                f2_is_temporal=m2["is_temporal"],
            )
            pair_candidates.append((pair_score, f1, f2, chart_type))

    # Sort pairs by score
    pair_candidates.sort(reverse=True)

    for pair_score, f1, f2, chart_type in pair_candidates:
        if len(plans) >= n_charts:
            break
        add_plan([f1, f2], chart_type, "pair")

    # ── Phase 3: Fill remaining with single-field charts (with diversity) ─────
    # Prefer donut for binary/few-category fields to break up bar monotony
    for col in ranked:
        if len(plans) >= n_charts:
            break
        m = field_meta[col]
        if m["is_temporal"]:
            continue
        chart_type = select_chart_type_for_single(m["n"], m["is_temporal"], m["is_numeric"])
        add_plan([col], chart_type, "single")

    # ── Phase 4: Always end with a summary table if we have room ─────────────
    if len(plans) < n_charts and type_counts.get("table", 0) == 0:
        for col in ranked[:3]:
            m = field_meta[col]
            if not m["is_temporal"] and not m["is_numeric"]:
                f2_col = next((c for c in ranked if c != col
                               and not field_meta[c]["is_temporal"]
                               and not field_meta[c]["is_numeric"]), None)
                fields = [col, f2_col] if f2_col else [col]
                if add_plan(fields, "table", "summary"):
                    break

    return plans


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
                df_filtered, classified, user_message, n_charts=7, df_raw=df_raw
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
        df_raw2 = load_dataset()
        df_latest, _ = get_latest_snapshot(df_raw2) if df_raw2 is not None else (None, "")
        viz_data_context = []
        for viz in dashboard.get("visualizations", []):
            fields = viz.get("fields", [])
            computed = compute_chart_data(df_latest, viz["type"], fields, active_filters) if df_latest is not None else []
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