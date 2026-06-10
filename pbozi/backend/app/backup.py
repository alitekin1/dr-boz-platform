import os
import shutil
import tarfile
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import (
    BACKUP_ENABLED,
    BACKUP_INTERVAL_MINUTES,
    BACKUP_MAX_COUNT,
    BACKUP_GOOGLE_DRIVE_FOLDER_ID,
    BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON,
    CHROMA_PERSIST_DIR,
)

logger = logging.getLogger(__name__)

_BACKUP_SCHEDULER = None
_BACKUP_JOB = None


def get_backup_paths() -> list[Path]:
    backend_dir = Path(__file__).parent.parent
    paths = []

    # Database files
    db_path = backend_dir / "jgpti.db"
    if db_path.exists():
        paths.append(db_path)
    for ext in [".db-shm", ".db-wal"]:
        p = backend_dir / f"jgpti{ext}"
        if p.exists():
            paths.append(p)

    # Uploads
    uploads_dir = backend_dir / "uploads"
    if uploads_dir.exists():
        paths.append(uploads_dir)

    # Chroma data
    chroma_dir = Path(CHROMA_PERSIST_DIR)
    if not chroma_dir.is_absolute():
        chroma_dir = backend_dir / chroma_dir
    if chroma_dir.exists():
        paths.append(chroma_dir)

    # Env file
    env_file = backend_dir / ".env"
    if env_file.exists():
        paths.append(env_file)

    return paths


def create_backup_archive() -> Path:
    backend_dir = Path(__file__).parent.parent
    backups_dir = backend_dir / "backups"
    backups_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"jgpti_backup_{timestamp}.tar.gz"
    archive_path = backups_dir / archive_name

    paths = get_backup_paths()

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in paths:
            tar.add(path, arcname=path.name)

    logger.info(f"Backup archive created: {archive_path}")
    return archive_path


def get_drive_service():
    if not BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON or not os.path.exists(BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON):
        raise RuntimeError("Google service account JSON not configured or file missing")

    credentials = service_account.Credentials.from_service_account_file(
        BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=credentials)


def upload_to_drive(file_path: Path) -> str:
    service = get_drive_service()

    file_metadata = {
        "name": file_path.name,
        "parents": [BACKUP_GOOGLE_DRIVE_FOLDER_ID] if BACKUP_GOOGLE_DRIVE_FOLDER_ID else []
    }

    media = MediaFileUpload(str(file_path), mimetype="application/gzip", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = file.get("id")
    logger.info(f"Uploaded backup to Drive: {file_id}")
    return file_id


def rotate_drive_backups():
    service = get_drive_service()

    query = "mimeType='application/gzip' and name contains 'jgpti_backup_'"
    if BACKUP_GOOGLE_DRIVE_FOLDER_ID:
        query += f" and '{BACKUP_GOOGLE_DRIVE_FOLDER_ID}' in parents"

    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, createdTime)",
        orderBy="createdTime desc",
        pageSize=100
    ).execute()

    files = results.get("files", [])
    if len(files) <= BACKUP_MAX_COUNT:
        return

    to_delete = files[BACKUP_MAX_COUNT:]
    for f in to_delete:
        service.files().delete(fileId=f["id"]).execute()
        logger.info(f"Deleted old backup from Drive: {f['name']} ({f['id']})")


def perform_backup() -> dict:
    if not BACKUP_ENABLED:
        return {"status": "skipped", "reason": "backup disabled"}

    try:
        archive_path = create_backup_archive()
        file_id = upload_to_drive(archive_path)
        rotate_drive_backups()

        archive_path.unlink(missing_ok=True)

        return {
            "status": "success",
            "archive_name": archive_path.name,
            "drive_file_id": file_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.exception("Backup failed")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def start_scheduler():
    global _BACKUP_SCHEDULER, _BACKUP_JOB
    from apscheduler.schedulers.background import BackgroundScheduler

    if _BACKUP_SCHEDULER is not None:
        return

    _BACKUP_SCHEDULER = BackgroundScheduler()
    _BACKUP_SCHEDULER.start()
    _BACKUP_JOB = _BACKUP_SCHEDULER.add_job(
        perform_backup,
        "interval",
        minutes=BACKUP_INTERVAL_MINUTES,
        id="auto_backup",
        replace_existing=True
    )
    logger.info(f"Backup scheduler started (every {BACKUP_INTERVAL_MINUTES} minutes)")


def stop_scheduler():
    global _BACKUP_SCHEDULER, _BACKUP_JOB
    if _BACKUP_SCHEDULER is not None:
        _BACKUP_SCHEDULER.shutdown()
        _BACKUP_SCHEDULER = None
        _BACKUP_JOB = None
        logger.info("Backup scheduler stopped")


def get_scheduler_status() -> dict:
    next_run = None
    if _BACKUP_JOB and _BACKUP_JOB.next_run_time:
        next_run = _BACKUP_JOB.next_run_time.isoformat()

    return {
        "enabled": BACKUP_ENABLED,
        "interval_minutes": BACKUP_INTERVAL_MINUTES,
        "max_count": BACKUP_MAX_COUNT,
        "running": _BACKUP_SCHEDULER is not None and _BACKUP_SCHEDULER.running,
        "next_run": next_run
    }
