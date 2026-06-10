import os
import shutil
import re
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Skill, CodexAccount
from app.services.codex_runtime import CODEX_ACCOUNTS_DIR

async def sync_codex_account_config(account: CodexAccount):
    """Ensures account-specific config.toml has browser_use and other features disabled."""
    if not account.codex_home:
        return
        
    config_path = Path(account.codex_home) / "config.toml"
    
    # Features to disable for users to restrict capabilities and reduce token overhead
    disabled_features = {
        "browser_use": "true",           # Enabled for web search
        "browser_use_external": "true",  # Enabled for web search
        "in_app_browser": "true",        # Enabled for web search
        "skill_mcp_dependency_install": "true", # Enabled for complex skills
        "hooks": "false",        # Disables automatic superpowers orientation (saves 50k+ tokens)
        "personality": "false",  # Disables personality-driven internal steps
        "artifact": "true",      # Enabled for file creation and PDF generation
    }
    
    if not config_path.exists():
        # Create a basic config
        features_str = "\n".join([f"{k} = {v}" for k, v in disabled_features.items()])
        config_content = f"[features]\n{features_str}\n"
    else:
        try:
            config_content = config_path.read_text(encoding="utf-8")
        except Exception:
            config_content = ""

        if "[features]" not in config_content:
            features_str = "\n".join([f"{k} = {v}" for k, v in disabled_features.items()])
            config_content += f"\n[features]\n{features_str}\n"
        else:
            # Update each feature in the section
            for feature, value in disabled_features.items():
                pattern = rf"^{feature}\s*="
                if re.search(pattern, config_content, re.MULTILINE):
                    config_content = re.sub(rf"^{feature}\s*=.*$", f"{feature} = {value}", config_content, flags=re.MULTILINE)
                else:
                    # Insert after [features] header
                    config_content = config_content.replace("[features]", f"[features]\n{feature} = {value}")

    try:
        config_path.write_text(config_content, encoding="utf-8")
    except Exception as e:
        print(f"Error writing config for account {account.id}: {e}")

async def sync_codex_system_skills(account: CodexAccount):
    """Deactivates specific native system skills for a Codex account."""
    if not account.codex_home:
        return
        
    system_skills_dir = Path(account.codex_home) / "skills" / ".system"
    if not system_skills_dir.exists():
        return
        
    skills_to_deactivate = [
        "openai-docs",
        "skill-creator",
        "skill-installer"
    ]
    
    for skill_name in skills_to_deactivate:
        skill_path = system_skills_dir / skill_name
        if skill_path.exists() and skill_path.is_dir():
            disabled_path = system_skills_dir / f"{skill_name}.disabled"
            try:
                if disabled_path.exists():
                    shutil.rmtree(disabled_path)
                shutil.move(str(skill_path), str(disabled_path))
            except Exception as e:
                print(f"Error deactivating system skill {skill_name} for account {account.id}: {e}")

async def sync_codex_account_skills(account: CodexAccount, active_skills: list[Skill]):
    """Syncs active skills to a specific Codex account's skills directory."""
    if not account.codex_home:
        return
        
    account_skills_dir = Path(account.codex_home) / "skills"
    account_skills_dir.mkdir(parents=True, exist_ok=True)
    
    # Get current skill directories in the account
    try:
        existing_dirs = {d.name: d for d in account_skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}
    except Exception:
        existing_dirs = {}
    
    active_skill_dirs = set()
    for skill in active_skills:
        if not skill.file_path or not os.path.exists(skill.file_path):
            continue
            
        skill_dir_name = os.path.basename(skill.file_path)
        active_skill_dirs.add(skill_dir_name)
        
        source_dir = Path(skill.file_path)
        target_dir = account_skills_dir / skill_dir_name
        
        # Sync the directory
        try:
            if target_dir.exists():
                # Simple check: if source is newer or we just want to be sure
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
        except Exception as e:
            print(f"Error syncing skill {skill.name} to account {account.id}: {e}")
        
    # Remove skills that are no longer active
    for name, path in existing_dirs.items():
        if name not in active_skill_dirs:
            try:
                shutil.rmtree(path)
            except Exception as e:
                print(f"Error removing old skill {name} from account {account.id}: {e}")

async def sync_all_codex_accounts(db: AsyncSession):
    """Main entry point to sync all Codex accounts in the pool."""
    # Fetch all Codex accounts
    result = await db.execute(select(CodexAccount))
    accounts = result.scalars().all()
    
    # Fetch all active skills
    skill_result = await db.execute(select(Skill).where(Skill.is_active == True))
    active_skills = skill_result.scalars().all()
    
    for account in accounts:
        # 1. Sync config (disable browser_use, etc.)
        await sync_codex_account_config(account)
        
        # 2. Sync system skills (deactivate specific ones)
        await sync_codex_system_skills(account)
        
        # 3. Sync custom skills from DB
        await sync_codex_account_skills(account, active_skills)

async def sync_skill_to_all_accounts(db: AsyncSession, skill: Skill):
    """Sync a specific skill to all accounts (called on update/upload)."""
    result = await db.execute(select(CodexAccount))
    accounts = result.scalars().all()
    
    # We still need to know all active skills to handle deletions/deactivations properly
    # but for a single update, we can just sync this one.
    # However, to be safe and simple, we'll just run the full sync.
    await sync_all_codex_accounts(db)
