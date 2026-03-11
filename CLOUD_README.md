# ☁️ SRP MediFlow — Cloud Deployment Reference

> **Last Updated:** March 11, 2026  
> **Version:** 4.0 (security hardened + E2E verified)  
> **Status:** LIVE ✅  All 42/42 E2E checks PASS

---

## 🖥️ Server Details

| Property | Value |
|---|---|
| Provider | Hetzner Cloud |
| Plan | CPX12 (1 vCPU / 2 GB RAM / 40 GB SSD) |
| Cost | ~€6.99 / month |
| OS | Ubuntu 22.04 LTS (Jammy) |
| Server Name | `srp-ai-server` |
| IP Address | `5.223.67.236` |
| SSH User | `root` |
| SSH Password | See `.env` → `SERVER_ROOT_PASSWORD` |
| SSH Key | `~/.ssh/id_ed25519` (on dev machine) |

**SSH command:**
```bash
ssh root@5.223.67.236
```

---

## 🌐 Domain & DNS

| Record | Type | Target | Proxy |
|---|---|---|---|
| `mediflow.srpailabs.com` | A | `5.223.67.236` | Cloudflare Proxied (Orange) |
| `*.mediflow.srpailabs.com` | A | `5.223.67.236` | Cloudflare Proxied (Orange) |
| `n8n.srpailabs.com` | A | `5.223.67.236` | Cloudflare Proxied (Orange) |

**Domain Registrar:** Namecheap  
**DNS / CDN:** Cloudflare  
**SSL:** Let's Encrypt (wildcard `*.mediflow.srpailabs.com`) — expires 2026-06-08

---

## 📁 App Structure on Server

```
/opt/srp-mediflow/
└── srp-mediflow/          ← App root (git repo)
    ├── srp_mediflow_server.py   ← Main Flask server (port 7500)
    ├── .env                     ← All secrets (never commit)
    ├── venv/                    ← Python virtualenv
    ├── backups/                 ← Auto DB backups
    └── logs/                    ← App logs
```

**Git Remote:** `https://github.com/shashankpasikanti91-blip/srp-mediflow`  
**Branch:** `main`

---

## 🐘 PostgreSQL

| Property | Value |
|---|---|
| Host | `localhost:5432` |
| App User | `ats_user` |
| App Password | See `.env` → `PG_PASSWORD` |

**Databases:**

| DB Name | Purpose | Status |
|---|---|---|
| `srp_platform_db` | SaaS platform (tenants, billing, analytics) | ✅ Live |
| `hospital_ai` | Star Hospital (star_hospital) | ✅ 5 doctors, 6 staff |
| `srp_sai_care` | Sai Care Hospital | ✅ 5 doctors, 6 staff |
| `srp_city_medical` | City Medical Centre  | ✅ 5 doctors, 6 staff |
| `srp_apollo_warangal` | Apollo Clinic Warangal | ✅ 5 doctors, 6 staff |
| `srp_green_cross` | Green Cross Hospital | ✅ 5 doctors, 6 staff |
| `mediflow_platform` | Reserved | created |

---

## 🏥 Live Client URLs

| Hospital | Base URL | Admin User | Admin Password |
|---|---|---|---|
| Star Hospital | `https://star-hospital.mediflow.srpailabs.com` | `star_hospital_admin` | `Star@Admin2026!` |
| SRP Sai Care | `https://sai-care.mediflow.srpailabs.com` | `sai_care_admin` | `Sai_@Admin2026!` |
| City Medical | `https://city-medical.mediflow.srpailabs.com` | `city_medical_admin` | `City@Admin2026!` |
| Apollo Warangal | `https://apollo-warangal.mediflow.srpailabs.com` | `apollo_warangal_admin` | `Apol@Admin2026!` |
| Green Cross | `https://green-cross.mediflow.srpailabs.com` | `green_cross_admin` | `Gree@Admin2026!` |

**URL pattern per client subdomain:**
```
https://{subdomain}.mediflow.srpailabs.com/          ← public chatbot
https://{subdomain}.mediflow.srpailabs.com/login     ← all staff login
https://{subdomain}.mediflow.srpailabs.com/admin     ← admin dashboard
https://{subdomain}.mediflow.srpailabs.com/doctor    ← doctor portal
https://{subdomain}.mediflow.srpailabs.com/nurse     ← nurse portal
https://{subdomain}.mediflow.srpailabs.com/lab       ← lab portal
https://{subdomain}.mediflow.srpailabs.com/stock     ← stock portal
```

**Platform / Founder:**
```
https://mediflow.srpailabs.com/              ← SaaS landing page
https://mediflow.srpailabs.com/login        ← Founder login
https://mediflow.srpailabs.com/founder      ← Founder dashboard
```

