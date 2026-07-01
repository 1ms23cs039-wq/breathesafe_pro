#project
# BreatheSafe — AI-Powered Air Quality Intelligence Platform

**Explainable Multi-Agent Decision Intelligence for AQI Forecasting, Personalised Health Risk & Pollution-Aware Travel Optimisation**

> Built for India | FastAPI + React + PostgreSQL | XGBoost v2 | Docker  
> **Status: Live and fully operational**

---

## Live Deployment

| Service | URL |
|---------|-----|
| **Frontend** | https://breathesafe-two.vercel.app |
| **Backend API** | https://breathesafe-backend.onrender.com |
| **API Docs (Swagger)** | https://breathesafe-backend.onrender.com/docs |
| **Health Check** | https://breathesafe-backend.onrender.com/health |
| **GitHub Repo** | https://github.com/Dhanush27m/deploy_breathesafe |

> **Free-tier note:** The Render backend spins down after 15 minutes of no traffic. The first request after idle takes ~30 seconds. Subsequent requests are normal speed.

---

## What This Project Does

BreatheSafe is a full-stack AI platform that helps people in Indian cities make health-conscious decisions around air quality. It provides:

- **Real-time AQI monitoring** for 29 major Indian cities, updated every hour automatically from satellite and weather data sources (no paid API keys needed).
- **1/3/7-day AQI forecasts** per city using XGBoost models trained on 3.5 years of historical data (942,761 rows, 27 features including lag patterns, seasonal encodings, weather, and pollution chemistry).
- **PAERI personalised health risk scoring** — a risk index that takes your health profile (age, conditions like asthma or heart disease, smoking status, pregnancy, activity level) and calculates a 0–100 personal risk score for any AQI reading, not just a generic category.
- **Pollution-aware route planning** — given a start and end point anywhere in India, generates fastest / cleanest / balanced route options with AQI exposure scores for each, backed by OSRM routing.
- **SHAP explainability** — every forecast comes with feature importance explanations: which factors (e.g. lag from yesterday, monsoon season, temperature) drove the predicted AQI.
- **Smart email alerts** — HTML emails sent on route save (showing risk score, journey details, and personalised recommendations), plus ongoing AQI monitoring emails if conditions change before your planned trip.
- **JWT authentication** with automatic token refresh — sessions stay alive for 7 days without re-login.

---

## Current Data & Model Status

| Item | Value |
|------|-------|
| Cities covered | 29 Indian cities |
| DB rows (live) | ~63,000 (90-day rolling window, auto-maintained) |
| Training CSV rows | 956,043 rows (Aug 2022 – May 2026) |
| Model version | v2.0 (trained May 9, 2026) |
| Model type | XGBoost (one model per city) |
| Training features | 27 (lag features, rolling averages, weather, temporal, seasonal) |
| Best city MAE | Chennai: 8.47 AQI units |
| Hardest city MAE | Gurugram: 108.67 (extreme pollution variability) |
| Data sources | Open-Meteo archive API + CAMS air quality API (both free, no key) |
| AQI formula | CPCB India standard (computed locally, not fetched) |
| Pipeline frequency | Hourly (APScheduler on Render) |
| Data retention | 90 days rolling (old rows auto-deleted daily) |

---

## Architecture Overview

```
User Browser (React + Vite)
        │
        ▼ HTTPS
Vercel CDN (static files)
        │
        ▼ API calls to VITE_API_URL
Render (FastAPI backend, Docker container)
        │
        ├── APScheduler (hourly AQI pipeline, daily cleanup, alert checks)
        │         │
        │         ├── Open-Meteo archive API  (weather: temp, wind, humidity, pressure)
        │         └── CAMS air quality API    (pollutants: PM2.5, PM10, NO2, SO2, CO, O3)
        │
        ├── XGBoost models (29 .joblib files, loaded from /app/ml/models/ at startup)
        │
        └── Supabase PostgreSQL (aqi_data, users, routes, notifications, health_profiles)
                  │
                  └── 90-day rolling window (~63k rows, ~78 MB)
```

---

## Hosting Stack

**Free cloud stack: Vercel + Render + Supabase — $0/month**

See **[HOSTING_GUIDE.md](./HOSTING_GUIDE.md)** for full step-by-step deployment instructions.

