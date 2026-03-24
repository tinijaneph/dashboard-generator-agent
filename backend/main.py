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


def compute_descriptive_stats(df):
    """
    Compute real descriptive statistics from any DataFrame.
    Returns a dict of {field: {value: count}} for every categorical column,
    plus numeric summaries for numeric columns.
    This is completely data-driven — no field names or values are assumed.
    """
    stats = {}
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        # Detect numeric
        numeric = pd.to_numeric(non_null, errors='coerce').dropna()
        if len(numeric) / max(len(non_null), 1) > 0.8:
            # Numeric column
            stats[col] = {
                "type": "numeric",
                "count": int(len(numeric)),
                "mean": round(float(numeric.mean()), 2),
                "median": round(float(numeric.median()), 2),
                "min": round(float(numeric.min()), 2),
                "max": round(float(numeric.max()), 2),
            }
        else:
            # Categorical column
            vc = non_null.astype(str).value_counts()
            n_unique = len(vc)
            # Only include if cardinality is useful (2-200 unique values)
            if 2 <= n_unique <= 200:
                stats[col] = {
                    "type": "categorical",
                    "n_unique": n_unique,
                    "top_values": {str(k): int(v) for k, v in vc.head(15).items()},
                }
    return stats


def get_data_summary():
    """
    Builds a 100% data-driven summary from whatever CSV is loaded.
    No field names, values, or counts are hardcoded anywhere.
    The summary reflects the actual data at the latest snapshot point-in-time.
    If the data changes (new fields, different categories, more/fewer employees),
    this function automatically reflects those changes without any code modification.
    """
    df_raw = load_dataset()
    if df_raw is None:
        return "Dataset not available."

    df, snapshot_label = get_latest_snapshot(df_raw)

    # Distinct employee count — try common ID columns, fall back to row count
    id_col = next((c for c in ["Corporate_ID", "Nominative_List_Unique_ID", "Employee_ID", "EmpID"]
                   if c in df.columns), None)
    distinct_employees = int(df[id_col].nunique()) if id_col else len(df)

    # Date range from full longitudinal data
    date_range = ""
    if "Snapshot_Month_Series" in df_raw.columns:
        try:
            ts = pd.to_datetime(df_raw["Snapshot_Month_Series"], errors="coerce")
            date_range = f"{ts.min().strftime('%Y-%m')} to {ts.max().strftime('%Y-%m')}"
        except Exception:
            pass

    # Build header
    lines = [
        f"=== DATASET STATISTICS (computed from actual data) ===",
        f"Snapshot: {snapshot_label}",
        f"Distinct employees (latest snapshot): {distinct_employees:,}",
        f"Total longitudinal rows: {len(df_raw):,}",
        f"Columns available ({len(df.columns)}): {', '.join(df.columns.tolist())}",
    ]
    if date_range:
        lines.append(f"Date range covered: {date_range}")

    # Compute descriptive stats on latest snapshot
    stats = compute_descriptive_stats(df)

    lines.append("")
    lines.append("=== FIELD STATISTICS (actual values from latest snapshot) ===")

    for col, s in stats.items():
        if s["type"] == "categorical":
            # Format: FIELD_NAME (N unique): {"Val1": count, "Val2": count, ...}
            lines.append(f'{col} ({s["n_unique"]} unique): {json.dumps(s["top_values"])}')
        elif s["type"] == "numeric":
            lines.append(
                f'{col} [numeric]: mean={s["mean"]}, median={s["median"]}, '
                f'min={s["min"]}, max={s["max"]}, n={s["count"]:,}'
            )

    lines.append("")
    lines.append(
        "=== INSTRUCTION TO AI ===\n"
        "The statistics above are the ONLY source of truth. "
        "Use ONLY the field names listed in 'Columns available'. "
        "Use ONLY the values shown in the field statistics above — never invent category names. "
        "Use the exact counts shown for KPI values and insights. "
        "Distinct employees = total headcount at latest snapshot."
    )

    return "\n".join(lines)



SYSTEM_PROMPT = """You are an expert HR Analytics AI that generates data-driven dashboards.

You receive computed statistics from the actual dataset. Your job is to:
1. Read the field statistics and understand what the data contains
2. Select the most relevant fields for the user's request
3. Generate a dashboard JSON that reflects the REAL data — using only field names and values that exist in the statistics

=== DATA CONTEXT ===
{data_summary}

=== CRITICAL RULES ===
- NEVER use field names not listed in "Columns available"
- NEVER invent category values — use ONLY values shown in the field statistics
- NEVER use hardcoded numbers — derive all values from the statistics above
- KPI values must come from the statistics (e.g. distinct employees = total headcount)
- Chart fields must be real columns. Category names in insights must match actual values.
- The data is longitudinal (one employee can have many rows over time). Always work from the latest snapshot counts.

=== OUTPUT FORMAT RULES ===

OVERVIEW: 1-2 sentences. What the dashboard analyzes + why it matters. No lists.

OVERALL_INSIGHTS: Exactly 5 bullets. Each must:
  - Quote a real number derived from the statistics
  - Be under 20 words
  - State a finding + implication (not just a description)

METRICS: 3-5 KPI cards derived from actual statistics.

VISUALIZATIONS: 6-8 charts. For each:
  - "fields" must only contain column names that exist in the data
  - "key_insights": exactly 2-3 bullets, each under 15 words with a real number
  - First bullet = specific number. Second bullet = what it implies for the business.

CHART TYPE GUIDE:
  bar — simple categorical count (1 field)
  grouped_bar — two categorical fields side by side (2 fields)
  stacked_bar — composition stacked (2 fields)
  horizontal_bar — when category label names are long (1-2 fields)
  composed — bar + line dual axis for count + rate (2 fields)
  donut — proportions, max 6 slices (1 field)
  line — time trend using snapshot columns (1-2 fields)
  table — multi-column detail view (2-4 fields)

SUGGESTIONS: 5 follow-up prompts using real field names from the data.

=== RESPONSE FORMAT (valid JSON only, no markdown) ===
{{
  "message": "One sentence confirming what was built.",
  "analysis_type": "workforce|attrition|headcount|demographics|org|custom",
  "suggestions": ["suggestion using real field name", "..."],
  "dashboard": {{
    "title": "Short title — max 6 words",
    "overview": "1-2 sentences about what this dashboard shows.",
    "overall_insights": [
      "Insight 1 with real number from statistics",
      "Insight 2 with real number and implication",
      "Insight 3",
      "Insight 4",
      "Insight 5"
    ],
    "metrics": [
      {{
        "label": "KPI label",
        "value": "Number from statistics",
        "trend": "up|down|stable",
        "change": "change value if known",
        "insight": "One sentence under 12 words"
      }}
    ],
    "visualizations": [
      {{
        "id": "viz-1",
        "type": "chart_type",
        "title": "Chart title",
        "description": "One sentence describing what the chart shows.",
        "fields": ["RealColumnName1", "RealColumnName2"],
        "data_hint": "descriptive_hint_for_backend",
        "key_insights": [
          "Specific finding with real number from data",
          "What this implies for the business"
        ]
      }}
    ],
    "recommendations": [
      "Actionable recommendation based on data findings"
    ]
  }}
}}

If modifying an existing dashboard: keep all existing visualizations, only add/change what was requested.
Return the complete updated dashboard JSON.
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
