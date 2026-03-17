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


def get_data_summary():
    df = load_dataset()
    if df is None:
        return "Dataset not available. Using schema-only mode."

    total = len(df)
    cols = list(df.columns)

    summary_parts = [f"DATASET: {total:,} employee records", f"COLUMNS ({len(cols)}): {', '.join(cols[:30])}"]

    # Snapshot/time dimension
    if "Snapshot_Year" in df.columns:
        years = sorted(df["Snapshot_Year"].dropna().unique().tolist())
        summary_parts.append(f"YEARS IN DATA: {years}")
    if "Snapshot_Month" in df.columns:
        months = sorted(df["Snapshot_Month"].dropna().unique().tolist())
        summary_parts.append(f"MONTHS: {months[:12]}")

    # Workforce status / attrition proxy
    for col in ["Active_Workforce_Status", "Current_Staffing_Status"]:
        if col in df.columns:
            dist = df[col].value_counts().head(5).to_dict()
            summary_parts.append(f"{col}: {json.dumps(dist)}")

    # Demographics
    for col in ["Gender", "Age_Group", "Band", "Blue_White_Collar", "Worker_Category", "Contract_Type"]:
        if col in df.columns:
            dist = df[col].value_counts().head(6).to_dict()
            summary_parts.append(f"{col}: {json.dumps(dist)}")

    # Org
    for col in ["Function", "Job_Family_Group", "Job_Family", "Job_Category", "Professional_Category"]:
        if col in df.columns:
            dist = df[col].value_counts().head(6).to_dict()
            summary_parts.append(f"{col}: {json.dumps(dist)}")

    # Location
    for col in ["Reporting_Region", "Company_Country", "City_Name"]:
        if col in df.columns:
            dist = df[col].value_counts().head(6).to_dict()
            summary_parts.append(f"{col}: {json.dumps(dist)}")

    # FTE
    if "FTE" in df.columns:
        summary_parts.append(f"FTE: avg={df['FTE'].mean():.2f}, total={df['FTE'].sum():,.1f}")

    return "\n".join(summary_parts)


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


def calculate_actual_data(viz_type, fields, data_hint=""):
    """Compute real data from the dataset for chart rendering."""
    df = load_dataset()
    if df is None:
        return []

    try:
        hint = data_hint.lower() if data_hint else ""
        primary_field = fields[0] if fields else None

        # Use only the latest snapshot if available
        if "Is_Latest_Snapshot" in df.columns:
            latest = df[df["Is_Latest_Snapshot"] == True]
            if len(latest) > 0:
                df = latest

        if viz_type == "table":
            if len(fields) >= 2 and fields[0] in df.columns:
                rows = []
                group_col = fields[0]
                metric_cols = [f for f in fields[1:] if f in df.columns]
                if metric_cols:
                    grp = df.groupby(group_col).agg(
                        {c: "count" for c in metric_cols[:1]}
                    ).reset_index()
                    grp.columns = [group_col] + [f"Count_{c}" for c in metric_cols[:1]]
                    for _, row in grp.head(10).iterrows():
                        rows.append(row.to_dict())
                    return rows
            # Fallback: counts for primary field
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(10).reset_index()
                counts.columns = [primary_field, "Count"]
                return counts.to_dict("records")

        elif viz_type in ("bar", "stacked_bar", "grouped_bar"):
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(10)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

        elif viz_type == "line":
            # Time series
            if "Snapshot_Month_Series" in df.columns:
                ts = df.groupby("Snapshot_Month_Series").size().reset_index(name="value")
                ts = ts.sort_values("Snapshot_Month_Series")
                return [{"name": str(r["Snapshot_Month_Series"]), "value": int(r["value"])} for _, r in ts.iterrows()]
            elif "Snapshot_Year" in df.columns:
                ts = df.groupby("Snapshot_Year").size().reset_index(name="value")
                return [{"name": str(r["Snapshot_Year"]), "value": int(r["value"])} for _, r in ts.iterrows()]

        elif viz_type in ("pie", "donut"):
            if primary_field and primary_field in df.columns:
                counts = df[primary_field].value_counts().head(6)
                return [{"name": str(k), "value": int(v)} for k, v in counts.items()]

    except Exception as e:
        print(f"Data calculation error: {e}")

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

        data_summary = get_data_summary()
        context = SYSTEM_PROMPT.format(data_summary=data_summary) + "\n\n"

        if current_dashboard:
            context += f"""CURRENT DASHBOARD (modify, don't replace):
{json.dumps(current_dashboard, indent=2)}

Instructions: The user wants to MODIFY this dashboard. Add/change only what they request.
Keep all existing visualizations. Return the complete updated dashboard JSON.\n\n"""

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
        # Strip markdown fences
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

        # Enrich visualizations with actual computed data
        dashboard = parsed.get("dashboard")
        if dashboard and "visualizations" in dashboard:
            for viz in dashboard["visualizations"]:
                fields = viz.get("fields", [])
                hint = viz.get("data_hint", "")
                computed = calculate_actual_data(viz["type"], fields, hint)
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
    """Compute real chart data for a given visualization config."""
    try:
        data = request.json
        viz_type = data.get("type", "bar")
        fields = data.get("fields", [])
        hint = data.get("data_hint", "")
        computed = calculate_actual_data(viz_type, fields, hint)
        return jsonify({"data": computed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schema", methods=["GET"])
def get_schema():
    df = load_dataset()
    if df is None:
        return jsonify({"columns": [], "sample": {}})
    sample = {col: df[col].dropna().unique()[:3].tolist() for col in df.columns[:20]}
    return jsonify({"columns": list(df.columns), "row_count": len(df), "sample": sample})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)