**Password Pattern (for all roles):**
```
Admin:      {slug[:4].capitalize()}@Admin2026!     e.g. Star@Admin2026!
Doctor:     Doctor@{slug[:4]}2026!                 e.g. Doctor@star2026!
Nurse:      Nurse@{slug[:4]}2026!
Lab:        Lab@{slug[:4]}2026!
Stock:      Stock@{slug[:4]}2026!
Reception:  Recep@{slug[:4]}2026!
Founder:    Srp@Founder2026!
```

---

## ⚙️ Services

| Service | Command | Status |
|---|---|---|
| App | `systemctl status srp-mediflow` | auto-restart |
| Nginx | `systemctl status nginx` | proxy + SSL |
| PostgreSQL | `systemctl status postgresql` | persistent |
| n8n | `systemctl status n8n` (or `pm2 list`) | automation |

---

## 🚀 Deploy / Update Commands

**SSH in & update to latest code:**
```bash
ssh root@5.223.67.236
cd /opt/srp-mediflow/srp-mediflow
git pull origin main
systemctl restart srp-mediflow
```

**Check app logs:**
```bash
journalctl -u srp-mediflow -f
```

**Check nginx logs:**
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

**Restart all services:**
```bash
systemctl restart srp-mediflow nginx postgresql
```

**Manual DB backup:**
```bash
cd /opt/srp-mediflow/srp-mediflow
source venv/bin/activate
python3 saas_backup.py
```

---

## 🔄 CI/CD — Deploy Locally via Script

When you push code locally, run this to deploy to the server:

```bash
# From your local Windows machine (workspace folder):
C:/Python314/python.exe _deploy_fix2.py
```

Or use the paramiko script `_deploy_fix.py` for a full fresh deploy.

---

## 🔐 Security Checklist

| Check | Status |
|---|---|
| All API keys in `.env` only | ✅ |
| `.env` in `.gitignore` | ✅ |
| Security headers (nginx) | ✅ X-Frame, CSP, HSTS, etc. |
| HTTPS / SSL wildcard cert | ✅ Let's Encrypt |
| Brute-force lockout (2 attempts) | ✅ DB-persisted |
| Password bcrypt hashed | ✅ |
| CORS restricted | ✅ no wildcard `*` |
| Error messages sanitised | ✅ no stack traces |
| SSH key auth (dev machine) | ✅ `~/.ssh/id_ed25519` |

---

## 🔑 Credentials Storage

**All credentials are stored in:**
```
/opt/srp-mediflow/srp-mediflow/.env   (server)
.env                                   (local dev — gitignored)
```

**Never commit `.env` to git.**  
See `.env.example` for the full list of required keys.

**Server root credentials are stored as:**
```
SERVER_SSH_HOST=5.223.67.236
SERVER_SSH_USER=root
SERVER_ROOT_PASSWORD=856Reey@nsh
```

---

## 🔧 SSL Certificate Renewal

Let's Encrypt auto-renews via certbot cron. To manually renew:
```bash
certbot renew --dry-run    # test
certbot renew              # renew
systemctl reload nginx
```

**Current expiry:** 2026-06-08 (89 days from March 11, 2026)

---

## 📦 Stack

| Component | Version |
|---|---|
| Python | 3.10 (venv) |
| Flask | 3.1.3 |
| PostgreSQL | 14 |
| Nginx | 1.18+ |
| OpenAI API | gpt-4o-mini |
| Telegram Bot | python-telegram-bot |
| Let's Encrypt | certbot wildcard |
| OS | Ubuntu 22.04 LTS |

---

## 🛠️ Troubleshooting

**App not starting:**
```bash
journalctl -u srp-mediflow -n 50
cd /opt/srp-mediflow/srp-mediflow && source venv/bin/activate && python3 srp_mediflow_server.py
```

**502 Bad Gateway (nginx):**
```bash
systemctl status srp-mediflow   # is app running?
netstat -tlnp | grep 7500       # is port bound?
```

**Database connection error:**
```bash
systemctl status postgresql
sudo -u postgres psql -c "\l"   # list databases
```

**SSL cert issue:**
```bash
nginx -t                         # test config
certbot certificates             # check expiry
```

---

## 📝 Changelog

| Date | Change |
|---|---|
| 2026-03-11 | Full production deployment to Hetzner, SSL, systemd, .env fixed |
| 2026-03-11 | Security hardening: headers, brute-force, API key cleanup |
| 2026-03-11 | All 7 DBs created + schemas applied, 6 staff/DB + 5 doctors/DB seeded |
| 2026-03-11 | Subdomain routing fixed — star-hospital.mediflow.srpailabs.com etc. live |
| 2026-03-11 | HSTS added to nginx, all security headers verified |
| 2026-03-11 | Platform DB subdomain column updated for all 5 tenants |
| 2026-03-11 | E2E test: 42/42 checks PASS — all logins, doctors, dashboards verified |
