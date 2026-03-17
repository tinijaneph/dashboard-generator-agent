# Dashboard Agent — HR Analytics AI

An AI-powered dashboard generator that turns natural language prompts into executive-grade HR dashboards. Describe what you want to analyze, and the agent generates a full dashboard with KPI cards, 7–8 visualizations, and analyst-quality insights — all from your workforce data.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [How Data Is Processed](#2-how-data-is-processed)
3. [How the Agent Picks Relevant Data](#3-how-the-agent-picks-relevant-data)
4. [Handling Unknown Data — No Context Mode](#4-handling-unknown-data--no-context-mode)
5. [Field Categories — Handling Different Values](#5-field-categories--handling-different-values)
6. [Deployment](#6-deployment)
7. [Environment Variables](#7-environment-variables)
8. [What Improved vs the Previous Version](#8-what-improved-vs-the-previous-version)

---

## 1. Project Structure

```
agent-dash/
├── Dockerfile              # Single unified build (Node → React → Python + Flask)
├── serve_static.py         # Flask wrapper that serves the React SPA
├── cloudbuild.yaml         # GCP Cloud Build pipeline (build → push → deploy)
├── .gcloudignore           # Prevents node_modules/venv from being uploaded
├── backend/
│   ├── main.py             # Flask API: data loading, system prompt, Gemini calls
│   └── requirements.txt    # Python dependencies
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── components/
            └── DashboardAgent.jsx   # Full UI: chat, filters, themes, charts
```

The app is deployed as a **single container** on Cloud Run. The Dockerfile has two stages: Stage 1 uses Node 20 Alpine to build the React frontend (`npm run build`). Stage 2 uses Python 3.11 slim, installs the backend dependencies, copies the compiled React `dist/` folder into `static/`, and serves everything via Gunicorn. The `serve_static.py` wrapper registers a catch-all Flask route that returns `index.html` for all non-API paths, enabling React client-side routing.

---

## 2. How Data Is Processed

### Loading

On startup, `load_dataset()` in `main.py` attempts to load the CSV in this order:

1. **GCS first** — downloads `nominative_list.csv` from `gs://dashboard-generator-data/` using `google-cloud-storage`. This is the production path on Cloud Run, which uses the Compute Engine service account for authentication automatically.
2. **Local fallback** — reads from `data/nominative_list.csv` on disk. Useful for local development without GCP credentials.

The loaded DataFrame is stored in a module-level `_df_cache` variable so it is only read once per container instance, not on every request.

```python
_df_cache = None

def load_dataset():
    global _df_cache
    if _df_cache is not None:
        return _df_cache
    # try GCS, then local
```

### Summarization

Before every chat request, `get_data_summary()` scans the loaded DataFrame and builds a compact text summary that gets injected into the system prompt. This tells the AI what is actually in the data — real counts, real category values — rather than relying on assumptions.

The summary includes:

| Category | What is extracted |
|---|---|
| Row count | Total number of employee records |
| Column list | First 30 column names |
| Snapshot dimensions | Unique years and months present |
| Workforce status | Value counts for `Active_Workforce_Status`, `Current_Staffing_Status` |
| Demographics | Top 6 values for `Gender`, `Age_Group`, `Band`, `Blue_White_Collar`, `Worker_Category`, `Contract_Type` |
| Org structure | Top 6 values for `Function`, `Job_Family_Group`, `Job_Family`, `Job_Category`, `Professional_Category` |
| Geography | Top 6 values for `Reporting_Region`, `Company_Country`, `City_Name` |
| FTE | Average and total FTE |

Example of what gets injected into the prompt:

```
DATASET: 9,848 employee records
COLUMNS (87): Nominative_List_Unique_ID, Corporate_ID, ...
YEARS IN DATA: [2022, 2023, 2024]
Active_Workforce_Status: {"Active": 8234, "Inactive": 1614}
Gender: {"Male": 5318, "Female": 4530}
Function: {"Operations": 2756, "Sales": 1820, ...}
Reporting_Region: {"EMEA": 4432, "APAC": 2905, ...}
FTE: avg=0.96, total=9,453.1
```

### Chart Data Computation

Each visualization returned by Gemini includes a `fields` array and a `data_hint` string. The `/api/chart-data` endpoint and the `calculate_actual_data()` function use these to compute real aggregations from the DataFrame:

- **Categorical counts** (`bar`, `pie`, `donut`) — `df[field].value_counts()`
- **Time series** (`line`) — groups by `Snapshot_Month_Series` or `Snapshot_Year`
- **Cross-tabulations** (`grouped_bar`, `stacked_bar`) — `df.groupby([field1, field2]).size()`
- **Multi-metric tables** — `df.groupby(field).agg({...})`

If the DataFrame is unavailable (GCS unreachable and no local file), the frontend falls back to illustrative sample data built into the chart renderer's `generateFallbackData()` function.

---

## 3. How the Agent Picks Relevant Data

The agent does not hard-code which fields to use. Instead, relevance selection happens in two places:

### At the system prompt level

The system prompt tells Gemini the full schema plus the actual category values from `get_data_summary()`. When a user asks for "attrition by region", Gemini reads the summary and knows:

- `Active_Workforce_Status` has values `{"Active": 8234, "Inactive": 1614}` — so it uses this as the attrition proxy
- `Reporting_Region` has values `{"EMEA": 4432, "APAC": 2905, ...}` — so it groups by this field

Gemini returns a structured JSON response that includes a `fields` array per visualization:

```json
{
  "type": "grouped_bar",
  "title": "Active vs Inactive by Region",
  "fields": ["Reporting_Region", "Active_Workforce_Status"],
  "data_hint": "region_by_active_status"
}
```

### At the computation level

`calculate_actual_data()` receives the `fields` list and uses whichever fields are present in the DataFrame:

```python
primary_field = fields[0] if fields else None
if primary_field and primary_field in df.columns:
    counts = df[primary_field].value_counts().head(10)
```

Fields that don't exist in the DataFrame are silently skipped — the function returns an empty list, and the frontend falls back to illustrative data rather than crashing.

### Snapshot filtering

When computing chart data, the function first filters to the latest snapshot if `Is_Latest_Snapshot` is present and has `True` values. This ensures charts show current headcount rather than a sum across all historical snapshots:

```python
if "Is_Latest_Snapshot" in df.columns:
    latest = df[df["Is_Latest_Snapshot"] == True]
    if len(latest) > 0:
        df = latest
```

---

## 4. Handling Unknown Data — No Context Mode

If the CSV cannot be loaded (network issue, wrong bucket name, file not found), the system degrades gracefully rather than failing.

`get_data_summary()` returns a fallback string:

```python
if df is None:
    return "Dataset not available. Using schema-only mode."
```

This string is injected into the system prompt. Gemini then knows it is operating without real data and will:

- Generate dashboards based on the known schema (field names are still hardcoded in the prompt)
- Use plausible illustrative numbers rather than real counts
- Still return a valid, well-structured JSON dashboard

On the frontend, `generateFallbackData()` in `DashboardAgent.jsx` provides realistic-looking placeholder data for every chart type so the UI renders fully rather than showing empty charts. For example:

```js
if (viz.type === 'grouped_bar') return [
  { name: 'Finance', Active: 280, Inactive: 108 },
  { name: 'Sales', Active: 354, Inactive: 92 },
  ...
];
```

This means a user can demo the product or test the UI before the data file is available, and it will look like a real dashboard.

**To fix no-data mode**, verify:
1. The bucket name matches: `GCS_BUCKET=dashboard-generator-data`
2. The file name matches: `GCS_FILE=nominative_list.csv`
3. The Cloud Run service account has `roles/storage.objectViewer` on the bucket
4. Check logs with `gcloud run services logs read dashboard-agent --region=us-central1`

---

## 5. Field Categories — Handling Different Values

The field values in the data (e.g. what `Active_Workforce_Status` actually contains) are not hardcoded in the agent. They are discovered dynamically from the data each time via `get_data_summary()`. This means:

### If your data uses different category names

The agent adapts automatically. Examples:

| Scenario | What happens |
|---|---|
| `Active_Workforce_Status` contains `"Active"`, `"Inactive"`, `"On Leave"` | Summary shows `{"Active": 8234, "Inactive": 1614, "On Leave": 484}` — Gemini uses all three |
| `Gender` contains `"M"`, `"F"` instead of `"Male"`, `"Female"` | Summary shows the actual values — Gemini uses `"M"` and `"F"` in insights |
| `Contract_Type` contains `"CDI"`, `"CDD"` (French labels) | Summary shows these values — Gemini adapts its language accordingly |
| A field is missing entirely from the CSV | `get_data_summary()` skips it; Gemini won't reference it |

### Filter dropdowns in the UI

The filter chips in `DashboardAgent.jsx` currently use hardcoded fallback option lists for the most common fields:

```js
const defaults = {
  'Function': ['Finance','Marketing','Sales','HR','IT','Operations'],
  'Contract_Type': ['Permanent','Temporary','Internship','Freelance'],
  ...
};
```

**If your data uses different values**, update this `defaults` object in `DashboardAgent.jsx` to match your actual category names. A future improvement would be to call the `/api/schema` endpoint at load time to populate these dynamically.

### The `/api/schema` endpoint

The backend exposes a schema endpoint that returns real column names and sample values:

```
GET /api/schema
```

Response:
```json
{
  "columns": ["Gender", "Band", "Function", ...],
  "row_count": 9848,
  "sample": {
    "Gender": ["Male", "Female"],
    "Band": ["Band I", "Band II", "Band III"],
    ...
  }
}
```

This can be used in a future version to dynamically populate filter dropdowns rather than relying on hardcoded lists.

### Adding a new dataset

If you want to point the agent at a completely different CSV:

1. Upload the new file to GCS: `gsutil cp your_file.csv gs://dashboard-generator-data/your_file.csv`
2. Update the Cloud Run environment variable: `GCS_FILE=your_file.csv`
3. Update the `AVAILABLE FIELDS` section in `SYSTEM_PROMPT` in `main.py` to list your new field names
4. Update the `get_data_summary()` function to scan the relevant columns from your new schema
5. Redeploy: `gcloud builds submit --config cloudbuild.yaml .`

---

## 6. Deployment

### Prerequisites (one-time)

```bash
# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com storage.googleapis.com

# Create Artifact Registry repo
gcloud artifacts repositories create dashboard-agent \
  --repository-format=docker --location=us-central1

# Grant IAM permissions
PROJECT_NUMBER=$(gcloud projects describe molten-album-478703-d8 --format='value(projectNumber)')

gcloud projects add-iam-policy-binding molten-album-478703-d8 \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding molten-album-478703-d8 \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### Every deployment

```bash
cd ~/agent-dash
gcloud builds submit --config cloudbuild.yaml .
```

This builds the Docker image, pushes it to Artifact Registry, and deploys to Cloud Run automatically. Takes 5–8 minutes.

### Local development

```bash
# Backend only
cd backend && pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
python main.py

# Frontend only (hot reload, proxies /api to localhost:8080)
cd frontend && npm install && npm run dev
```

---

## 7. Environment Variables

---

## 8. What Improved vs the Previous Version

This section documents what changed from the original `main.py` and `DashboardAgent.jsx` files.

### Backend — `main.py`

**Data source**

The original hardcoded a local file path (`data/WA_Fn-UseC_-HR-Employee-Attrition.csv`) and had no cloud storage support. The new version loads from GCS first and falls back to local, with in-memory caching so the file is only read once.

**Data awareness**

The original `get_data_summary()` was written specifically for the IBM HR Attrition dataset — it hardcoded column names like `Attrition`, `MonthlyIncome`, `JobSatisfaction`, and computed fixed statistics. It would silently fail or produce wrong output if columns were missing. The new version dynamically scans whatever columns are present in the DataFrame, computes real value distributions for each, and builds a data-adaptive summary that works regardless of the schema.

**System prompt quality**

The original system prompt asked for 7–8 overall insights as long paragraph bullets, 3–4 key insights per chart also written as paragraphs, and a verbose 2–3 sentence overview. This produced the "essay-style" outputs visible in the first screenshots. The new prompt enforces strict word limits, requires specific numeric patterns, includes BAD/GOOD examples with explicit WRONG patterns banned, adds an "analyst interpretation rule" requiring the second insight bullet to explain WHY a finding matters rather than just restating a number, and provides a full example dashboard in the prompt so Gemini has a concrete template to follow rather than inferring structure.

**Chart data computation**

The original `DashboardAgent.jsx` had a large `generateChartDataFromDashboard()` function that matched chart titles using `.toLowerCase().includes()` string matching and returned hardcoded arrays. This meant every chart showed the same fixed data regardless of what was actually in the dataset. The new backend computes real aggregations from the DataFrame using `value_counts()`, `groupby()`, and time-series aggregations, and returns `computed_data` arrays attached to each visualization object. The frontend uses these real arrays directly.

**API endpoints**

The original had only `/health` and `/api/chat`. The new version adds `/api/chart-data` for on-demand chart data computation and `/api/schema` for exposing column names and sample values to the frontend.

### Frontend — `DashboardAgent.jsx`

**Theme system**

The original used a single fixed color palette (`#567c8d`, `#c8d9e5`, `#2f4156`) applied via inline styles throughout. The new version has a full theme object system with 5 named themes (Brick Blue, Dark, Clean, Emerald, Slate), each defining 20+ color tokens covering backgrounds, surfaces, borders, text, accent, positive/negative states, chart palettes, and table header colors. Switching themes re-renders the entire UI consistently.

**Default theme**

The original defaulted to a generic grey-blue palette. The new default (`brickblue`) exactly replicates Brick AI's visual language: `#0a2342` deep navy header, `#1a6bb5` accent, `#eef2f7` background, white cards, `#c9a96e` golden table headers.

**Dashboard layout**

The original rendered overview text as a plain paragraph, then stacked all charts in a single-column list with insights below each chart. The new version adds a dark navy title banner (matching Brick AI's rounded header), a separate Overview card with a label, and uses a two-column grid where each chart card is placed side-by-side with its Key Insights panel — alternating which side the chart appears on for visual rhythm.

**Chart renderer**

The original `renderChart()` function produced basic charts with no labels on bars, no gradient fills on lines, no dual-axis support, and simple fallback data based on title string matching. The new renderer adds value labels on every bar type (formatted as 1.2K, 3.4M), gradient area fills beneath line charts, proper dual-axis composed charts with hollow dots on the line series, stacked bars with rounded top corners and total labels, and a smart number formatter (`fmtNum`) used consistently across all chart types and tooltips.

**Filter system**

The original "Add filters" chip sent a text message to the AI asking it to filter the dashboard. This did nothing visually — the dashboard did not change. The new implementation adds real UI state: clicking a field name in the filter panel adds a filter chip to a filter bar that appears above the KPI cards in the dashboard. Each chip opens a dropdown with checkboxes for every category value, a Select All / Deselect All button, and a remove option — matching Brick AI's filter UX from the screenshots.

**Smart suggestions**

The original had no follow-up suggestions after a dashboard was generated. The new version returns a `suggestions[]` array from the backend with every response, which the frontend renders as clickable blue pills below the AI message. Clicking any suggestion sends it as the next message without typing.

**Export**

The original had a Present mode (fullscreen) but no export. The new version adds an Export dropdown with PDF (opens a print-ready styled HTML page in a new tab) and PPTX (sends a prompt to the AI asking for a slide-by-slide PowerPoint outline).
