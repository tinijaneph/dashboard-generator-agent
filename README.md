### AI Employee Dashboard Agent – Technical & Product Spec  

#### 1. Current Stack & Infrastructure
| Layer              | Technology / Choice                                 | Notes |
|--------------------|-----------------------------------------------------|-------|
| Backend            | FastAPI (Python 3.10+)                              | Lightweight, async-ready |
| AI Query Parser    | Google Vertex AI → `gemini-1.5-pro-001` <br>Fallback: rule-based keyword parser | Works even if Vertex AI keys missing |
| Data Layer         | In-memory Pandas DataFrames (cached)                | Fake data generated on first call |
| Frontend           | Pure HTML + CSS + vanilla JS (no React/Vue)        | Single-page, minimal UI |
| Charts             | Plotly.js 2.27 (via CDN)                            | Responsive, good-looking |
| Deployment ready   | Any platform that runs Python + uvicorn/gunicorn    | Docker-ready with minimal changes |
| Hosting examples   | **GCP Cloud Run** (primary: https://dashboard-agent-799818976326.us-central1.run.app/) <br> | Zero-ops possible; Cloud Run confirmed live with core UI (header, analytics feature list) rendering successfully |

#### 2. Core Logic Flow
```
User query → POST /generate-dashboard
   ↓
parse_query_with_ai() → tries Gemini → falls back to keyword parser
   ↓
filter_data() → applies simple column filters + time period (quarter/month)
   ↓
generate_dashboard_html() → 
      • picks dashboard_type (attrition | hours | band | etc.)
      • builds 3–4 Plotly figures + smart KPI cards
      • returns raw HTML string
   ↓
Frontend replaces #dashboardContainer with the HTML
```

#### 3. Current Capabilities (what actually works today)
- Natural-language → dashboard in <3 sec
- 7 pre-defined dashboard types
- Time-period filtering (this quarter / this month / last 90 days)
- Fake dataset (75 employees + 90 days of time entries)
- Fully client-side rendering → zero latency after response
- Live deployment: Core landing page loads (welcome header + 6 example analytics cards); query input and dashboard generation endpoints operational (tested via live URL)

#### 4. Critical Parts to Improve for Real HR Use

| Area                     | Current State                            | Production-Grade Target |
|--------------------------|------------------------------------------|-------------------------|
| Data source              | Hard-coded fake data                     | Secure connection to Workday/ myPulse via API or export |
| Authentication           | None                                     | OAuth2 + role-based access (HRBP, Manager, Exec) |
| Query parsing accuracy   | 60–70 % with Gemini, 40 % fallback      | Fine-tune smaller model (Gemini Flash / Llama-3 8B) on 500+ real HR queries |
| Filters & granularity    | Only basic column equals                 | Multi-condition, date ranges, regex, top-N, exclusions |
| Caching                  | In-memory only (dies on restart)         | Redis + per-user cache + data refresh scheduler |
| Export                   | None                                     | PDF / PNG / CSV export buttons |
| Responsiveness           | Works on mobile but not optimized        | Proper mobile layout + touch-friendly |
| Accessibility            | Minimal                                  | WCAG 2.1 AA |
| Audit & compliance       | None                                     | Log every query + generated dashboard (GDPR/CCPA) |
| Multi-language           | English only                             | Spanish / French if roll out to larger group of user? |
| Real-time data           | Static fake data                         | WebSocket or periodic polling for live updates |

#### 5. Realistic Roadmap to Make It HR-Team Useful (MVP → v1.0)

| Phase | Duration | Deliverable | Value to HR |
|-------|----------|-------------|-------------|
| 0 (current) | – | Prototype with fake data; live on Cloud Run | Demo & stakeholder buy-in |
| 1 | 2–3 weeks | Connect to real HRIS (read-only API?) + basic auth | Real numbers, no more “fake” objection |
| 2 | 3–4 weeks | Fine-tune query parser on real past HR questions + add 5 more dashboard types | 90 %+ intent recognition |
| 3 | 2 weeks | Role-based views + export + audit log | Compliance-ready |
| 4 | 2 weeks | Mobile optimization + Slack/Teams bot integration | Used daily by managers |
| 5 | TBD | Scheduled reports + anomaly alerts | Proactive people analytics |

#### 6. Next Step Plan: Enhance & Scale to All Users (GCP-Centric)
Focus on GCP-native tools for scaling; aim for 30+ concurrent users in 1–2 months.

| Step | Action Items | Timeline | GCP Integration | Scale Impact |
|------|--------------|----------|-----------------|--------------|
| **Enhance (Weeks 1–4)** | 1. Add GCP Secret Manager for Vertex AI keys.<br>2. Integrate Cloud SQL (PostgreSQL) for persistent data/caching (migrate from in-memory).<br>3. Implement IAM-based auth via GCP Identity-Aware Proxy (IAP).<br>4. Add Artifact Registry for Docker images; use Cloud Build for CI/CD.<br>5. Test with real HRIS export (e.g., BigQuery load from Workday CSV). | 1 week per item | Secret Manager, Cloud SQL, IAP, Artifact Registry, Cloud Build, BigQuery | Handles 10–50 users; data persistence across restarts |
| **Scale (Weeks 5–8)** | 1. Auto-scale Cloud Run to 1000 instances max; set concurrency=80.<br>2. Add Cloud Load Balancer for multi-region (us-central1 → us-east1 failover).<br>3. Use Memorystore (Redis) for session/query caching.<br>4. Monitor with Cloud Monitoring/Logging; set alerts for >80% CPU.<br>5. Enable Cloud CDN for static assets (Plotly CDN already, but cache HTML responses). | 1–2 weeks total | Cloud Run autoscaling, Load Balancer, Memorystore, Monitoring/Logging, CDN | 100–500 users; <200ms latency; cost ~$50–200/mo at scale |
| **Rollout (Week 9+)** | 1. Beta to 5 HR users.<br>2. Gather feedback via integrated Google Forms.<br>3. Full rollout: Share via GCP custom domain (e.g., hr-dashboard.yourcompany.com).<br>4. Backup: Cloud Run revisions for rollback. | Ongoing | IAP groups, Custom domains | Enterprise-ready; audit logs to BigQuery for compliance |


#### 7. Technical note:
- Built 

gcloud builds submit   --tag us-central1-docker.pkg.dev/$PROJECT_ID/dashboard-agent/agent:v1   --timeout=20m

- Deploy

gcloud run deploy dashboard-agent   --image us-central1-docker.pkg.dev/$PROJECT_ID/dashboard-agent/agent:v1   --region us-central1   --allow-unauthenticated   --set-env-vars PROJECT_ID=$PROJECT_ID   --memory 2Gi   --cpu 2   --timeout 300

-----------------------
#### Agent Processing How To? - End-to-End Flow
1. User types a question  
   Example: “Show me attrition this quarter in Engineering”

2. Browser sends it instantly  
   POST → https://your-app.run.app/generate-dashboard  
   Body: `{ "query": "Show me attrition this quarter in Engineering" }`

3. Backend receives the request (FastAPI)

4. Query parsing (the brain)  
   - First tries Gemini 1.5 Pro (Vertex AI)  
     → returns clean JSON in one shot:  
       ```json
       {
         "dashboard_type": "attrition",
         "filters": {"Department": "Engineering"},
         "time_period": "this quarter",
         "focus": "Engineering Attrition Q4 2025"
       }
       ```
   - If Gemini unavailable → fast keyword fallback parser (still works surprisingly well)

5. Data filtering (Pandas – in memory)  
   - Loads the 75-employee + 90-day time-tracking DataFrames (cached)  
   - Filters rows: Department == "Engineering"  
   - Filters time entries to current quarter only

6. Dashboard generator  
   - Picks the “attrition” template  
   - Calculates 4 smart KPIs (active, terminated, attrition %, avg tenure)  
   - Builds 3–4 beautiful Plotly charts (stacked bars, tenure histogram, location retention, etc.)  
   - Wraps everything in styled HTML + CSS grid

7. Response sent back  
   → ~150–300 KB of ready-to-render HTML containing KPIs + interactive Plotly charts

8. Browser instantly replaces the page content  
   - Welcome screen disappears  
   - Full professional dashboard appears (no page reload)  
   - All charts are interactive, responsive, and work offline after first load

#### Next Action - Methodology 

| # | Goal | Recommended Methodology (proven in production HR agents) | Effort | Impact |
|---|------|------------------------------------------------------------|--------|--------|
| 1 | 95–99 % query understanding | **RAG + Fine-tuned small model** (not raw Gemini Pro) | Medium | Massive |
|   | • Collect 500–2,000 real past HR questions (from emails, Slack, tickets)  <br>• Clean & label intent + entities (department, location, band, time period, metric)  <br>• Fine-tune **Gemini-1.5-Flash-8B** or **Llama-3.1-8B-Instruct** on Vertex AI Custom Training or GCP Vertex AI Model Garden  <br>• Add Retrieval-Augmented Generation: embed all past queries + example outputs → retrieve 3–5 most similar examples and inject into prompt | 3–4 weeks | Turns “somewhat works” → “scary accurate” |
| 2 | Never hallucinate schema or filters | **Structured Output + JSON Schema Enforcement** | Low | Critical |
|   | Force the model to always output this exact JSON schema (use Gemini function calling / guidance / Outlines / jsonformer):  
```json
{
  "intent": "attrition|headcount|hours|compensation|diversity|...",
  "filters": {"Department": "...", "Work_Location": "...", "Band": "..."},
  "time_period": "Q4 2025 | last 6 months | YTD | ...",
  "group_by": ["Department", "Location"],
  "metrics": ["headcount", "attrition_rate", "avg_tenure"]
}
```
| 2 days | Eliminates 90 % of wrong dashboards |
| 3 | Handle complex multi-intent queries | **Agentic workflow with tools** (LangGraph / CrewAI style) | Medium | High |
|   | Example query: “Compare headcount and average salary of engineers in Herndon vs Seattle for senior bands only, last 12 months”  <br>→ Agent breaks into steps: 1. parse → 2. validate filters exist → 3. call SQL/BigQuery tool → 4. decide best viz → 5. generate dashboard | 4–6 weeks | Handles 80 % of real HR ad-hoc requests |
| 4 | Scale to 50 k–500 k employees & real-time | **BigQuery + Materialized Views + Dataform** | Medium | Massive |
|   | • Nightly (or hourly) pipeline: HRIS → Cloud Storage → BigQuery  <br>• Pre-aggregate common views (headcount by dept/location/band/month, terminations, hours by project, etc.)  <br>• Agent queries BigQuery directly instead of Pandas → 0.3 s response even on 200 k rows | 2–3 weeks | From 75 fake rows → millions of rows, still <1 s |
| 5 | Zero wrong answers on sensitive data | **Guardrails + Approval Layer** | Low–Medium | Trust |
|   | • Block or mask PII in response  <br>• For queries containing “salary”, “compensation”, “individual” → require manager+ approval or return aggregated only  <br>• Use Vertex AI Gemini guardrails or NeMo Guardrails | 1 week | Makes legal/compliance happy |
| 6 | Continuous improvement loop | **Human-in-the-loop feedback** | Low | Sustained accuracy |
|   | Add “Not what I wanted / Perfect” thumbs up/down button → logs to BigQuery → weekly re-training/few-shot update | 3 days | Model gets smarter every week |

### Final Architecture

```
User → Cloud Run (FastAPI)
        ↓
Identity-Aware Proxy (Google login + role check)
        ↓
Query → Vertex AI Endpoint (fine-tuned Gemini-Flash-8B or Llama-3.1-8B)
        ↓ → RAG lookup (past examples)
        ↓ → Structured JSON output (function calling)
        ↓
Query Planner → translates JSON → BigQuery SQL (using Vertex AI code generation or dbt)
        ↓
BigQuery returns aggregated table (always < 10 k rows)
        ↓
Dashboard Renderer (same Plotly code you already have)
        ↓
HTML response → browser
```

1. Week 1–2 → Collect 500 real HR queries + fine-tune Gemini-Flash with JSON mode  
2. Week 3   → Switch data layer to BigQuery (even with fake data first)  
3. Week 4   → Add function calling / structured output  
4. Week 5–6 → Connect real HRIS → BigQuery pipeline  
5. Week 7+  → Add HITL feedback + guardrails
