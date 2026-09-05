# AI Commerce OS — Phase 1: Foundation

**Razorpay AI Buildathon 2026 · Track 01 — AI Growth & Agentic Commerce**

> Build an AI shopping agent for your store — no AI team required.

---

## What this is

Phase 1 is the production-ready foundation that every future feature plugs into. No AI engine, no workflow builder, no Razorpay integration yet — those are Phase 2. What Phase 1 gives you is the **secure, modular basement** that makes Phase 2 possible without rewrites:

- JWT authentication (access + refresh tokens, real logout via session revocation)
- Merchant profile (company, name, phone, business type — stored in MongoDB)
- Protected dashboard with sidebar navigation
- Audit log trail (every action: signup, login, profile update, logout)
- Permission-ready architecture (encryption util ready for AI + Razorpay keys)
- Phase 2 hooks clearly marked throughout the codebase

---

## Quick start

### Prerequisites

- Python 3.11+
- MongoDB running locally (`mongod`) or a MongoDB Atlas connection string
- A terminal

### 1. Clone and enter the project

```bash
cd ai-commerce-os
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
SECRET_KEY=your-long-random-string
MONGO_URI=mongodb://localhost:27017/
JWT_ACCESS_SECRET=another-long-random-string
JWT_REFRESH_SECRET=yet-another-long-random-string

# Required for Phase 2 (AI + Razorpay key encryption).
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
API_KEY_ENCRYPTION_KEY=
```

### 5. Run

```bash
python app.py
```

Open **http://localhost:5000**

---

## Project structure

```
ai-commerce-os/
│
│  ── Backend ──────────────────────────────────────────────────────
├── app.py          Flask application factory. Registers blueprints,
│                   init DB, wires error handlers. Entry point.
│
├── config.py       All settings from environment variables. Single
│                   source of truth — never os.environ outside here.
│
├── db.py           MongoDB connection + index declarations for all
│                   five Phase 1 collections.
│
├── models.py       Data access layer. Every DB read/write goes
│                   through a typed function here, never raw collection
│                   access from routes.
│
├── security.py     All crypto primitives: bcrypt, JWT issue/verify,
│                   Fernet encryption, input validation, @jwt_required.
│
├── auth.py         /api/auth/* blueprint: signup, login, logout,
│                   refresh, email verification (stubbed), password
│                   reset (stubbed).
│
├── routes.py       Page routes (/) and protected merchant API
│                   (/api/merchant/*): profile CRUD + dashboard summary.
│
├── utils.py        ApiError, api_response(), error handlers,
│                   get_client_ip(), utcnow().
│
│  ── Templates ─────────────────────────────────────────────────────
├── templates/
│   ├── index.html      Landing page
│   ├── login.html      Auth split-screen, login form
│   ├── signup.html     Auth split-screen, signup form
│   ├── dashboard.html  Protected dashboard home
│   └── settings.html   Profile + account + security settings
│
│  ── Frontend ──────────────────────────────────────────────────────
└── static/
    ├── style.css       Design tokens, base layout, form fields,
    │                   buttons, badges, auth split-screen CSS
    ├── dashboard.css   Sidebar, topbar, metrics grid, activity list,
    │                   settings layout, responsive breakpoints
    ├── app.js          ACOS namespace: token storage, apiFetch() with
    │                   silent token refresh, requireAuth() route guard,
    │                   logout, mobile sidebar, format helpers
    └── auth.js         Login + signup form handling, client-side
                        validation, forgot-password inline swap
```

---

## API reference

All endpoints return: `{ "success": bool, "message": str, "data": any | null, "error": { "code": str, "message": str } }`

### Auth — `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/signup` | — | Create account + merchant profile |
| POST | `/login` | — | Returns access + refresh tokens |
| POST | `/logout` | JWT | Revokes refresh token session |
| POST | `/refresh` | — | Exchange refresh token for new access token |
| GET | `/verify-email/<token>` | — | Mark email verified |
| POST | `/resend-verification` | JWT | Resend verification email |
| POST | `/forgot-password` | — | Send reset link (enum-safe) |
| POST | `/reset-password/<token>` | — | Set new password + revoke all sessions |

### Merchant — `/api/merchant`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/profile` | JWT | Full user + merchant profile |
| PUT | `/profile` | JWT | Update merchant profile fields |
| GET | `/dashboard-summary` | JWT | Metric cards + recent activity |
| GET | `/activity` | JWT | Paginated audit log (`?limit=20`) |

---

## MongoDB collections

| Collection | Purpose |
|---|---|
| `users` | Auth identity: email, bcrypt hash, verification state, reset tokens |
| `merchants` | Business profile: company name, merchant name, phone, business type |
| `sessions` | Refresh token registry — enables real logout and force-revocation. TTL-indexed. |
| `api_keys` | **Phase 2 hook** — encrypted AI provider + Razorpay keys. Schema ready, unused in Phase 1. |
| `audit_logs` | Append-only action trail. Compound index on `{merchant_id, timestamp}`. |

