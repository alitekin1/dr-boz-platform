import json
import asyncio
import os
import subprocess
import tempfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session, async_session
from app.admin_routes import verify_admin

router = APIRouter(prefix="/admin/python", tags=["admin-python"])

class PythonRunRequest(BaseModel):
    code: str

class PythonRunResponse(BaseModel):
    output: str
    error: Optional[str] = None

@router.post("/run", response_model=PythonRunResponse)
async def run_python_sandbox(request: PythonRunRequest, _=Depends(verify_admin)):
    """
    Run Python code in a sandbox (restricted to admin).
    """
    code = request.code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        # Run in the same environment to have access to installed packages
        # CWD to a temp dir might be safer
        result = await asyncio.to_thread(
            subprocess.run,
            ["python", temp_path],
            timeout=30,
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        
        output = result.stdout
        error = result.stderr if result.stderr else None

        from app.services.admin_audit import create_admin_action
        async with async_session() as db:
            await create_admin_action(
                db,
                action="python_run",
                target_type="system",
                metadata={
                    "code_snippet": code[:1000],
                    "has_error": error is not None,
                    "output_len": len(output)
                },
                commit=True
            )
        
        return PythonRunResponse(output=output, error=error)
        
    except asyncio.TimeoutError:
        return PythonRunResponse(output="", error="Error: Execution timed out after 30 seconds.")
    except Exception as e:
        return PythonRunResponse(output="", error=f"Error: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
