import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, async_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from app.models import ErrorLog
from app.admin_routes import router as admin_router
from app.account_routes import router as account_router
from app.main_routes import router as main_router
from app.agent_routes import router as agent_router
from app.admin_python_routes import router as admin_python_router
from app.admin_skills_routes import router as admin_skills_router
from app.admin_referral_routes import router as admin_referral_router
from app.admin_tips_routes import router as admin_tips_router
from app.admin_subscription_routes import router as admin_subscription_router
from app.user_subscription_routes import router as user_subscription_router
from app.admin_backup_routes import router as admin_backup_router
from app.admin_codex_proxy_routes import router as admin_codex_proxy_router
from app.payment_routes import router as payment_router
from app.backup import start_scheduler, stop_scheduler
from app.config import BACKUP_ENABLED
from app.codex_proxy import router as codex_proxy_router
from app.link_code_routes import router as link_code_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if BACKUP_ENABLED:
        start_scheduler()
    yield
    if BACKUP_ENABLED:
        stop_scheduler()


app = FastAPI(title="دکتر بز", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    async with async_session() as session:
        try:
            error_log = ErrorLog(
                source="API",
                error_message=str(exc),
                stack_trace=traceback.format_exc(),
            )
            session.add(error_log)
            await session.commit()
        except Exception as e:
            import logging

            logging.error(f"Failed to save error log: {e}")

    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://91.107.175.43:4000",
        "http://91.107.175.43",
        "http://localhost:4000",
        "http://localhost",
        "http://127.0.0.1:4000",
        "http://127.0.0.1",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|91\.107\.175\.43)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/api")
app.include_router(account_router, prefix="/api")
app.include_router(main_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(admin_python_router, prefix="/api")
app.include_router(admin_skills_router, prefix="/api")
app.include_router(admin_referral_router, prefix="/api")
app.include_router(admin_tips_router)
app.include_router(admin_subscription_router)
app.include_router(user_subscription_router)
app.include_router(admin_backup_router, prefix="/api")
app.include_router(admin_codex_proxy_router)
app.include_router(codex_proxy_router)
app.include_router(link_code_router, prefix="/api")
app.include_router(payment_router)


@app.get("/")
async def root():
    return {"app": "دکتر بز", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