| Service | Role | Free Tier Used |
|---------|------|----------------|
| Vercel | React/Vite frontend (static CDN) | ~30 min of 6,000 build minutes |
| Render | FastAPI backend (Docker, 1 worker) | ~720 of 750 instance hours/month |
| Supabase | PostgreSQL database | ~78 MB of 500 MB |

---

## Key Differences: Dev vs Deploy Version

| | Dev (`breathesafe/`) | Deploy (`deploy_breathesafe/`) |
|---|---|---|
| Frontend serving | Vite dev server (HMR) | nginx static (multi-stage Docker) |
| Frontend port | 5173 | 5174 (local) / Vercel (cloud) |
| Backend port | 8000 | 8001 (local) / `$PORT` (cloud) |
| DB port | 5432 | 5434 (local) / Supabase pooler (cloud) |
| uvicorn workers | 1 (dev reload) | 1 (prevents double pipeline runs) |
| ML models | Docker volume | Committed to git (`backend/ml/models/`) |
| Hot reload | Yes | No |
| Data pipeline | Manual | Auto (APScheduler hourly) |

---

## Running Locally (Docker)

```bash
docker-compose up --build
```

| Service | Local URL |
|---------|-----------|
| Frontend | http://localhost:5174 |
| Backend API | http://localhost:8001 |
| API Docs | http://localhost:8001/docs |
| PostgreSQL | localhost:5434 |

Database migrations and city seeding run automatically on container start (via the Dockerfile CMD). No manual steps needed.

---

## ML Models

The trained XGBoost models live in `backend/ml/models/` and are **committed to git** so Render's Docker build bakes them into the image. No training happens at deploy time.

**Model v2.0 details:**
- Trained on 942,761 rows of hourly data (Aug 2022 – May 2026)
- 27 features: temporal encodings, 5 lag windows (24h/48h/72h/168h/336h), 4 rolling averages, rolling std devs, and current weather conditions
- One model per city (29 total)
- Training time: ~10–15 minutes on a local machine
- `metadata.json` in `backend/ml/models/` records exact training date, rows, features, and per-city MAE/RMSE

**When to retrain:** Every 3–6 months, or when forecast accuracy visibly degrades. Run from the `backend/` folder:
```bash
python train_models.py --csv ..\data\aqi_india_enriched.csv --skip-prophet --models-dir ml\models
```
Then commit the updated `.joblib` files and push. Render redeploys automatically.

**Keeping the training CSV updated:**
```bash
# From deploy_breathesafe/ folder — pulls new rows from Supabase into the local CSV
python sync_csv.py
```
The CSV is at `data/aqi_india_enriched.csv` (956,043 rows as of May 2026). Run `sync_csv.py` before retraining to include the latest data.

---

## Data Pipeline (Automatic)

The backend runs a fully automatic data pipeline on Render. Every hour:

1. APScheduler triggers `run_pipeline()` for all 29 cities
2. For each city, fetches weather from **Open-Meteo** (temperature, wind, humidity, pressure, precipitation, dew point, cloud cover, gusts)
3. Fetches pollutants from **CAMS air quality API** (PM2.5, PM10, NO2, SO2, CO, O3, dust, aerosol optical depth)
4. Computes India AQI using the **CPCB formula** locally
5. Inserts new rows into Supabase with `ON CONFLICT DO NOTHING` (idempotent)
6. If the app restarts after a long idle (Render cold start), it auto-detects the gap and uses the archive endpoints to backfill missing hours

The pipeline handles gaps of any size — short gaps (under 5 days) use the recent API, longer gaps use the historical archive APIs with date-range queries.

---

## Authentication

- JWT access tokens (24-hour expiry) + refresh tokens (7-day expiry)
- **Automatic token refresh** in the frontend axios interceptor: when a 401 is received on any request, the app silently calls `/auth/refresh`, updates the stored token, and retries the original request — no re-login needed unless both tokens expire
- On app startup, `AuthContext` validates the stored token via `/auth/me` to catch expiry early

---

## Environment Variables

### Backend (set in Render → Environment)

