"""
SRP MediFlow Hospital Management System - PRODUCTION READY
Full HMS: OPD + IPD + Pharmacy + Surgery + GST Billing + Multi-Tenant
"""

import sys
import io

# Fix Windows console encoding for emoji/unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import json
import os
import hashlib
import time
from dotenv import load_dotenv
import subprocess
import threading

# RBAC modules
import auth
import roles

try:
    from chatbot import generate_chatbot_response, reset_state, set_chatbot_state, get_chatbot_state, get_last_booking_record, clear_last_booking_record
except ImportError:
    # Fallback for missing chatbot
    def generate_chatbot_response(msg, state): return {"response": "AI temporarily unavailable", "state": state}
    def get_last_booking_record(): return None
    def clear_last_booking_record(): pass

# Load environment variables
load_dotenv()

# ── Founder / platform-level alert system (SaaS) ─────────────────────────────
try:
    from notifications.founder_alerts import send_founder_alert
    _FOUNDER_ALERTS_AVAILABLE = True
except ImportError:
    _FOUNDER_ALERTS_AVAILABLE = False
    def send_founder_alert(event_type, message): pass  # no-op fallback

# PostgreSQL database module
try:
    import db as hospital_db
    _DB_AVAILABLE = hospital_db.test_connection()
    if _DB_AVAILABLE:
        print("✅ PostgreSQL connected (localhost:5434 / hospital_ai)")
    else:
        print("⚠️  PostgreSQL unavailable — falling back to file storage")
        send_founder_alert(
            "DATABASE_CONNECTION_ERROR",
            "PostgreSQL is unreachable at startup. "
            "Server running in file-storage fallback mode."
        )
except Exception as _db_err:
    print(f"⚠️  DB module error: {_db_err} — falling back to file storage")
    send_founder_alert(
        "DATABASE_CONNECTION_ERROR",
        f"DB module raised an exception at startup: {_db_err}"
    )
    hospital_db = None
    _DB_AVAILABLE = False

try:
    from kie_ai_integration import transcribe_audio
except ImportError:
    transcribe_audio = None

# WhatsApp Business API gateway
try:
    from whatsapp_gateway import (
        receive_message as wa_receive_message,
        send_message as wa_send_message,
        verify_webhook_challenge,
        verify_webhook_signature,
        parse_inbound_payload,
        get_gateway_status,
    )
    _WHATSAPP_AVAILABLE = True
except ImportError:
    _WHATSAPP_AVAILABLE = False
    def wa_receive_message(p, m): return {"reply": "WhatsApp gateway unavailable"}
    def wa_send_message(p, m): return {"status": "error", "error": "gateway unavailable"}
    def verify_webhook_challenge(q): return None
    def verify_webhook_signature(b, s): return True
    def parse_inbound_payload(p): return []
    def get_gateway_status(): return {"active": False, "mode": "unavailable"}

# Telegram bot — always imported at startup for instant alerting
try:
    import telegram_bot as _tg
    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False
    class _tg:
        @staticmethod
        def notify_admin(m): pass
        @staticmethod
        def send_daily_summary(s): pass

# Dynamic client config (SRP MediFlow multi-client branding)
try:
    from client_config import get_cached_config as _get_client_cfg
    _CLIENT_CONFIG_AVAILABLE = True
except ImportError:
    _CLIENT_CONFIG_AVAILABLE = False
    def _get_client_cfg(host_header=""): return {"hospital_name": "Star Hospital", "product_name": "SRP MediFlow"}

# Multi-client tenant provisioning
try:
    from srp_mediflow_tenant import create_tenant_db as _create_tenant_db
    _TENANT_AVAILABLE = True
except ImportError:
    _TENANT_AVAILABLE = False
    def _create_tenant_db(*a, **kw): return {"error": "tenant module unavailable"}

# Security middleware
try:
    from api_security import sanitize_dict, log_access, check_rate_limit
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
    def sanitize_dict(d, **_): return d
    def log_access(*_, **__): pass
    def check_rate_limit(_ip): return True

# ── SaaS modules ──────────────────────────────────────────────────────────────
try:
    from saas_logging import system_log as _sys_log, security_log as _sec_log
    _SAAS_LOGGING = True
except ImportError:
    _SAAS_LOGGING = False
    class _sys_log:   # noqa: E701
        @staticmethod
        def info(m): pass
        @staticmethod
        def warning(m): pass
        @staticmethod
        def error(m): pass
    class _sec_log:   # noqa: E701
        @staticmethod
        def info(m): pass
        @staticmethod
        def warning(m): pass
        @staticmethod
        def error(m): pass

try:
    from saas_billing import (
        is_client_active as _billing_is_active,
        list_billing_accounts as _list_billing_accounts,
        get_billing_account as _get_billing_account,
        update_billing_status as _update_billing_status,
        flag_expired_accounts as _flag_expired_accounts,
        PLANS as _BILLING_PLANS,
    )
    _SAAS_BILLING = True
except ImportError:
    _SAAS_BILLING = False
    def _billing_is_active(_cid): return True
    def _list_billing_accounts(): return []
    def _get_billing_account(_cid): return None
    def _update_billing_status(*a, **kw): return False
    def _flag_expired_accounts(): return []
    _BILLING_PLANS = {}

try:
    from saas_export import export_data as _export_data
    _SAAS_EXPORT = True
except ImportError:
    _SAAS_EXPORT = False
    def _export_data(*a, **kw): return (b"", "text/plain", "error.txt")

try:
    from saas_analytics import (
        get_revenue_analytics,
        get_appointment_analytics,
        get_doctor_analytics,
    )
    _SAAS_ANALYTICS = True
except ImportError:
    _SAAS_ANALYTICS = False
    def get_revenue_analytics(**_): return {}
    def get_appointment_analytics(**_): return {}
    def get_doctor_analytics(**_): return {}

try:
    from saas_onboarding import onboard_hospital as _onboard_hospital
    _SAAS_ONBOARDING = True
except ImportError:
    _SAAS_ONBOARDING = False
    def _onboard_hospital(_d): return {"status": "error", "error": "onboarding module unavailable"}

try:
    from saas_backup import start_backup_scheduler as _start_backup_scheduler
    _SAAS_BACKUP = True
except ImportError:
    _SAAS_BACKUP = False
    def _start_backup_scheduler(): pass

# ── HMS v4 Core Modules (Patient, Billing, Doctor, Pharmacy, Lab, Analytics) ─
try:
    import hms_db as _hms
    _HMS_AVAILABLE = True
