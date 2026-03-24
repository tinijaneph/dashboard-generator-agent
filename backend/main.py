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
DATA_FILE_LOCAL = os.environ.get("LOCAL_DATA_FILE", "data/nominative_list.csv")

vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.0-flash-001")

_df_cache = None

def load_dataset():
    global _df_cache
    if _df_cache is not None:
        return _df_cache
    # Try GCS first
    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(DATA_FILE_GCS)
        content = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(content))
        _df_cache = df
        print(f"Loaded {len(df)} rows from GCS gs://{BUCKET_NAME}/{DATA_FILE_GCS}")
        return df
    except Exception as e:
        print(f"GCS load failed: {e}, trying local...")
    # Fallback local
    try:
        df = pd.read_csv(DATA_FILE_LOCAL)
        _df_cache = df
        print(f"Loaded {len(df)} rows from local {DATA_FILE_LOCAL}")
        return df
    except Exception as e:
        print(f"Local load failed: {e}")
        return None


def get_latest_snapshot(df):
    """
    Returns a DataFrame scoped to the single latest snapshot only.
    This is critical because the CSV is a longitudinal record — each employee
    can appear many times (one row per snapshot month). We never want to count
    raw rows; we always want distinct employees at the most recent point in time.

    Priority:
    1. Is_Latest_Snapshot == True  (explicit flag in data)
    2. Most recent Snapshot_Month_Series timestamp
    3. Most recent Snapshot_Year + Snapshot_Month combination
    4. Full DataFrame as last resort (with a warning)
    """
    # Option 1: explicit flag
    if "Is_Latest_Snapshot" in df.columns:
        latest = df[df["Is_Latest_Snapshot"].astype(str).str.lower().isin(["true", "1", "yes"])]
        if len(latest) > 0:
            return latest, "Is_Latest_Snapshot flag"

    # Option 2: timestamp column
    if "Snapshot_Month_Series" in df.columns:
        try:
            df["_ts"] = pd.to_datetime(df["Snapshot_Month_Series"], errors="coerce")
            max_ts = df["_ts"].max()
            latest = df[df["_ts"] == max_ts].drop(columns=["_ts"])
            if len(latest) > 0:
                return latest, f"Snapshot_Month_Series={max_ts}"
        except Exception:
            pass

    # Option 3: year + month combo
    if "Snapshot_Year" in df.columns and "Snapshot_Month" in df.columns:
        try:
            df["_ym"] = df["Snapshot_Year"].astype(str) + "-" + df["Snapshot_Month"].astype(str).str.zfill(2)
            max_ym = df["_ym"].max()
            latest = df[df["_ym"] == max_ym].drop(columns=["_ym"])
            if len(latest) > 0:
                return latest, f"Snapshot {max_ym}"
        except Exception:
            pass

    # Fallback
    print("WARNING: Could not isolate latest snapshot — using full dataset")
    return df, "full dataset (no snapshot column found)"


