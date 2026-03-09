"""
saas_backup.py — SRP MediFlow Scheduled Database Backup
========================================================
Performs daily automated pg_dump backups for all registered hospital databases.

Backup layout:
  backups/
    {client_slug}/
      {client_slug}_YYYYMMDD_HHMMSS.sql.gz

Features:
  - Runs in a daemon background thread (no server blocking)
  - Backs up main hospital_ai DB + all tenant DBs from tenant_registry.json
  - Logs every backup event to logs/system.log
  - Sends founder alert via notifications/founder_alerts.py on failure
  - Records last successful backup timestamp to logs/last_backup.txt
  - Default schedule: 02:00 local time daily (configurable via env)

Environment variables:
  BACKUP_HOUR          — hour (0-23) to run daily backup, default 2
  BACKUP_DIR           — override backup root directory
  PG_HOST, PG_PORT, PG_ADMIN_PASS — PostgreSQL connection (inherit from main config)

Usage (called once at server start):
  from saas_backup import start_backup_scheduler
  start_backup_scheduler()
"""

from __future__ import annotations
import os
import gzip
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
_BASE_DIR   = Path(__file__).parent
_BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(_BASE_DIR / "backups")))
_LOG_DIR    = _BASE_DIR / "logs"
_LAST_BK    = _LOG_DIR / "last_backup.txt"
_BACKUP_HOUR = int(os.getenv("BACKUP_HOUR", "2"))      # 02:00 AM

# PostgreSQL connection settings (matches admin connection in tenant module)
_PG_HOST    = os.getenv("PG_HOST",       "localhost")
_PG_PORT    = os.getenv("PG_PORT",       "5434")
_PG_USER    = os.getenv("PG_ADMIN_USER", "ats_user")
_PG_PASS    = os.getenv("PG_ADMIN_PASS", "ats_password")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _log(msg: str) -> None:
    try:
        from saas_logging import system_log
        system_log.info(f"[BACKUP] {msg}")
    except Exception:
        pass
    print(f"[BACKUP] {msg}")


def _alert_failure(msg: str) -> None:
    try:
        from notifications.founder_alerts import send_founder_alert
        send_founder_alert("BACKUP_FAILED", msg)
    except Exception:
        pass


def _write_last_backup(ts: str) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _LAST_BK.write_text(ts, encoding="utf-8")
    except Exception:
        pass


