### AI Employee Dashboard Agent – Technical & Product Spec  
Access Link: [https://dashboard-agent-799818976326.us-central1.run.app/](url)

#### 1. Current Stack & Infrastructure
| Layer              | Technology / Choice                                 | Notes |
|--------------------|-----------------------------------------------------|-------|
| Backend            | FastAPI (Python 3.10+)                              | Lightweight, async-ready |
| AI Query Parser    | Google Vertex AI → `gemini-1.5-pro-001` <br>Fallback: rule-based keyword parser | Works even if Vertex AI keys missing |
| Data Layer         | In-memory Pandas DataFrames (cached)                | Fake data generated on first call |
| Frontend           | Pure HTML + CSS + vanilla JS (no React/Vue)        | Single-page, minimal UI |
| Charts             | Plotly.js 2.27 (via CDN)                            | Responsive, good-looking |
| Deployment ready   | Any platform that runs Python + uvicorn/gunicorn    | Docker-ready with minimal changes |
| Hosting examples   | **GCP Cloud Run** (primary: https://dashboard-agent-799818976326.us-central1.run.app/) <br>Alternatives: Render, Fly.io, Railway, Vercel (with serverless adapter), AWS | Zero-ops possible; Cloud Run confirmed live with core UI (header, analytics feature list) rendering successfully |

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