def get_data_summary():
    """
    Build a data-adaptive summary injected into every prompt.
    Always operates on the LATEST SNAPSHOT only — never on raw row counts.
    This means the summary is accurate regardless of dataset size (50k or 5M rows).
    """
    df_raw = load_dataset()
    if df_raw is None:
        return "Dataset not available. Using schema-only mode."

    # Always scope to latest snapshot
    df, snapshot_label = get_latest_snapshot(df_raw)
    total_raw = len(df_raw)
    total_snapshot = len(df)
    cols = list(df.columns)

    # Distinct employee count (using corporate ID if available)
    id_col = next((c for c in ["Corporate_ID", "Nominative_List_Unique_ID"] if c in df.columns), None)
    distinct_employees = df[id_col].nunique() if id_col else total_snapshot

    parts = [
        f"SNAPSHOT: {snapshot_label}",
        f"DISTINCT EMPLOYEES (latest snapshot): {distinct_employees:,}",
        f"TOTAL ROWS IN FULL DATASET: {total_raw:,} (longitudinal — multiple rows per employee over time)",
        f"SNAPSHOT ROWS: {total_snapshot:,}",
        f"COLUMNS ({len(cols)}): {', '.join(cols[:35])}",
    ]

    # Time coverage
    if "Snapshot_Year" in df_raw.columns:
        years = sorted(df_raw["Snapshot_Year"].dropna().unique().tolist())
        parts.append(f"YEARS COVERED IN FULL DATA: {years}")
    if "Snapshot_Month_Series" in df_raw.columns:
        try:
            ts = pd.to_datetime(df_raw["Snapshot_Month_Series"], errors="coerce")
            parts.append(f"DATE RANGE: {ts.min().strftime('%Y-%m')} to {ts.max().strftime('%Y-%m')}")
        except Exception:
            pass

    def dist(col, n=8):
        """Return value_counts as dict for a column, from latest snapshot."""
        if col not in df.columns:
            return None
        counts = df[col].dropna().value_counts().head(n).to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def pct(col, val):
        """Return percentage of rows where col == val."""
        if col not in df.columns:
            return None
        return round(len(df[df[col].astype(str) == str(val)]) / len(df) * 100, 1)

    # Workforce status — most important field
    for col in ["Active_Workforce_Status", "Current_Staffing_Status"]:
        d = dist(col)
        if d:
            parts.append(f"{col} (distinct employee counts at latest snapshot): {json.dumps(d)}")

    # Demographics
    for col in ["Gender", "Age_Group", "Band", "Band_Level", "Blue_White_Collar",
                "Worker_Category", "Contract_Type", "Professional_Category"]:
        d = dist(col)
        if d:
            parts.append(f"{col}: {json.dumps(d)}")

    # Org structure
    for col in ["Function", "Job_Family_Group", "Job_Family", "Job_Category",
                "Direct_Indirect", "Position_Worker_Type"]:
        d = dist(col)
        if d:
            parts.append(f"{col}: {json.dumps(d)}")

    # Geography
    for col in ["Reporting_Region", "Company_Country", "City_Name", "Company_Name"]:
        d = dist(col)
        if d:
            parts.append(f"{col}: {json.dumps(d)}")

    # FTE — numeric, use mean/total on latest snapshot
    if "FTE" in df.columns:
        try:
            fte = pd.to_numeric(df["FTE"], errors="coerce").dropna()
            parts.append(f"FTE: avg={fte.mean():.2f}, total={fte.sum():,.1f}, min={fte.min():.2f}, max={fte.max():.2f}")
        except Exception:
            pass

    # Seniority / tenure if available
    for col in ["Original_Hire_Date", "Seniority_Date", "Continuous_Service_Date"]:
        if col in df.columns:
            try:
                dates = pd.to_datetime(df[col], errors="coerce").dropna()
                if len(dates) > 0:
                    import datetime as dt_mod
                    now = pd.Timestamp.now()
                    tenure_years = ((now - dates).dt.days / 365.25).dropna()
                    parts.append(f"{col} → avg tenure: {tenure_years.mean():.1f} yrs, median: {tenure_years.median():.1f} yrs")
            except Exception:
                pass

    # Supervisory org depth
    for level in range(1, 5):
        col = f"Supervisory_Organization_Level_{level}_Name"
        d = dist(col, n=5)
        if d:
            parts.append(f"Supervisory Level {level} (top 5): {json.dumps(d)}")
            break  # just show the top level found

    parts.append(
        "IMPORTANT FOR AI: All counts above are for DISTINCT EMPLOYEES at the latest snapshot. "
        "Do NOT reference 555k or any raw row count — that is longitudinal history. "
        "Use the distinct employee numbers when writing insights and KPI values."
    )

    return "\n".join(parts)