---

## Security model

| Concern | How it's handled |
|---|---|
| Passwords | bcrypt (cost factor 12). Never stored plaintext. |
| Access tokens | HS256 JWT, 15-minute expiry, `JWT_ACCESS_SECRET` |
| Refresh tokens | HS256 JWT, 7-day expiry, stored only as a SHA-256 hash in `sessions` |
| Logout | Refresh token hash is revoked in `sessions`; access token expires naturally (15 min) |
| Force-logout | `revoke_all_sessions_for_user()` called on password reset |
| Third-party secrets | AES-256-GCM (Fernet) via `encrypt_secret()` / `decrypt_secret()` in `security.py` |
| Email enumeration | `forgot-password` returns identical response whether email exists or not |
| Input sanitization | `sanitize_string()` trims, caps length, strips non-printable chars before any DB write |

---

## Phase 2 integration hooks

Every file contains clearly marked `# Phase 2 hook` comments. The main connection points:

**`config.py`**
```python
FEATURE_AI_ENGINE_ENABLED = ...       # flip to True in Phase 2
FEATURE_PAYMENTS_ENABLED = ...
FEATURE_WORKFLOW_BUILDER_ENABLED = ...
```

**`models.py`**
```python
create_api_key(merchant_id, provider, encrypted_key)
get_api_keys_for_merchant(merchant_id)
# Phase 2: AI engine + Razorpay bridge call these to read encrypted keys
```

**`security.py`**
```python
encrypt_secret(plaintext)    # wrap merchant's AI / Razorpay key before storing
decrypt_secret(ciphertext)   # unwrap in-memory during a request, never log
```

**`routes.py` — dashboard-summary shape**
The `metrics` dict in `GET /api/merchant/dashboard-summary` already returns the exact contract the dashboard renders against. Phase 2 only has to populate real values:
```python
"metrics": {
    "conversations": { "value": 0 },     # → real session count
    "conversion_rate": { "value": None }, # → agent checkout %
    "revenue": { "value": 0 },            # → Razorpay captured total
    "active_agents": { "value": 0 },      # → published workflow count
}
```

**`auth.py` — `_send_email()` stub**
```python
def _send_email(to_address, subject, body):
    print(f"[EMAIL STUB] ...")
```
Replace the `print` with a call to SES / SendGrid / Postmark. The call sites (`signup`, `resend_verification`, `forgot_password`) already pass the full content.

---

## Environment variables reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `FLASK_ENV` | No | `development` | Set `production` in prod |
| `SECRET_KEY` | **Yes** | dev string | Flask session secret |
| `MONGO_URI` | **Yes** | `mongodb://localhost:27017/` | Any pymongo URI |
| `MONGO_DB_NAME` | No | `ai_commerce_os` | |
| `JWT_ACCESS_SECRET` | **Yes** | dev string | Separate from SECRET_KEY |
| `JWT_REFRESH_SECRET` | **Yes** | dev string | Different from access secret |
| `JWT_ACCESS_EXPIRES_MINUTES` | No | `15` | |
| `JWT_REFRESH_EXPIRES_DAYS` | No | `7` | |
| `API_KEY_ENCRYPTION_KEY` | Phase 2 | — | Fernet key; generate with script above |
| `FRONTEND_BASE_URL` | No | `http://localhost:5000` | Used in email links |

---

## Running the test suite (manual)

```bash
# With MongoDB running:
python app.py

# Then verify in a second terminal:
curl http://localhost:5000/api/health
# → {"service": "ai-commerce-os", "status": "ok", "success": true}

curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@test.com","password":"Test1234","merchant_name":"Your Name"}'
```

---

## Design system

Colours are declared as CSS variables in `style.css` under `:root`. The palette follows a Razorpay-inspired clean SaaS blue-on-off-white scheme:

```css
--color-primary:   #3395FF   /* links, buttons, active states */
--color-navy:      #0B1F3A   /* sidebar background, headings */
--color-bg:        #F5F7FA   /* page background */
--color-surface:   #FFFFFF   /* cards, panels */
--color-border:    #E3E8F0   /* all dividers and borders */
```

All type is Inter (display/body) + JetBrains Mono (metric values, code).

---

## What's NOT in Phase 1 (by design)

- AI engine (Gemini/OpenAI integration) — Phase 2
- Workflow / agent builder — Phase 2
- Product catalog upload — Phase 2
- Razorpay payment integration — Phase 2
- Real email sending (stubs only) — Phase 2
- Profile photo upload — Phase 2
- Rate limiting / abuse protection — Phase 2
- Real vector/semantic search — Phase 2
