from fastapi import APIRouter, Depends
from app.config import ADMIN_PASSWORD
from app.schemas import BackupStatusOut, BackupRunOut
from app.backup import perform_backup, get_scheduler_status, start_scheduler, stop_scheduler
from app.admin_routes import verify_admin

router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])


@router.get("/status", response_model=BackupStatusOut)
async def backup_status(_=Depends(verify_admin)):
    return get_scheduler_status()


@router.post("/run", response_model=BackupRunOut)
async def backup_run(_=Depends(verify_admin)):
    result = perform_backup()
    return BackupRunOut(**result)


@router.post("/start")
async def backup_start(_=Depends(verify_admin)):
    start_scheduler()
    return {"ok": True}


@router.post("/stop")
async def backup_stop(_=Depends(verify_admin)):
    stop_scheduler()
    return {"ok": True}