def _pg_dump(db_name: str, dest_file: Path) -> bool:
    """
    Run pg_dump to dump the specified database into dest_file (.sql.gz).
    Returns True on success, False on failure.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = _PG_PASS

    # Prefer pg_dump from PATH; fall back to common locations
    pg_dump_cmd = "pg_dump"
    for candidate in [
        "pg_dump",
        r"C:\Program Files\PostgreSQL\14\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        "/usr/bin/pg_dump",
        "/usr/local/bin/pg_dump",
    ]:
        if candidate == "pg_dump" or Path(candidate).exists():
            pg_dump_cmd = candidate
            break

    cmd = [
        pg_dump_cmd,
        "-h", _PG_HOST,
        "-p", _PG_PORT,
        "-U", _PG_USER,
        "--no-password",
        "--format=plain",
        "--encoding=UTF8",
        db_name,
    ]
    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            timeout=300,   # 5-minute max per DB
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[:500]
            _log(f"pg_dump failed for '{db_name}': {err}")
            return False
        # Write as gzip
        with gzip.open(dest_file, "wb") as gz:
            gz.write(result.stdout)
        _log(f"Backup created: {dest_file}  ({dest_file.stat().st_size / 1024:.1f} KB)")
        return True
    except FileNotFoundError:
        _log(f"pg_dump binary not found — skipping DB '{db_name}'")
        return False
    except subprocess.TimeoutExpired:
        _log(f"pg_dump timeout for DB '{db_name}'")
        return False
    except Exception as exc:
        _log(f"pg_dump exception for DB '{db_name}': {exc}")
        return False


def _cleanup_old_backups(client_dir: Path, keep_days: int = 30) -> None:
    """Delete backup files older than keep_days."""
    cutoff = time.time() - keep_days * 86400
    try:
        for f in client_dir.glob("*.sql.gz"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                _log(f"Deleted old backup: {f.name}")
    except Exception:
        pass


# ── Core backup routine ───────────────────────────────────────────────────────
def run_backup_now() -> dict:
    """
    Run immediate backup for all registered databases.
    Returns summary dict: { 'success': [...], 'failed': [...], 'timestamp': str }

    Backup layout:
      backups/
        platform/        ← platform_db  (srp_platform_db)
        star_hospital/   ← tenant DB
        sai_care/        ← tenant DB
        …
    """
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success:  list[str] = []
    failed:   list[str] = []

    # ── 1. Platform database (srp_platform_db) — backed up first ─────────────
    platform_db_name = os.getenv("PLATFORM_DB_NAME", "srp_platform_db")
    platform_dest    = _BACKUP_DIR / "platform" / f"platform_{ts}.sql.gz"
    _log(f"Backing up platform DB: {platform_db_name}")
    if _pg_dump(platform_db_name, platform_dest):
        success.append(platform_db_name)
        _cleanup_old_backups(platform_dest.parent)
    else:
        failed.append(platform_db_name)

    # ── 2. Main hospital_ai database (star_hospital / default tenant) ─────────
    main_db   = os.getenv("PG_DB", "hospital_ai")
    main_dest = _BACKUP_DIR / "star_hospital" / f"star_hospital_{ts}.sql.gz"
    _log(f"Backing up default tenant DB: {main_db}")
    if _pg_dump(main_db, main_dest):
        success.append(main_db)
        _cleanup_old_backups(main_dest.parent)
    else:
        failed.append(main_db)

    # ── 3. Additional tenant databases from registry ───────────────────────────
    try:
        import json
        registry_file = _BASE_DIR / "tenant_registry.json"
        if registry_file.exists():
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
            for slug, info in registry.items():
                db_name  = info.get("db_name", f"srp_{slug}")
                # Skip star_hospital — already backed up above
                if db_name == main_db or slug == "star_hospital":
                    continue
                # Skip the platform DB if somehow listed in registry
                if db_name == platform_db_name:
                    continue
                dest_dir = _BACKUP_DIR / slug
                dest     = dest_dir / f"{slug}_{ts}.sql.gz"
                _log(f"Backing up tenant DB: {db_name} ({slug})")
                if _pg_dump(db_name, dest):
                    success.append(db_name)
                    _cleanup_old_backups(dest_dir)
                else:
                    failed.append(db_name)
    except Exception as exc:
        _log(f"Tenant registry error during backup: {exc}")

    # ── 4. Record result ───────────────────────────────────────────────────────
    _write_last_backup(timestamp)
    _log(f"Backup complete — success: {len(success)}, failed: {len(failed)}")

    if failed:
        _alert_failure(
            f"Backup completed with {len(failed)} failure(s):\n"
            f"Failed: {', '.join(failed)}\n"
            f"Succeeded: {', '.join(success) or 'none'}"
        )

    # ── 5. Record alert in platform_db ────────────────────────────────────────
    try:
        from platform_db import record_system_alert
        if failed:
            record_system_alert(
                "BACKUP_PARTIAL_FAILURE",
                f"Backup finished: {len(success)} OK, {len(failed)} failed. "
                f"Failed: {', '.join(failed)}",
                severity="warning",
            )
        else:
            record_system_alert(
                "BACKUP_OK",
                f"All {len(success)} database backups completed successfully.",
                severity="info",
            )
    except Exception:
        pass

    return {"success": success, "failed": failed, "timestamp": timestamp}


# ── Scheduler thread ──────────────────────────────────────────────────────────
_scheduler_started = False
_scheduler_lock    = threading.Lock()


def _scheduler_loop() -> None:
    """Background daemon that runs run_backup_now() once daily at BACKUP_HOUR."""
    import time as _time
    while True:
        now  = datetime.now()
        # Seconds until next scheduled hour
        next_run = now.replace(hour=_BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if next_run <= now:
            # Already past today's window → schedule for tomorrow
            next_run = next_run.replace(day=next_run.day + 1)
        wait_secs = (next_run - now).total_seconds()
        _log(f"Next scheduled backup at {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
             f"({wait_secs / 3600:.1f} h)")
        _time.sleep(wait_secs)
        try:
            run_backup_now()
        except Exception as exc:
            _log(f"Scheduler error: {exc}")
            _alert_failure(f"Backup scheduler raised an exception: {exc}")


def start_backup_scheduler() -> None:
    """
    Start the background backup scheduler daemon thread.
    Safe to call multiple times — only one thread is ever started.
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="SRP-BackupScheduler")
        t.start()
        _scheduler_started = True
        _log(f"Backup scheduler started (daily at {_BACKUP_HOUR:02d}:00)")