| Variable | Value / Description |
|----------|---------------------|
| `DATABASE_URL` | Supabase Session pooler URL (ends in `pooler.supabase.com`) |
| `SECRET_KEY` | Random 32-char hex string for JWT signing |
| `DEBUG` | `false` |
| `JWT_ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 hours) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Gmail address for sending alert emails |
| `SMTP_PASSWORD` | Gmail App Password (16 chars — not the account password) |
| `EMAIL_FROM` | `BreatheSafe <your-email@gmail.com>` |
| `AQI_FETCH_INTERVAL_MINUTES` | `60` |
| `ALERT_CHECK_INTERVAL_MINUTES` | `30` |
| `ALLOWED_ORIGINS` | `["https://breathesafe-two.vercel.app","http://localhost:5174"]` |

### Frontend (set in Vercel → Environment Variables)

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://breathesafe-backend.onrender.com` |

---

## API Endpoints

### Public (no auth required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness probe — `{"status":"healthy"}` |
| POST | `/auth/register` | Create account → returns JWT tokens |
| POST | `/auth/login` | Login with email + password → JWT tokens |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| GET | `/auth/me` | Get current user (used for token validation) |
| GET | `/aqi/cities` | List all 29 supported cities |
| GET | `/aqi/latest` | Most recent AQI reading per city |
| GET | `/aqi/rankings` | Cities ranked worst → best by current AQI |
| GET | `/aqi/stats` | Dataset statistics (total rows, date range, avg AQI) |
| GET | `/aqi/{city}/current` | Latest reading for one city |
| GET | `/aqi/{city}/history` | Hourly history (default 7 days, max 90) |
| GET | `/forecast/{city}` | 1, 3, 7-day AQI forecast (XGBoost) |
| POST | `/route/suggest` | AQI-aware route options (fastest/clean/balanced) |
| GET | `/explain/{city}/trends` | AQI trend analysis (90-day) |
| GET | `/explain/{city}/shap` | SHAP feature importance for last forecast |
| GET | `/explain/{city}/patterns` | Seasonal and time-of-day AQI patterns |

### Authenticated (JWT Bearer token required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/profile/` | Get health profile |
| POST | `/profile/` | Create health profile |
| PUT | `/profile/` | Update health profile |
| POST | `/risk/calculate` | PAERI personalised risk score |
| POST | `/route/save` | Save a route + trigger health check + email alert |
| DELETE | `/route/{id}` | Delete / cancel a saved route |
| GET | `/route/history` | Past saved routes (default 30 days) |
| GET | `/notifications/` | List all notifications |
| PATCH | `/notifications/{id}/read` | Mark one as read |
| PATCH | `/notifications/read-all` | Mark all as read |
| DELETE | `/notifications/{id}` | Delete one notification |

---

## Project Structure

