from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import json
import os
import random
from datetime import datetime, timedelta

app = FastAPI(title="Employee Dashboard Agent - Enhanced")

# Initialize Vertex AI
PROJECT_ID = os.getenv("PROJECT_ID", "molten-album-478703-d8")
LOCATION = "us-central1"

try:
    from google.cloud import aiplatform
    import vertexai
    try:
        from vertexai.generative_models import GenerativeModel
        VERTEX_AI_ENABLED = True
    except ImportError:
        try:
            from vertexai.preview.generative_models import GenerativeModel
            VERTEX_AI_ENABLED = True
        except ImportError:
            GenerativeModel = None
            VERTEX_AI_ENABLED = False
    
    if VERTEX_AI_ENABLED:
        try:
            vertexai.init(project=PROJECT_ID, location=LOCATION)
        except Exception as e:
            VERTEX_AI_ENABLED = False
            print(f"Vertex AI initialization failed: {e}")
except:
    VERTEX_AI_ENABLED = False
    print("Vertex AI not available - using fallback query parsing")

# ============================================================================
# FAKE DATA GENERATION
# ============================================================================

def generate_fake_employees(count=75):
    """Generate realistic employee data"""
    
    first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
                   "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
                   "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
                   "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
                   "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"]
    
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
                  "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
                  "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White"]
    
    work_locations = ["Herndon, VA", "Seattle, WA", "New York, NY", "Austin, TX", "Chicago, IL",
                      "San Francisco, CA", "Boston, MA", "Denver, CO", "Atlanta, GA", "Remote - US"]
    
    supervisory_orgs = ["AAB", "XYZ", "DEF", "GHI", "JKL", "MNO", "PQR", "STU"]
    
    job_profiles = [
        ("Software Engineer", "JP001", "J001"), ("Senior Software Engineer", "JP002", "J002"),
        ("Data Analyst", "JP003", "J003"), ("Senior Data Analyst", "JP004", "J004"),
        ("Product Manager", "JP005", "J005"), ("Senior Product Manager", "JP006", "J006"),
        ("DevOps Engineer", "JP007", "J007"), ("UX Designer", "JP008", "J008"),
        ("Data Scientist", "JP009", "J009"), ("Business Analyst", "JP010", "J010"),
        ("Project Manager", "JP011", "J011"), ("QA Engineer", "JP012", "J012")
    ]
    
    bands = ["BI", "BII", "BIII", "BIV", "BV"]
    
    employees = []
    
    for i in range(count):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        corporate_id = f"EMP{str(i+1000).zfill(5)}"
        age = random.randint(22, 65)
        year_of_birth = datetime.now().year - age
        work_location = random.choice(work_locations)
        siglum = random.choice(supervisory_orgs)
        job_profile_name, job_profile_code, job_code = random.choice(job_profiles)
        cost_center_code = f"CC{siglum[:2]}{random.randint(100, 999)}"
        days_ago = random.randint(180, 7300)
        hire_date = datetime.now() - timedelta(days=days_ago)
        company_service_date = hire_date
        tenure_years = days_ago / 365.25
        
        if "Senior" in job_profile_name or "Lead" in job_profile_name:
            band = random.choice(["BIII", "BIV", "BV"])
        else:
            band = random.choice(["BI", "BII", "BIII"])
        
        if "Engineer" in job_profile_name or "DevOps" in job_profile_name:
            department = "Engineering"
        elif "Data" in job_profile_name:
            department = "Data & Analytics"
        elif "Product" in job_profile_name:
            department = "Product Management"
        elif "UX" in job_profile_name or "Designer" in job_profile_name:
            department = "Design"
        elif "QA" in job_profile_name:
            department = "Quality Assurance"
        else:
            department = "Operations"
        
        if random.random() > 0.95:
            employment_status = "Terminated"
            termination_date = datetime.now() - timedelta(days=random.randint(1, 180))
        else:
            employment_status = "Active"
            termination_date = None
        
        employees.append({
            "Corporate_ID": corporate_id,
            "First_Name": first_name,
            "Last_Name": last_name,
            "Full_Name": f"{first_name} {last_name}",
            "Age": age,
            "Year_of_Birth": year_of_birth,
            "Work_Location": work_location,
            "Supervisory_Organization_Siglum": siglum,
            "Job_Profile_Name": job_profile_name,
            "Job_Profile_Code": job_profile_code,
            "Cost_Center_Code": cost_center_code,
            "Job_Code": job_code,
            "Position_Title": job_profile_name,
            "Hire_Date": hire_date.strftime("%Y-%m-%d"),
            "Company_Service_Date": company_service_date.strftime("%Y-%m-%d"),
            "Band": band,
            "Department": department,
            "Employment_Status": employment_status,
            "Termination_Date": termination_date.strftime("%Y-%m-%d") if termination_date else None,
            "Tenure_Years": round(tenure_years, 1)
        })
    
    return pd.DataFrame(employees)


def generate_fake_time_tracking(employees_df, days=90):
    """Generate realistic time tracking data"""
    
    work_types = ["Project Work", "Meetings", "Training", "Administrative", 
                  "Code Review", "Documentation", "Client Communication"]
    
    project_codes = ["PRJ001-Alpha", "PRJ002-Beta", "PRJ003-Gamma", "PRJ004-Delta",
                     "PRJ005-Epsilon", "INT-001-Infrastructure", "MAINT-Support"]
    
    time_entries = []
    base_date = datetime.now() - timedelta(days=days)
    
    active_employees = employees_df[employees_df['Employment_Status'] == 'Active']
    
    for _, employee in active_employees.iterrows():
        corporate_id = employee['Corporate_ID']
        
        for day in range(days):
            current_date = base_date + timedelta(days=day)
            
            if current_date.weekday() >= 5:
                continue
            
            if random.random() > 0.9:
                continue
            
            num_entries = random.randint(1, 4)
            daily_hours = random.uniform(7.5, 9.5)
            
            for entry in range(num_entries):
                work_type = random.choice(work_types)
                project_code = random.choice(project_codes)
                
                if entry == num_entries - 1:
                    hours = daily_hours
                else:
                    hours = random.uniform(1, daily_hours * 0.4)
                    daily_hours -= hours
                
                hours = round(hours, 2)
                
                time_entries.append({
                    "Corporate_ID": corporate_id,
                    "Entry_Date": current_date.strftime("%Y-%m-%d"),
                    "Hours": hours,
                    "Work_Type": work_type,
                    "Project_Code": project_code,
                    "Week_Number": current_date.isocalendar()[1],
                    "Month": current_date.strftime("%Y-%m"),
                    "Quarter": f"Q{(current_date.month-1)//3 + 1} {current_date.year}"
                })
    
    return pd.DataFrame(time_entries)


