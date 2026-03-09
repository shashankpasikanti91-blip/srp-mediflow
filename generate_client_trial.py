"""
generate_client_trial.py
========================
Generates a 7-day client trial access card for SRP MediFlow HMS v4.

Usage:
    python generate_client_trial.py [--hospital "City Hospital"] [--days 7]

What it does:
  1. Reads the current ngrok tunnel URL from localhost:4040
  2. Creates a dated trial-access HTML file in trials/
  3. Also prints a formatted summary to the console for WhatsApp/Telegram sharing
  4. Auto-opens the HTML trial card in the browser

The trial HTML file contains:
  - Hospital name
  - ngrok URL (clickable)
  - Expiry date (today + N days)
  - Login credentials (demo)
  - Modules available
  - QR-ready short URL section
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta

try:
    import urllib.request
    def _get_ngrok_url():
        try:
            with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=4) as r:
                data = json.loads(r.read())
                tunnels = data.get("tunnels", [])
                if tunnels:
                    return tunnels[0]["public_url"]
        except Exception:
            pass
        return None
except Exception:
    pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRIALS_DIR = os.path.join(BASE_DIR, "trials")
os.makedirs(TRIALS_DIR, exist_ok=True)


def generate_trial(hospital_name: str, days: int = 7, contact: str = "") -> str:
    """Create a trial access card and return the path to the HTML file."""

    ngrok_url = _get_ngrok_url()
    if not ngrok_url:
        print("⚠️  ngrok not running. Using placeholder URL.")
        print("   Start the server first: run '🏥 START SRP MEDIFLOW AUTO.bat'")
        ngrok_url = "https://YOUR-NGROK-URL.ngrok-free.app"

    today      = datetime.now()
    expiry     = today + timedelta(days=days)
    trial_id   = f"TRIAL-{today.strftime('%Y%m%d-%H%M')}"
    safe_name  = hospital_name.replace(' ', '_').replace('/', '_')
    filename   = f"trial_{safe_name}_{today.strftime('%Y%m%d')}.html"
    out_path   = os.path.join(TRIALS_DIR, filename)

    admin_url  = f"{ngrok_url}/admin"
    test_creds = [
        ("Admin",      "admin",      "hospital2024", "Full access — all modules"),
        ("Doctor",     "doctor1",    "doctor123",    "Patient queue, prescriptions, lab orders"),
        ("Receptionist","reception1","recept123",    "Registration, appointments, billing"),
        ("Lab Staff",  "lab1",       "lab123",       "Lab orders & results"),
        ("Pharmacist", "pharmacy1",  "stock123",     "Pharmacy stock & sales"),
    ]

    cred_rows = "\n".join(
        f"""<tr>
          <td><span class="role-badge">{r}</span></td>
          <td><code>{u}</code></td>
          <td><code>{p}</code></td>
          <td>{d}</td>
        </tr>"""
        for r, u, p, d in test_creds
    )

    modules = [
        ("🧑‍⚕️ Patient Registration", "OPD/IPD/ER registration with OP ticket numbering"),
        ("🏥 Doctor Workflow",           "Patient queue, clinical notes, structured prescriptions"),
        ("🧪 Lab & Diagnostics",         "Lab orders, result entry with auto-link to patient history"),
        ("💊 Pharmacy & Stock",          "Medicine inventory, sales, low-stock & expiry alerts"),
        ("💰 Billing & GST",             "OPD/IPD invoices, GST line items, payment tracking"),
        ("📊 Owner Analytics",           "Daily/weekly/monthly revenue, patient volume, doctor stats"),
        ("📱 Mobile Dashboard",          "Single-call lightweight API for mobile owner view"),
        ("🔔 Appointment Scheduling",    "Reception module with patient phone linking"),
        ("📁 Data Export",               "Patients / Billing / Appointments export (CSV/Excel)"),
        ("🔐 RBAC Security",             "7 roles with granular permission enforcement"),
    ]

    module_rows = "\n".join(
        f'<tr><td>{icon_name}</td><td>{desc}</td></tr>'
        for icon_name, desc in modules
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SRP MediFlow HMS v4 — 7-Day Trial | {hospital_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f4f8;
         color: #1a1a2e; min-height: 100vh; padding: 20px; }}
  .card {{ max-width: 820px; margin: 0 auto; background: #fff;
           border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,.12);
           overflow: hidden; }}
  .header {{ background: linear-gradient(135deg, #1a73e8, #00b896);
             padding: 36px 40px; color: #fff; }}
  .header h1 {{ font-size: 28px; font-weight: 700; }}
  .header h2 {{ font-size: 18px; font-weight: 400; opacity: .9; margin-top: 4px; }}
  .badge {{ display: inline-block; background: rgba(255,255,255,.2);
            border: 1px solid rgba(255,255,255,.4);
            padding: 4px 12px; border-radius: 20px; font-size: 13px;
            margin-top: 12px; letter-spacing: .5px; }}
  .body {{ padding: 36px 40px; }}
  .section {{ margin-bottom: 32px; }}
  .section h3 {{ font-size: 16px; font-weight: 700;
                 border-bottom: 2px solid #1a73e8;
                 padding-bottom: 8px; margin-bottom: 16px;
                 color: #1a73e8; text-transform: uppercase;
                 letter-spacing: .5px; }}
  .url-box {{ background: #e8f4fd; border: 2px solid #1a73e8;
              border-radius: 10px; padding: 16px 20px;
              font-size: 20px; font-weight: 600; text-align: center;
              word-break: break-all; }}
  .url-box a {{ color: #1a73e8; text-decoration: none; }}
  .url-box a:hover {{ text-decoration: underline; }}
  .expiry-box {{ display: flex; gap: 16px; margin-top: 12px; }}
  .info-pill {{ flex: 1; background: #f8f9fa; border-radius: 8px;
                padding: 12px 16px; text-align: center; }}
  .info-pill .label {{ font-size: 11px; text-transform: uppercase;
                       letter-spacing: .5px; color: #666; }}
  .info-pill .value {{ font-size: 16px; font-weight: 700; color: #1a2e; margin-top: 4px; }}
  .expiry-val {{ color: #e53935 !important; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ background: #1a73e8; color: #fff; padding: 10px 12px;
        text-align: left; font-weight: 600; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  tr:hover td {{ background: #f5f9ff; }}
  .role-badge {{ background: #1a73e8; color: #fff; padding: 2px 8px;
                 border-radius: 10px; font-size: 12px; white-space: nowrap; }}
  code {{ background: #f0f4f8; border: 1px solid #d0d8e4;
          padding: 2px 6px; border-radius: 4px; font-size: 13px;
          font-family: 'Courier New', monospace; }}
  .footer {{ background: #f8f9fa; padding: 20px 40px;
             text-align: center; font-size: 13px; color: #666;
             border-top: 1px solid #eee; }}
  .footer strong {{ color: #1a73e8; }}
  .note {{ background: #fff3cd; border-left: 4px solid #ffc107;
           padding: 12px 16px; border-radius: 0 8px 8px 0;
           font-size: 13px; color: #856404; margin-top: 16px; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .card {{ box-shadow: none; }}
  }}
</style>
</head>
<body>
<div class="card">

  <div class="header">
    <h1>🏥 SRP MediFlow HMS v4</h1>
    <h2>7-Day Trial Access — {hospital_name}</h2>
    <div class="badge">Trial ID: {trial_id}</div>
  </div>

  <div class="body">

    <div class="section">
      <h3>🌐 Your Live Trial URL</h3>
      <div class="url-box">
        <a href="{ngrok_url}" target="_blank">{ngrok_url}</a>
      </div>
      <div class="expiry-box">
        <div class="info-pill">
          <div class="label">Trial Starts</div>
          <div class="value">{today.strftime('%d %b %Y')}</div>
        </div>
        <div class="info-pill">
          <div class="label">Trial Expires</div>
          <div class="value expiry-val">{expiry.strftime('%d %b %Y')}</div>
        </div>
        <div class="info-pill">
          <div class="label">Trial Duration</div>
          <div class="value">{days} Days</div>
        </div>
        <div class="info-pill">
          <div class="label">Admin Login</div>
          <div class="value">
            <a href="{admin_url}" target="_blank" style="color:#1a73e8;">/admin</a>
          </div>
        </div>
      </div>
      <div class="note">
        ⚠️ <strong>Note:</strong> This is an ngrok URL — it may change if the server restarts.
        If the link stops working, contact your SRP representative for the updated URL.
        For production deployment, a permanent domain will be used.
      </div>
    </div>

    <div class="section">
      <h3>🔑 Login Credentials</h3>
      <table>
        <thead>
          <tr><th>Role</th><th>Username</th><th>Password</th><th>Access</th></tr>
        </thead>
        <tbody>
          {cred_rows}
        </tbody>
      </table>
    </div>

    <div class="section">
      <h3>✅ Modules Included in Trial</h3>
      <table>
        <thead>
          <tr><th>Module</th><th>Description</th></tr>
        </thead>
        <tbody>
          {module_rows}
        </tbody>
      </table>
    </div>

  </div>

  <div class="footer">
    Powered by <strong>SRP MediFlow HMS v4</strong> &nbsp;|&nbsp;
    Product of <strong>SRP AI Labs</strong> &nbsp;|&nbsp;
    Support: <strong>SRP Team</strong>
    {"&nbsp;|&nbsp; Contact: " + contact if contact else ""}
    <br><br>
    Generated: {today.strftime('%d %b %Y, %I:%M %p')} &nbsp;|&nbsp; Trial ID: {trial_id}
  </div>

</div>
</body>
</html>"""

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return out_path, ngrok_url, expiry