```
deploy_breathesafe/
├── README.md                        ← this file
├── HOSTING_GUIDE.md                 ← step-by-step cloud deployment
├── docker-compose.yml               ← local: db (5434) + backend (8001) + frontend (5174)
├── sync_csv.py                      ← pull new Supabase rows into local training CSV
├── data/
│   └── aqi_india_enriched.csv       ← 956k-row training dataset (not in Docker image)
├── backend/
│   ├── Dockerfile                   ← python:3.11-slim, STARTTLS email, 1 uvicorn worker
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/versions/            ← DB schema migration files
│   ├── seed_cities.py               ← idempotent city + station seeding
│   ├── train_models.py              ← local training script (--csv, --models-dir flags)
│   └── app/
│       ├── main.py                  ← FastAPI app, lifespan startup, catch-up pipeline
│       ├── config.py                ← pydantic-settings, CORS validator, SMTP fallback
│       ├── scheduler.py             ← APScheduler: hourly pipeline, daily cleanup, alert checks
│       ├── database.py
│       ├── dependencies.py          ← get_current_user JWT dependency
│       ├── models/                  ← SQLAlchemy ORM (aqi_data, users, routes, notifications…)
│       ├── routers/
│       │   ├── auth.py              ← register, login, refresh, /me
│       │   ├── aqi.py               ← cities, latest, rankings, current, history
│       │   ├── forecast.py          ← 1/3/7-day XGBoost forecasts
│       │   ├── risk.py              ← PAERI risk scoring
│       │   ├── route.py             ← suggest, save, delete, history
│       │   ├── explain.py           ← SHAP, trends, patterns
│       │   ├── notifications.py     ← list, read, delete
│       │   └── profile.py           ← health profile CRUD
│       ├── schemas/                 ← Pydantic request/response models
│       ├── services/
│       │   ├── data_pipeline.py     ← hourly fetch from Open-Meteo + CAMS, AQI compute
│       │   ├── paeri.py             ← personalised AQI exposure risk index engine
│       │   ├── notifier.py          ← HTML email builder + aiosmtplib SMTP (STARTTLS)
│       │   └── route_engine.py      ← OSRM routing, AQI sampling, route scoring
│       ├── ml/
│       │   ├── models/              ← 29 XGBoost .joblib files + metadata.json (committed)
│       │   └── predictor.py         ← model loading, feature engineering, inference
│       └── core/
│           └── security.py          ← JWT (python-jose) + bcrypt password hashing
└── frontend/
    ├── Dockerfile                   ← multi-stage: node:20-alpine build → nginx:alpine serve
    ├── nginx.conf                   ← SPA routing (all paths → index.html)
    ├── vercel.json                  ← SPA rewrites for Vercel
    ├── vite.config.js
    └── src/
        ├── App.jsx                  ← routes, auth-gated navigation
        ├── context/AuthContext.jsx  ← login/register/logout + token validation on startup
        ├── services/api.js          ← axios with auto token refresh interceptor
        ├── components/              ← Icons.jsx, Navbar.jsx, AQIBadge.jsx
        └── pages/
            ├── Landing.jsx          ← hero + feature overview
            ├── Dashboard.jsx        ← live AQI map + city cards
            ├── Forecast.jsx         ← 1/3/7-day charts
            ├── AQITrends.jsx        ← 90-day trend analysis + SHAP explanations
            ├── RiskAnalysis.jsx     ← public city risk overview + logged-in PAERI
            ├── PersonalRisk.jsx     ← detailed personal risk with activity selector
            ├── RoutePlanner.jsx     ← route search + map + save with travel window
            ├── Profile.jsx          ← health profile (demographics, conditions, prefs)
            ├── Notifications.jsx    ← in-app alert centre
            ├── Login.jsx
            └── Register.jsx
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | React | 18 |
| Frontend build | Vite | 5 |
| Frontend styling | TailwindCSS | 3 |
| Frontend charts | Recharts | latest |
| Frontend maps | Leaflet | latest |
| Frontend serving (cloud) | Vercel CDN | — |
| Frontend serving (local) | nginx | alpine |
| Backend | FastAPI | 0.111 |
| Backend runtime | Python | 3.11 |
| Backend server | Uvicorn | 1 worker |
| ORM | SQLAlchemy | 2 |
| Migrations | Alembic | latest |
| Database | PostgreSQL 16 (local) / Supabase (cloud) | — |
| ML — forecasting | XGBoost | 2.0.3 |
| ML — explainability | SHAP | 0.45.0 |
| Auth tokens | python-jose (JWT) | latest |
| Password hashing | bcrypt | latest |
| Scheduling | APScheduler | 3.10.4 |
| Email | aiosmtplib (STARTTLS, port 587) | 3.0.1 |
| HTTP client (pipeline) | httpx / urllib | stdlib |
| Containerisation | Docker + docker-compose | latest |
| Hosting | Vercel + Render + Supabase | free tier |

---

## Notes

**SMTP email:** Uses Gmail App Password (not the account password) with `aiosmtplib 3.0.1` on port 587 with STARTTLS. The `EMAIL_FROM`, `SMTP_USER`, and `SMTP_PASSWORD` env vars must be set in Render's dashboard for emails to send in production.

**Single uvicorn worker:** The Dockerfile intentionally uses `--workers 1`. Multiple workers would each start their own APScheduler and run the pipeline simultaneously, causing duplicate DB inserts and wasted API calls.

**Token refresh:** The frontend axios interceptor automatically refreshes expired access tokens using the stored refresh token. If the refresh token is also expired, the user is redirected to `/login`. This means users stay logged in for up to 7 days without any action.

**90-day data retention:** A daily scheduled job deletes `aqi_data` rows older than 90 days. This keeps the database permanently bounded at ~70–80 MB on the free Supabase tier regardless of how long the service runs.

**Model retraining:** Not needed at deploy time. Models were trained locally and committed to git. Retrain every 3–6 months using `sync_csv.py` to update the training data first, then `train_models.py`.

---

## License

MIT © 2026 BreatheSafe