_cached_employees = None
_cached_time_tracking = None

def get_sample_employees():
    global _cached_employees
    if _cached_employees is None:
        _cached_employees = generate_fake_employees(count=75)
    return _cached_employees.copy()

def get_sample_time_tracking():
    global _cached_time_tracking
    if _cached_time_tracking is None:
        employees_df = get_sample_employees()
        _cached_time_tracking = generate_fake_time_tracking(employees_df, days=90)
    return _cached_time_tracking.copy()

# ============================================================================
# MINIMAL LANDING PAGE - Claude/OpenAI Style
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    """Clean, minimal landing page"""
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard AI Agent</title>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
                background: linear-gradient(135deg, #0a1628 0%, #1a2942 50%, #0f1923 100%);
                min-height: 100vh;
                color: #e8eaed;
                display: flex;
                flex-direction: column;
            }
            
            /* Header */
            .header {
                padding: 20px 40px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(10, 22, 40, 0.6);
                backdrop-filter: blur(10px);
            }
            
            .logo {
                font-size: 20px;
                font-weight: 600;
                color: #e8eaed;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .logo-icon {
                width: 28px;
                height: 28px;
                background: linear-gradient(135deg, #4a9eff 0%, #2563eb 100%);
                border-radius: 6px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 16px;
            }
            
            /* Main Container */
            .main-container {
                flex: 1;
                display: flex;
                flex-direction: column;
                max-width: 1400px;
                width: 100%;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Welcome Section - Only shows initially */
            .welcome-section {
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 60px 20px;
                transition: all 0.5s ease;
            }
            
            .welcome-section.hidden {
                display: none;
            }
            
            .welcome-title {
                font-size: 48px;
                font-weight: 300;
                margin-bottom: 20px;
                background: linear-gradient(135deg, #e8eaed 0%, #9ca3af 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .welcome-subtitle {
                font-size: 18px;
                color: #9ca3af;
                margin-bottom: 50px;
                max-width: 600px;
            }
            
            .example-prompts {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 16px;
                max-width: 900px;
                width: 100%;
                margin-bottom: 40px;
            }
            
            .example-card {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 20px;
                cursor: pointer;
                transition: all 0.3s ease;
                text-align: left;
            }
            
            .example-card:hover {
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(74, 158, 255, 0.5);
                transform: translateY(-2px);
            }
            
            .example-icon {
                font-size: 24px;
                margin-bottom: 12px;
            }
            
            .example-title {
                font-size: 15px;
                font-weight: 500;
                color: #e8eaed;
                margin-bottom: 6px;
            }
            
            .example-desc {
                font-size: 13px;
                color: #9ca3af;
            }
            
            /* Input Section - Fixed at bottom */
            .input-section {
                position: sticky;
                bottom: 0;
                background: rgba(10, 22, 40, 0.95);
                backdrop-filter: blur(10px);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                padding: 20px;
                z-index: 100;
            }
            
            .input-wrapper {
                max-width: 900px;
                margin: 0 auto;
                position: relative;
            }
            
            .input-box {
                width: 100%;
                background: rgba(255, 255, 255, 0.08);
                border: 2px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
                padding: 16px 60px 16px 20px;
                font-size: 15px;
                color: #e8eaed;
                transition: all 0.3s ease;
                resize: none;
                font-family: inherit;
                line-height: 1.5;
            }
            
            .input-box:focus {
                outline: none;
                border-color: #4a9eff;
                background: rgba(255, 255, 255, 0.1);
            }
            
            .input-box::placeholder {
                color: #6b7280;
            }
            
            .send-button {
                position: absolute;
                right: 8px;
                bottom: 8px;
                width: 40px;
                height: 40px;
                background: linear-gradient(135deg, #4a9eff 0%, #2563eb 100%);
                border: none;
                border-radius: 10px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
                font-size: 18px;
            }
            
            .send-button:hover {
                transform: scale(1.05);
                box-shadow: 0 4px 20px rgba(74, 158, 255, 0.4);
            }
            
            .send-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            /* Dashboard Container */
            .dashboard-container {
                flex: 1;
                padding: 30px 20px;
                overflow-y: auto;
                display: none;
            }
            
            .dashboard-container.active {
                display: block;
            }
            
            /* Loading State */
            .loading-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 80px 20px;
            }
            
            .spinner {
                width: 50px;
                height: 50px;
                border: 3px solid rgba(255, 255, 255, 0.1);
                border-top-color: #4a9eff;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            
            .loading-text {
                margin-top: 20px;
                color: #9ca3af;
                font-size: 15px;
            }
            
            /* Dashboard Header */
            .dashboard-header {
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .dashboard-title {
                font-size: 28px;
                font-weight: 500;
                color: #e8eaed;
                margin-bottom: 8px;
            }
            
            .dashboard-subtitle {
                font-size: 14px;
                color: #9ca3af;
            }
            
            /* KPI Cards */
            .kpi-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .kpi-card {
                background: linear-gradient(135deg, rgba(74, 158, 255, 0.12) 0%, rgba(37, 99, 235, 0.08) 100%);
                border: 1px solid rgba(74, 158, 255, 0.2);
                border-radius: 12px;
                padding: 24px;
                transition: all 0.3s ease;
            }
            
            .kpi-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 30px rgba(74, 158, 255, 0.15);
            }
            
            .kpi-value {
                font-size: 36px;
                font-weight: 600;
                color: #e8eaed;
                margin-bottom: 8px;
            }
            
            .kpi-label {
                font-size: 13px;
                color: #9ca3af;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            /* Chart Grid */
            .chart-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                gap: 24px;
                margin-bottom: 30px;
            }
            
            .chart-container {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 20px;
                transition: all 0.3s ease;
                min-height: 400px;
            }
            
            .chart-container:hover {
                border-color: rgba(255, 255, 255, 0.15);
            }
            
            /* Plotly chart styling */
            .js-plotly-plot, .plotly {
                width: 100% !important;
                height: 100% !important;
            }
            
            .plotly .svg-container {
                width: 100% !important;
                height: 100% !important;
            }
            
            /* Error State */
            .error-message {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.3);
                color: #fca5a5;
                padding: 20px;
                border-radius: 12px;
                margin: 20px;
                text-align: center;
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .welcome-title { font-size: 32px; }
                .example-prompts { grid-template-columns: 1fr; }
                .chart-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">
                Dashboard AI
            </div>
        </div>
        
        <div class="main-container">
            <!-- Welcome Section -->
            <div class="welcome-section" id="welcomeSection">
                <h1 class="welcome-title">Generate insights instantly</h1>
                <p class="welcome-subtitle">
                    Ask questions about your employee data and get professional dashboards with AI-powered analytics
                </p>
                
                <div class="example-prompts">
                    <div class="example-card" onclick="setQuery('Show me attrition dashboard for this quarter')">
                        <div class="example-icon">📉</div>
                        <div class="example-title">Attrition Analysis</div>
                        <div class="example-desc">Analyze employee turnover trends and retention metrics</div>
                    </div>
                    
                    <div class="example-card" onclick="setQuery('Hours worked by department this month')">
                        <div class="example-icon">⏱️</div>
                        <div class="example-title">Time Tracking</div>
                        <div class="example-desc">View work hours distribution across teams and projects</div>
                    </div>
                    
                    <div class="example-card" onclick="setQuery('Compare Herndon vs Seattle locations')">
                        <div class="example-icon">🗺️</div>
                        <div class="example-title">Location Insights</div>
                        <div class="example-desc">Compare metrics between different office locations</div>
                    </div>
                    
                    <div class="example-card" onclick="setQuery('Show band distribution by department')">
                        <div class="example-icon">🎯</div>
                        <div class="example-title">Band Analysis</div>
                        <div class="example-desc">Examine employee levels and career progression</div>
                    </div>
                    
                    <div class="example-card" onclick="setQuery('Department demographics breakdown')">
                        <div class="example-icon">👥</div>
                        <div class="example-title">Demographics</div>
                        <div class="example-desc">Understand team composition and diversity metrics</div>
                    </div>
                    
                    <div class="example-card" onclick="setQuery('Project allocation overview')">
                        <div class="example-icon">📋</div>
                        <div class="example-title">Project Insights</div>
                        <div class="example-desc">See how resources are distributed across projects</div>
                    </div>
                </div>
            </div>
            
            <!-- Dashboard Container -->
            <div class="dashboard-container" id="dashboardContainer"></div>
        </div>
        
        <!-- Input Section -->
        <div class="input-section">
            <div class="input-wrapper">
                <textarea 
                    id="queryInput" 
                    class="input-box" 
                    placeholder="Ask anything about your employee data..."
                    rows="1"
                ></textarea>
                <button class="send-button" id="sendButton" onclick="generateDashboard()">
                    ➤
                </button>
            </div>
        </div>

        <script>
            const queryInput = document.getElementById('queryInput');
            const sendButton = document.getElementById('sendButton');
            const welcomeSection = document.getElementById('welcomeSection');
            const dashboardContainer = document.getElementById('dashboardContainer');
            
            // Auto-resize textarea
            queryInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 200) + 'px';
            });
            
            // Enter to submit (Shift+Enter for new line)
            queryInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    generateDashboard();
                }
            });
            
            function setQuery(text) {
                queryInput.value = text;
                queryInput.focus();
                generateDashboard();
            }
            
            async function generateDashboard() {
                const query = queryInput.value.trim();
                if (!query) return;
                
                // Hide welcome, show dashboard container
                welcomeSection.classList.add('hidden');
                dashboardContainer.classList.add('active');
                
                // Show loading
                dashboardContainer.innerHTML = `
                    <div class="loading-state">
                        <div class="spinner"></div>
                        <div class="loading-text">Analyzing your query and generating dashboard...</div>
                    </div>
                `;
                
                sendButton.disabled = true;
                
                try {
                    const response = await fetch('/generate-dashboard', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: query })
                    });
                    
                    const data = await response.json();
                    
                    if (data.error) {
                        dashboardContainer.innerHTML = `
                            <div class="error-message">
                                <strong>Error:</strong> ${data.error}
                            </div>
                        `;
                    } else {
                        dashboardContainer.innerHTML = data.html;
                        
                        // Force Plotly to resize after rendering
                        setTimeout(() => {
                            const plots = document.querySelectorAll('.js-plotly-plot');
                            plots.forEach(plot => {
                                if (window.Plotly) {
                                    window.Plotly.Plots.resize(plot);
                                }
                            });
                        }, 100);
                    }
                } catch (error) {
                    dashboardContainer.innerHTML = `
                        <div class="error-message">
                            <strong>Error:</strong> ${error.message}
                        </div>
                    `;
                } finally {
                    sendButton.disabled = false;
                    queryInput.value = '';
                    queryInput.style.height = 'auto';
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/generate-dashboard")
async def generate_dashboard(request: Request):
    """Generate professional dashboard with high-quality visualizations"""
    try:
        body = await request.json()
        user_query = body.get("query", "")
        
        parsed_query = await parse_query_with_ai(user_query)
        
        employees_df = get_sample_employees()
        time_df = get_sample_time_tracking()
        
        filtered_data = filter_data(parsed_query, employees_df, time_df)
        
        dashboard_html = generate_dashboard_html(parsed_query, filtered_data)
        
        return JSONResponse(content={
            "success": True,
            "html": dashboard_html,
            "query_interpretation": parsed_query
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Error: {error_detail}")
        return JSONResponse(content={
            "error": f"{str(e)}"
        }, status_code=500)


async def parse_query_with_ai(user_query: str) -> dict:
    """Parse query with AI or fallback"""
    
    if VERTEX_AI_ENABLED:
        try:
            model = GenerativeModel("gemini-1.5-pro-001")
            
            prompt = f"""Parse this employee data query into JSON format.

Query: "{user_query}"

Available data: Corporate_ID, Name, Age, Work_Location, Supervisory_Organization_Siglum, 
Job_Profile_Name, Position_Title, Band (BI/BII/BIII/BIV/BV), Department, Hire_Date, Tenure_Years, 
Employment_Status, Time Tracking (Hours, Work_Type, Project_Code, Entry_Date, Quarter, Month)

Return ONLY JSON (no markdown):
{{
    "dashboard_type": "attrition" | "hours" | "demographics" | "band_analysis" | "location_compare" | "project" | "general",
    "filters": {{}},
    "focus": "description",
    "time_period": "this quarter" | "this month" | "last 90 days" | null
}}"""
            
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            return json.loads(result_text.strip())
        except Exception as e:
            print(f"Vertex AI error: {e}")
    
    return fallback_query_parser(user_query)


def fallback_query_parser(user_query: str) -> dict:
    """Enhanced fallback parser"""
    
    query_lower = user_query.lower()
    
    # Time period detection
    time_period = None
    if "quarter" in query_lower:
        time_period = "this quarter"
    elif "month" in query_lower:
        time_period = "this month"
    
    # Dashboard type detection
    if any(word in query_lower for word in ["attrition", "turnover", "retention", "tenure"]):
        return {"dashboard_type": "attrition", "filters": {}, "focus": "employee attrition analysis", "time_period": time_period}
    elif any(word in query_lower for word in ["hours", "time", "tracking"]):
        return {"dashboard_type": "hours", "filters": {}, "focus": "time tracking analysis", "time_period": time_period}
    elif any(word in query_lower for word in ["band", "level"]):
        return {"dashboard_type": "band_analysis", "filters": {}, "focus": "band distribution", "time_period": time_period}
    elif any(word in query_lower for word in ["demographic", "age"]):
        return {"dashboard_type": "demographics", "filters": {}, "focus": "employee demographics", "time_period": time_period}
    elif any(word in query_lower for word in ["compare", "vs", "versus"]):
        return {"dashboard_type": "location_compare", "filters": {}, "focus": "location comparison", "time_period": time_period}
    elif any(word in query_lower for word in ["project", "allocation"]):
        return {"dashboard_type": "project", "filters": {}, "focus": "project allocation", "time_period": time_period}
    else:
        return {"dashboard_type": "general", "filters": {}, "focus": "general overview", "time_period": time_period}


def filter_data(parsed_query: dict, employees_df: pd.DataFrame, time_df: pd.DataFrame) -> dict:
    """Filter data based on query and time period"""
    
    filters = parsed_query.get("filters", {})
    time_period = parsed_query.get("time_period")
    
    filtered_employees = employees_df.copy()
    
    for key, value in filters.items():
        if key in filtered_employees.columns:
            filtered_employees = filtered_employees[filtered_employees[key] == value]
    
    corporate_ids = filtered_employees['Corporate_ID'].tolist()
    filtered_time = time_df[time_df['Corporate_ID'].isin(corporate_ids)]
    
    # Apply time period filter
    if time_period and not filtered_time.empty:
        filtered_time['Entry_Date'] = pd.to_datetime(filtered_time['Entry_Date'])
        now = datetime.now()
        
        if time_period == "this quarter":
            current_quarter = (now.month - 1) // 3 + 1
            current_year = now.year
            filtered_time = filtered_time[filtered_time['Quarter'] == f"Q{current_quarter} {current_year}"]
        elif time_period == "this month":
            current_month = now.strftime("%Y-%m")
            filtered_time = filtered_time[filtered_time['Month'] == current_month]
    
    return {
        "employees": filtered_employees,
        "time_tracking": filtered_time
    }


def generate_dashboard_html(parsed_query: dict, data: dict) -> str:
    """Generate professional dashboard with high-quality visualizations"""
    
    dashboard_type = parsed_query.get("dashboard_type", "general")
    employees_df = data["employees"]
    time_df = data["time_tracking"]
    time_period = parsed_query.get("time_period", "")
    
    if employees_df.empty:
        return """
        <div style="text-align: center; padding: 80px 20px; color: #9ca3af;">
            <div style="font-size: 48px; margin-bottom: 20px;">📭</div>
            <h2 style="color: #e8eaed; margin-bottom: 12px; font-size: 24px;">No Data Found</h2>
            <p>Try adjusting your query or check your filters</p>
        </div>
        """
    
    active_employees = employees_df[employees_df['Employment_Status'] == 'Active']
    
    # Color scheme - Professional and modern
    COLOR_SCHEME = ['#4a9eff', '#2563eb', '#1e40af', '#1e3a8a', '#6366f1', '#4f46e5']
    BG_COLOR = 'rgba(10, 22, 40, 0)'
    PAPER_COLOR = 'rgba(255, 255, 255, 0.02)'
    GRID_COLOR = 'rgba(255, 255, 255, 0.05)'
    TEXT_COLOR = '#9ca3af'
    TITLE_COLOR = '#e8eaed'
    
    figures = []
    
    # Generate smart KPIs based on dashboard type
    def generate_smart_kpis():
        kpis = []
        
        if dashboard_type == "attrition":
            terminated = len(employees_df[employees_df['Employment_Status'] == 'Terminated'])
            total = len(employees_df)
            attrition_rate = (terminated / total * 100) if total > 0 else 0
            avg_tenure = active_employees['Tenure_Years'].mean() if not active_employees.empty else 0
            
            # Attrition by recent quarter
            if not time_df.empty and time_period:
                period_label = time_period.title()
            else:
                period_label = "Overall"
            
            kpis = [
                {"value": len(active_employees), "label": "Active Employees"},
                {"value": terminated, "label": "Terminated"},
                {"value": f"{attrition_rate:.1f}%", "label": "Attrition Rate"},
                {"value": f"{avg_tenure:.1f}yr", "label": "Avg Tenure"}
            ]
        
        elif dashboard_type == "hours":
            if not time_df.empty:
                total_hours = time_df['Hours'].sum()
                avg_daily = time_df.groupby('Entry_Date')['Hours'].sum().mean()
                top_work_type = time_df.groupby('Work_Type')['Hours'].sum().idxmax()
                active_projects = time_df['Project_Code'].nunique()
                
                period_label = time_period.title() if time_period else "Last 90 Days"
                
                kpis = [
                    {"value": f"{int(total_hours):,}h", "label": f"Total Hours ({period_label})"},
                    {"value": f"{avg_daily:.1f}h", "label": "Avg Daily Hours"},
                    {"value": top_work_type.split()[0], "label": "Top Activity"},
                    {"value": active_projects, "label": "Active Projects"}
                ]
            else:
                kpis = [
                    {"value": "N/A", "label": "No Time Data"},
                    {"value": "N/A", "label": "Available"},
                    {"value": "N/A", "label": "For This"},
                    {"value": "N/A", "label": "Period"}
                ]
        
        elif dashboard_type == "band_analysis":
            band_counts = active_employees['Band'].value_counts()
            most_common = band_counts.idxmax() if not band_counts.empty else "N/A"
            senior_count = len(active_employees[active_employees['Band'].isin(['BIV', 'BV'])])
            
            kpis = [
                {"value": len(active_employees), "label": "Total Employees"},
                {"value": most_common, "label": "Most Common Band"},
                {"value": senior_count, "label": "Senior Level (IV-V)"},
                {"value": active_employees['Band'].nunique(), "label": "Band Levels"}
            ]
        
        elif dashboard_type == "demographics":
            avg_age = active_employees['Age'].mean()
            age_range = f"{active_employees['Age'].min()}-{active_employees['Age'].max()}"
            
            kpis = [
                {"value": len(active_employees), "label": "Active Employees"},
                {"value": f"{avg_age:.0f}", "label": "Average Age"},
                {"value": age_range, "label": "Age Range"},
                {"value": active_employees['Department'].nunique(), "label": "Departments"}
            ]
        
        elif dashboard_type == "location_compare":
            locations = active_employees['Work_Location'].nunique()
            top_location = active_employees['Work_Location'].value_counts().idxmax()
            
            kpis = [
                {"value": len(active_employees), "label": "Total Employees"},
                {"value": locations, "label": "Locations"},
                {"value": top_location.split(',')[0], "label": "Largest Office"},
                {"value": f"{active_employees['Tenure_Years'].mean():.1f}yr", "label": "Avg Tenure"}
            ]
        
        elif dashboard_type == "project":
            if not time_df.empty:
                projects = time_df['Project_Code'].nunique()
                top_project = time_df.groupby('Project_Code')['Hours'].sum().idxmax()
                
                kpis = [
                    {"value": projects, "label": "Active Projects"},
                    {"value": top_project.split('-')[0], "label": "Top Project"},
                    {"value": f"{time_df['Hours'].sum():,.0f}h", "label": "Total Hours"},
                    {"value": len(active_employees), "label": "Team Members"}
                ]
            else:
                kpis = [{"value": "N/A", "label": "No Project Data"} for _ in range(4)]
        
        else:  # general
            kpis = [
                {"value": len(active_employees), "label": "Active Employees"},
                {"value": active_employees['Work_Location'].nunique(), "label": "Locations"},
                {"value": active_employees['Department'].nunique(), "label": "Departments"},
                {"value": f"{active_employees['Tenure_Years'].mean():.1f}yr", "label": "Avg Tenure"}
            ]
        
        # Generate KPI HTML
        kpi_html = '<div class="kpi-grid">'
        for kpi in kpis:
            kpi_html += f'''
            <div class="kpi-card">
                <div class="kpi-value">{kpi["value"]}</div>
                <div class="kpi-label">{kpi["label"]}</div>
            </div>
            '''
        kpi_html += '</div>'
        return kpi_html
    
    kpi_html = generate_smart_kpis()
    
    # Build visualizations based on dashboard type
    plotly_config = {'displayModeBar': False, 'responsive': True}
    
    def create_figure_layout(title):
        return dict(
            title=dict(text=title, font=dict(color=TITLE_COLOR, size=18, family='Inter'), x=0.05),
            paper_bgcolor=PAPER_COLOR,
            plot_bgcolor=BG_COLOR,
            font=dict(color=TEXT_COLOR, family='Inter'),
            margin=dict(l=50, r=30, t=50, b=50),
            height=400,
            xaxis=dict(gridcolor=GRID_COLOR, color=TEXT_COLOR, showgrid=True),
            yaxis=dict(gridcolor=GRID_COLOR, color=TEXT_COLOR, showgrid=True),
            hovermode='closest'
        )
    
    if dashboard_type == "attrition":
        # Chart 1: Turnover by Department
        dept_status = employees_df.groupby(['Department', 'Employment_Status']).size().unstack(fill_value=0)
        
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            name='Active',
            x=dept_status.index,
            y=dept_status['Active'] if 'Active' in dept_status.columns else [],
            marker_color='#4a9eff',
            text=dept_status['Active'] if 'Active' in dept_status.columns else [],
            textposition='inside',
            textfont=dict(color='white', size=12)
        ))
        if 'Terminated' in dept_status.columns:
            fig1.add_trace(go.Bar(
                name='Terminated',
                x=dept_status.index,
                y=dept_status['Terminated'],
                marker_color='#ef4444',
                text=dept_status['Terminated'],
                textposition='inside',
                textfont=dict(color='white', size=12)
            ))
        
        fig1.update_layout(
            **create_figure_layout('Employee Status by Department'),
            barmode='stack',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font=dict(color=TEXT_COLOR))
        )
        figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
        
        # Chart 2: Tenure Distribution
        fig2 = go.Figure()
        fig2.add_trace(go.Histogram(
            x=active_employees['Tenure_Years'],
            nbinsx=20,
            marker=dict(
                color='#4a9eff',
                line=dict(color='#2563eb', width=1)
            ),
            hovertemplate='Tenure: %{x:.1f} years<br>Count: %{y}<extra></extra>'
        ))
        
        fig2.update_layout(
            **create_figure_layout('Tenure Distribution'),
            xaxis_title='Years of Service',
            yaxis_title='Number of Employees'
        )
        figures.append(fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config))
        
        # Chart 3: Location-wise Retention
        location_counts = active_employees['Work_Location'].value_counts().head(8).sort_values()
        
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            y=location_counts.index,
            x=location_counts.values,
            orientation='h',
            marker=dict(
                color='#4a9eff',
                line=dict(color='#2563eb', width=1)
            ),
            text=location_counts.values,
            textposition='auto',
            textfont=dict(color='white', size=12),
            hovertemplate='%{y}<br>Employees: %{x}<extra></extra>'
        ))
        
        layout3 = create_figure_layout('Active Employees by Location')
        layout3['xaxis_title'] = 'Number of Employees'
        layout3['yaxis'] = dict(color=TEXT_COLOR, showgrid=False)
        fig3.update_layout(**layout3)
        figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
        
    elif dashboard_type == "hours":
        if not time_df.empty:
            # Map departments
            emp_dept_map = employees_df.set_index('Corporate_ID')['Department'].to_dict()
            time_df['Department'] = time_df['Corporate_ID'].map(emp_dept_map)
            
            # Chart 1: Hours by Department
            hours_by_dept = time_df.groupby('Department')['Hours'].sum().sort_values(ascending=False)
            
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(
                x=hours_by_dept.index,
                y=hours_by_dept.values,
                marker=dict(
                    color=COLOR_SCHEME[:len(hours_by_dept)],
                    line=dict(color='#1e3a8a', width=1)
                ),
                text=[f'{int(v):,}h' for v in hours_by_dept.values],
                textposition='outside',
                textfont=dict(color=TEXT_COLOR, size=11),
                hovertemplate='%{x}<br>Hours: %{y:,.0f}<extra></extra>'
            ))
            
            period_text = f" ({time_period.title()})" if time_period else " (Last 90 Days)"
            fig1.update_layout(**create_figure_layout(f'Total Hours by Department{period_text}'))
            figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
            
            # Chart 2: Work Type Breakdown
            hours_by_type = time_df.groupby('Work_Type')['Hours'].sum().sort_values(ascending=False)
            
            fig2 = go.Figure()
            fig2.add_trace(go.Pie(
                labels=hours_by_type.index,
                values=hours_by_type.values,
                hole=0.45,
                marker=dict(colors=COLOR_SCHEME, line=dict(color='#0a1628', width=2)),
                textfont=dict(color='white', size=12),
                hovertemplate='%{label}<br>%{value:,.0f} hours (%{percent})<extra></extra>'
            ))
            
            layout2 = create_figure_layout('Hours by Work Type')
            layout2['showlegend'] = True
            layout2['legend'] = dict(orientation='v', yanchor='middle', y=0.5, xanchor='left', x=1.05, font=dict(color=TEXT_COLOR))
            fig2.update_layout(**layout2)
            figures.append(f'<div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart2")}</div>')
            
            # Chart 3: Daily Trend
            time_df['Entry_Date'] = pd.to_datetime(time_df['Entry_Date'])
            daily_hours = time_df.groupby('Entry_Date')['Hours'].sum().reset_index()
            
            # Calculate 7-day moving average
            daily_hours['MA7'] = daily_hours['Hours'].rolling(window=7, min_periods=1).mean()
            
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=daily_hours['Entry_Date'],
                y=daily_hours['Hours'],
                mode='lines',
                name='Daily Hours',
                line=dict(color='#4a9eff', width=1),
                fill='tozeroy',
                fillcolor='rgba(74, 158, 255, 0.2)',
                hovertemplate='%{x|%b %d}<br>Hours: %{y:.1f}<extra></extra>'
            ))
            fig3.add_trace(go.Scatter(
                x=daily_hours['Entry_Date'],
                y=daily_hours['MA7'],
                mode='lines',
                name='7-Day Average',
                line=dict(color='#fbbf24', width=2, dash='dash'),
                hovertemplate='%{x|%b %d}<br>Avg: %{y:.1f}<extra></extra>'
            ))
            
            layout3 = create_figure_layout('Daily Hours Trend')
            layout3['showlegend'] = True
            layout3['legend'] = dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font=dict(color=TEXT_COLOR))
            layout3['xaxis_title'] = 'Date'
            layout3['yaxis_title'] = 'Hours'
            fig3.update_layout(**layout3)
            figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
            
            # Chart 4: Top Projects
            project_hours = time_df.groupby('Project_Code')['Hours'].sum().sort_values(ascending=True).tail(10)
            
            fig4 = go.Figure()
            fig4.add_trace(go.Bar(
                y=project_hours.index,
                x=project_hours.values,
                orientation='h',
                marker=dict(
                    color='#6366f1',
                    line=dict(color='#4f46e5', width=1)
                ),
                text=[f'{int(v):,}h' for v in project_hours.values],
                textposition='auto',
                textfont=dict(color='white', size=10),
                hovertemplate='%{y}<br>Hours: %{x:,.0f}<extra></extra>'
            ))
            
            layout4 = create_figure_layout('Top 10 Projects by Hours')
            layout4['yaxis'] = dict(color=TEXT_COLOR, showgrid=False)
            layout4['xaxis_title'] = 'Total Hours'
            fig4.update_layout(**layout4)
            figures.append(f'<div class="chart-container">{fig4.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart4")}</div>')
    
    elif dashboard_type == "band_analysis":
        # Chart 1: Band Distribution
        band_order = ['BI', 'BII', 'BIII', 'BIV', 'BV']
        band_counts = active_employees['Band'].value_counts().reindex(band_order, fill_value=0)
        
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=band_counts.index,
            y=band_counts.values,
            marker=dict(
                color=COLOR_SCHEME[:len(band_counts)],
                line=dict(color='#1e3a8a', width=1)
            ),
            text=band_counts.values,
            textposition='outside',
            textfont=dict(color=TEXT_COLOR, size=14, weight='bold'),
            hovertemplate='Band %{x}<br>Employees: %{y}<extra></extra>'
        ))
        
        fig1.update_layout(
            **create_figure_layout('Employee Distribution by Band'),
            xaxis_title='Band Level',
            yaxis_title='Number of Employees'
        )
        figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
        
        # Chart 2: Band by Department (Stacked)
        band_dept = active_employees.groupby(['Department', 'Band']).size().unstack(fill_value=0)
        
        fig2 = go.Figure()
        for i, band in enumerate(band_order):
            if band in band_dept.columns:
                fig2.add_trace(go.Bar(
                    name=band,
                    x=band_dept.index,
                    y=band_dept[band],
                    marker_color=COLOR_SCHEME[i % len(COLOR_SCHEME)],
                    text=band_dept[band],
                    textposition='inside',
                    textfont=dict(color='white', size=10),
                    hovertemplate='%{x}<br>Band ' + band + ': %{y}<extra></extra>'
                ))
        
        layout2 = create_figure_layout('Band Distribution by Department')
        layout2['barmode'] = 'stack'
        layout2['showlegend'] = True
        layout2['legend'] = dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font=dict(color=TEXT_COLOR))
        layout2['yaxis_title'] = 'Number of Employees'
        fig2.update_layout(**layout2)
        figures.append(f'<div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart2")}</div>')
        
        # Chart 3: Average Tenure by Band
        tenure_by_band = active_employees.groupby('Band')['Tenure_Years'].mean().reindex(band_order)
        
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=tenure_by_band.index,
            y=tenure_by_band.values,
            marker=dict(
                color='#6366f1',
                line=dict(color='#4f46e5', width=1)
            ),
            text=[f'{v:.1f}y' for v in tenure_by_band.values],
            textposition='outside',
            textfont=dict(color=TEXT_COLOR, size=12),
            hovertemplate='Band %{x}<br>Avg Tenure: %{y:.1f} years<extra></extra>'
        ))
        
        layout3 = create_figure_layout('Average Tenure by Band')
        layout3['xaxis_title'] = 'Band'
        layout3['yaxis_title'] = 'Average Tenure (Years)'
        fig3.update_layout(**layout3)
        figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
    
    elif dashboard_type == "demographics":
        # Chart 1: Age Distribution
        fig1 = go.Figure()
        fig1.add_trace(go.Histogram(
            x=active_employees['Age'],
            nbinsx=15,
            marker=dict(
                color='#4a9eff',
                line=dict(color='#2563eb', width=1)
            ),
            hovertemplate='Age: %{x}<br>Count: %{y}<extra></extra>'
        ))
        
        layout1 = create_figure_layout('Age Distribution')
        layout1['xaxis_title'] = 'Age'
        layout1['yaxis_title'] = 'Number of Employees'
        fig1.update_layout(**layout1)
        figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
        
        # Chart 2: Department Distribution
        dept_counts = active_employees['Department'].value_counts()
        
        fig2 = go.Figure()
        fig2.add_trace(go.Pie(
            labels=dept_counts.index,
            values=dept_counts.values,
            hole=0.45,
            marker=dict(colors=COLOR_SCHEME, line=dict(color='#0a1628', width=2)),
            textfont=dict(color='white', size=12),
            hovertemplate='%{label}<br>%{value} employees (%{percent})<extra></extra>'
        ))
        
        layout2 = create_figure_layout('Employees by Department')
        layout2['showlegend'] = True
        layout2['legend'] = dict(orientation='v', yanchor='middle', y=0.5, xanchor='left', x=1.05, font=dict(color=TEXT_COLOR))
        fig2.update_layout(**layout2)
        figures.append(f'<div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart2")}</div>')
        
        # Chart 3: Top Locations
        location_counts = active_employees['Work_Location'].value_counts().head(8).sort_values()
        
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            y=location_counts.index,
            x=location_counts.values,
            orientation='h',
            marker=dict(
                color='#6366f1',
                line=dict(color='#4f46e5', width=1)
            ),
            text=location_counts.values,
            textposition='auto',
            textfont=dict(color='white', size=12),
            hovertemplate='%{y}<br>Employees: %{x}<extra></extra>'
        ))
        
        layout3 = create_figure_layout('Top Work Locations')
        layout3['yaxis'] = dict(color=TEXT_COLOR, showgrid=False)
        layout3['xaxis_title'] = 'Number of Employees'
        fig3.update_layout(**layout3)
        figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
    
    elif dashboard_type == "location_compare":
        # Chart 1: Employees by Location
        location_counts = active_employees['Work_Location'].value_counts().head(10)
        
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=location_counts.index,
            y=location_counts.values,
            marker=dict(
                color=COLOR_SCHEME[:len(location_counts)],
                line=dict(color='#1e3a8a', width=1)
            ),
            text=location_counts.values,
            textposition='outside',
            textfont=dict(color=TEXT_COLOR, size=11),
            hovertemplate='%{x}<br>Employees: %{y}<extra></extra>'
        ))
        
        layout1 = create_figure_layout('Employee Count by Location')
        layout1['xaxis'] = dict(color=TEXT_COLOR, showgrid=False, tickangle=-45)
        layout1['yaxis_title'] = 'Number of Employees'
        fig1.update_layout(**layout1)
        figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
        
        # Chart 2: Department Mix by Top Locations
        top_locations = location_counts.head(5).index
        loc_dept_data = active_employees[active_employees['Work_Location'].isin(top_locations)]
        loc_dept = loc_dept_data.groupby(['Work_Location', 'Department']).size().unstack(fill_value=0)
        
        fig2 = go.Figure()
        for i, dept in enumerate(loc_dept.columns):
            fig2.add_trace(go.Bar(
                name=dept,
                x=loc_dept.index,
                y=loc_dept[dept],
                marker_color=COLOR_SCHEME[i % len(COLOR_SCHEME)],
                hovertemplate='%{x}<br>' + dept + ': %{y}<extra></extra>'
            ))
        
        layout2 = create_figure_layout('Department Mix by Location')
        layout2['barmode'] = 'stack'
        layout2['showlegend'] = True
        layout2['legend'] = dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font=dict(color=TEXT_COLOR))
        layout2['xaxis'] = dict(color=TEXT_COLOR, showgrid=False, tickangle=-45)
        layout2['yaxis_title'] = 'Number of Employees'
        fig2.update_layout(**layout2)
        figures.append(f'<div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart2")}</div>')
        
        # Chart 3: Average Tenure by Location
        tenure_by_loc = active_employees.groupby('Work_Location')['Tenure_Years'].mean().sort_values(ascending=False).head(8)
        
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=tenure_by_loc.index,
            y=tenure_by_loc.values,
            marker=dict(
                color='#6366f1',
                line=dict(color='#4f46e5', width=1)
            ),
            text=[f'{v:.1f}y' for v in tenure_by_loc.values],
            textposition='outside',
            textfont=dict(color=TEXT_COLOR, size=11),
            hovertemplate='%{x}<br>Avg Tenure: %{y:.1f} years<extra></extra>'
        ))
        
        layout3 = create_figure_layout('Average Tenure by Location')
        layout3['xaxis'] = dict(color=TEXT_COLOR, showgrid=False, tickangle=-45)
        layout3['yaxis_title'] = 'Average Tenure (Years)'
        fig3.update_layout(**layout3)
        figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
    
    else:  # general
        # Chart 1: Department Overview
        dept_counts = active_employees['Department'].value_counts()
        
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=dept_counts.index,
            y=dept_counts.values,
            marker=dict(
                color=COLOR_SCHEME[:len(dept_counts)],
                line=dict(color='#1e3a8a', width=1)
            ),
            text=dept_counts.values,
            textposition='outside',
            textfont=dict(color=TEXT_COLOR, size=11),
            hovertemplate='%{x}<br>Employees: %{y}<extra></extra>'
        ))
        
        layout1 = create_figure_layout('Employees by Department')
        layout1['xaxis'] = dict(color=TEXT_COLOR, showgrid=False)
        layout1['yaxis_title'] = 'Number of Employees'
        fig1.update_layout(**layout1)
        figures.append(f'<div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs="cdn", config=plotly_config, div_id="chart1")}</div>')
        
        # Chart 2: Supervisory Organization Distribution
        siglum_counts = active_employees['Supervisory_Organization_Siglum'].value_counts()
        
        fig2 = go.Figure()
        fig2.add_trace(go.Pie(
            labels=siglum_counts.index,
            values=siglum_counts.values,
            hole=0.45,
            marker=dict(colors=COLOR_SCHEME, line=dict(color='#0a1628', width=2)),
            textfont=dict(color='white', size=12),
            hovertemplate='%{label}<br>%{value} employees (%{percent})<extra></extra>'
        ))
        
        layout2 = create_figure_layout('Distribution by Supervisory Organization')
        layout2['showlegend'] = True
        layout2['legend'] = dict(orientation='v', yanchor='middle', y=0.5, xanchor='left', x=1.05, font=dict(color=TEXT_COLOR))
        fig2.update_layout(**layout2)
        figures.append(f'<div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart2")}</div>')
        
        # Chart 3: Top Locations
        location_counts = active_employees['Work_Location'].value_counts().head(8).sort_values()
        
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            y=location_counts.index,
            x=location_counts.values,
            orientation='h',
            marker=dict(
                color='#6366f1',
                line=dict(color='#4f46e5', width=1)
            ),
            text=location_counts.values,
            textposition='auto',
            textfont=dict(color='white', size=12),
            hovertemplate='%{y}<br>Employees: %{x}<extra></extra>'
        ))
        
        layout3 = create_figure_layout('Employees by Location')
        layout3['yaxis'] = dict(color=TEXT_COLOR, showgrid=False)
        layout3['xaxis_title'] = 'Number of Employees'
        fig3.update_layout(**layout3)
        figures.append(f'<div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, config=plotly_config, div_id="chart3")}</div>')
        
    # Combine all charts - they're already wrapped in divs with chart-grid class applied
    if figures:
        charts_html = '<div class="chart-grid">' + '\n'.join(figures) + '</div>'
    else:
        charts_html = "<p style='color: #9ca3af; text-align: center; padding: 40px;'>No visualizations available for this query</p>"
        
    # Build final dashboard HTML
    time_period_display = f" - {time_period.title()}" if time_period else ""
    
    return f"""
    <div class="dashboard-header">
        <h2 class="dashboard-title">{parsed_query.get('focus', 'Dashboard').title()}{time_period_display}</h2>
        <p class="dashboard-subtitle">Generated from {len(employees_df)} employee records</p>
    </div>
    
    {kpi_html}
    
    {charts_html}
    """


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "vertex_ai_enabled": VERTEX_AI_ENABLED
    }