def main():
    parser = argparse.ArgumentParser(
        description="Generate 7-day SRP MediFlow trial access card for a client"
    )
    parser.add_argument(
        "--hospital", "-H",
        default="Demo Hospital",
        help="Hospital / client name (default: 'Demo Hospital')"
    )
    parser.add_argument(
        "--days", "-d",
        type=int, default=7,
        help="Trial duration in days (default: 7)"
    )
    parser.add_argument(
        "--contact", "-c",
        default="",
        help="Your contact number/email to include in the card"
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open the HTML file in browser"
    )
    args = parser.parse_args()

    print()
    print("=" * 62)
    print("  SRP MediFlow HMS v4 — Client Trial Generator")
    print("=" * 62)

    html_path, ngrok_url, expiry = generate_trial(
        hospital_name = args.hospital,
        days          = args.days,
        contact       = args.contact,
    )

    # Console summary (copy-paste for WhatsApp/Telegram)
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  TRIAL ACCESS CARD — {args.hospital[:35]:<35} ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  🌐 URL     : {ngrok_url:<45} ║")
    print(f"║  🔐 Admin   : {ngrok_url + '/admin':<45} ║")
    print(f"║  👤 Username: admin                                      ║")
    print(f"║  🔑 Password: hospital2024                               ║")
    print(f"║  📅 Expires : {expiry.strftime('%d %b %Y'):<45} ║")
    print(f"║  ⏳ Duration: {args.days} days                                        ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  📄 HTML Trial Card saved:                               ║")
    print(f"║  {os.path.basename(html_path):<56} ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("📋 Copy for WhatsApp / Telegram:")
    print()
    print(f"🏥 *SRP MediFlow Trial Access*")
    print(f"🏷️ Hospital: {args.hospital}")
    print(f"🌐 URL: {ngrok_url}")
    print(f"👤 Login: admin / hospital2024")
    print(f"📅 Valid till: {expiry.strftime('%d %b %Y')}")
    print(f"📱 Admin Panel: {ngrok_url}/admin")
    print()

    if not args.no_open:
        print(f"🌐 Opening trial card in browser...")
        webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")

    print(f"✅ Done! Trial card: {html_path}")
    print()


if __name__ == "__main__":
    main()
