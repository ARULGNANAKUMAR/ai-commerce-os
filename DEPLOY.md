# AI Commerce OS — Production Deployment Guide

## Quick start (Docker Compose)

```bash
git clone <repo>
cd ai-commerce-os
cp .env.example .env       # fill in all values
docker compose up -d
# → app at http://localhost:8000
```

---

## MongoDB Atlas (recommended for production)

1. Create a free cluster at https://cloud.mongodb.com
2. Under **Database Access** → add a user with `readWriteAnyDatabase`.
3. Under **Network Access** → add your server IP (or `0.0.0.0/0` for PaaS).
4. Copy the connection string and set:

```env
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=ai_commerce_os
```

---

## Required environment variables

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | ✅ | Flask session secret. Use `openssl rand -hex 32`. |
| `JWT_ACCESS_SECRET` | ✅ | Different from SECRET_KEY. |
| `JWT_REFRESH_SECRET` | ✅ | Different from access secret. |
| `API_KEY_ENCRYPTION_KEY` | ✅ | Fernet key — see `.env.example`. |
| `MONGO_URI` | ✅ | Atlas URI or `mongodb://localhost:27017/`. |
| `RAZORPAY_KEY_ID` | ✅ | Razorpay Test Mode public key. |
| `RAZORPAY_KEY_SECRET` | ✅ | Razorpay Test Mode secret key. |
| `RAZORPAY_WEBHOOK_SECRET` | ✅ | Set in Razorpay Dashboard > Webhooks. |
| `ADMIN_EMAILS` | ✅ | Comma-separated admin email addresses. |
| `APP_BASE_URL` | ✅ | e.g. `https://yourapp.com` |

---

## Gunicorn (bare-metal / VM)

```bash
pip install -r requirements.txt

# Systemd service (recommended)
sudo tee /etc/systemd/system/acos.service << 'EOF'
[Unit]
Description=AI Commerce OS
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/ai-commerce-os
EnvironmentFile=/opt/ai-commerce-os/.env
ExecStart=/opt/ai-commerce-os/venv/bin/gunicorn -c gunicorn.conf.py "app:create_app()"
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now acos
```

---

## Nginx reverse proxy

```nginx
server {
    listen 80;
    server_name yourapp.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourapp.com;

    ssl_certificate     /etc/letsencrypt/live/yourapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourapp.com/privkey.pem;

    # Static files served directly by Nginx (faster than Flask)
    location /static/ {
        alias /opt/ai-commerce-os/static/;
        expires 1h;
        add_header Cache-Control "public";
    }

    # Everything else → Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

---

## Render / Railway one-click

Both platforms detect Python automatically.

**Render** (`render.yaml`):
```yaml
services:
  - type: web
    name: ai-commerce-os
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn -c gunicorn.conf.py "app:create_app()"
    envVars:
      - key: FLASK_ENV
        value: production
      # ... add remaining vars in Render Dashboard
```

**Railway**: Connect the repo, set env vars in the dashboard, Railway auto-detects `gunicorn.conf.py`.

---

## Razorpay Webhook configuration

1. Razorpay Dashboard → Settings → Webhooks → Add new endpoint.
2. URL: `https://yourapp.com/api/payments/webhook`
3. Events to subscribe:
   - `payment.captured`
   - `payment.failed`
   - `order.paid`
   - `refund.processed`
4. Copy the **Webhook Secret** into `RAZORPAY_WEBHOOK_SECRET`.

---

## Embed SDK usage (merchant storefront)

```bash
# Get embed snippet via API
curl -H "Authorization: Bearer <merchant_jwt>" \
  "https://yourapp.com/api/embed/code?widget=chat"
```

Merchants paste the returned `<script>` snippet into their website.
The chat button appears bottom-right. All AI, cart, and checkout flows
work within the embedded iframe — no additional setup required.

---

## Checklist before going live

- [ ] `FLASK_ENV=production`
- [ ] All JWT and encryption secrets are random, ≥ 32 chars
- [ ] MongoDB Atlas with TLS enabled
- [ ] Razorpay keys are **Test Mode** keys only (for Buildathon)
- [ ] `ADMIN_EMAILS` is set and does not include public addresses
- [ ] Nginx + SSL (Let's Encrypt) in front of Gunicorn
- [ ] `EMBED_CORS_ALLOWED_ORIGINS` restricted to merchant domains
- [ ] Webhook secret verified end-to-end
- [ ] Health check: `GET /api/health` returns `{"phase": 5}`
