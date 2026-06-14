# AI Job Application Agent

An AI-powered job application assistant that discovers LinkedIn **Easy Apply** jobs, matches them against your master resume using local Ollama models, tailors your resume without fabricating content, and requires **human approval** before any application is recorded as submitted.

## Features

- **LinkedIn Easy Apply Discovery** — Searches configurable keywords and locations; Easy Apply filter only
- **AI Job Matching** — Local Ollama scoring (0–100), missing skills, relevant experience
- **Resume Tailoring** — Reorders and emphasizes existing resume content only; anti-fabrication validation
- **ATS PDF Generation** — Clean, professional PDFs via ReportLab
- **Human Approval Workflow** — Preview, approve, then manually apply on LinkedIn
- **SQLite Database** — Jobs, applications, resumes, audit history; duplicate prevention
- **Web Dashboard** — FastAPI + Jinja2 UI for jobs, recommendations, resumes, applications
- **Scheduled Discovery** — APScheduler runs hourly (configurable)
- **Structured Logging** — Loguru with rotation, error logs, retries, browser crash recovery

## Safety Guarantees

| Rule | Enforcement |
|------|-------------|
| Never fabricate resume content | Pydantic validation + post-tailoring fabrication checks + strict LLM prompts |
| Easy Apply only | LinkedIn search filter `f_AL=true` + per-job Easy Apply button check |
| Human approval required | Applications stay `pending_approval` until explicitly approved |
| No auto-submission | System records submission only after you manually apply on LinkedIn |
| Match score threshold | Applications below `MIN_MATCH_SCORE` cannot be approved |
| Duplicate prevention | Unique constraints on `apply_url` and one application per job |

## Requirements

- Python 3.12+
- [Ollama](https://ollama.ai/) running locally with a model (e.g. `llama3.2`)
- LinkedIn account credentials
- Chromium (installed via Playwright)

## Installation

### 1. Clone and enter the project

```bash
cd "Resume agent"
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
```

Edit `.env` with your preferences (no LinkedIn credentials required):

```env
LINKEDIN_CONNECT_TIMEOUT=300
OLLAMA_MODEL=llama3.2
JOB_KEYWORDS=Software Engineer,Frontend Developer,Backend Developer,Full Stack Developer,React Developer
LOCATIONS=United States,Remote
MIN_MATCH_SCORE=70
```

### 5. Connect LinkedIn (manual login)

1. Start the dashboard (see below).
2. Click **Connect LinkedIn** — a headed Chromium window opens.
3. Sign in manually on LinkedIn (including CAPTCHA and 2FA if prompted).
4. When login succeeds, the session is saved to `data/browser_session/linkedin_state.json`.
5. **Disconnect** clears the saved session.

No LinkedIn email or password is stored in `.env` or the application.

### 6. Pull Ollama model

```bash
ollama pull llama3.2
```

### 7. Customize master resume

On first run, a sample resume is created at `data/master_resume.json`. **Replace it with your real resume data** before running discovery.

```bash
# Edit with your actual skills, experience, projects, etc.
notepad data\master_resume.json
```

## Running the Application

### Start the web dashboard

```bash
python -m app.main
```

Open **http://127.0.0.1:8000** in your browser.

### Alternative: uvicorn directly

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Usage Workflow

1. **Dashboard** → **Connect LinkedIn** (first time) → Click **Run Job Discovery Now** (or wait for hourly scheduler)
2. **Jobs Found** → Review discovered Easy Apply positions
3. **Recommended Jobs** → View jobs scoring above your threshold
4. **Applications** → Review pending applications:
   - Match score and missing skills
   - Tailored resume PDF download
   - Draft application answers
5. **Approve** → If satisfied, approve the application
6. **Apply manually** → Open the LinkedIn job link and complete Easy Apply yourself
7. **Mark as Submitted** → Record the submission in the system

## Project Structure

```
app/
├── agents/           # Job matcher, resume tailor, application assistant
├── linkedin/         # Playwright browser session & scraper
├── resume/           # Master resume management
├── database/         # SQLite schema & repository
├── pdf/              # ReportLab PDF generator
├── dashboard/        # FastAPI routes & Jinja2 templates
├── config/           # Pydantic settings (.env)
├── prompts/          # Ollama prompt templates
├── services/         # Ollama, scheduler, discovery, applications
├── models/           # Pydantic domain models
├── utils/            # Logging, retry utilities
├── container.py      # Dependency injection
└── main.py           # Application entry point

tests/                # Unit & integration tests
output/resumes/       # Generated PDF resumes
data/                 # Database, master resume, browser session
logs/                 # Application logs
```

## Database Schema

Four tables in SQLite (`data/agent.db`):

- **jobs** — Discovered LinkedIn positions with match scores
- **resumes** — Master and tailored resume JSON + PDF paths
- **applications** — Application records with approval status
- **application_history** — Audit trail of all actions

See `app/database/schema.sql` for full DDL.

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LINKEDIN_CONNECT_TIMEOUT` | `300` | Seconds to wait for manual LinkedIn login |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.2` | Model for matching & tailoring |
| `JOB_KEYWORDS` | Software Engineer,... | Comma-separated search terms |
| `LOCATIONS` | United States,Remote | Comma-separated locations |
| `MIN_MATCH_SCORE` | `70` | Minimum score to recommend/approve |
| `SCHEDULER_ENABLED` | `true` | Enable hourly discovery |
| `SCHEDULER_INTERVAL_HOURS` | `1` | Discovery interval |

## Testing

```bash
pytest tests/ -v
pytest tests/ -v --cov=app
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard with statistics |
| `GET /jobs` | Jobs found |
| `GET /recommended` | Recommended jobs |
| `GET /resumes` | Tailored resumes |
| `GET /applications` | Application list |
| `GET /applications/{id}` | Application review & approval |
| `POST /discover` | Trigger job discovery |
| `GET /health` | Health check (includes Ollama status) |

## Troubleshooting

### LinkedIn login fails
- LinkedIn may require CAPTCHA/2FA. Run with `DEBUG=true`, complete verification manually in the browser session saved at `data/browser_session/`.

### Ollama disconnected
- Ensure Ollama is running: `ollama serve`
- Verify model is pulled: `ollama list`

### Playwright errors
- Reinstall browsers: `playwright install chromium`

### Python not found (Windows)
- Install Python 3.12+ from [python.org](https://www.python.org/downloads/) and check "Add to PATH"

## License

MIT — Use responsibly and in compliance with LinkedIn's Terms of Service.