except ImportError as _hms_err:
    print(f"⚠️  hms_db not available: {_hms_err}")
    _HMS_AVAILABLE = False
    class _hms:  # noqa: E701  — fallback stubs
        @staticmethod
        def register_patient(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def search_patient_by_phone(p): return []
        @staticmethod
        def get_patient_history(pid): return {'error': 'HMS module unavailable'}
        @staticmethod
        def create_invoice(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def get_invoice(iid): return None
        @staticmethod
        def get_daily_revenue_report(**kw): return {}
        @staticmethod
        def get_doctor_patient_queue(u, n=''): return []
        @staticmethod
        def add_doctor_note(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def add_structured_prescription(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def get_pharmacy_stock_list(): return []
        @staticmethod
        def record_pharmacy_sale(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def get_pharmacy_alerts(): return {}
        @staticmethod
        def order_lab_test(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def record_lab_result(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def get_patient_lab_reports(pid): return []
        @staticmethod
        def get_analytics_revenue(period='daily'): return {}
        @staticmethod
        def get_analytics_patients(period='daily'): return {}
        @staticmethod
        def get_analytics_doctors(): return {}
        @staticmethod
        def get_mobile_dashboard(): return {}
        @staticmethod
        def create_appointment(d): return {'error': 'HMS module unavailable'}
        @staticmethod
        def create_hms_v4_tables(): pass

PORT = int(os.getenv('PORT', 7500))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Session storage (conversation sessions for chatbot only; auth sessions managed by auth.py)
conversation_sessions = {}


def _save_to_file(record: dict):
    """Fallback: append registration record to flat file."""
    registrations_file = os.path.join(BASE_DIR, 'registrations.txt')
    with open(registrations_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
        f.flush()


class Handler(BaseHTTPRequestHandler):
    
    # ─── Subdomain / Tenant Detection ────────────────────────────────────────
    def _detect_tenant_subdomain(self):
        """
        Parse the Host header to detect a per-tenant subdomain.
        Sets  self.current_subdomain  (str | None) for downstream route handlers.
        Also updates client last_activity in the clients_registry when a known
        subdomain is present — non-blocking; silently ignores errors.

        Examples
        --------
        Host: star.srpmediflow.com     → self.current_subdomain = "star"
        Host: localhost:7500           → self.current_subdomain = None
        Host: 127.0.0.1:7500           → self.current_subdomain = None
        """
        self.current_subdomain = None
        host = self.headers.get("Host", "")
        # Strip port suffix
        hostname = host.split(":")[0]
        # Only treat as subdomain when there is at least  sub.domain.tld
        parts = hostname.split(".")
        if len(parts) < 3:
            return
        sub = parts[0].lower()
        # Ignore generic / non-tenant prefixes
        if sub in ("www", "localhost", "mail", "ftp", "smtp", "api"):
            return
        self.current_subdomain = sub
        # Touch last_activity for the matching client (best-effort)
        try:
            import db as _db
            import psycopg2
            conn = psycopg2.connect(
                host=_db.DB_HOST, port=_db.DB_PORT,
                database=_db.DB_NAME,
                user=_db.DB_USER, password=_db.DB_PASS
            )
            cur = conn.cursor()
            cur.execute(
                "UPDATE clients SET last_activity = CURRENT_TIMESTAMP "
                "WHERE subdomain = %s",
                (sub,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-critical — never block the request

    def do_GET(self):
        # Subdomain / tenant detection
        self._detect_tenant_subdomain()
        # Apply per-user tenant DB routing (thread-local, affects all hospital_db.* calls)
        try:
            _req_user = self.get_session_user()
            if _req_user and _req_user.get('tenant_slug'):
                hospital_db.set_request_tenant(_req_user['tenant_slug'])
        except Exception:
            pass
        # Rate limiting
        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_json({'error': 'Too many requests — slow down'}, 429)
            return
        # Strip query string so route comparisons work with and without params
        path = self.path.split('?')[0]

        if path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif path == '/admin' or path == '/admin/':
            user = self.get_session_user()
            if user and roles.has_permission(user['role'], 'view_dashboard'):
                self.serve_file('admin_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/doctor':
            user = self.get_session_user()
            if user and user['role'] == 'DOCTOR':
                self.serve_file('doctor_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/nurse':
            user = self.get_session_user()
            if user and user['role'] == 'NURSE':
                self.serve_file('nurse_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/lab':
            user = self.get_session_user()
            if user and user['role'] in ('LAB', 'XRAY'):
                self.serve_file('lab_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/stock':
            user = self.get_session_user()
            if user and user['role'] == 'STOCK':
                self.serve_file('stock_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/founder' or path == '/founder/':
            user = self.get_session_user()
            if user and user['role'] == 'FOUNDER':
                self.serve_file('founder_dashboard.html', 'text/html')
            else:
                self._redirect_to_login()
        elif path == '/dashboard':
            user = self.get_session_user()
            if user:
                self.send_response(302)
                self.send_header('Location', roles.get_dashboard(user['role']))
                self.end_headers()
            else:
                self._redirect_to_login()
        elif path == '/login' or path == '/admin/login':
            self.serve_login_page()
        elif path == '/style.css':
            self.serve_file('style.css', 'text/css')
        elif path == '/script.js':
            self.serve_file('script.js', 'application/javascript')
        elif path == '/api/admin/data':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                self.send_admin_data()
        elif path == '/api/admin/doctors':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE', 'LAB', 'XRAY'):
                if _DB_AVAILABLE:
                    self.send_json({'doctors': hospital_db.get_all_doctors()})
                else:
                    self.send_json({'doctors': []})
        elif path == '/api/admin/attendance/today':
            if self.require_role('ADMIN', 'RECEPTION'):
                if _DB_AVAILABLE:
                    self.send_json({'attendance': hospital_db.get_attendance_today()})
                else:
                    self.send_json({'attendance': []})
        elif path == '/api/admin/rounds':
            if self.require_role('ADMIN', 'DOCTOR', 'NURSE', 'RECEPTION'):
                if _DB_AVAILABLE:
                    self.send_json({'rounds': hospital_db.get_doctor_rounds()})
                else:
                    self.send_json({'rounds': []})
        elif path == '/api/staff/list':
            if self.require_role('ADMIN'):
                users = hospital_db.list_staff_users() if _DB_AVAILABLE else []
                self.send_json({'users': users})
        elif path == '/api/stock/list':
            if self.require_role('ADMIN', 'STOCK', 'DOCTOR', 'NURSE'):
                items = hospital_db.get_all_stock() if _DB_AVAILABLE else []
                self.send_json({'stock': items})
        elif path == '/api/doctor/appointments':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                recs = hospital_db.get_all_registrations(200) if _DB_AVAILABLE else []
                if user['role'] == 'DOCTOR':
                    recs = [r for r in recs if r.get('doctor', '').lower() == user['full_name'].lower()]
                self.send_json({'appointments': recs})
        elif path == '/api/doctor/prescriptions':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                data_result = hospital_db.get_prescriptions_by_doctor(user['username']) if _DB_AVAILABLE else []
                self.send_json({'prescriptions': data_result})
        elif path == '/api/doctor/visits':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                visits = hospital_db.get_visit_records_by_doctor(user['username']) if _DB_AVAILABLE else []
                self.send_json({'visits': visits})
        elif path == '/api/admin/visits':
            if self.require_role('ADMIN'):
                visits = hospital_db.get_all_visit_records(200) if _DB_AVAILABLE else []
                self.send_json({'visits': visits})
        elif path == '/api/nurse/vitals':
            if self.require_role('NURSE', 'ADMIN', 'DOCTOR'):
                items = hospital_db.get_all_vitals(200) if _DB_AVAILABLE else []
                self.send_json({'vitals': items})
        elif path == '/api/nurse/assignments':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('NURSE', 'ADMIN'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                nurse_filter = user['username'] if user['role'] == 'NURSE' else None
                items = hospital_db.get_nurse_assignments(nurse_filter) if _DB_AVAILABLE else []
                self.send_json({'assignments': items})
        elif path == '/api/lab/orders':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('LAB', 'XRAY', 'DOCTOR', 'ADMIN'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                ttype = 'XRAY' if user['role'] == 'XRAY' else None
                items = hospital_db.get_lab_orders(ttype) if _DB_AVAILABLE else []
                self.send_json({'orders': items})
        elif path == '/api/session/me':
            user = self.get_session_user()
            if user:
                safe = {k: v for k, v in user.items() if k != 'expires'}
                self.send_json({'user': safe})
            else:
                self.send_json({'error': 'Not authenticated'}, 401)
        elif path == '/api/admin/billing/list':
            if self.require_role('ADMIN', 'RECEPTION'):
                bills = hospital_db.get_all_bills(200) if _DB_AVAILABLE else []
                self.send_json({'bills': bills})
        elif path == '/api/admin/logs':
            if self.require_role('ADMIN'):
                logs = hospital_db.get_system_logs(200) if _DB_AVAILABLE else []
                self.send_json({'logs': logs})
        elif path == '/api/admin/doctors':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('ADMIN', 'RECEPTION', 'NURSE'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                docs = hospital_db.get_all_doctors() if _DB_AVAILABLE else []
                self.send_json({'doctors': docs})
        elif path == '/health':
            self.send_json({'status': 'ok', 'timestamp': time.time(), 'db': _DB_AVAILABLE})

        # ── WhatsApp webhook verification (Meta GET challenge) ─────────────────
        elif path.startswith('/api/whatsapp/webhook'):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            params = {k: v[0] for k, v in qs.items()}
            challenge = verify_webhook_challenge(params)
            if challenge:
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(challenge.encode())
            else:
                self.send_json({'error': 'Verification failed'}, 403)

        elif path == '/api/whatsapp/status':
            self.send_json(get_gateway_status())

        elif path == '/api/telegram/status':
            try:
                from telegram_bot import get_bot_status
                self.send_json(get_bot_status())
            except ImportError:
                self.send_json({'active': False, 'note': 'Telegram module not loaded'})

        # ── SRP MediFlow Phase-2 GET routes ───────────────────────────────────
        elif path == '/api/admin/extended-data':
            if self.require_role('ADMIN', 'RECEPTION'):
                data_out = hospital_db.get_extended_dashboard_data() if _DB_AVAILABLE else {}
                self.send_json(data_out)

        elif path == '/api/medicines':
            if self.require_role('ADMIN', 'STOCK', 'DOCTOR', 'NURSE', 'RECEPTION'):
                meds = hospital_db.get_all_medicines() if _DB_AVAILABLE else []
                self.send_json({'medicines': meds})
        elif path == '/api/ipd/admissions':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                admissions = hospital_db.get_all_admissions() if _DB_AVAILABLE else []
                self.send_json({'admissions': admissions})
        elif path.startswith('/api/ipd/admission/'):
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                try:
                    adm_id = int(path.split('/')[-1])
                    rec = hospital_db.get_admission_by_id(adm_id) if _DB_AVAILABLE else None
                    self.send_json({'admission': rec})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid admission id'}, 400)
        elif path.startswith('/api/ipd/rounds/'):
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                try:
                    adm_id = int(path.split('/')[-1])
                    rounds = hospital_db.get_daily_rounds(adm_id) if _DB_AVAILABLE else []
                    self.send_json({'rounds': rounds})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid admission id'}, 400)
        elif path.startswith('/api/ipd/discharge/'):
            if self.require_role('ADMIN', 'DOCTOR'):
                try:
                    adm_id = int(path.split('/')[-1])
                    summary = hospital_db.get_discharge_summary(adm_id) if _DB_AVAILABLE else None
                    self.send_json({'discharge_summary': summary})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid admission id'}, 400)

        # Surgery
        elif path == '/api/surgery/list':
            if self.require_role('ADMIN', 'DOCTOR', 'RECEPTION'):
                records = hospital_db.get_surgery_records(200) if _DB_AVAILABLE else []
                self.send_json({'surgeries': records})

        # Pharmacy / Inventory
        elif path == '/api/pharmacy/inventory':
            if self.require_role('ADMIN', 'STOCK', 'DOCTOR', 'NURSE', 'RECEPTION'):
                inv = hospital_db.get_full_inventory() if _DB_AVAILABLE else []
                self.send_json({'inventory': inv})
        elif path == '/api/pharmacy/alerts/low-stock':
            if self.require_role('ADMIN', 'STOCK'):
                items = hospital_db.get_low_stock_alerts() if _DB_AVAILABLE else []
                self.send_json({'low_stock': items, 'count': len(items)})
        elif path == '/api/pharmacy/alerts/expiry':
            if self.require_role('ADMIN', 'STOCK'):
                items = hospital_db.get_expiry_alerts(90) if _DB_AVAILABLE else []
                self.send_json({'expiring': items, 'count': len(items)})
        elif path == '/api/procedures/list':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR'):
                procs = hospital_db.get_procedure_charges() if _DB_AVAILABLE else []
                self.send_json({'procedures': procs})

        elif path == '/api/services':
            # Public endpoint – no auth required (used by appointment booking & chatbot)
            data = hospital_db.get_services_catalogue() if _DB_AVAILABLE else []
            self.send_json({'services': data, 'count': len(data)})

        elif path == '/api/config':
            # Public: returns hospital branding so the JS front-end can personalise pages
            host_hdr = self.headers.get('Host', '')
            cfg = _get_client_cfg(host_hdr)
            # Also enrich with session tenant info if user is logged in
            user = self.get_session_user()
            if user and user.get('tenant_slug'):
                try:
                    import json as _j, os as _o
                    _reg = _j.load(open(
                        _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'tenant_registry.json'),
                        encoding='utf-8'))
                    _ti = _reg.get(user['tenant_slug'], {})
                    if _ti:
                        cfg = dict(cfg)
                        cfg['hospital_name']  = _ti.get('display_name', cfg.get('hospital_name', 'Hospital'))
                        cfg['hospital_phone'] = _ti.get('phone', cfg.get('hospital_phone', ''))
                        cfg['city']           = _ti.get('city', cfg.get('city', ''))
                except Exception:
                    pass
            self.send_json({
                'hospital_name':    cfg.get('hospital_name', 'Star Hospital'),
                'hospital_phone':   cfg.get('hospital_phone', ''),
                'hospital_address': cfg.get('hospital_address', ''),
                'city':             cfg.get('city', ''),
                'tagline':          cfg.get('hospital_tagline', ''),
                'primary_color':    cfg.get('primary_color', '#1a73e8'),
                'secondary_color':  cfg.get('secondary_color', '#00b896'),
                'product_name':     cfg.get('product_name', 'SRP MediFlow'),
            })

        elif path == '/api/tenants/list':
            # Public endpoint — returns all registered tenants for the login page selector
            try:
                import json as _j, os as _o
                reg_path = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'tenant_registry.json')
                with open(reg_path, encoding='utf-8') as _f:
                    registry = _j.load(_f)
                tenants_out = [
                    {'slug': slug, 'display_name': info.get('display_name', slug),
                     'city': info.get('city', '')}
                    for slug, info in registry.items()
                ]
                self.send_json({'tenants': tenants_out, 'count': len(tenants_out)})
            except Exception as _te:
                self.send_json({'tenants': [{'slug': 'star_hospital', 'display_name': 'Star Hospital', 'city': 'Kothagudem'}], 'count': 1})

        elif path == '/api/admin/clients':
            # List all registered clients (ADMIN only)
            if self.require_role('ADMIN'):
                clients = hospital_db.get_all_clients() if _DB_AVAILABLE else []
                self.send_json({'clients': clients, 'count': len(clients)})

        # ── Founder monitoring dashboard (platform-level, no patient data) ─────
        elif path == '/api/founder/system-status':
            self._handle_founder_system_status()

        elif path == '/api/doctors/directory':
            # Returns full doctor directory with qualifications & registration_no
            if _DB_AVAILABLE:
                try:
                    import psycopg2.extras as _px
                    with hospital_db.get_conn() as _conn:
                        _cur = _conn.cursor(cursor_factory=_px.RealDictCursor)
                        _cur.execute(
                            "SELECT id, name, department, specialization, "
                            "qualifications, registration_no, status, on_duty "
                            "FROM doctors ORDER BY department, name"
                        )
                        _rows = [dict(r) for r in _cur.fetchall()]
                        _cur.close()
                    self.send_json({'doctors': _rows, 'count': len(_rows)})
                except Exception as _e:
                    self.send_json({'error': str(_e)}, 500)
            else:
                self.send_json({'doctors': [], 'count': 0})

        # Billing
        elif path.startswith('/api/billing/items/'):
            if self.require_role('ADMIN', 'RECEPTION'):
                try:
                    bill_id = int(path.split('/')[-1])
                    bill = hospital_db.get_bill_with_items(bill_id) if _DB_AVAILABLE else None
                    self.send_json({'bill': bill})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid bill id'}, 400)

        # ── SaaS: Billing / Subscription routes ───────────────────────────────
        elif path == '/api/admin/billing/accounts':
            if self.require_role('ADMIN'):
                accounts = _list_billing_accounts() if _SAAS_BILLING else []
                self.send_json({'accounts': accounts, 'count': len(accounts)})

        elif path == '/api/admin/billing/plans':
            self.send_json({'plans': list(_BILLING_PLANS.values())})

        elif path.startswith('/api/admin/billing/account/'):
            if self.require_role('ADMIN'):
                try:
                    cid = int(path.split('/')[-1])
                    acct = _get_billing_account(cid) if _SAAS_BILLING else None
                    self.send_json({'account': acct})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid client_id'}, 400)

        # ── SaaS: Analytics routes ────────────────────────────────────────────
        elif path == '/api/admin/analytics/revenue':
            if self.require_role('ADMIN'):
                from urllib.parse import parse_qs, urlparse as _up
                qs  = parse_qs(_up(self.path).query)
                # Accept both ?period= (HMS) and ?range= (SaaS legacy) params
                rng = qs.get('period', qs.get('range', ['monthly']))[0]
                if _HMS_AVAILABLE:
                    data_out = _hms.get_analytics_revenue(period=rng)
                elif _SAAS_ANALYTICS:
                    data_out = get_revenue_analytics(date_range=rng)
                else:
                    data_out = {'summary': {'total_revenue': 0, 'total_bills': 0}}
                self.send_json(data_out)

        elif path == '/api/admin/analytics/appointments':
            if self.require_role('ADMIN', 'RECEPTION'):
                from urllib.parse import parse_qs, urlparse as _up
                qs = parse_qs(_up(self.path).query)
                rng = qs.get('range', ['monthly'])[0]
                data_out = get_appointment_analytics(date_range=rng) if _SAAS_ANALYTICS else {}
                self.send_json(data_out)

        elif path == '/api/admin/analytics/doctors':
            if self.require_role('ADMIN', 'DOCTOR'):
                if _HMS_AVAILABLE:
                    data_out = _hms.get_analytics_doctors()
                elif _SAAS_ANALYTICS:
                    from urllib.parse import parse_qs, urlparse as _up
                    qs = parse_qs(_up(self.path).query)
                    rng = qs.get('range', ['monthly'])[0]
                    data_out = get_doctor_analytics(date_range=rng)
                else:
                    data_out = {'doctors_on_duty': [], 'doctors_on_duty_count': 0}
                self.send_json(data_out)

        # ── SaaS: Audit log ───────────────────────────────────────────────────
        elif path == '/api/admin/audit-log':
            if self.require_role('ADMIN'):
                from urllib.parse import parse_qs, urlparse as _up
                qs     = parse_qs(_up(self.path).query)
                limit  = int(qs.get('limit', ['200'])[0])
                logs   = hospital_db.get_audit_logs(limit) if _DB_AVAILABLE else []
                self.send_json({'logs': logs, 'count': len(logs)})

        # ── SaaS: Clients registry (enhanced) ─────────────────────────────────
        elif path == '/api/admin/clients/registry':
            if self.require_role('ADMIN'):
                clients = hospital_db.get_clients_registry() if _DB_AVAILABLE else []
                self.send_json({'clients': clients, 'count': len(clients)})

        # ── SaaS: Export endpoints ─────────────────────────────────────────────
        elif path in ('/api/admin/export/patients',
                      '/api/admin/export/billing',
                      '/api/admin/export/appointments'):
            if not self.require_role('ADMIN'):
                return
            export_type = path.split('/')[-1]   # patients | billing | appointments
            from urllib.parse import parse_qs, urlparse as _up
            qs         = parse_qs(_up(self.path).query)
            fmt        = qs.get('format', ['excel'])[0].lower()
            date_range = qs.get('range',  ['monthly'])[0].lower()
            from_date  = qs.get('from',   [None])[0]
            to_date    = qs.get('to',     [None])[0]
            if not _SAAS_EXPORT:
                self.send_json({'error': 'Export module not available'}, 503)
                return
            try:
                file_bytes, mime_type, filename = _export_data(
                    export_type=export_type,
                    fmt=fmt,
                    date_range=date_range,
                    from_date=from_date,
                    to_date=to_date,
                )
                self.send_response(200)
                self.send_header('Content-Type', mime_type)
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(file_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(file_bytes)
                _sys_log.info(
                    f"Export: type={export_type} fmt={fmt} range={date_range} "
                    f"user={self.get_session_user().get('username','?') if self.get_session_user() else '?'}"
                )
            except Exception as _ex:
                self.send_json({'error': f'Export failed: {_ex}'}, 500)

        # ── SaaS: Backup status ───────────────────────────────────────────────
        elif path == '/api/admin/backup/status':
            if self.require_role('ADMIN'):
                import os as _os
                _last_bk_file = _os.path.join(
                    _os.path.dirname(_os.path.abspath(__file__)), 'logs', 'last_backup.txt'
                )
                last_backup = None
                if _os.path.exists(_last_bk_file):
                    try:
                        with open(_last_bk_file, encoding='utf-8') as _f:
                            last_backup = _f.read().strip()
                    except Exception:
                        pass
                backup_dir = _os.path.join(
                    _os.path.dirname(_os.path.abspath(__file__)), 'backups'
                )
                backup_count = 0
                try:
                    for _root, _dirs, _files in _os.walk(backup_dir):
                        backup_count += len([x for x in _files if x.endswith('.sql.gz')])
                except Exception:
                    pass
                self.send_json({
                    'last_backup':    last_backup,
                    'backup_count':   backup_count,
                    'backup_enabled': _SAAS_BACKUP,
                    'backup_dir':     backup_dir,
                })

        # ── SaaS: Security logs ───────────────────────────────────────────────
        elif path == '/api/admin/security-logs':
            if self.require_role('ADMIN'):
                import os as _os
                _sec_log_path = _os.path.join(
                    _os.path.dirname(_os.path.abspath(__file__)), 'logs', 'security.log'
                )
                lines = []
                try:
                    if _os.path.exists(_sec_log_path):
                        with open(_sec_log_path, encoding='utf-8') as _f:
                            lines = _f.readlines()[-200:]  # last 200 lines
                except Exception:
                    pass
                self.send_json({'lines': [l.strip() for l in lines], 'count': len(lines)})

        # ══════════════════════════════════════════════════════════════════════
        # HMS v4 — GET ROUTES
        # ══════════════════════════════════════════════════════════════════════

        # ── 1. Patient Registration Module ───────────────────────────────────
        elif path.startswith('/api/patients/search'):
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                from urllib.parse import parse_qs, urlparse as _up
                qs    = parse_qs(_up(self.path).query)
                phone = qs.get('phone', [''])[0].strip()
                name  = qs.get('name',  [''])[0].strip()
                if phone:
                    results = _hms.search_patient_by_phone(phone)
                elif name and _DB_AVAILABLE:
                    import psycopg2.extras as _px
                    with hospital_db.get_conn() as _c:
                        _cur = _c.cursor(cursor_factory=_px.RealDictCursor)
                        _cur.execute(
                            "SELECT id AS patient_id, full_name, phone, gender, "
                            "blood_group, TO_CHAR(created_at,'YYYY-MM-DD') AS registered_on "
                            "FROM patients WHERE full_name ILIKE %s ORDER BY full_name LIMIT 20",
                            (f"%{name}%",))
                        results = [dict(r) for r in _cur.fetchall()]
                else:
                    results = []
                self.send_json({'patients': results, 'count': len(results)})

        elif path.startswith('/api/patients/') and path.endswith('/history'):
            if self.require_role('ADMIN', 'DOCTOR', 'NURSE', 'RECEPTION'):
                try:
                    patient_id = int(path.split('/')[3])
                    data_out   = _hms.get_patient_history(patient_id)
                    self.send_json(data_out)
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid patient_id'}, 400)

        # ── 2. Billing Module ─────────────────────────────────────────────────
        elif path.startswith('/api/billing/invoice/'):
            if self.require_role('ADMIN', 'RECEPTION'):
                try:
                    inv_id  = int(path.split('/')[-1])
                    invoice = _hms.get_invoice(inv_id)
                    if invoice:
                        self.send_json({'invoice': invoice})
                    else:
                        self.send_json({'error': 'Invoice not found'}, 404)
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid invoice_id'}, 400)

        elif path == '/api/billing/reports/daily':
            if self.require_role('ADMIN', 'RECEPTION'):
                from urllib.parse import parse_qs, urlparse as _up
                qs   = parse_qs(_up(self.path).query)
                tgt  = qs.get('date', [None])[0]
                data_out = _hms.get_daily_revenue_report(target_date=tgt)
                self.send_json(data_out)

        # ── 3. Doctor Workflow ────────────────────────────────────────────────
        elif path == '/api/doctor/patient-queue':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN', 'NURSE', 'RECEPTION'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                dname = user.get('full_name', '') if user['role'] == 'DOCTOR' else ''
                duname = user.get('username', '') if user['role'] == 'DOCTOR' else ''
                queue  = _hms.get_doctor_patient_queue(duname, dname)
                self.send_json({'queue': queue, 'count': len(queue)})

        elif path.startswith('/api/doctor/patient/'):
            if self.require_role('DOCTOR', 'ADMIN', 'NURSE'):
                try:
                    patient_id = int(path.split('/')[-1])
                    data_out   = _hms.get_patient_history(patient_id)
                    self.send_json(data_out)
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid patient_id'}, 400)

        # ── 4. Pharmacy Module ────────────────────────────────────────────────
        elif path == '/api/pharmacy/stock':
            if self.require_role('ADMIN', 'STOCK', 'DOCTOR', 'NURSE', 'RECEPTION'):
                stock = _hms.get_pharmacy_stock_list()
                self.send_json({'stock': stock, 'count': len(stock)})

        elif path == '/api/pharmacy/alerts':
            if self.require_role('ADMIN', 'STOCK'):
                alerts = _hms.get_pharmacy_alerts()
                self.send_json(alerts)

        # ── 5. Lab Module ─────────────────────────────────────────────────────
        elif path.startswith('/api/lab/report/'):
            if self.require_role('ADMIN', 'LAB', 'DOCTOR', 'NURSE'):
                try:
                    patient_id = int(path.split('/')[-1])
                    reports    = _hms.get_patient_lab_reports(patient_id)
                    self.send_json({'reports': reports, 'count': len(reports)})
                except (ValueError, IndexError):
                    self.send_json({'error': 'Invalid patient_id'}, 400)

        # ── 6. Owner Analytics Dashboard ──────────────────────────────────────
        elif path == '/api/admin/analytics/patients':
            if self.require_role('ADMIN'):
                from urllib.parse import parse_qs, urlparse as _up
                qs     = parse_qs(_up(self.path).query)
                period = qs.get('period', qs.get('range', ['daily']))[0]
                data_out = _hms.get_analytics_patients(period=period)
                self.send_json(data_out)

        # ── 7. Mobile-Ready Dashboard ─────────────────────────────────────────
        elif path == '/api/admin/mobile-dashboard':
            if self.require_role('ADMIN'):
                data_out = _hms.get_mobile_dashboard()
                self.send_json(data_out)

        # ── Appointments (Reception Module) ───────────────────────────────────
        elif path == '/api/appointments/list':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                if _DB_AVAILABLE:
                    appts = hospital_db.get_all_registrations(200)
                    self.send_json({'appointments': appts, 'count': len(appts)})
                else:
                    self.send_json({'appointments': [], 'count': 0})

        elif path == '/api/health' or path == '/api/health/':
            self.send_json({
                'status':      'ok',
                'timestamp':   time.time(),
                'db':          _DB_AVAILABLE,
                'hms_modules': _HMS_AVAILABLE,
                'version':     '4.0',
            })

        # ── Founder platform-level API endpoints ──────────────────────────────
        elif path == '/api/founder/clients':
            self._handle_founder_clients()

        elif path.startswith('/api/founder/client/'):
            slug = path.split('/')[-1]
            if slug:
                self._handle_founder_client_detail(slug)
            else:
                self.send_json({'error': 'Missing client slug'}, 400)

        elif path == '/api/founder/db-isolation-test':
            self._handle_founder_db_isolation_test()

        elif path == '/api/founder/all-users':
            self._handle_founder_all_users()

        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>404 Not Found</h1>')

    # ── Founder platform handlers ──────────────────────────────────────────────
    def _handle_founder_clients(self):
        """GET /api/founder/clients — list all registered tenants with DB status."""
        user = self.get_session_user()
        if not user or user['role'] not in ('FOUNDER', 'ADMIN'):
            self.send_json({'error': 'Forbidden — FOUNDER role required'}, 403)
            return
        import json as _json
        import os as _os
        reg_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tenant_registry.json')
        try:
            with open(reg_file, encoding='utf-8') as f:
                registry = _json.load(f)
        except Exception:
            registry = {}
        clients_out = []
        for slug, info in registry.items():
            db_name = info.get('db_name', '')
            db_ok = False
            user_count = 0
            try:
                import psycopg2 as _pg
                conn = _pg.connect(host=info.get('db_host','localhost'),
                                   port=info.get('db_port', 5434),
                                   dbname=db_name,
                                   user=info.get('db_user','ats_user'),
                                   password='ats_password')
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM staff_users')
                user_count = cur.fetchone()[0]
                cur.close(); conn.close()
                db_ok = True
            except Exception:
                pass
            clients_out.append({
                'slug':         slug,
                'display_name': info.get('display_name', slug),
                'city':         info.get('city', ''),
                'phone':        info.get('phone', ''),
                'db_name':      db_name,
                'db_status':    'connected' if db_ok else 'unreachable',
                'staff_count':  user_count,
                'admin_user':   info.get('admin_user', ''),
                'created_at':   info.get('created_at', ''),
            })
        self.send_json({'clients': clients_out, 'total': len(clients_out)})

    def _handle_founder_client_detail(self, slug: str):
        """GET /api/founder/client/{slug} — detail for one tenant."""
        user = self.get_session_user()
        if not user or user['role'] not in ('FOUNDER', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        import json as _json, os as _os
        reg_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tenant_registry.json')
        try:
            with open(reg_file, encoding='utf-8') as f:
                registry = _json.load(f)
        except Exception:
            registry = {}
        info = registry.get(slug)
        if not info:
            self.send_json({'error': f'Client {slug!r} not found'}, 404)
            return
        db_name = info.get('db_name', '')
        staff = []
        tables = []
        try:
            import psycopg2 as _pg
            import psycopg2.extras as _pge
            conn = _pg.connect(host=info.get('db_host','localhost'),
                               port=info.get('db_port', 5434),
                               dbname=db_name,
                               user=info.get('db_user','ats_user'),
                               password='ats_password')
            cur = conn.cursor(cursor_factory=_pge.RealDictCursor)
            cur.execute('SELECT id, username, role, full_name, department, is_active, created_at FROM staff_users ORDER BY role, username')
            staff = [dict(r) for r in cur.fetchall()]
            # Remove password_hash from output
            for s in staff:
                s.pop('password_hash', None)
                if 'created_at' in s and s['created_at']:
                    s['created_at'] = str(s['created_at'])
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            tables = [r['tablename'] for r in cur.fetchall()]
            cur.close(); conn.close()
        except Exception as e:
            pass
        self.send_json({
            'slug':        slug,
            'info':        info,
            'staff_users': staff,
            'tables':      tables,
            'total_staff': len(staff),
        })

    def _handle_founder_db_isolation_test(self):
        """GET /api/founder/db-isolation-test
        Verifies that each client DB is independent:
        - Checks each tenant DB has its OWN staff_users table
        - Verifies client 1 data is NOT visible in client 2
        """
        user = self.get_session_user()
        if not user or user['role'] not in ('FOUNDER', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        import json as _json, os as _os
        reg_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tenant_registry.json')
        try:
            with open(reg_file, encoding='utf-8') as f:
                registry = _json.load(f)
        except Exception:
            registry = {}
        results = []
        for slug, info in registry.items():
            db_name = info.get('db_name', '')
            test = {'slug': slug, 'db_name': db_name, 'isolated': False, 'details': ''}
            try:
                import psycopg2 as _pg
                conn = _pg.connect(host=info.get('db_host','localhost'),
                                   port=info.get('db_port', 5434),
                                   dbname=db_name,
                                   user=info.get('db_user','ats_user'),
                                   password='ats_password')
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM staff_users')
                cnt = cur.fetchone()[0]
                cur.execute('SELECT username FROM staff_users ORDER BY id LIMIT 5')
                sample = [r[0] for r in cur.fetchall()]
                # Isolation check: no OTHER tenant's usernames should be in this DB
                other_slugs = [s for s in registry if s != slug]
                leaked = []
                for other in other_slugs:
                    cur.execute('SELECT COUNT(*) FROM staff_users WHERE username LIKE %s',
                                (f'{other}_%',))
                    if cur.fetchone()[0] > 0:
                        leaked.append(other)
                cur.close(); conn.close()
                test['isolated'] = len(leaked) == 0
                test['staff_count'] = cnt
                test['sample_users'] = sample
                test['leaked_from'] = leaked
                test['details'] = ('PASS: no cross-tenant data found' if not leaked
                                   else f'FAIL: leaked data from {leaked}')
            except Exception as e:
                test['details'] = f'DB unreachable: {e}'
            results.append(test)
        # Cross-isolation: check no slug_A username exists in slug_B DB
        slugs = list(registry.keys())
        cross_checks = []
        if len(slugs) >= 2:
            for i, slug_a in enumerate(slugs):
                for slug_b in slugs[i+1:]:
                    info_b = registry[slug_b]
                    try:
                        import psycopg2 as _pg
                        conn = _pg.connect(host=info_b.get('db_host','localhost'),
                                           port=info_b.get('db_port', 5434),
                                           dbname=info_b.get('db_name',''),
                                           user=info_b.get('db_user','ats_user'),
                                           password='ats_password')
                        cur = conn.cursor()
                        cur.execute('SELECT COUNT(*) FROM staff_users WHERE username LIKE %s',
                                    (f'{slug_a}%',))
                        leak_count = cur.fetchone()[0]
                        cur.close(); conn.close()
                        cross_checks.append({
                            'check': f'{slug_a} users visible in {slug_b} DB',
                            'leaked': leak_count,
                            'result': 'PASS (no leak)' if leak_count == 0 else f'FAIL: {leak_count} leaked rows',
                        })
                    except Exception as e:
                        cross_checks.append({'check': f'{slug_a}/{slug_b}', 'result': f'error: {e}'})
        self.send_json({
            'isolation_test': results,
            'cross_db_checks': cross_checks,
            'verdict': 'ISOLATED' if all(r.get('isolated', False) for r in results) else 'NEEDS_REVIEW',
        })

    def _handle_founder_all_users(self):
        """GET /api/founder/all-users — lists all staff across all tenant DBs."""
        user = self.get_session_user()
        if not user or user['role'] not in ('FOUNDER', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        import json as _json, os as _os
        reg_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tenant_registry.json')
        try:
            with open(reg_file, encoding='utf-8') as f:
                registry = _json.load(f)
        except Exception:
            registry = {}
        all_users = []
        for slug, info in registry.items():
            try:
                import psycopg2 as _pg
                conn = _pg.connect(host=info.get('db_host','localhost'),
                                   port=info.get('db_port', 5434),
                                   dbname=info.get('db_name',''),
                                   user=info.get('db_user','ats_user'),
                                   password='ats_password')
                cur = conn.cursor()
                cur.execute('SELECT username, role, full_name, is_active FROM staff_users ORDER BY role')
                for row in cur.fetchall():
                    all_users.append({
                        'client': info.get('display_name', slug),
                        'slug': slug,
                        'username': row[0],
                        'role': row[1],
                        'full_name': row[2],
                        'is_active': row[3],
                    })
                cur.close(); conn.close()
            except Exception:
                pass
        self.send_json({'users': all_users, 'total': len(all_users)})

    # ── Founder system-status handler ─────────────────────────────────────────
    def _handle_founder_system_status(self):
        """
        GET /api/founder/system-status
        ══════════════════════════════
        Returns platform-level system health for the founder dashboard.

        DATA SOURCE: platform_db ONLY — never queries tenant patient data.

        Response schema:
          server_status, total_hospitals, active_hospitals, alerts,
          client_activity_summary, billing_summary, last_backup,
          database_health, modules, timestamp
        """
        if not self.require_role('FOUNDER', 'ADMIN'):
            return

        import os as _os
        from datetime import datetime as _dt

        # ── 1. Load data exclusively from platform_db ─────────────────────────
        _platform_ok = False
        _metrics     = {
            "total_hospitals": 0, "active_hospitals": 0,
            "trial_hospitals": 0, "expired_hospitals": 0,
            "suspended_hospitals": 0, "open_alerts": 0,
        }
        _clients        = []
        _recent_alerts  = []
        _client_health  = []

        try:
            from platform_db import (
                get_platform_metrics,
                get_all_clients,
                get_recent_alerts,
                test_platform_connection,
                check_all_tenants_health,
            )
            _platform_ok = test_platform_connection()
            if _platform_ok:
                _metrics        = get_platform_metrics()
                _clients        = get_all_clients()
                _recent_alerts  = get_recent_alerts(limit=10)
                # Run live health checks against each tenant DB
                # (reads only table names and activity timestamps — no patient data)
                _client_health  = check_all_tenants_health()
        except Exception as _pex:
            _sys_log.error(f"[system-status] platform_db unavailable: {_pex}")

        # ── 2. Billing summary (from saas_billing, no patient data) ───────────
        billing_summary = {
            'total': 0, 'trial': 0, 'paid': 0,
            'expired': 0, 'suspended': 0,
        }
        if _SAAS_BILLING:
            try:
                for acct in _list_billing_accounts():
                    status = (acct.get('payment_status') or 'unknown').lower()
                    billing_summary['total'] += 1
                    billing_summary[status] = billing_summary.get(status, 0) + 1
            except Exception:
                pass

        # ── 3. Worker threads ─────────────────────────────────────────────────
        num_workers = 1
        try:
            import psutil as _psutil
            num_workers = _psutil.Process(_os.getpid()).num_threads()
        except Exception:
            pass

        # ── 4. Last backup timestamp ──────────────────────────────────────────
        last_backup = None
        _backup_log = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), 'logs', 'last_backup.txt'
        )
        if _os.path.exists(_backup_log):
            try:
                with open(_backup_log, encoding='utf-8') as _bf:
                    last_backup = _bf.read().strip()
            except Exception:
                pass

        # ── 5. Safe client_activity_summary (no patient fields) ──────────────
        safe_client_summary = [
            {
                'hospital_name':  ch.get('hospital_name', 'Unknown'),
                'slug':           ch.get('slug', ''),
                'city':           ch.get('city', ''),
                'db_status':      ch.get('db_status', 'unknown'),
                'tables_present': ch.get('tables_present', False),
                'missing_tables': ch.get('missing_tables', []),
                'last_activity':  ch.get('last_activity'),
                'system_health':  'ok' if ch.get('db_status') == 'connected' else 'degraded',
            }
            for ch in _client_health
        ]

        # Fallback: use clients list if health check returned nothing
        if not safe_client_summary:
            safe_client_summary = [
                {
                    'hospital_name': c.get('hospital_name', 'Unknown'),
                    'slug':          c.get('slug', ''),
                    'city':          c.get('city', ''),
                    'db_status':     'unknown',
                    'tables_present': False,
                    'missing_tables': [],
                    'last_activity':  str(c.get('last_activity') or ''),
                    'system_health':  'unknown',
                }
                for c in _clients
            ]

        # ── 6. Alert text list (from platform_db, no patient data) ────────────
        alert_texts = [
            f"[{a.get('severity','info').upper()}] {a.get('event_type','')}: {a.get('message','')}"
            for a in _recent_alerts
        ]

        self.send_json({
            # ── Top-level metrics (required by frontend + test suite) ─────────
            'server_status':    'running',
            'total_hospitals':  _metrics.get('total_hospitals', len(_clients)),
            'active_hospitals': _metrics.get('active_hospitals', 0),
            'alerts':           _metrics.get('open_alerts', len(_recent_alerts)),
            # ── Per-client health (no patient data) ───────────────────────────
            'active_clients':          len(_clients),
            'client_activity_summary': safe_client_summary,
            'databases': [
                c.get('db_name', '') for c in _clients if c.get('db_name')
            ],
            # ── Platform connectivity ─────────────────────────────────────────
            'platform_db': {
                'status':    'connected' if _platform_ok else 'unreachable',
                'db_name':   _os.getenv('PLATFORM_DB_NAME', 'srp_platform_db'),
            },
            'database_health': {
                'reachable':       _platform_ok,
                'status':          'connected' if _platform_ok else 'unreachable',
                'total_tenants':   _metrics.get('total_hospitals', 0),
                'healthy_tenants': sum(
                    1 for ch in _client_health if ch.get('db_status') == 'connected'
                ),
            },
            # ── Billing (aggregate counts only, no patient data) ──────────────
            'billing_summary':      billing_summary,
            # ── System alerts (from platform_db, no patient data) ─────────────
            'recent_system_alerts': alert_texts,
            # ── Operational ──────────────────────────────────────────────────
            'worker_processes': num_workers,
            'last_backup':      last_backup,
            'modules': {
                'billing':    _SAAS_BILLING,
                'export':     _SAAS_EXPORT,
                'analytics':  _SAAS_ANALYTICS,
                'backup':     _SAAS_BACKUP,
                'onboarding': _SAAS_ONBOARDING,
                'logging':    _SAAS_LOGGING,
            },
            'timestamp': _dt.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        })

    def do_POST(self):
        # Subdomain / tenant detection
        self._detect_tenant_subdomain()
        # Apply per-user tenant DB routing (thread-local, affects all hospital_db.* calls)
        try:
            _req_user = self.get_session_user()
            if _req_user and _req_user.get('tenant_slug'):
                hospital_db.set_request_tenant(_req_user['tenant_slug'])
        except Exception:
            pass
        # Rate limiting
        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_json({'error': 'Too many requests — slow down'}, 429)
            return
        path = urlparse(self.path).path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            data = sanitize_dict(data)   # scrub HTML/SQL injection from all string values
        except:
            data = {}
        
        if path == '/api/chat':
            self.handle_chat(data)
        elif path == '/api/register':
            self.handle_register(data)
        elif path == '/api/transcribe':
            self.handle_transcribe(data)
        elif path == '/api/admin/attendance':
            if self.require_role('ADMIN', 'RECEPTION'):
                self.handle_attendance(data)
        elif path == '/api/admin/appointments':
            if self.require_role('ADMIN', 'RECEPTION'):
                self.handle_admin_appointments(data)
        elif path == '/api/admin/doctor/checkin':
            if self.require_role('ADMIN', 'RECEPTION'):
                self.handle_doctor_checkin(data)
        elif path == '/api/admin/doctor/checkout':
            if self.require_role('ADMIN', 'RECEPTION'):
                self.handle_doctor_checkout(data)
        elif path == '/api/admin/doctors/reset-duty':
            # Reset ALL doctors to off-duty (clears stale on_duty flags)
            if self.require_role('ADMIN'):
                if _DB_AVAILABLE:
                    try:
                        with hospital_db.get_conn() as _conn:
                            with _conn.cursor() as _cur:
                                _cur.execute("UPDATE doctors SET on_duty=FALSE, status='off_duty'")
                                count = _cur.rowcount
                        self.send_json({'status': 'ok',
                                        'message': f'Reset {count} doctors to off-duty.'})
                    except Exception as _e:
                        self.send_json({'error': str(_e)}, 500)
                else:
                    self.send_json({'status': 'ok', 'message': 'Reset done (file mode)'})
        elif path == '/api/admin/rounds/add':
            if self.require_role('ADMIN', 'DOCTOR'):
                self.handle_add_round(data)
        elif path == '/api/admin/rounds/complete':
            if self.require_role('ADMIN', 'DOCTOR'):
                self.handle_complete_round(data)
        elif path == '/api/login':
            self.handle_login(data)
        elif path == '/api/change-password':
            self.handle_change_password(data)
        elif path == '/api/logout':
            self.handle_logout()
        elif path == '/api/staff/create':
            self.handle_create_staff(data)
        elif path == '/api/staff/delete':
            self.handle_delete_staff(data)
        elif path == '/api/stock/add':
            self.handle_stock_add(data)
        elif path == '/api/stock/update':
            self.handle_stock_update(data)
        elif path == '/api/doctor/prescription':
            self._handle_hms_prescription(data)  # unified: structured + legacy
        elif path == '/api/doctor/lab/request':
            self.handle_lab_request(data)
        elif path == '/api/nurse/vitals/add':
            self.handle_add_vitals(data)
        elif path == '/api/lab/complete':
            self.handle_complete_lab(data)
        elif path == '/api/doctor/visit/add':
            self.handle_add_visit_record(data)
        elif path == '/api/nurse/assign':
            self.handle_nurse_assign(data)
        elif path == '/api/admin/billing/create':
            self.handle_billing_create(data)
        # ── SRP MediFlow Phase-2 POST routes ─────────────────────────────────
        elif path == '/api/ipd/admit':
            self.handle_ipd_admit(data)
        elif path == '/api/ipd/round/add':
            self.handle_ipd_round_add(data)
        elif path == '/api/ipd/discharge':
            self.handle_ipd_discharge(data)
        elif path == '/api/surgery/create':
            self.handle_surgery_create(data)
        elif path == '/api/surgery/update-cost':
            self.handle_surgery_update_cost(data)
        elif path == '/api/pharmacy/add-stock':
            self.handle_pharmacy_add_stock(data)
        elif path == '/api/pharmacy/sell':
            self.handle_pharmacy_sell(data)
        elif path == '/api/billing/add-item':
            self.handle_billing_add_item(data)
        elif path == '/api/billing/ipd/create':
            self.handle_billing_ipd_create(data)
        elif path == '/api/billing/payment':
            self.handle_billing_payment(data)
        elif path == '/api/procedures/add':
            self.handle_procedure_add(data)

        # ── WhatsApp webhook (inbound messages from Meta) ───────────────────────
        elif path == '/api/whatsapp/webhook':
            raw_body = body  # already read above
            sig = self.headers.get('X-Hub-Signature-256', '')
            if not verify_webhook_signature(raw_body, sig):
                self.send_json({'error': 'Invalid signature'}, 403)
                return
            messages = parse_inbound_payload(data)
            replies  = []
            for msg in messages:
                result = wa_receive_message(msg['phone'], msg['text'])
                reply_text = result.get('reply', '')
                if reply_text:
                    wa_send_message(msg['phone'], reply_text)
                # Notify hospital staff via Telegram
                try:
                    from telegram_bot import notify_whatsapp_inquiry
                    notify_whatsapp_inquiry(msg['phone'], msg['text'], reply_text)
                except Exception:
                    pass
                replies.append({'phone': msg['phone'], 'sent': reply_text[:50]})
            self.send_json({'status': 'ok', 'processed': len(messages), 'replies': replies})

        # ── Telegram: manual notification send ──────────────────────────────────
        elif path == '/api/telegram/send':
            user = self.get_session_user()
            if not user or user['role'] not in ('ADMIN',):
                self.send_json({'error': 'Forbidden'}, 403)
                return
            try:
                from telegram_bot import send_telegram_message
                msg_text = data.get('message', '').strip()
                if not msg_text:
                    self.send_json({'error': 'message required'}, 400)
                    return
                result = send_telegram_message(msg_text)
                self.send_json(result)
            except ImportError:
                self.send_json({'error': 'Telegram module not available'}, 503)

        # ── SRP MediFlow Multi-Client Management (ADMIN only) ──────────────────
        elif path == '/api/admin/create-client':
            if not self.require_role('ADMIN'):
                return
            hospital_name = data.get('hospital_name', '').strip()
            subdomain     = data.get('subdomain', '').strip().lower()
            if not hospital_name or not subdomain:
                self.send_json({'error': 'hospital_name and subdomain are required'}, 400)
                return
            import re as _re
            slug    = _re.sub(r'[^a-z0-9_]', '_', subdomain)[:60]
            db_name = f'srp_{slug}_db'
            admin_username = data.get('admin_username', 'admin')
            admin_password = data.get('admin_password', 'hospital2024')
            phone   = data.get('phone', '')
            address = data.get('address', '')
            city    = data.get('city', '')
            state   = data.get('state', '')
            country = data.get('country', 'India')
            try:
                # 1. Create tenant database + schema + default admin account
                if _TENANT_AVAILABLE:
                    tenant_result = _create_tenant_db(
                        slug=slug,
                        display_name=hospital_name,
                        city=city,
                        phone=phone,
                        admin_username=admin_username,
                        admin_password=admin_password,
                    )
                else:
                    tenant_result = {'note': 'tenant module not available — DB not created'}
                # 2. Register client in master clients table
                client_row = None
                if _DB_AVAILABLE:
                    client_row = hospital_db.create_client_record(
                        slug=slug,
                        hospital_name=hospital_name,
                        hospital_phone=phone,
                        hospital_address=address,
                        city=city,
                        state=state,
                        country=country,
                        database_name=db_name,
                    )
                self.send_json({
                    'status':        'created',
                    'slug':          slug,
                    'database':      db_name,
                    'client':        client_row,
                    'tenant_result': tenant_result,
                    'login_url':     f'http://{subdomain}.srpmediflow.com/login',
                    'admin_user':    admin_username,
                })
                # Notify the FOUNDER only (platform-level event).
                # Each hospital's Telegram bot belongs to THAT hospital only —
                # never fire client-creation alerts through a hospital channel.
                # Notify founder via the platform-level alert channel.
                send_founder_alert(
                    "NEW_CLIENT_REGISTERED",
                    f"New hospital onboarded!\n"
                    f"Hospital: {hospital_name}\n"
                    f"Slug: {slug}\n"
                    f"Database: {db_name}\n"
                    f"Location: {city}, {state}"
                )
            except Exception as _ce:
                self.send_json({'error': str(_ce)}, 500)

        # ── SaaS: Automated hospital onboarding (enhanced register-client) ────
        elif path == '/api/admin/register-client':
            if not self.require_role('ADMIN'):
                return
            if not _SAAS_ONBOARDING:
                self.send_json({'error': 'Onboarding module unavailable'}, 503)
                return
            result = _onboard_hospital(data)
            code   = 201 if result.get('status') == 'success' else 400
            self.send_json(result, code)

        # ── SaaS: Billing management ──────────────────────────────────────────
        elif path == '/api/admin/billing/update':
            if not self.require_role('ADMIN'):
                return
            client_id      = data.get('client_id')
            payment_status = data.get('payment_status', '').strip()
            if not client_id or not payment_status:
                self.send_json({'error': 'client_id and payment_status required'}, 400)
                return
            if payment_status not in ('trial', 'paid', 'expired', 'suspended'):
                self.send_json({'error': 'payment_status must be trial|paid|expired|suspended'}, 400)
                return
            ok = _update_billing_status(
                client_id=int(client_id),
                payment_status=payment_status,
                next_payment_date=data.get('next_payment_date'),
                plan_name=data.get('plan_name'),
            ) if _SAAS_BILLING else False
            if ok:
                _sys_log.info(
                    f"Billing updated: client_id={client_id} status={payment_status} "
                    f"by={self.get_session_user().get('username','?') if self.get_session_user() else '?'}"
                )
            self.send_json({'status': 'ok' if ok else 'error'})

        elif path == '/api/admin/billing/flag-expired':
            if not self.require_role('ADMIN'):
                return
            flagged = _flag_expired_accounts() if _SAAS_BILLING else []
            self.send_json({'flagged': flagged, 'count': len(flagged)})

        # ── SaaS: Manual backup trigger ───────────────────────────────────────
        elif path == '/api/admin/backup/trigger':
            if not self.require_role('ADMIN'):
                return
            if not _SAAS_BACKUP:
                self.send_json({'error': 'Backup module unavailable'}, 503)
                return
            # Run backup in a background thread so HTTP response returns immediately
            def _run_bk():
                from saas_backup import run_backup_now
                run_backup_now()
            threading.Thread(target=_run_bk, daemon=True, name="ManualBackup").start()
            self.send_json({'status': 'started',
                            'message': 'Backup started in background — check /api/admin/backup/status'})

        # ── SaaS: Subdomain lookup ────────────────────────────────────────────
        elif path == '/api/admin/subdomain/lookup':
            if not self.require_role('ADMIN'):
                return
            subdomain = data.get('subdomain', '').strip().lower()
            if not subdomain:
                self.send_json({'error': 'subdomain required'}, 400)
                return
            clients_list = hospital_db.get_clients_registry() if _DB_AVAILABLE else []
            match = next((c for c in clients_list if c.get('slug') == subdomain or
                          c.get('subdomain') == subdomain), None)
            self.send_json({'found': match is not None, 'client': match})

        # ══════════════════════════════════════════════════════════════════════
        # HMS v4 — POST ROUTES
        # ══════════════════════════════════════════════════════════════════════

        # ── 1. Patient Registration ───────────────────────────────────────────
        elif path == '/api/patients/register':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                user = self.get_session_user()
                data['created_by'] = user.get('username', 'reception') if user else 'reception'
                result = _hms.register_patient(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    _sys_log.info(
                        f"PATIENT_REGISTERED: {result.get('full_name','')} "
                        f"ticket={result.get('op_ticket_no','')} "
                        f"by={data.get('created_by','')}"
                    )
                    self.send_json(result, 201)

        # ── 2. Billing ────────────────────────────────────────────────────────
        elif path == '/api/billing/create':
            if self.require_role('ADMIN', 'RECEPTION'):
                user = self.get_session_user()
                data['created_by'] = user.get('username', 'reception') if user else 'reception'
                result = _hms.create_invoice(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    _sys_log.info(
                        f"INVOICE_CREATED: bill_id={result.get('bill_id')} "
                        f"patient={result.get('patient_name','')} "
                        f"amount={result.get('net_amount',0)} "
                        f"by={data.get('created_by','')}"
                    )
                    self.send_json(result, 201)

        # ── 3. Doctor Note & Prescription ────────────────────────────────────
        elif path == '/api/doctor/note':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN', 'NURSE'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                data['doctor_username'] = user.get('username', '')
                data['doctor_name']     = user.get('full_name', '')
                result = _hms.add_doctor_note(data)
                self.send_json(result, 201 if 'note_id' in result else 400)

        # ── 4. Pharmacy Sale ──────────────────────────────────────────────────
        elif path == '/api/pharmacy/sale':
            if self.require_role('ADMIN', 'STOCK', 'RECEPTION'):
                user = self.get_session_user()
                data['staff_username'] = user.get('username', 'pharmacy') if user else 'pharmacy'
                result = _hms.record_pharmacy_sale(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    _sys_log.info(
                        f"PHARMACY_SALE: sale_id={result.get('sale_id')} "
                        f"patient={result.get('patient_name','')} "
                        f"amount={result.get('net_amount',0)}"
                    )
                    self.send_json(result, 201)

        # ── 5. Lab Module ─────────────────────────────────────────────────────
        elif path == '/api/lab/order':
            user = self.get_session_user()
            if not user:
                self.send_json({'error': 'Authentication required'}, 401)
            elif user['role'] not in ('DOCTOR', 'ADMIN', 'NURSE'):
                self.send_json({'error': 'Forbidden'}, 403)
            else:
                data['doctor_username'] = user.get('username', '')
                result = _hms.order_lab_test(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    self.send_json(result, 201)

        elif path == '/api/lab/result':
            if self.require_role('LAB', 'XRAY', 'ADMIN'):
                user = self.get_session_user()
                data['lab_username'] = user.get('username', 'lab') if user else 'lab'
                result = _hms.record_lab_result(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    _sys_log.info(
                        f"LAB_RESULT: result_id={result.get('result_id')} "
                        f"test={result.get('test_name','')} "
                        f"abnormal={result.get('is_abnormal',False)}"
                    )
                    self.send_json(result, 201)

        # ── Appointment Scheduling (Reception) ────────────────────────────────
        elif path == '/api/appointments/create':
            if self.require_role('ADMIN', 'RECEPTION', 'DOCTOR', 'NURSE'):
                user = self.get_session_user()
                data['source'] = f"reception:{user.get('username','?')}" if user else 'reception'
                result = _hms.create_appointment(data)
                if 'error' in result:
                    self.send_json(result, 400)
                else:
                    self.send_json(result, 201)

        else:
            self.send_json({'error': 'Not found'}, 404)

    # ── HMS: Prescription handler (structured + legacy) ───────────────────────
    def _handle_hms_prescription(self, data: dict):
        """Handle POST /api/doctor/prescription — supports both structured
        medicines_list and the legacy plain-text medicines field."""
        user = self.get_session_user()
        if not user:
            self.send_json({'error': 'Authentication required'}, 401)
            return
        if user['role'] not in ('DOCTOR', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        data['doctor_username'] = user.get('username', '')
        data['doctor_name']     = user.get('full_name', '')

        if data.get('medicines_list'):
            # New structured path via hms_db
            result = _hms.add_structured_prescription(data)
            code   = 201 if 'prescription_id' in result else 400
        else:
            # Legacy path (existing handler)
            if not _DB_AVAILABLE:
                self.send_json({'error': 'DB unavailable'}, 503)
                return
            presc_id = hospital_db.add_prescription(
                patient_name    = data.get('patient_name', ''),
                patient_phone   = data.get('patient_phone', ''),
                doctor_username = data.get('doctor_username', ''),
                doctor_name     = data.get('doctor_name', ''),
                diagnosis       = data.get('diagnosis', ''),
                medicines       = data.get('medicines', ''),
                notes           = data.get('notes', ''),
            )
            result = {'prescription_id': presc_id, 'status': 'saved'}
            code   = 201 if presc_id else 500

        _sys_log.info(
            f"PRESCRIPTION: id={result.get('prescription_id')} "
            f"patient={data.get('patient_name','')} "
            f"doctor={data.get('doctor_name','')}"
        )
        self.send_json(result, code)

    def serve_file(self, filename, content_type):
        try:
            file_path = os.path.join(BASE_DIR, filename)
            with open(file_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
    
    # ── Auth helpers ────────────────────────────────────────────────────────────

    def get_session_user(self) -> dict | None:
        """Return session user dict if the request has a valid auth cookie, else None."""
        cookie_header = self.headers.get('Cookie', '')
        token = auth.extract_token(cookie_header)
        return auth.get_session(token)

    def require_role(self, *allowed_roles) -> bool:
        """
        Check that the request is authenticated and the role is in allowed_roles.
        Sends 401/403 automatically and returns False if not.
        Returns True (and does nothing) when the role is allowed.
        """
        user = self.get_session_user()
        if not user:
            self.send_json({'error': 'Authentication required'}, 401)
            return False
        if user['role'] not in allowed_roles:
            _sec_log.warning(
                f"FORBIDDEN: user={user.get('username','?')} role={user['role']} "
                f"required={allowed_roles} path={self.path} ip={self.client_address[0]}"
            )
            self.send_json({'error': 'Forbidden — insufficient permissions'}, 403)
            return False
        return True

    def _redirect_to_login(self):
        self.send_response(302)
        self.send_header('Set-Cookie', 'admin_session=; Path=/; HttpOnly; Max-Age=0')
        self.send_header('Location', '/login')
        self.end_headers()

    # ── Multi-tenant DB helper ──────────────────────────────────────────────────
    def _get_tenant_db(self):
        """Return a TenantDB proxy routing DB calls to the current user's hospital DB.
        Falls back to the default hospital_db (star_hospital / hospital_ai) when
        no session is present or TenantDB cannot be imported."""
        try:
            user = self.get_session_user()
            slug = user.get('tenant_slug', 'star_hospital') if user else 'star_hospital'
            from db import TenantDB
            return TenantDB(slug)
        except Exception:
            return hospital_db  # safe fallback

    def handle_login(self, data):
        """Authenticate staff against the CORRECT tenant DB; issue secure session cookie."""
        username    = data.get('username', '').strip()
        password    = data.get('password', '').strip()
        tenant_slug = data.get('tenant_slug', 'star_hospital').strip() or 'star_hospital'
        client_ip   = self.client_address[0]

        # Route authentication to the tenant's own database
        user_rec = None
        try:
            from db import TenantDB
            tdb      = TenantDB(tenant_slug)
            user_rec = tdb.get_staff_user_by_username(username)
        except Exception as _e:
            _sec_log.warning(f"LOGIN_DB_ERROR: tenant={tenant_slug} err={_e}")
            # Fall back to default DB only for star_hospital
            if _DB_AVAILABLE:
                user_rec = hospital_db.get_staff_user_by_username(username)

        if user_rec and auth.verify_password(password, user_rec['password_hash']):
            # ── Force password change on first login ─────────────────────────
            if user_rec.get('must_change_password', False):
                _sys_log.info(
                    f"PASSWORD_CHANGE_REQUIRED: user={username} tenant={tenant_slug} ip={client_ip}"
                )
                self.send_json({
                    'status':      'password_change_required',
                    'username':    username,
                    'tenant_slug': tenant_slug,
                    'message':     'You must change your password before continuing.',
                })
                return

            # Embed tenant_slug so every downstream API call routes to right DB
            user_rec['tenant_slug'] = tenant_slug
            token     = auth.create_session(user_rec)
            dashboard = roles.get_dashboard(user_rec['role'])

            # Fetch display name for this tenant
            try:
                import json as _j, os as _o
                _reg = _j.load(open(
                    _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'tenant_registry.json'),
                    encoding='utf-8'))
                hospital_name = _reg.get(tenant_slug, {}).get('display_name', tenant_slug)
            except Exception:
                hospital_name = tenant_slug

            # Log successful login
            _sys_log.info(f"LOGIN_SUCCESS: user={username} role={user_rec['role']} tenant={tenant_slug} ip={client_ip}")
            try:
                from db import TenantDB as _tdb
                _tdb(tenant_slug).log_action(
                    username=username,
                    role=user_rec['role'],
                    action='login_success',
                    details=f"ip={client_ip} tenant={tenant_slug}",
                    ip_address=client_ip,
                )
            except Exception:
                pass

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie',
                f'admin_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status':        'success',
                'redirect':      dashboard,
                'role':          user_rec['role'],
                'username':      user_rec['username'],
                'tenant_slug':   tenant_slug,
                'hospital_name': hospital_name,
            }).encode())
        else:
            # Security log for failed login
            _sec_log.warning(f"LOGIN_FAILED: user={username!r} tenant={tenant_slug} ip={client_ip}")
            try:
                from db import TenantDB as _tdb
                _tdb(tenant_slug).log_action(
                    username=username or 'UNKNOWN',
                    role='UNKNOWN',
                    action='login_failed',
                    details=f"ip={client_ip} tenant={tenant_slug}",
                    ip_address=client_ip,
                )
            except Exception:
                pass
            self.send_json({'status': 'error', 'message': 'Invalid username or password'}, 401)

    def handle_change_password(self, data):
        """
        POST /api/change-password
        Body: {username, tenant_slug, current_password, new_password}
        Works for both forced first-login change (no session) and
        voluntary change by an authenticated user.
        """
        username         = data.get('username', '').strip()
        tenant_slug      = data.get('tenant_slug', 'star_hospital').strip() or 'star_hospital'
        current_password = data.get('current_password', '').strip()
        new_password     = data.get('new_password', '').strip()
        client_ip        = self.client_address[0]

        if not username or not current_password or not new_password:
            self.send_json({'status': 'error', 'message': 'username, current_password and new_password are required'}, 400)
            return
        if len(new_password) < 8:
            self.send_json({'status': 'error', 'message': 'New password must be at least 8 characters'}, 400)
            return
        if current_password == new_password:
            self.send_json({'status': 'error', 'message': 'New password must differ from current password'}, 400)
            return

        # Fetch user from the correct tenant DB
        user_rec = None
        try:
            from db import TenantDB
            tdb      = TenantDB(tenant_slug)
            user_rec = tdb.get_staff_user_by_username(username)
        except Exception as _e:
            _sec_log.warning(f"CHANGE_PW_DB_ERROR: tenant={tenant_slug} err={_e}")
            if _DB_AVAILABLE:
                user_rec = hospital_db.get_staff_user_by_username(username)

        if not user_rec:
            self.send_json({'status': 'error', 'message': 'User not found'}, 404)
            return

        # Verify current password
        if not auth.verify_password(current_password, user_rec['password_hash']):
            _sec_log.warning(
                f"CHANGE_PW_FAILED: user={username!r} tenant={tenant_slug} ip={client_ip} reason=wrong_current_pw"
            )
            self.send_json({'status': 'error', 'message': 'Current password is incorrect'}, 401)
            return

        # Hash and store new password
        new_hash = auth.hash_password(new_password)
        try:
            from db import TenantDB
            ok = TenantDB(tenant_slug).update_password(username, new_hash)
        except Exception as _e:
            _sec_log.warning(f"CHANGE_PW_UPDATE_ERROR: user={username} tenant={tenant_slug} err={_e}")
            ok = False

        if not ok:
            self.send_json({'status': 'error', 'message': 'Password update failed — please try again'}, 500)
            return

        _sys_log.info(
            f"PASSWORD_CHANGED: user={username} tenant={tenant_slug} ip={client_ip}"
        )
        try:
            from db import TenantDB as _tdb
            _tdb(tenant_slug).log_action(
                username=username,
                role=user_rec.get('role', 'UNKNOWN'),
                action='password_changed',
                details=f"ip={client_ip} tenant={tenant_slug}",
                ip_address=client_ip,
            )
        except Exception:
            pass

        self.send_json({'status': 'success', 'message': 'Password updated successfully'})

    def handle_logout(self):
        """Invalidate session token and clear cookie."""
        cookie_header = self.headers.get('Cookie', '')
        token = auth.extract_token(cookie_header)
        if token:
            auth.destroy_session(token)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Set-Cookie', 'admin_session=; Path=/; HttpOnly; Max-Age=0')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'success'}).encode())

    # ── Staff management endpoints ───────────────────────────────────────────────

    def handle_create_staff(self, data):
        """ADMIN only: create a new staff user."""
        if not self.require_role('ADMIN'):
            return
        username  = data.get('username', '').strip()
        password  = data.get('password', '').strip()
        role      = data.get('role', 'RECEPTION').upper()
        dept      = data.get('department', '').strip()
        full_name = data.get('full_name', username).strip()

        if not username or not password:
            self.send_json({'error': 'username and password are required'}, 400)
            return
        if not roles.is_valid_role(role):
            self.send_json({'error': f'Invalid role: {role}'}, 400)
            return

        pwd_hash = auth.hash_password(password)
        new_id = hospital_db.create_staff_user(username, pwd_hash, role, dept, full_name) if _DB_AVAILABLE else None
        if new_id:
            self.send_json({'status': 'ok', 'id': new_id, 'username': username, 'role': role})
        else:
            self.send_json({'error': 'Could not create user (username may already exist)'}, 400)

    def handle_delete_staff(self, data):
        """ADMIN only: deactivate a staff user."""
        if not self.require_role('ADMIN'):
            return
        user_id = data.get('id')
        if not user_id:
            self.send_json({'error': 'id required'}, 400)
            return
        ok = hospital_db.delete_staff_user(int(user_id)) if _DB_AVAILABLE else False
        self.send_json({'status': 'ok' if ok else 'error'})

    # ── Stock endpoints ──────────────────────────────────────────────────────────

    def handle_stock_add(self, data):
        if not self.require_role('ADMIN', 'STOCK'):
            return
        name  = data.get('item_name', '').strip()
        cat   = data.get('category', 'Medicine').strip()
        qty   = int(data.get('quantity', 0))
        unit  = data.get('unit', 'units').strip()
        minq  = int(data.get('min_quantity', 10))
        if not name:
            self.send_json({'error': 'item_name required'}, 400)
            return
        new_id = hospital_db.add_stock_item(name, cat, qty, unit, minq) if _DB_AVAILABLE else None
        self.send_json({'status': 'ok', 'id': new_id})

    def handle_stock_update(self, data):
        if not self.require_role('ADMIN', 'STOCK'):
            return
        item_id  = data.get('id')
        quantity = data.get('quantity')
        if item_id is None or quantity is None:
            self.send_json({'error': 'id and quantity required'}, 400)
            return
        ok = hospital_db.update_stock_qty(int(item_id), int(quantity)) if _DB_AVAILABLE else False
        self.send_json({'status': 'ok' if ok else 'error'})

    # ── Doctor endpoints ─────────────────────────────────────────────────────────

    def handle_add_prescription(self, data):
        user = self.get_session_user()
        if not user or user['role'] not in ('DOCTOR',):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        new_id = hospital_db.add_prescription(
            patient_name    = data.get('patient_name', ''),
            patient_phone   = data.get('patient_phone', ''),
            doctor_username = user['username'],
            doctor_name     = user['full_name'],
            diagnosis       = data.get('diagnosis', ''),
            medicines       = data.get('medicines', ''),
            notes           = data.get('notes', ''),
        ) if _DB_AVAILABLE else None
        self.send_json({'status': 'ok', 'id': new_id})

    def handle_lab_request(self, data):
        user = self.get_session_user()
        if not user or user['role'] not in ('DOCTOR',):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        new_id = hospital_db.add_lab_order(
            patient_name    = data.get('patient_name', ''),
            patient_phone   = data.get('patient_phone', ''),
            doctor_username = user['username'],
            test_type       = data.get('test_type', 'LAB'),
            test_name       = data.get('test_name', ''),
        ) if _DB_AVAILABLE else None
        self.send_json({'status': 'ok', 'id': new_id})

    # ── Nurse endpoints ──────────────────────────────────────────────────────────

    def handle_add_vitals(self, data):
        user = self.get_session_user()
        if not user or user['role'] not in ('NURSE', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        new_id = hospital_db.add_vitals(
            patient_name   = data.get('patient_name', ''),
            patient_phone  = data.get('patient_phone', ''),
            nurse_username = user['username'],
            bp             = data.get('bp', ''),
            pulse          = data.get('pulse', ''),
            temperature    = data.get('temperature', ''),
            spo2           = data.get('spo2', ''),
            weight         = data.get('weight', ''),
            notes          = data.get('notes', ''),
        ) if _DB_AVAILABLE else None
        self.send_json({'status': 'ok', 'id': new_id})

    # ── Lab/Xray endpoints ───────────────────────────────────────────────────────

    def handle_complete_lab(self, data):
        user = self.get_session_user()
        if not user or user['role'] not in ('LAB', 'XRAY', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        order_id    = data.get('id')
        result_text = data.get('result', '')
        if not order_id:
            self.send_json({'error': 'id required'}, 400)
            return
        ok = hospital_db.complete_lab_order(int(order_id), result_text) if _DB_AVAILABLE else False
        self.send_json({'status': 'ok' if ok else 'error'})

    # ── SRP MediFlow — new HMS endpoints ─────────────────────────────────────

    def handle_add_visit_record(self, data):
        """POST /api/doctor/visit/add — create a visit record."""
        user = self.get_session_user()
        if not user or user['role'] not in ('DOCTOR', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        patient_name    = data.get('patient_name', '').strip()
        patient_phone   = data.get('patient_phone', '').strip()
        chief_complaint = data.get('chief_complaint', '').strip()
        diagnosis       = data.get('diagnosis', '').strip()
        if not patient_name or not chief_complaint or not diagnosis:
            self.send_json({'error': 'patient_name, chief_complaint, and diagnosis are required'}, 400)
            return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0, 'note': 'DB unavailable'})
            return
        new_id = hospital_db.add_visit_record(
            patient_name    = patient_name,
            patient_phone   = patient_phone,
            doctor_username = user['username'],
            doctor_name     = user.get('full_name', user['username']),
            chief_complaint = chief_complaint,
            examination     = data.get('examination', ''),
            diagnosis       = diagnosis,
            treatment_plan  = data.get('treatment_plan', ''),
            department      = data.get('department', user.get('department', '')),
        )
        if new_id:
            log_access(user, 'create_visit_record',
                       f"patient={patient_name}", self.client_address[0])
            self.send_json({'status': 'ok', 'id': new_id})
        else:
            self.send_json({'error': 'Failed to save visit record'}, 500)

    def handle_nurse_assign(self, data):
        """POST /api/nurse/assign — assign nurse to a patient."""
        user = self.get_session_user()
        if not user or user['role'] not in ('NURSE', 'ADMIN'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        patient_name = data.get('patient_name', '').strip()
        if not patient_name:
            self.send_json({'error': 'patient_name is required'}, 400)
            return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0, 'note': 'DB unavailable'})
            return
        new_id = hospital_db.add_nurse_assignment(
            nurse_username = user['username'],
            patient_name   = patient_name,
            patient_phone  = data.get('patient_phone', ''),
            ward           = data.get('ward', ''),
            bed_number     = data.get('bed_number', ''),
            shift          = data.get('shift', 'Morning'),
        )
        if new_id:
            log_access(user, 'nurse_assignment',
                       f"patient={patient_name} ward={data.get('ward','')} shift={data.get('shift','')}",
                       self.client_address[0])
            self.send_json({'status': 'ok', 'id': new_id})
        else:
            self.send_json({'error': 'Failed to save assignment'}, 500)

    def handle_billing_create(self, data):
        """POST /api/admin/billing/create — generate a new bill."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403)
            return
        patient_name = data.get('patient_name', '').strip()
        if not patient_name:
            self.send_json({'error': 'patient_name is required'}, 400)
            return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0, 'note': 'DB unavailable'})
            return
        bill_id = hospital_db.create_bill(
            patient_name      = patient_name,
            patient_phone     = data.get('patient_phone', ''),
            bill_type         = data.get('bill_type', 'OPD'),
            consultation_fee  = float(data.get('consultation_fee', 0)),
            lab_charges       = float(data.get('lab_charges', 0)),
            pharmacy_charges  = float(data.get('pharmacy_charges', 0)),
            imaging_charges   = float(data.get('imaging_charges', 0)),
            misc_charges      = float(data.get('misc_charges', 0)),
            discount          = float(data.get('discount', 0)),
            created_by        = user['username'],
        )
        if bill_id:
            log_access(user, 'create_bill',
                       f"patient={patient_name} type={data.get('bill_type','OPD')}",
                       self.client_address[0])
            self.send_json({'status': 'ok', 'id': bill_id})
        else:
            self.send_json({'error': 'Failed to create bill'}, 500)

    # ══════════════════════════════════════════════════════════════════════════
    # SRP MediFlow Phase-2 — IPD / Surgery / Pharmacy / Billing handlers
    # ══════════════════════════════════════════════════════════════════════════

    def handle_ipd_admit(self, data):
        """POST /api/ipd/admit — admit a patient (IPD)."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'RECEPTION', 'DOCTOR'):
            self.send_json({'error': 'Forbidden'}, 403); return
        patient_name = data.get('patient_name', '').strip()
        if not patient_name:
            self.send_json({'error': 'patient_name is required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0, 'note': 'DB unavailable'}); return
        adm_id = hospital_db.admit_patient(
            patient_name     = patient_name,
            patient_phone    = data.get('patient_phone', ''),
            patient_aadhar   = data.get('patient_aadhar', ''),
            age              = data.get('age', ''),
            gender           = data.get('gender', 'Unknown'),
            blood_group      = data.get('blood_group', ''),
            address          = data.get('address', ''),
            ward_name        = data.get('ward_name', ''),
            bed_number       = data.get('bed_number', ''),
            admitting_doctor = data.get('admitting_doctor', user.get('full_name', '')),
            department       = data.get('department', user.get('department', '')),
            diagnosis        = data.get('diagnosis', ''),
            admission_notes  = data.get('admission_notes', ''),
            created_by       = user['username'],
        )
        if adm_id:
            hospital_db.log_action(user['username'], user['role'], 'ipd_admit',
                                   f"patient={patient_name} ward={data.get('ward_name','')}",
                                   self.client_address[0])
            # Telegram alert
            try:
                from telegram_bot import notify_ipd_admission
                notify_ipd_admission(
                    name=patient_name,
                    phone=data.get('patient_phone', ''),
                    ward=data.get('ward_name', ''),
                    bed=data.get('bed_number', ''),
                    doctor=data.get('admitting_doctor', user.get('full_name', '')),
                )
            except Exception:
                pass
            self.send_json({'status': 'ok', 'admission_id': adm_id,
                            'message': f'{patient_name} admitted successfully'})
        else:
            self.send_json({'error': 'Admission failed'}, 500)

    def handle_ipd_round_add(self, data):
        """POST /api/ipd/round/add — add a daily round entry."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'DOCTOR', 'NURSE'):
            self.send_json({'error': 'Forbidden'}, 403); return
        admission_id = data.get('admission_id')
        patient_name = data.get('patient_name', '').strip()
        if not admission_id:
            self.send_json({'error': 'admission_id is required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        new_id = hospital_db.add_daily_round(
            admission_id     = int(admission_id),
            patient_name     = patient_name,
            doctor_name      = user.get('full_name', user['username']),
            doctor_username  = user['username'],
            bp               = data.get('bp', ''),
            pulse            = data.get('pulse', ''),
            temperature      = data.get('temperature', ''),
            spo2             = data.get('spo2', ''),
            clinical_notes   = data.get('clinical_notes', ''),
            treatment_change = data.get('treatment_change', ''),
        )
        self.send_json({'status': 'ok' if new_id else 'error', 'id': new_id})

    def handle_ipd_discharge(self, data):
        """POST /api/ipd/discharge — discharge IPD patient and save discharge summary."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'DOCTOR'):
            self.send_json({'error': 'Forbidden'}, 403); return
        admission_id = data.get('admission_id')
        if not admission_id:
            self.send_json({'error': 'admission_id is required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        ds_id = hospital_db.discharge_patient(
            admission_id       = int(admission_id),
            doctor_username    = user['username'],
            doctor_name        = user.get('full_name', user['username']),
            final_diagnosis    = data.get('final_diagnosis', ''),
            treatment_given    = data.get('treatment_given', ''),
            discharge_medicines= data.get('discharge_medicines', ''),
            follow_up_date     = data.get('follow_up_date'),
            follow_up_notes    = data.get('follow_up_notes', ''),
            diet_advice        = data.get('diet_advice', ''),
            activity_advice    = data.get('activity_advice', ''),
        )
        if ds_id:
            hospital_db.log_action(user['username'], user['role'], 'ipd_discharge',
                                   f"admission_id={admission_id}", self.client_address[0])
            # Telegram alert
            try:
                from telegram_bot import notify_ipd_discharge
                notify_ipd_discharge(
                    name=data.get('patient_name', f'Admission #{admission_id}'),
                    phone=data.get('patient_phone', ''),
                )
            except Exception:
                pass
            self.send_json({'status': 'ok', 'discharge_summary_id': ds_id,
                            'message': 'Patient discharged and summary saved'})
        else:
            self.send_json({'error': 'Discharge failed'}, 500)

    def handle_surgery_create(self, data):
        """POST /api/surgery/create — record a surgery."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'DOCTOR'):
            self.send_json({'error': 'Forbidden'}, 403); return
        patient_name  = data.get('patient_name', '').strip()
        surgery_type  = data.get('surgery_type', '').strip()
        if not patient_name or not surgery_type:
            self.send_json({'error': 'patient_name and surgery_type are required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        sur_id = hospital_db.create_surgery_record(
            patient_name     = patient_name,
            patient_phone    = data.get('patient_phone', ''),
            admission_id     = data.get('admission_id'),
            surgeon_name     = data.get('surgeon_name', user.get('full_name', '')),
            surgeon_username = user['username'],
            surgery_type     = surgery_type,
            anesthesia_type  = data.get('anesthesia_type', 'General'),
            estimated_cost   = float(data.get('estimated_cost', 0)),
            negotiated_cost  = float(data.get('negotiated_cost', data.get('estimated_cost', 0))),
            operation_date   = data.get('operation_date'),
            operation_notes  = data.get('operation_notes', ''),
            created_by       = user['username'],
        )
        if sur_id:
            hospital_db.log_action(user['username'], user['role'], 'surgery_created',
                                   f"patient={patient_name} type={surgery_type}", self.client_address[0])
            # Telegram alert
            try:
                from telegram_bot import notify_surgery_scheduled
                notify_surgery_scheduled(
                    patient=patient_name,
                    surgery_type=surgery_type,
                    surgeon=data.get('surgeon_name', user.get('full_name', '')),
                    date=data.get('operation_date', 'TBD'),
                    cost=float(data.get('estimated_cost', 0)),
                )
            except Exception:
                pass
            self.send_json({'status': 'ok', 'surgery_id': sur_id})
        else:
            self.send_json({'error': 'Failed to create surgery record'}, 500)

    def handle_surgery_update_cost(self, data):
        """POST /api/surgery/update-cost — update negotiated surgery cost."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'DOCTOR', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403); return
        surgery_id = data.get('surgery_id')
        negotiated_cost = data.get('negotiated_cost')
        if not surgery_id or negotiated_cost is None:
            self.send_json({'error': 'surgery_id and negotiated_cost required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok'}); return
        ok = hospital_db.update_surgery_negotiated_cost(
            int(surgery_id), float(negotiated_cost), data.get('notes', ''))
        self.send_json({'status': 'ok' if ok else 'error'})

    def handle_pharmacy_add_stock(self, data):
        """POST /api/pharmacy/add-stock — add medicine batch to inventory."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'STOCK'):
            self.send_json({'error': 'Forbidden'}, 403); return
        medicine_id  = data.get('medicine_id')
        batch_number = data.get('batch_number', '').strip()
        expiry_date  = data.get('expiry_date', '').strip()
        quantity     = int(data.get('quantity', 0))
        purchase_price= float(data.get('purchase_price', 0))
        sell_price   = float(data.get('sell_price', 0))
        if not medicine_id or quantity <= 0:
            self.send_json({'error': 'medicine_id and quantity (>0) required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        stock_id = hospital_db.add_medicine_stock(
            medicine_id    = int(medicine_id),
            batch_number   = batch_number,
            expiry_date    = expiry_date or None,
            quantity       = quantity,
            purchase_price = purchase_price,
            sell_price     = sell_price,
            supplier       = data.get('supplier', ''),
            min_quantity   = int(data.get('min_quantity', 10)),
        )
        self.send_json({'status': 'ok' if stock_id else 'error', 'id': stock_id})

    def handle_pharmacy_sell(self, data):
        """POST /api/pharmacy/sell — record pharmacy sale and deduct stock."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'STOCK', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        items = data.get('items', [])
        if not items:
            self.send_json({'error': 'items list required'}, 400); return
        conn = hospital_db.get_connection()
        if not conn:
            self.send_json({'error': 'DB unavailable'}, 503); return
        try:
            import psycopg2.extras as _extras
            cur = conn.cursor()
            total_amount = 0
            for it in items:
                total_amount += float(it.get('unit_price', 0)) * int(it.get('quantity', 1))
            discount   = float(data.get('discount', 0))
            net_amount = max(0, total_amount - discount)
            # Create sale header
            cur.execute(
                "INSERT INTO pharmacy_sales (patient_name, patient_phone, total_amount, "
                "discount, net_amount, payment_mode, staff_username) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (data.get('patient_name', 'Walk-in'), data.get('patient_phone', ''),
                 total_amount, discount, net_amount,
                 data.get('payment_mode', 'Cash'), user['username'])
            )
            sale_id = cur.fetchone()[0]
            # Insert line items and deduct stock
            for it in items:
                med_id    = it.get('medicine_id')
                med_name  = it.get('medicine_name', '')
                qty       = int(it.get('quantity', 1))
                uprice    = float(it.get('unit_price', 0))
                cur.execute(
                    "INSERT INTO pharmacy_sale_items (sale_id, medicine_id, medicine_name, "
                    "quantity, unit_price, total_price) VALUES (%s,%s,%s,%s,%s,%s)",
                    (sale_id, med_id, med_name, qty, uprice, round(qty * uprice, 2))
                )
                # Deduct from inventory
                if med_id:
                    hospital_db.deduct_medicine_stock(int(med_id), qty,
                                                      it.get('batch_number'))
            conn.commit()
            cur.close(); conn.close()
            self.send_json({'status': 'ok', 'sale_id': sale_id,
                            'net_amount': net_amount})
        except Exception as e:
            conn.rollback(); conn.close()
            self.send_json({'error': f'Pharmacy sale error: {e}'}, 500)

    def handle_billing_add_item(self, data):
        """POST /api/billing/add-item — add line item with GST to a bill."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403); return
        bill_id   = data.get('bill_id')
        item_name = data.get('item_name', '').strip()
        if not bill_id or not item_name:
            self.send_json({'error': 'bill_id and item_name required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        item_id = hospital_db.add_bill_item(
            bill_id          = int(bill_id),
            item_type        = data.get('item_type', 'consultation'),
            item_name        = item_name,
            item_price       = float(data.get('item_price', 0)),
            quantity         = int(data.get('quantity', 1)),
            negotiated_price = float(data.get('negotiated_price')) if data.get('negotiated_price') is not None else None,
            tax_percent      = float(data.get('tax_percent')) if data.get('tax_percent') is not None else None,
            notes            = data.get('notes', ''),
        )
        self.send_json({'status': 'ok' if item_id else 'error', 'id': item_id})

    def handle_billing_ipd_create(self, data):
        """POST /api/billing/ipd/create — create full IPD bill."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403); return
        patient_name = data.get('patient_name', '').strip()
        if not patient_name:
            self.send_json({'error': 'patient_name is required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        bill_id = hospital_db.create_ipd_bill(
            patient_name            = patient_name,
            patient_phone           = data.get('patient_phone', ''),
            admission_id            = data.get('admission_id'),
            consultation_fee        = float(data.get('consultation_fee', 0)),
            lab_charges             = float(data.get('lab_charges', 0)),
            imaging_charges         = float(data.get('imaging_charges', 0)),
            pharmacy_charges        = float(data.get('pharmacy_charges', 0)),
            bed_charges             = float(data.get('bed_charges', 0)),
            surgery_charges         = float(data.get('surgery_charges', 0)),
            procedure_charges_total = float(data.get('procedure_charges', 0)),
            misc_charges            = float(data.get('misc_charges', 0)),
            discount                = float(data.get('discount', 0)),
            notes                   = data.get('notes', ''),
            created_by              = user['username'],
        )
        if bill_id:
            hospital_db.log_action(user['username'], user['role'], 'ipd_bill_created',
                                   f"patient={patient_name}", self.client_address[0])
            self.send_json({'status': 'ok', 'bill_id': bill_id})
        else:
            self.send_json({'error': 'Failed to create IPD bill'}, 500)

    def handle_billing_payment(self, data):
        """POST /api/billing/payment — record a payment against a bill."""
        user = self.get_session_user()
        if not user or user['role'] not in ('ADMIN', 'RECEPTION'):
            self.send_json({'error': 'Forbidden'}, 403); return
        bill_id    = data.get('bill_id')
        amount_paid = float(data.get('amount_paid', 0))
        if not bill_id or amount_paid <= 0:
            self.send_json({'error': 'bill_id and amount_paid (>0) required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        pay_id = hospital_db.record_payment(
            bill_id      = int(bill_id),
            amount_paid  = amount_paid,
            payment_mode = data.get('payment_mode', 'Cash'),
            reference_no = data.get('reference_no', ''),
            received_by  = user['username'],
        )
        self.send_json({'status': 'ok' if pay_id else 'error', 'payment_id': pay_id})

    def handle_procedure_add(self, data):
        """POST /api/procedures/add — add a procedure to the catalogue."""
        user = self.get_session_user()
        if not user or user['role'] != 'ADMIN':
            self.send_json({'error': 'Admin only'}, 403); return
        proc_name = data.get('procedure_name', '').strip()
        if not proc_name:
            self.send_json({'error': 'procedure_name required'}, 400); return
        if not _DB_AVAILABLE:
            self.send_json({'status': 'ok', 'id': 0}); return
        new_id = hospital_db.add_procedure_charge(
            procedure_name = proc_name,
            category       = data.get('category', 'General'),
            default_price  = float(data.get('default_price', 0)),
            gst_percent    = float(data.get('gst_percent', 0)),
            description    = data.get('description', ''),
        )
        self.send_json({'status': 'ok' if new_id else 'error', 'id': new_id})

    def serve_login_page(self):
        """Serve admin login page with multi-tenant hospital selector"""
        login_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SRP MediFlow – Staff Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-container { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.15); width: 100%; max-width: 420px; }
        .login-header { text-align: center; margin-bottom: 28px; }
        .login-header .logo { font-size: 36px; margin-bottom: 8px; }
        .login-header h1 { color: #333; margin-bottom: 6px; font-size: 22px; }
        .login-header p { color: #666; font-size: 13px; }
        .form-group { margin-bottom: 18px; }
        label { display: block; color: #444; margin-bottom: 7px; font-weight: 600; font-size: 14px; }
        input[type="text"], input[type="password"], select {
            width: 100%; padding: 12px 14px; border: 2px solid #e1e5e9;
            border-radius: 8px; font-size: 15px; transition: border-color 0.25s;
            background: #fff; color: #333;
        }
        input:focus, select:focus { border-color: #667eea; outline: none; box-shadow: 0 0 0 3px rgba(102,126,234,0.12); }
        select { cursor: pointer; }
        .hospital-badge {
            display: flex; align-items: center; gap: 10px;
            background: linear-gradient(135deg, #667eea15, #764ba215);
            border: 1px solid #667eea30; border-radius: 8px;
            padding: 10px 14px; margin-bottom: 20px; font-size: 13px; color: #444;
        }
        .hospital-badge .icon { font-size: 22px; }
        .hospital-badge strong { color: #333; display: block; font-size: 15px; }
        .login-btn { width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; transition: opacity 0.2s, transform 0.1s; }
        .login-btn:hover { opacity: 0.92; transform: translateY(-1px); }
        .login-btn:active { transform: translateY(0); }
        .login-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .error-message { color: #dc3545; text-align: center; margin-top: 14px; padding: 12px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; display: none; font-size: 14px; }
        .divider { text-align: center; color: #999; font-size: 12px; margin: 16px 0 4px; }
        .powered-by { text-align: center; color: #bbb; font-size: 11px; margin-top: 20px; }
        .loading-tenants { color: #999; font-size: 13px; font-style: italic; }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <div class="logo">🏥</div>
            <h1>SRP MediFlow</h1>
            <p>Hospital Staff Login — Authorized Personnel Only</p>
        </div>

        <!-- Hospital selector (loaded dynamically) -->
        <div class="form-group">
            <label for="tenantSelect">🏦 Select Your Hospital</label>
            <select id="tenantSelect" onchange="onTenantChange()">
                <option value="">Loading hospitals...</option>
            </select>
        </div>

        <!-- Selected hospital badge -->
        <div class="hospital-badge" id="hospitalBadge" style="display:none">
            <span class="icon">🏥</span>
            <div>
                <strong id="badgeName">Hospital</strong>
                <span id="badgeCity">City</span>
            </div>
        </div>

        <form id="loginForm">
            <div class="form-group">
                <label for="username">👤 Username</label>
                <input type="text" id="username" name="username" required placeholder="Enter your username" autocomplete="username">
            </div>

            <div class="form-group">
                <label for="password">🔒 Password</label>
                <input type="password" id="password" name="password" required placeholder="Enter your password" autocomplete="current-password">
            </div>

            <button type="submit" class="login-btn" id="loginBtn">Login to Hospital System</button>
            <div id="errorMessage" class="error-message"></div>
        </form>

        <div class="powered-by">Powered by SRP MediFlow &nbsp;•&nbsp; Multi-Tenant HMS Platform</div>
    </div>

    <script>
        let tenants = [];
        let selectedTenant = null;

        async function loadTenants() {
            try {
                const resp = await fetch('/api/tenants/list');
                const data = await resp.json();
                tenants = data.tenants || [];
                const sel = document.getElementById('tenantSelect');
                sel.innerHTML = '<option value="">-- Select Hospital --</option>';
                tenants.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.slug;
                    opt.textContent = t.display_name + (t.city ? ' (' + t.city + ')' : '');
                    sel.appendChild(opt);
                });
                // Auto-select if only one tenant
                if (tenants.length === 1) {
                    sel.value = tenants[0].slug;
                    onTenantChange();
                }
            } catch(e) {
                document.getElementById('tenantSelect').innerHTML =
                    '<option value="star_hospital">Star Hospital (Kothagudem)</option>';
                onTenantChange();
            }
        }

        function onTenantChange() {
            const slug = document.getElementById('tenantSelect').value;
            const tenant = tenants.find(t => t.slug === slug);
            const badge = document.getElementById('hospitalBadge');
            if (tenant) {
                selectedTenant = tenant;
                document.getElementById('badgeName').textContent = tenant.display_name;
                document.getElementById('badgeCity').textContent = tenant.city || '';
                badge.style.display = 'flex';
            } else if (slug === 'star_hospital') {
                selectedTenant = {slug: 'star_hospital', display_name: 'Star Hospital', city: 'Kothagudem'};
                document.getElementById('badgeName').textContent = 'Star Hospital';
                document.getElementById('badgeCity').textContent = 'Kothagudem';
                badge.style.display = 'flex';
            } else {
                selectedTenant = null;
                badge.style.display = 'none';
            }
        }

        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();
            const tenantSlug = document.getElementById('tenantSelect').value || 'star_hospital';
            const errorDiv = document.getElementById('errorMessage');
            const btn = document.getElementById('loginBtn');

            if (!username || !password) {
                errorDiv.textContent = 'Please enter both username and password';
                errorDiv.style.display = 'block';
                return;
            }
            if (!tenantSlug) {
                errorDiv.textContent = 'Please select your hospital first';
                errorDiv.style.display = 'block';
                return;
            }

            btn.textContent = 'Logging in...';
            btn.disabled = true;
            errorDiv.style.display = 'none';

            try {
                const resp = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, tenant_slug: tenantSlug })
                });
                const data = await resp.json();

                if (data.status === 'success') {
                    btn.textContent = '✓ Success! Redirecting...';
                    // Store tenant info for dashboard header
                    if (data.hospital_name) {
                        sessionStorage.setItem('hospital_name', data.hospital_name);
                        sessionStorage.setItem('tenant_slug', data.tenant_slug || tenantSlug);
                    }
                    window.location.href = data.redirect || '/admin';
                } else {
                    errorDiv.textContent = data.message || 'Invalid credentials';
                    errorDiv.style.display = 'block';
                    btn.textContent = 'Login to Hospital System';
                    btn.disabled = false;
                }
            } catch (err) {
                errorDiv.textContent = 'Network error — please try again';
                errorDiv.style.display = 'block';
                btn.textContent = 'Login to Hospital System';
                btn.disabled = false;
            }
        });

        // Load on page load
        loadTenants();
    </script>
</body>
</html>'''

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(login_html.encode('utf-8'))
    
    def handle_chat(self, data):
        try:
            message = data.get('message', '').strip()
            session_id = data.get('session_id', 'default')
            
            if not message:
                self.send_json({'error': 'Empty message'}, 400)
                return
            
            # Load or create session state
            if session_id not in conversation_sessions:
                conversation_sessions[session_id] = {
                    'booking_active': False,
                    'doctor_selected': None,
                    'name': None,
                    'age': None,
                    'phone': None,
                    'issue': None,
                    'aadhar': None,
                    'time': None,
                    'symptoms': [],
                    'conversation_history': []
                }
            
            current_state = conversation_sessions[session_id]
            current_state['conversation_history'].append({'user': message, 'timestamp': time.time()})
            
            # SYNC: Load session state into chatbot global state before processing
            from chatbot import set_chatbot_state, get_chatbot_state
            chatbot_state = {
                'booking_active': current_state.get('booking_active', False),
                'doctor_selected': current_state.get('doctor_selected', None),
                'name': current_state.get('name', None),
                'age': current_state.get('age', None),
                'phone': current_state.get('phone', None),
                'issue': current_state.get('issue', None),
                'aadhar': current_state.get('aadhar', None),
                'appointment_time': current_state.get('appointment_time', None)
            }
            set_chatbot_state(chatbot_state)
            
            # Generate response
            response_result = generate_chatbot_response(message)
            
            # Handle response format
            if isinstance(response_result, tuple):
                bot_response, detected_language = response_result
            else:
                bot_response = response_result
                detected_language = 'en'
            
            # SYNC: Update session state from chatbot state after processing
            updated_chatbot_state = get_chatbot_state()
            current_state.update({
                'booking_active': updated_chatbot_state.get('booking_active', False),
                'doctor_selected': updated_chatbot_state.get('doctor_selected', None),
                'name': updated_chatbot_state.get('name', None),
                'age': updated_chatbot_state.get('age', None),
                'phone': updated_chatbot_state.get('phone', None),
                'issue': updated_chatbot_state.get('issue', None),
                'aadhar': updated_chatbot_state.get('aadhar', None),
                'appointment_time': updated_chatbot_state.get('appointment_time', None)
            })
            current_state['conversation_history'].append({'bot': bot_response, 'timestamp': time.time()})
            conversation_sessions[session_id] = current_state
            
            self.send_json({
                'message': bot_response,  # Frontend expects 'message' not 'response'
                'session_id': session_id,
                'language': detected_language,
                'state': current_state
            })
            
        except Exception as e:
            self.send_json({'error': f'Chat error: {str(e)}'}, 500)
    
    def handle_register(self, data):
        try:
            # Handle both form registration and chatbot registration
            if 'name' in data and 'phone' in data:
                # Direct form registration
                booking_record = {
                    'name': data.get('name', ''),
                    'age': data.get('age', ''),
                    'phone': data.get('phone', ''),
                    'aadhar': data.get('aadhar', ''),
                    'issue': data.get('health_issue', ''),
                    'doctor': data.get('preferred_doctor', ''),
                    'appointment_time': data.get('preferred_time', ''),
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'form_registration'
                }
            else:
                # Chatbot registration
                booking_record = get_last_booking_record()
                if not booking_record:
                    self.send_json({'error': 'No booking record found'}, 400)
                    return
                booking_record['source'] = 'chatbot_registration'
                # Ensure timestamp exists for chatbot records
                if 'timestamp' not in booking_record:
                    booking_record['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')

            # Save to PostgreSQL (primary) + file (backup)
            print(f"💾 Saving registration for: {booking_record['name']}")

            if _DB_AVAILABLE:
                try:
                    new_id = hospital_db.save_registration(booking_record)
                    booking_record['db_id'] = new_id
                    print(f"✅ Registration saved to PostgreSQL (id={new_id}): {booking_record['name']}")
                except Exception as _dbe:
                    print(f"⚠️  DB save failed ({_dbe}), using file fallback")
                    _save_to_file(booking_record)
            else:
                _save_to_file(booking_record)
                print(f"✅ Registration saved to file: {booking_record['name']}")

            # Clear the chatbot record after saving (if it was from chatbot)
            if 'source' in booking_record and booking_record['source'] == 'chatbot_registration':
                clear_last_booking_record()

            # Telegram alert for new OPD patient
            try:
                from telegram_bot import notify_new_registration
                notify_new_registration(
                    name=booking_record.get('name', ''),
                    phone=booking_record.get('phone', ''),
                    issue=booking_record.get('issue', ''),
                    doctor=booking_record.get('doctor', ''),
                )
            except Exception:
                pass

            self.send_json({
                'status': 'ok',
                'message': 'Registration completed successfully',
                'data': booking_record
            })

        except Exception as e:
            print(f"Registration error: {e}")
            self.send_json({'error': f'Registration error: {str(e)}'}, 500)
    
    def handle_transcribe(self, data):
        if not transcribe_audio:
            self.send_json({'error': 'Transcription not available'}, 503)
            return
        
        try:
            audio_data = data.get('audio')
            if not audio_data:
                self.send_json({'error': 'No audio data provided'}, 400)
                return
            
            # Transcribe audio
            transcription = transcribe_audio(audio_data)
            self.send_json({'transcription': transcription})
            
        except Exception as e:
            self.send_json({'error': f'Transcription error: {str(e)}'}, 500)
    
    def send_admin_data(self):
        try:
            if _DB_AVAILABLE:
                # Primary: PostgreSQL
                data = hospital_db.get_admin_dashboard_data()
                data['total_sessions']  = len(conversation_sessions)
                data['active_sessions'] = len([s for s in conversation_sessions.values() if s.get('booking_active')])
                data['db_source'] = 'postgresql'
            else:
                # Fallback: text files
                data = {
                    'timestamp': time.time(),
                    'status': 'online',
                    'db_source': 'file',
                    'total_sessions': len(conversation_sessions),
                    'active_sessions': len([s for s in conversation_sessions.values() if s.get('booking_active')]),
                    'registrations': [],
                    'appointments': [],
                    'total_appointments': 0,
                    'today_patients': 0,
                    'doctors_on_duty': 2,
                }
                registrations_file = os.path.join(BASE_DIR, 'registrations.txt')
                if os.path.exists(registrations_file):
                    with open(registrations_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                data['registrations'].append(json.loads(line.strip()))
                            except:
                                pass
                data['registrations'].sort(key=lambda x: x.get('timestamp', '0'), reverse=True)
                data['appointments'] = data['registrations']
                data['total_appointments'] = len(data['registrations'])

            self.send_json(data)

        except Exception as e:
            self.send_json({'error': f'Admin data error: {str(e)}'}, 500)
    
    def handle_attendance(self, data):
        try:
            action     = data.get('action', 'checkin').lower().replace('_', '')
            staff_name = data.get('staff_name', 'Unknown').strip()
            notes      = data.get('notes', '')

            if action not in ('checkin', 'checkout'):
                action = 'checkin'

            now_str = time.strftime('%Y-%m-%d %H:%M:%S')

            if _DB_AVAILABLE:
                rec_id = hospital_db.save_attendance(staff_name, action, notes)
                record = {'id': rec_id, 'staff_name': staff_name, 'action': action, 'date': now_str}
            else:
                attendance_file = os.path.join(BASE_DIR, 'attendance.txt')
                record = {'staff_name': staff_name, 'action': action,
                          'timestamp': time.time(), 'date': now_str}
                with open(attendance_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record) + '\n')

            self.send_json({
                'status': 'success',
                'message': f'{action.capitalize()} recorded for {staff_name}',
                'record': record
            })

        except Exception as e:
            self.send_json({'error': f'Attendance error: {str(e)}'}, 500)

    def handle_doctor_checkin(self, data):
        """Check in a doctor — marks on_duty=True and logs attendance."""
        try:
            doctor_name = data.get('doctor_name', '').strip()
            if not doctor_name:
                self.send_json({'error': 'doctor_name required'}, 400)
                return

            if _DB_AVAILABLE:
                ok = hospital_db.doctor_checkin(doctor_name)
                if ok:
                    self.send_json({'status': 'success',
                                    'message': f'{doctor_name} checked in successfully'})
                else:
                    self.send_json({'status': 'error',
                                    'message': f'Doctor "{doctor_name}" not found in DB'}, 404)
            else:
                self.send_json({'status': 'success',
                                'message': f'{doctor_name} check-in recorded (file mode)'})
        except Exception as e:
            self.send_json({'error': f'Doctor check-in error: {str(e)}'}, 500)

    def handle_doctor_checkout(self, data):
        """Check out a doctor — marks on_duty=False and logs attendance."""
        try:
            doctor_name = data.get('doctor_name', '').strip()
            if not doctor_name:
                self.send_json({'error': 'doctor_name required'}, 400)
                return

            if _DB_AVAILABLE:
                ok = hospital_db.doctor_checkout(doctor_name)
                if ok:
                    self.send_json({'status': 'success',
                                    'message': f'{doctor_name} checked out successfully'})
                else:
                    self.send_json({'status': 'error',
                                    'message': f'Doctor "{doctor_name}" not found in DB'}, 404)
            else:
                self.send_json({'status': 'success',
                                'message': f'{doctor_name} check-out recorded (file mode)'})
        except Exception as e:
            self.send_json({'error': f'Doctor check-out error: {str(e)}'}, 500)

    def handle_add_round(self, data):
        """Add a doctor round schedule."""
        try:
            doctor_name = data.get('doctor_name', '').strip()
            ward        = data.get('ward', '').strip()
            round_time  = data.get('round_time', '').strip()
            if not all([doctor_name, ward]):
                self.send_json({'error': 'doctor_name and ward are required'}, 400)
                return
            if _DB_AVAILABLE:
                rid = hospital_db.add_doctor_round(doctor_name, ward, round_time)
                self.send_json({'status': 'success', 'round_id': rid,
                                'message': f'Round scheduled for {doctor_name} in {ward}'})
            else:
                self.send_json({'status': 'success', 'message': 'Round recorded (file mode)'})
        except Exception as e:
            self.send_json({'error': f'Add round error: {str(e)}'}, 500)

    def handle_complete_round(self, data):
        """Mark a doctor round as completed."""
        try:
            round_id = data.get('round_id')
            if round_id is None:
                self.send_json({'error': 'round_id required'}, 400)
                return
            if _DB_AVAILABLE:
                ok = hospital_db.complete_doctor_round(int(round_id))
                self.send_json({'status': 'success' if ok else 'error',
                                'message': 'Round marked as completed' if ok else 'Round not found'})
            else:
                self.send_json({'status': 'success', 'message': 'Completed (file mode)'})
        except Exception as e:
            self.send_json({'error': f'Complete round error: {str(e)}'}, 500)
    
    def handle_admin_appointments(self, data):
        try:
            appointment_id = data.get('appointment_id') or data.get('id')
            status = data.get('status', 'confirmed')
            
            if appointment_id is None:
                self.send_json({'error': 'Appointment ID required'}, 400)
                return
            
            if _DB_AVAILABLE:
                ok = hospital_db.update_registration_status(int(appointment_id), status)
                if ok:
                    self.send_json({
                        'status': 'success',
                        'message': f'Appointment #{appointment_id} updated to {status}'
                    })
                else:
                    self.send_json({'error': f'Appointment #{appointment_id} not found'}, 404)
            else:
                self.send_json({
                    'status': 'success',
                    'message': f'Appointment {appointment_id} updated to {status} (file mode)'
                })
            
        except Exception as e:
            self.send_json({'error': f'Appointment update error: {str(e)}'}, 500)
    
    def send_json(self, data, code=200):
        import decimal, datetime
        class _Enc(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, decimal.Decimal): return float(o)
                if isinstance(o, (datetime.datetime, datetime.date)): return o.isoformat()
                return super().default(o)
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, cls=_Enc).encode('utf-8'))
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def start_ngrok_tunnel():
    """Start ngrok tunnel automatically"""
    try:
        print("🚀 Starting Ngrok tunnel...")
        team_token = "37Rwq30wuAywubCrSJLEDEppC2T_edeYm2GjcqSt6DQnHWnC"
        
        # Start ngrok process in background
        ngrok_cmd = f"ngrok http {PORT} --authtoken={team_token}"
        subprocess.Popen(
            ngrok_cmd.split(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        
        # Wait for ngrok to start and get URL
        time.sleep(8)
        
        try:
            import requests
            response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
            tunnels = response.json()["tunnels"]
            
            if tunnels:
                public_url = tunnels[0]["public_url"]
                print(f"✅ Ngrok tunnel: {public_url}")
                print(f"🌐 Team Access: {public_url}")
                print(f"👨‍💼 Admin Panel: {public_url}/admin")
                return public_url
            else:
                print("⚠️  Ngrok starting... URL will be available shortly")
                return None
        except:
            print("⚠️  Ngrok starting... URL will be available shortly")
            return None
            
    except Exception as e:
        print(f"⚠️  Could not start ngrok: {e}")
        print("💡 You can start it manually: ngrok http 7500")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-INSTANCE GUARD
# Prevents multiple server processes from all firing Telegram notifications and
# writing duplicate DB records when the .bat / IDE accidentally starts the server
# more than once.
# ═══════════════════════════════════════════════════════════════════════════════
_PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.pid')

def _acquire_pid_lock() -> bool:
    """
    Write current PID to server.pid.
    If a server.pid already exists and that process is still alive → refuse
    to start and return False.
    Returns True if we acquired the lock (safe to continue starting).
    """
    if os.path.exists(_PID_FILE):
        try:
            old_pid = int(open(_PID_FILE).read().strip())
            # Check on Windows whether that PID is still alive
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {old_pid}', '/NH', '/FO', 'CSV'],
                capture_output=True, text=True, timeout=5
            )
            if str(old_pid) in result.stdout:
                print(f"\n❌  DUPLICATE START BLOCKED")
                print(f"    SRP MediFlow is already running (PID {old_pid})")
                print(f"    Stop that instance first, or delete: {_PID_FILE}")
                print(f"    To kill it: taskkill /PID {old_pid} /F\n")
                return False
        except Exception:
            pass  # Stale / unreadable PID file — overwrite it
    # Write our PID
    with open(_PID_FILE, 'w') as _f:
        _f.write(str(os.getpid()))
    return True

def _release_pid_lock():
    """Remove server.pid on clean shutdown."""
    try:
        if os.path.exists(_PID_FILE):
            os.remove(_PID_FILE)
    except Exception:
        pass


if __name__ == '__main__':
    print()
    print("="*80)
    print("🏥 SRP MEDIFLOW - Hospital Management System")
    print("="*80)

    # ── Single-instance guard ────────────────────────────────────────────────
    if not _acquire_pid_lock():
        sys.exit(1)

    # Start ngrok tunnel first
    public_url = start_ngrok_tunnel()

    # Initialise RBAC tables and seed default admin
    if _DB_AVAILABLE:
        hospital_db.create_all_tables()
        hospital_db.ensure_default_admin(auth.hash_password('hospital2024'))
        # Phase-2 and Phase-3 tables + Star Hospital seed data
        try:
            hospital_db.create_hms_tables()
        except Exception as _e:
            print(f"⚠️  create_hms_tables: {_e}")
        try:
            hospital_db.create_extended_tables()
        except Exception as _e:
            print(f"⚠️  create_extended_tables: {_e}")
        try:
            hospital_db.create_phase3_tables()
        except Exception as _e:
            print(f"⚠️  create_phase3_tables: {_e}")
        try:
            hospital_db.create_saas_tables()
        except Exception as _e:
            print(f"⚠️  create_saas_tables: {_e}")
        # ── HMS v4 tables ────────────────────────────────────────────────────
        try:
            _hms.create_hms_v4_tables()
        except Exception as _e:
            print(f"⚠️  create_hms_v4_tables: {_e}")
        try:
            hospital_db.seed_star_hospital_doctors()
        except Exception as _e:
            print(f"⚠️  seed_star_hospital_doctors: {_e}")
        try:
            hospital_db.deduplicate_doctors()
        except Exception as _e:
            print(f"⚠️  deduplicate_doctors: {_e}")
        try:
            hospital_db.seed_services_catalogue()
        except Exception as _e:
            print(f"⚠️  seed_services_catalogue: {_e}")
        try:
            hospital_db.seed_client_record()
        except Exception as _e:
            print(f"⚠️  seed_client_record: {_e}")
        # Flag any expired billing accounts
        try:
            expired = _flag_expired_accounts()
            if expired:
                print(f"⚠️  {len(expired)} billing account(s) flagged as expired: {expired}")
        except Exception as _e:
            print(f"⚠️  billing flag check: {_e}")

    # ── Platform DB init (SaaS architecture step 1) ──────────────────────────
    # Must run before backup scheduler and before serving any founder requests.
    try:
        from platform_db import init_platform as _init_platform
        _pdb_ok = _init_platform()
        if _pdb_ok:
            print("✅ Platform DB (srp_platform_db) — READY")
        else:
            print("⚠️  Platform DB init failed — founder dashboard will use fallback data")
    except Exception as _pdb_err:
        print(f"⚠️  platform_db import error: {_pdb_err}")

    # Start daily backup scheduler (runs at BACKUP_HOUR, default 02:00)
    _start_backup_scheduler()

    print(f"🌐 Local Server: http://localhost:{PORT}")
    print(f"🔐 Local Admin: http://localhost:{PORT}/admin")
    print("📱 Patients: OPD / IPD / Chatbot booking")
    print("👥 Staff: Secure RBAC login (7 roles)")
    print("="*80)
    print(f"✅ Authentication: bcrypt RBAC — ENABLED")
    print(f"✅ IPD Admissions / Rounds / Discharge — ENABLED")
    print(f"✅ Surgery Module — ENABLED")
    print(f"✅ Pharmacy Batch/Expiry Tracking — ENABLED")
    print(f"✅ GST Billing (India) — ENABLED")
    print(f"✅ Multi-Tenant DB Provisioning — ENABLED")
    print(f"✅ Patient Registration + OP Tickets — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ HMS Billing / GST Invoices — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ Doctor Queue / Notes / Prescriptions — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ Pharmacy Stock / Alerts — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ Lab Orders + Result Auto-Link — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ Owner Analytics + Mobile Dashboard — {'ENABLED' if _HMS_AVAILABLE else 'UNAVAILABLE'}")
    print(f"✅ Admin / Doctor / Nurse / Lab / Stock dashboards — ENABLED")
    print(f"✅ Chatbot Voice/Text Appointment Booking — ENABLED")
    print(f"✅ Auto Ngrok Tunnel — ENABLED")
    print(f"✅ WhatsApp Gateway — {'ACTIVE' if _WHATSAPP_AVAILABLE else 'PLACEHOLDER (set WHATSAPP_API_KEY)'}")
    print(f"✅ Telegram Alerts — {'ACTIVE' if _TELEGRAM_AVAILABLE else 'NOT LOADED'}")
    print(f"✅ Multi-Client SaaS — {'ACTIVE' if _CLIENT_CONFIG_AVAILABLE else 'DEGRADED'}")
    print(f"✅ Client Registry API — /api/admin/clients | /api/admin/create-client")
    print("="*80)
    print(f"🚀 SaaS Platform Features:")
    print(f"   Billing & Subscriptions  — {'ACTIVE' if _SAAS_BILLING    else 'UNAVAILABLE'}")
    print(f"   Data Export (XLS/CSV/PDF)— {'ACTIVE' if _SAAS_EXPORT     else 'UNAVAILABLE'}")
    print(f"   Analytics Dashboard      — {'ACTIVE' if _SAAS_ANALYTICS  else 'UNAVAILABLE'}")
    print(f"   Automated Backup         — {'ACTIVE' if _SAAS_BACKUP     else 'UNAVAILABLE'}")
    print(f"   Hospital Onboarding API  — {'ACTIVE' if _SAAS_ONBOARDING else 'UNAVAILABLE'}")
    print(f"   Centralized Logging      — {'ACTIVE' if _SAAS_LOGGING    else 'UNAVAILABLE'}")
    print(f"   Audit Log                — ENABLED (audit_log table)")
    print(f"   Security Event Logging   — ENABLED (logs/security.log)")
    print("="*80)
    print()

    # Write system log entry
    _sys_log.info(f"SRP MediFlow SaaS server started on port {PORT}")

    # ── Founder alert: SERVER_START ────────────────────────────────────────
    send_founder_alert(
        "SERVER_START",
        f"SRP MediFlow SaaS server started successfully on port {PORT}\n"
        f"Modules: billing={_SAAS_BILLING} export={_SAAS_EXPORT} "
        f"analytics={_SAAS_ANALYTICS} backup={_SAAS_BACKUP}"
    )

    # Hospital-level Telegram startup notification (internal, not founder)
    if _TELEGRAM_AVAILABLE:
        try:
            _cfg = _get_client_cfg()
            _tg.notify_admin(
                f"🚀 SRP MediFlow server started\n"
                f"🌐 Port: {PORT}\n"
                f"🏥 {_cfg.get('hospital_name', 'Star Hospital')}\n"
                f"📍 {_cfg.get('city', 'Kothagudem')}"
            )
        except Exception:
            pass

    try:
        server = HTTPServer(('0.0.0.0', PORT), Handler)
        print("🚀 SRP MediFlow SaaS Server starting...")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        _sys_log.info("Server stopped by KeyboardInterrupt")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()
        _sys_log.error(f"SERVER_CRASH: {type(e).__name__}: {e}")
        # ── Founder alert: SERVER_CRASH ──────────────────────────────────────
        send_founder_alert(
            "SERVER_CRASH",
            f"Unhandled server exception: {type(e).__name__}: {e}"
        )
        import time as _time; _time.sleep(1)  # give daemon thread a moment to fire
    finally:
        _release_pid_lock()
        print("🔄 Hospital AI Server shutdown complete")