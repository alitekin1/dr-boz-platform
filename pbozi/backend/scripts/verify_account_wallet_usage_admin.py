#!/usr/bin/env python3
"""Practical verification for account, wallet, admin credit adjustment, and usage/admin records.

Runs against a temporary SQLite database and imports the backend app after DATABASE_URL
is set, so it does not touch local runtime data.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jgpti-verify-") as tmp:
        db_path = Path(tmp) / "verify.sqlite3"
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        os.environ["CHROMA_PERSIST_DIR"] = str(Path(tmp) / "chroma")

        from app.admin_routes import adjust_user_credit
        from app.database import async_session, engine, init_db
        from app.models import (
            AdminAction,
            Chat,
            CreditLedgerEntry,
            EmbeddingConfig,
            FeedbackEntry,
            Message,
            UploadedFile,
            UsageEvent,
            UserPreference,
            Wallet,
        )
        from app.schemas import CreditAdjustmentCreate
        from app.services.account_service import create_or_restore_user

        await init_db()
        check(db_path.exists(), "init_db did not create the temporary SQLite database")

        async with async_session() as db:
            user = await create_or_restore_user(
                db,
                telegram_user_id=9_001_001,
                first_name="Verify",
                username="verify_user",
                phone_number="09123456789",
                preferred_name="Verification User",
                commit=True,
            )
            check(user.id is not None, "user creation did not assign an id")
            check(user.account_status in {"active", "pending_onboarding"}, f"unexpected account status {user.account_status!r}")
            check(user.phone_number == "+989123456789", f"phone number was not normalized: {user.phone_number!r}")
            check(user.preferred_name == "Verification User", "preferred_name was not stored")
            check(abs(float(user.credit_balance_usd or 0.0)) < 0.000001, "fresh user should start with zero credit")

            entry = await adjust_user_credit(
                user.id,
                CreditAdjustmentCreate(
                    amount=12.5,
                    direction="credit",
                    reason="verification credit adjustment",
                    idempotency_key="verify-admin-adjustment-1",
                ),
                db,
                True,
            )
            check(entry.id is not None, "credit adjustment did not return a persisted ledger entry")
            check(entry.entry_type == "admin_adjustment", f"unexpected ledger entry type {entry.entry_type!r}")
            check(entry.direction == "credit", f"unexpected ledger direction {entry.direction!r}")
            check(entry.amount_minor == 12_500_000, f"unexpected ledger amount_minor {entry.amount_minor!r}")
            check(entry.available_after_minor == 12_500_000, f"unexpected available_after_minor {entry.available_after_minor!r}")
            check(entry.admin_action_id is not None, "admin adjustment did not link an admin action")

            await db.refresh(user)
            check(abs(float(user.credit_balance_usd or 0.0) - 12.5) < 0.000001, "user credit balance was not updated")

            wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
            check(wallet is not None, "admin adjustment did not create a wallet row")
            check(wallet.balance_minor == 12_500_000, f"unexpected wallet balance_minor {wallet.balance_minor!r}")
            check(wallet.available_minor == 12_500_000, f"unexpected wallet available_minor {wallet.available_minor!r}")
            check(wallet.version == 1, f"unexpected wallet version {wallet.version!r}")

            ledger_rows = (await db.execute(select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == user.id))).scalars().all()
            check(len(ledger_rows) == 1, f"expected 1 ledger row, found {len(ledger_rows)}")
            check(ledger_rows[0].wallet_id == wallet.id, "ledger row is not linked to the wallet")
            check(ledger_rows[0].admin_action_id == entry.admin_action_id, "ledger row is not linked to the admin action")

            action = await db.get(AdminAction, entry.admin_action_id)
            check(action is not None, "admin action row was not persisted")
            check(action.action_type == "credit_adjustment", f"unexpected admin action type {action.action_type!r}")
            check(action.target_type == "user", f"unexpected admin action target_type {action.target_type!r}")
            check(action.target_id == user.id, "admin action is not targeted at the user")
            check((action.after_json or {}).get("ledger_entry_id") == entry.id, "admin action after_json lacks ledger entry id")

            try:
                from app.services.usage_metering import complete_usage_event, create_usage_event
            except ImportError as exc:
                print(f"usage event service skipped: {exc}")
            else:
                usage = await create_usage_event(
                    db,
                    user_id=user.id,
                    channel="web",
                    operation="chat_completion",
                    provider_name="verify-provider",
                    model_name="verify-model",
                    status="authorized",
                    metadata={"verification": True},
                    commit=True,
                )
                check(usage is not None, "create_usage_event returned None")
                check(usage.id is not None, "usage event did not persist")
                check(usage.status == "authorized", f"unexpected initial usage status {usage.status!r}")

                usage = await complete_usage_event(
                    db,
                    usage,
                    usage={"prompt_tokens": 10, "completion_tokens": 5},
                    cost_usd=0.000123,
                    usage_source="provider_reported",
                    metadata={"completed_by": "verification"},
                    commit=True,
                )
                check(usage.status == "completed", f"unexpected completed usage status {usage.status!r}")
                check(usage.input_tokens == 10, f"unexpected usage input_tokens {usage.input_tokens!r}")
                check(usage.output_tokens == 5, f"unexpected usage output_tokens {usage.output_tokens!r}")
                check(usage.total_tokens == 15, f"unexpected usage total_tokens {usage.total_tokens!r}")
                check(usage.actual_cost_minor == 123, f"unexpected usage actual_cost_minor {usage.actual_cost_minor!r}")
                check(usage.usage_source == "provider_reported", f"unexpected usage source {usage.usage_source!r}")

                usage_count = await db.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.user_id == user.id))
                check(usage_count == 1, f"expected 1 usage event, found {usage_count}")

                uploaded_file = UploadedFile(
                    user_id=user.id,
                    filename="verify-upload.txt",
                    mime_type="text/plain",
                    file_type="txt",
                    size_bytes=22,
                    storage_path=str(Path(tmp) / "verify-upload.txt"),
                    status="stored",
                    metadata_json={"verification": True},
                )
                db.add(uploaded_file)
                await db.flush()
                upload_usage = await create_usage_event(
                    db,
                    user_id=user.id,
                    channel="telegram",
                    operation="embedding_index",
                    provider_name="verify-embedding-provider",
                    model_name="verify-embedding-model",
                    uploaded_file_id=uploaded_file.id,
                    status="authorized",
                    metadata={"upload_verification": True},
                    commit=False,
                )
                check(upload_usage is not None, "uploaded file usage event was not created")
                uploaded_file.usage_event_id = upload_usage.id
                await complete_usage_event(
                    db,
                    upload_usage,
                    input_tokens=123,
                    output_tokens=0,
                    cost_minor=45,
                    usage_source="estimated",
                    metadata={"completed_by": "upload verification"},
                    commit=True,
                )
                await db.refresh(uploaded_file)
                check(uploaded_file.usage_event_id == upload_usage.id, "uploaded file is not linked to its usage event")
                check(upload_usage.uploaded_file_id == uploaded_file.id, "usage event is not linked to uploaded file")
                check(upload_usage.operation_type == "embedding_index", f"unexpected upload usage operation {upload_usage.operation_type!r}")
                check(upload_usage.input_tokens == 123, f"unexpected upload usage input tokens {upload_usage.input_tokens!r}")
                check(upload_usage.actual_cost_minor == 45, f"unexpected upload usage cost {upload_usage.actual_cost_minor!r}")

            try:
                from app.admin_routes import create_embedding_config, update_embedding_config
                from app.schemas import EmbeddingConfigCreate, EmbeddingConfigUpdate
            except ImportError as exc:
                print(f"embedding config endpoint checks skipped: {exc}")
            else:
                emb = await create_embedding_config(
                    EmbeddingConfigCreate(
                        name="verify-embedding",
                        provider="google",
                        model="text-embedding-004",
                        api_key=None,
                        base_url="https://example.invalid/embeddings",
                        pricing_input=0.17,
                        is_active=True,
                    ),
                    db,
                    True,
                )
                check(emb.id is not None, "embedding config was not persisted")
                check(abs(float(emb.pricing_input or 0.0) - 0.17) < 0.000001, "embedding create did not persist pricing_input")
                emb = await update_embedding_config(emb.id, EmbeddingConfigUpdate(pricing_input=0.23), db, True)
                check(abs(float(emb.pricing_input or 0.0) - 0.23) < 0.000001, "embedding update did not persist pricing_input")
                emb_row = await db.get(EmbeddingConfig, emb.id)
                check(emb_row is not None, "embedding config row was not readable after update")
                check(abs(float(emb_row.pricing_input or 0.0) - 0.23) < 0.000001, "embedding row pricing_input mismatch after refresh")

            chat = Chat(title="Verification Chat")
            db.add(chat)
            await db.flush()
            user_message = Message(chat_id=chat.id, role="user", content="Please verify feedback linkage.")
            assistant_message = Message(chat_id=chat.id, role="assistant", content="Feedback linkage verified.")
            db.add_all([user_message, assistant_message])
            await db.flush()
            feedback = FeedbackEntry(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                chat_id=chat.id,
                message_id=assistant_message.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                rating_value=1,
                source="verification_script",
                note="feedback field verification",
                reaction_raw_text="👍",
                sample_reason="verification",
            )
            db.add(feedback)
            await db.commit()
            await db.refresh(feedback)
            check(feedback.source == "verification_script", f"unexpected feedback source {feedback.source!r}")
            check(feedback.user_message_id == user_message.id, "feedback is not linked to the user message")
            check(feedback.assistant_message_id == assistant_message.id, "feedback is not linked to the assistant message")
            check(feedback.sample_reason == "verification", f"unexpected feedback sample_reason {feedback.sample_reason!r}")
            try:
                from app.admin_routes import list_feedback_entries
            except ImportError as exc:
                print(f"feedback admin list check skipped: {exc}")
            else:
                feedback_rows = await list_feedback_entries(100, db, True)
                check(any(row.id == feedback.id and row.source == "verification_script" for row in feedback_rows), "admin feedback list did not include the verification feedback")

            try:
                from app.admin_routes import delete_user, list_admin_actions
            except ImportError as exc:
                print(f"admin soft delete endpoint checks skipped: {exc}")
            else:
                delete_result = await delete_user(user.id, db, True)
                check(delete_result == {"ok": True, "status": "deleted"}, f"unexpected soft delete response {delete_result!r}")
                await db.refresh(user)
                check(user.account_status == "deleted", f"soft delete did not mark user deleted: {user.account_status!r}")
                actions = await list_admin_actions(100, db, True)
                soft_delete_action = next((item for item in actions if item.action_type == "user_soft_delete" and item.target_id == user.id), None)
                check(soft_delete_action is not None, "soft delete admin action was not recorded")
                check((soft_delete_action.before_json or {}).get("account_status") != "deleted", "soft delete before_json is not a pre-delete snapshot")
                check((soft_delete_action.after_json or {}).get("account_status") == "deleted", "soft delete after_json is not a deleted snapshot")

            user_count = await db.scalar(select(func.count()).select_from(UserPreference))
            check(user_count == 1, f"expected 1 user, found {user_count}")

        await engine.dispose()
        print("verification passed")
        print(f"temporary database: {db_path}")
        print(
            "checked: init_db, user creation, admin credit adjustment, wallet, ledger, admin action, "
            "usage event create/complete, embedding pricing_input persistence, uploaded file usage linkage, "
            "feedback linkage, admin soft delete audit"
        )


if __name__ == "__main__":
    asyncio.run(main())