SYSTEM_PROMPT = """You are an elite HR Analytics AI generating executive-grade dashboards matching Brick AI and Tableau quality.

DATASET CONTEXT:
{data_summary}

AVAILABLE FIELDS:
Gender, Age, Age_Group, Position_Title, Job_Profile, Job_Family, Job_Family_Group, Job_Category,
Function, Band, Blue_White_Collar, Worker_Category, Professional_Category, Contract_Type, FTE,
Active_Workforce_Status, Current_Staffing_Status, Company_Name, Entity_Name, Financial_Division_Name,
Core_Division, City_Name, Company_Country, Reporting_Region, Snapshot_Month, Snapshot_Year,
Snapshot_Month_Series, Is_Latest_Snapshot, Supervisory_Organization_Name, Supervisory_Organization_Level_1_Name

══════════════════════════════════════════
STRICT QUALITY RULES — FOLLOW EXACTLY
══════════════════════════════════════════

OVERVIEW: Max 2 sentences. What it analyzes + why it matters. Never a list.

OVERALL_INSIGHTS: Exactly 5 bullets. Each MUST be under 20 words with a real number.
  WRONG: "This dashboard provides a comprehensive view of workforce distribution across multiple dimensions"
  RIGHT: "Operations and Sales account for 58% of all inactive employees in the dataset"
  RIGHT: "Internship contracts show 3x higher attrition rate than permanent roles at 24% vs 8%"

METRICS: 3-5 KPI cards. Keep insight field under 12 words.

VISUALIZATIONS: Always generate exactly 7-8 charts. Use a variety of types.
  For each visualization key_insights must be EXACTLY 2-3 bullets.
  Each insight MUST include a real number AND be under 15 words.
  Use these patterns:
    "[Category]: [N] employees, [X]% rate — [superlative]"
    "[Category A] has [X]x higher [metric] than [Category B] ([N]% vs [M]%)"
    "[N] of [total] [group] are inactive — [X]% rate"
  WRONG: "Operations has the highest number of inactive employees across all functions"
  WRONG: "The chart reveals internship contracts show elevated departure rates"
  WRONG: "Finance shows strong retention compared to other departments"
  RIGHT: "Operations: 771 inactive, 28% rate — highest of all functions"
  RIGHT: "Internship contracts: 24% attrition — 3x higher than permanent (8%)"
  RIGHT: "Band I: 420 inactive of 1,350 total — 31% rate, most at-risk group"

  ANALYST INTERPRETATION RULE: The second or third bullet per chart should be an INTERPRETATION,
  not just another number. It should explain WHY the finding matters or what it implies.
  Example: "Internship contracts: 24% attrition — 3x higher than permanent (8%)"
  Follow-up interpretation: "High intern churn suggests onboarding and conversion pipeline gaps"
  Example: "Operations: 771 inactive — suggesting workload and management quality issues"
  
  The insight must read like a human analyst wrote it, not like a data label.
  Brick AI style: "Sales revenue growth notably outpaces ad spend in Q4, suggesting improved efficiency"
  Our style: "Attrition falls sharply from Band I (31%) to Band V (4%), confirming seniority protects retention"

CHART TYPE SELECTION:
  grouped_bar — two categories side by side (Active vs Inactive by Function, Male vs Female by Band)
  stacked_bar — stacked composition (headcount by Band stacked by Contract_Type)
  horizontal_bar — long category names (Job Role, Supervisory Org names)
  composed — bar + line dual axis (Headcount bar + Attrition Rate line by Department)
  donut — overall proportions max 6 slices (Active vs Inactive overall)
  line — time trend with Snapshot_Month_Series
  table — 3-5 column breakdowns with real numbers (Department, Count, Rate, Avg FTE)
  bar — simple categorical (headcount by Region, by Gender)

SUGGESTIONS: 5 specific follow-up prompts. Must reference actual field names.

══════════════════════════════════════════
RESPONSE — valid JSON only, no markdown:
══════════════════════════════════════════
{{
  "message": "One sentence confirming what was built.",
  "analysis_type": "workforce|attrition|headcount|demographics|org|custom",
  "suggestions": [
    "Show attrition by Band and Contract_Type",
    "Add headcount trend by Snapshot_Month",
    "Break down by Reporting_Region",
    "Compare Blue vs White Collar inactive rates",
    "Show top 10 Functions by inactive headcount"
  ],
  "dashboard": {{
    "title": "Short punchy title — max 6 words",
    "overview": "1-2 sentences max. What it analyzes and why it matters.",
    "overall_insights": [
      "Operations accounts for 28% of all inactive employees",
      "Internship contracts show 24% attrition — 3x the company average",
      "EMEA region has 45% of workforce but only 38% of attrition",
      "Band I-II employees represent 62% of all inactive cases",
      "Female employees show 12% lower attrition than male counterparts"
    ],
    "metrics": [
      {{
        "label": "Total Active Headcount",
        "value": "8,234",
        "trend": "up",
        "change": "+4.1% YoY",
        "insight": "Growth concentrated in APAC and EMEA regions"
      }},
      {{
        "label": "Overall Attrition Rate",
        "value": "16.4%",
        "trend": "up",
        "change": "+2.1pp",
        "insight": "Driven by internship and temporary contract exits"
      }},
      {{
        "label": "Total FTE",
        "value": "7,891.5",
        "trend": "stable",
        "change": "0.0%",
        "insight": "Part-time roles offsetting headcount growth"
      }}
    ],
    "visualizations": [
      {{
        "id": "viz-1",
        "type": "donut",
        "title": "Active vs Inactive Employee Distribution",
        "description": "Overall workforce retention showing proportion of active vs inactive employees.",
        "fields": ["Active_Workforce_Status"],
        "data_hint": "active_workforce_status_counts",
        "key_insights": [
          "83.6% of employees are active — 8,234 of 9,848 total",
          "1,614 inactive employees represent retention improvement opportunity"
        ]
      }},
      {{
        "id": "viz-2",
        "type": "grouped_bar",
        "title": "Active vs Inactive Employees by Function",
        "description": "Headcount breakdown by business function comparing active vs inactive employees.",
        "fields": ["Function", "Active_Workforce_Status"],
        "data_hint": "function_by_active_status",
        "key_insights": [
          "Operations has highest inactive count at 28% of its workforce",
          "Finance shows strongest retention at only 9% inactive rate",
          "Sales and Operations together account for 58% of all inactive cases"
        ]
      }},
      {{
        "id": "viz-3",
        "type": "bar",
        "title": "Headcount by Reporting Region",
        "description": "Geographic distribution of workforce across global reporting regions.",
        "fields": ["Reporting_Region"],
        "data_hint": "reporting_region_counts",
        "key_insights": [
          "EMEA leads with 45% of total workforce headcount",
          "APAC shows fastest growth trajectory in recent snapshots"
        ]
      }},
      {{
        "id": "viz-4",
        "type": "composed",
        "title": "Inactive Count and Attrition Rate by Band",
        "description": "Dual-axis view of absolute inactive counts (bar) and attrition rate (line) per band level.",
        "fields": ["Band", "Active_Workforce_Status"],
        "data_hint": "band_inactive_count_and_rate",
        "key_insights": [
          "Band I has highest attrition rate at 31% — 3x the senior band average",
          "Band IV-V show under 5% attrition, correlating with higher seniority and pay"
        ]
      }},
      {{
        "id": "viz-5",
        "type": "horizontal_bar",
        "title": "Inactive Employees by Contract Type",
        "description": "Breakdown of inactive headcount by employment contract type.",
        "fields": ["Contract_Type", "Active_Workforce_Status"],
        "data_hint": "contract_type_inactive",
        "key_insights": [
          "Internship contracts have highest attrition rate at 24% of segment",
          "Permanent employees have lowest attrition at 8% — most stable group"
        ]
      }},
      {{
        "id": "viz-6",
        "type": "stacked_bar",
        "title": "Workforce Composition by Band and Worker Category",
        "description": "Stacked view of worker categories within each band level.",
        "fields": ["Band", "Worker_Category"],
        "data_hint": "band_by_worker_category",
        "key_insights": [
          "Band I is 72% non-management, highest concentration of individual contributors",
          "Management roles concentrated in Bands III-V at 68% share"
        ]
      }},
      {{
        "id": "viz-7",
        "type": "table",
        "title": "Attrition Summary by Function",
        "description": "Detailed table showing headcount, inactive count, and attrition rate by function.",
        "fields": ["Function", "Total", "Inactive", "Attrition Rate"],
        "data_hint": "function_attrition_table",
        "key_insights": [
          "Operations: 2,756 total, 771 inactive — 28% attrition rate",
          "Finance: 1,203 total, 108 inactive — best retention at 9%",
          "HR and Sales both exceed 20% attrition, flagging retention risk"
        ]
      }},
      {{
        "id": "viz-8",
        "type": "grouped_bar",
        "title": "Gender Distribution by Function",
        "description": "Male vs female headcount split across all business functions.",
        "fields": ["Function", "Gender"],
        "data_hint": "function_by_gender",
        "key_insights": [
          "Engineering is 78% male — highest gender skew in the organization",
          "HR is 71% female, the most female-majority function",
          "Overall workforce is 54% male across all functions combined"
        ]
      }}
    ],
    "recommendations": [
      "Launch targeted retention program for Operations and Sales — highest attrition functions",
      "Review internship-to-permanent conversion rate — internships show 3x average attrition",
      "Investigate Band I attrition drivers — 31% rate suggests early-career retention gap"
    ]
  }}
}}

If modifying existing dashboard: keep all existing visualizations, only add/change what was requested.
Return the complete updated dashboard JSON with all sections.
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
            elif "Snapshot_Year" in df.columns:
                ts = df.groupby("Snapshot_Year").size().reset_index(name="value")
                return [{"name": str(r["Snapshot_Year"]), "value": int(r["value"])} for _, r in ts.iterrows()]

        # ── COMPOSED — bar + line (e.g. count bar + rate line) ───────────────
        elif viz_type == "composed":
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(8)
                result = []
                for k, v in counts.items():
                    subset = df[df[primary_field] == k]
                    entry = {"name": str(k), "Count": int(v)}
                    # If there's a status field, compute a rate
                    if "Active_Workforce_Status" in df.columns:
                        inactive = len(subset[subset["Active_Workforce_Status"].astype(str).str.lower() != "active"])
                        rate = round(inactive / v * 100, 1) if v > 0 else 0
                        entry["Attrition Rate %"] = rate
                    elif secondary_field and secondary_field in df.columns:
                        try:
                            val = pd.to_numeric(subset[secondary_field], errors="coerce").mean()
                            entry[secondary_field] = round(float(val), 2) if not pd.isna(val) else 0
                        except Exception:
                            pass
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
    return jsonify({
        "status": "healthy",
        "project_id": PROJECT_ID,
        "model": "gemini-2.0-flash-001",
        "dataset_loaded": df is not None,
        "records": len(df) if df is not None else 0,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        conversation_history = data.get("history", [])
        current_dashboard = data.get("current_dashboard", None)

        active_filters = data.get("active_filters", {})  # {field: [selected_values]}

        data_summary = get_data_summary()
        context = SYSTEM_PROMPT.format(data_summary=data_summary) + "\n\n"

        if current_dashboard:
            context += f"""CURRENT DASHBOARD (modify, don't replace):
{json.dumps(current_dashboard, indent=2)}

Instructions: The user wants to MODIFY this dashboard. Add/change only what they request.
Keep all existing visualizations. Return the complete updated dashboard JSON.\n\n"""

        if active_filters:
            filter_desc = ", ".join([f"{k}={v}" for k, v in active_filters.items()])
            context += f"ACTIVE FILTERS (data is pre-filtered to these values): {filter_desc}\n\n"

        for msg in conversation_history[-6:]:  # last 3 turns
            role = "User" if msg["role"] == "user" else "Assistant"
            context += f"{role}: {msg['content']}\n\n"

        context += f"User: {user_message}\n\nAssistant (valid JSON only, no markdown):"

        response = model.generate_content(
            context,
            generation_config={
                "max_output_tokens": 8192,
                "temperature": 0.25,
                "top_p": 0.9,
            },
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
            print(f"JSON parse error: {e}\nRaw: {raw[:500]}")
            parsed = {
                "message": "Dashboard generated. Displaying results.",
                "dashboard": current_dashboard,
                "suggestions": ["Try again", "Add a chart", "Explore themes"],
            }

        # Enrich visualizations with actual computed data (respecting active filters)
        dashboard = parsed.get("dashboard")
        if dashboard and "visualizations" in dashboard:
            for viz in dashboard["visualizations"]:
                fields = viz.get("fields", [])
                hint = viz.get("data_hint", "")
                computed = calculate_actual_data(viz["type"], fields, hint, active_filters)
                if computed:
                    viz["computed_data"] = computed

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
    Compute real chart data for a given visualization config.
    Accepts active_filters to recompute filtered chart data when user changes filter selections.
    """
    try:
        data = request.json
        viz_type = data.get("type", "bar")
        fields = data.get("fields", [])
        hint = data.get("data_hint", "")
        active_filters = data.get("active_filters", {})
        computed = calculate_actual_data(viz_type, fields, hint, active_filters)
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

    # Key fields for filtering — return all distinct values (up to 50 per field)
    filter_fields = [
        "Active_Workforce_Status", "Current_Staffing_Status",
        "Gender", "Age_Group", "Band", "Band_Level",
        "Blue_White_Collar", "Worker_Category", "Contract_Type",
        "Professional_Category", "Function", "Job_Family_Group",
        "Job_Family", "Job_Category", "Direct_Indirect",
        "Reporting_Region", "Company_Country", "Company_Name",
        "Snapshot_Year", "Position_Worker_Type",
    ]

    distinct_values = {}
    for col in filter_fields:
        if col in df.columns:
            vals = df[col].dropna().unique().tolist()
            distinct_values[col] = sorted([str(v) for v in vals])[:50]

    # Small sample for all columns (for schema browsing)
    sample = {}
    for col in df.columns[:30]:
        sample[col] = [str(v) for v in df[col].dropna().unique()[:3].tolist()]

    id_col = next((c for c in ["Corporate_ID", "Nominative_List_Unique_ID"] if c in df.columns), None)
    distinct_employees = int(df[id_col].nunique()) if id_col else len(df)

    return jsonify({
        "columns": list(df.columns),
        "total_rows": len(df_raw),
        "snapshot_rows": len(df),
        "distinct_employees": distinct_employees,
        "snapshot_label": snapshot_label,
        "sample": sample,
        "distinct_values": distinct_values,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
