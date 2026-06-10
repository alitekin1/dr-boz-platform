from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import call_llm, get_default_model
from app.models import UserPreference

ONBOARDING_VERSION = "learning_preferences_v2"
TARGET_QUESTION_COUNT = 4

_SKIP_KEYWORDS = {
    "skip",
    "later",
    "not now",
    "اسکیپ",
    "ردش کن",
    "بعدا",
    "بعداً",
    "فعلا نه",
    "فعلاً نه",
    "نمیخوام",
    "نمی‌خوام",
}

_FINISH_KEYWORDS = {
    "done",
    "finish",
    "enough",
    "تمام",
    "کافیه",
    "کافی",
    "تموم",
    "اتمام",
}

_INTERVIEWER_SYSTEM_PROMPT = (
    "You are an AI interviewer running a learning-preferences onboarding chat. "
    "The user should feel this is a normal, natural conversation. "
    "Your goal is to infer how this user learns best, based on exactly four answered questions. "
    "Rules: "
    "1) Ask only one question per turn. "
    "2) Keep each turn concise and conversational. "
    "3) Avoid numbered forms and avoid sounding like a survey. "
    "4) Across the full chat, cover these four areas: real-world examples, depth/brevity, practice/quizzes, sequencing (step-by-step vs overview-first). "
    "5) If the user's answer is vague, ask a clearer follow-up but still one question only. "
    "6) Match the user's language. If unknown, default to Persian (fa). "
    "7) Do not provide final analysis or summary."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_persian_text(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = _safe_str(raw_text)
    if not text:
        return None

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    candidate = match.group(0)
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return None
    return None


def _new_onboarding_state() -> dict[str, Any]:
    now = utcnow().isoformat()
    return {
        "version": ONBOARDING_VERSION,
        "started_at": now,
        "updated_at": now,
        "language_hint": None,
        "answers": [],
        "history": [],
        "dialogue": [],
        "session": {
            "target_questions": TARGET_QUESTION_COUNT,
            "asked_questions": 0,
            "last_assistant_question": None,
            "conversation_style": "natural_chat",
        },
    }


def _normalize_state(raw_state: Any) -> dict[str, Any]:
    state = raw_state if isinstance(raw_state, dict) else {}
    now = utcnow().isoformat()

    answers = state.get("answers") if isinstance(state.get("answers"), list) else []
    history = state.get("history") if isinstance(state.get("history"), list) else []
    dialogue = state.get("dialogue") if isinstance(state.get("dialogue"), list) else []

    session_raw = state.get("session") if isinstance(state.get("session"), dict) else {}
    session = {
        "target_questions": TARGET_QUESTION_COUNT,
        "asked_questions": int(session_raw.get("asked_questions") or 0),
        "last_assistant_question": _safe_str(session_raw.get("last_assistant_question")) or None,
        "conversation_style": "natural_chat",
    }

    # Backward compatibility: when old version has current_question.
    current_question = state.get("current_question") if isinstance(state.get("current_question"), dict) else None
    if current_question and not session["last_assistant_question"]:
        session["last_assistant_question"] = _safe_str(current_question.get("question")) or None

    normalized = {
        "version": ONBOARDING_VERSION,
        "started_at": state.get("started_at") or now,
        "updated_at": now,
        "language_hint": state.get("language_hint"),
        "answers": answers,
        "history": history,
        "dialogue": dialogue,
        "session": session,
    }
    return normalized


async def _resolve_llm_for_onboarding(db: AsyncSession):
    provider, model = await get_default_model(db)
    if not provider or not model:
        return None, None
    return provider, model


def _fallback_question(state: dict[str, Any], *, first_turn: bool = False) -> str:
    language_hint = _safe_str(state.get("language_hint")).lower()
    asked = int(((state.get("session") or {}).get("asked_questions") or 0))
    use_fa = language_hint != "en"

    fa_questions = [
        "برای فهم بهتر، ترجیح می‌دی مفاهیم با مثال واقعی توضیح داده بشن یا توضیح مفهومی برات کافیه؟",
        "معمولاً جواب کوتاه و خلاصه می‌خوای یا توضیح کامل و عمیق؟",
        "تمرین کوتاه یا سوال تستی چقدر به یادگیریت کمک می‌کنه؟",
        "برای شروع یک موضوع جدید، اول دید کلی رو می‌خوای یا مسیر قدم‌به‌قدم؟",
    ]
    en_questions = [
        "Do you learn better with concrete real-world examples, or conceptual explanations are enough?",
        "Do you usually prefer concise answers or detailed deep explanations?",
        "How much do short exercises or quiz-style checks help your learning?",
        "When starting a new topic, do you prefer a big-picture overview first or step-by-step guidance first?",
    ]

    if first_turn:
        if use_fa:
            return f"سلام. می‌خوام سبک یادگیریت رو تنظیم کنم تا جواب‌هام شخصی‌سازی بشه. {fa_questions[0]}"
        return f"Hi. I want to tune your learning profile so future responses are personalized. {en_questions[0]}"

    idx = max(0, min(asked, TARGET_QUESTION_COUNT - 1))
    if use_fa:
        return fa_questions[idx]
    return en_questions[idx]


def _build_interviewer_messages(state: dict[str, Any], *, user: UserPreference) -> list[dict[str, str]]:
    preferred_name = _safe_str(getattr(user, "preferred_name", None)) or _safe_str(getattr(user, "first_name", None)) or "User"
    answers_count = len(state.get("answers") or [])
    dialogue = state.get("dialogue") if isinstance(state.get("dialogue"), list) else []
    dialogue = dialogue[-14:]

    coaching_context = (
        f"Learner display name: {preferred_name}\n"
        f"Collected answers so far: {answers_count}/{TARGET_QUESTION_COUNT}\n"
        f"Current language hint: {_safe_str(state.get('language_hint')) or 'auto'}\n"
        "Default language: Persian unless user clearly uses another language.\n"
        "If this is the first turn, greet briefly and ask the first question in the same message."
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _INTERVIEWER_SYSTEM_PROMPT},
        {"role": "system", "content": coaching_context},
    ]
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        role = _safe_str(item.get("role"))
        content = _safe_str(item.get("content"))
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


async def _generate_interviewer_turn(
    db: AsyncSession,
    *,
    user: UserPreference,
    state: dict[str, Any],
    first_turn: bool = False,
) -> str:
    provider, model = await _resolve_llm_for_onboarding(db)
    if not provider or not model:
        return _fallback_question(state, first_turn=first_turn)

    try:
        messages = _build_interviewer_messages(state, user=user)
        text = await call_llm(provider, model.name, messages)
        cleaned = _safe_str(text)
        if cleaned:
            return cleaned
    except Exception:
        pass

    return _fallback_question(state, first_turn=first_turn)


def _record_history_event(state: dict[str, Any], *, role: str, text: str):
    history = state.get("history") if isinstance(state.get("history"), list) else []
    history.append({"role": role, "text": text, "at": utcnow().isoformat()})
    state["history"] = history[-80:]


def _append_dialogue(state: dict[str, Any], *, role: str, content: str):
    dialogue = state.get("dialogue") if isinstance(state.get("dialogue"), list) else []
    dialogue.append({"role": role, "content": content, "at": utcnow().isoformat()})
    state["dialogue"] = dialogue[-24:]


def _build_payload(user: UserPreference) -> dict[str, Any]:
    state = _normalize_state(getattr(user, "learning_preferences_onboarding_json", None))
    session = state.get("session") if isinstance(state.get("session"), dict) else {}
    next_question = _safe_str(session.get("last_assistant_question")) or None

    status = _safe_str(getattr(user, "learning_preferences_status", None)) or "not_started"
    answers_count = len(state.get("answers") or [])
    return {
        "status": status,
        "in_progress": status == "in_progress",
        "completed": status == "completed",
        "skipped": status == "skipped",
        "questions_answered": answers_count,
        "target_questions": TARGET_QUESTION_COUNT,
        "next_question": next_question,
        "summary": getattr(user, "learning_preferences_summary", None),
        "prompt_context": getattr(user, "learning_preferences_prompt", None),
        "profile": getattr(user, "learning_preferences_profile_json", None),
        "completed_at": getattr(user, "learning_preferences_completed_at", None),
    }


async def get_learning_preferences_status(user: UserPreference) -> dict[str, Any]:
    return _build_payload(user)


async def start_learning_preferences_onboarding(
    db: AsyncSession,
    *,
    user: UserPreference,
    restart: bool = False,
) -> dict[str, Any]:
    status = _safe_str(getattr(user, "learning_preferences_status", None))
    state = _normalize_state(getattr(user, "learning_preferences_onboarding_json", None))

    if status == "in_progress" and not restart:
        current = _safe_str(((state.get("session") or {}).get("last_assistant_question")))
        if current:
            user.learning_preferences_onboarding_json = state
            await db.commit()
            await db.refresh(user)
            return _build_payload(user)

    state = _new_onboarding_state()

    opening = await _generate_interviewer_turn(db, user=user, state=state, first_turn=True)
    if _is_persian_text(opening):
        state["language_hint"] = "fa"
    else:
        state["language_hint"] = "en"

    _append_dialogue(state, role="assistant", content=opening)
    _record_history_event(state, role="assistant", text=opening)
    state["session"]["asked_questions"] = 1
    state["session"]["last_assistant_question"] = opening

    user.learning_preferences_status = "in_progress"
    user.learning_preferences_onboarding_json = state
    await db.commit()
    await db.refresh(user)
    return _build_payload(user)


async def submit_learning_preferences_answer(
    db: AsyncSession,
    *,
    user: UserPreference,
    message: str,
) -> dict[str, Any]:
    text = _safe_str(message)
    if not text:
        raise ValueError("message is required")

    lowered = text.lower()
    if any(keyword in lowered for keyword in _SKIP_KEYWORDS):
        return await skip_learning_preferences_onboarding(db, user=user, reason="user_skip_keyword")

    if (_safe_str(getattr(user, "learning_preferences_status", None)) or "") != "in_progress":
        await start_learning_preferences_onboarding(db, user=user)

    state = _normalize_state(getattr(user, "learning_preferences_onboarding_json", None))
    if _is_persian_text(text):
        state["language_hint"] = "fa"

    last_question = _safe_str(((state.get("session") or {}).get("last_assistant_question")))
    if not last_question:
        last_question = await _generate_interviewer_turn(db, user=user, state=state, first_turn=True)
        _append_dialogue(state, role="assistant", content=last_question)
        _record_history_event(state, role="assistant", text=last_question)
        state["session"]["asked_questions"] = 1
        state["session"]["last_assistant_question"] = last_question

    answers = state.get("answers") if isinstance(state.get("answers"), list) else []
    answers.append(
        {
            "question": last_question,
            "answer": text,
            "answered_at": utcnow().isoformat(),
        }
    )
    state["answers"] = answers

    _append_dialogue(state, role="user", content=text)
    _record_history_event(state, role="user", text=text)

    # Explicit finish request after enough answers.
    if any(keyword in lowered for keyword in _FINISH_KEYWORDS) and len(answers) >= TARGET_QUESTION_COUNT:
        user.learning_preferences_onboarding_json = state
        await db.commit()
        await db.refresh(user)
        return await finalize_learning_preferences_onboarding(db, user=user)

    if len(answers) >= TARGET_QUESTION_COUNT:
        user.learning_preferences_onboarding_json = state
        await db.commit()
        await db.refresh(user)
        return await finalize_learning_preferences_onboarding(db, user=user)

    next_question = await _generate_interviewer_turn(db, user=user, state=state, first_turn=False)
    state["session"]["asked_questions"] = int(state["session"].get("asked_questions") or 0) + 1
    state["session"]["last_assistant_question"] = next_question
    _append_dialogue(state, role="assistant", content=next_question)
    _record_history_event(state, role="assistant", text=next_question)

    user.learning_preferences_status = "in_progress"
    user.learning_preferences_onboarding_json = state
    await db.commit()
    await db.refresh(user)
    return _build_payload(user)


async def _summarize_learning_profile(
    db: AsyncSession,
    *,
    user: UserPreference,
    state: dict[str, Any],
) -> dict[str, Any]:
    answers = state.get("answers") if isinstance(state.get("answers"), list) else []
    provider, model = await _resolve_llm_for_onboarding(db)

    fallback_profile = _fallback_profile_from_answers(answers)
    if not provider or not model:
        return fallback_profile

    qa_lines: list[str] = []
    for idx, item in enumerate(answers, start=1):
        if not isinstance(item, dict):
            continue
        q = _safe_str(item.get("question"))
        a = _safe_str(item.get("answer"))
        qa_lines.append(f"{idx}. question={q}\nanswer={a}")
    transcript = "\n\n".join(qa_lines) or "(no answers)"

    system_prompt = (
        "You are an educational personalization analyst. "
        "Given onboarding answers, infer how the learner should be taught by an AI tutor. "
        "Return strict JSON only with this schema: "
        "{"
        "\"summary\": string,"
        "\"prompt_context\": string,"
        "\"preferences\": {"
        "\"real_world_examples\": string,"
        "\"depth\": string,"
        "\"practice\": string,"
        "\"sequencing\": string,"
        "\"interaction\": string"
        "},"
        "\"confidence\": number"
        "}. "
        "Use neutral evidence-based language. Do not label the learner with unsupported 'learning style' categories."
    )

    user_prompt = (
        f"User preferred name: {_safe_str(getattr(user, 'preferred_name', None)) or 'unknown'}\n"
        f"Onboarding transcript:\n{transcript}\n\n"
        "Requirements:\n"
        "- summary: one concise sentence describing how this user learns best.\n"
        "- prompt_context: short instruction paragraph for system prompt injection.\n"
        "- confidence: value from 0 to 1 based on answer quality/coverage.\n"
        "- If evidence is weak, explicitly say preferences are tentative in summary."
    )

    try:
        raw = await call_llm(
            provider,
            model.name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        parsed = _extract_json_object(raw)
        if not parsed:
            return fallback_profile

        summary = _safe_str(parsed.get("summary")) or fallback_profile["summary"]
        prompt_context = _safe_str(parsed.get("prompt_context")) or fallback_profile["prompt_context"]
        preferences = parsed.get("preferences") if isinstance(parsed.get("preferences"), dict) else fallback_profile["preferences"]

        confidence_raw = parsed.get("confidence")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = float(fallback_profile.get("confidence") or 0.5)
        confidence = max(0.0, min(confidence, 1.0))

        return {
            "summary": summary,
            "prompt_context": prompt_context,
            "preferences": preferences,
            "confidence": confidence,
            "answers_count": len(answers),
        }
    except Exception:
        return fallback_profile


def _fallback_profile_from_answers(answers: list[Any]) -> dict[str, Any]:
    joined_answers = " ".join(
        _safe_str(item.get("answer"))
        for item in answers
        if isinstance(item, dict)
    ).lower()

    wants_examples = any(token in joined_answers for token in ["example", "real", "scenario", "مثال", "واقعی", "سناریو"])
    wants_brief = any(token in joined_answers for token in ["brief", "short", "concise", "خلاصه", "کوتاه"])
    wants_practice = any(token in joined_answers for token in ["quiz", "test", "practice", "تمرین", "آزمون", "سوال"])
    wants_step = any(token in joined_answers for token in ["step", "step-by-step", "مرحله", "گام"])
    wants_big_picture = any(token in joined_answers for token in ["overview", "big picture", "کلی", "تصویر کلی"])

    depth_pref = "concise-first" if wants_brief else "detailed"
    sequencing_pref = "step-by-step" if wants_step and not wants_big_picture else "overview-then-detail"

    summary = "This user learns best with"
    summary += " real-life examples," if wants_examples else " clear conceptual explanations,"
    summary += f" {depth_pref} explanations,"
    summary += " regular practice checkpoints," if wants_practice else " occasional understanding checks,"
    summary += f" and a {sequencing_pref} teaching flow."

    prompt_context = (
        "Personalize responses for this user: "
        f"use {'concrete real-life examples' if wants_examples else 'clear conceptual framing'}, "
        f"start {'concise then expand' if wants_brief else 'with full depth unless asked shorter'}, "
        f"include {'small practice questions/checkpoints' if wants_practice else 'light comprehension checks'}, "
        f"and follow {'step-by-step sequencing' if sequencing_pref == 'step-by-step' else 'big-picture then stepwise detail'}."
    )

    return {
        "summary": summary,
        "prompt_context": prompt_context,
        "preferences": {
            "real_world_examples": "preferred" if wants_examples else "neutral",
            "depth": depth_pref,
            "practice": "preferred" if wants_practice else "neutral",
            "sequencing": sequencing_pref,
            "interaction": "adaptive",
        },
        "confidence": 0.45,
        "answers_count": len(answers),
    }


async def finalize_learning_preferences_onboarding(
    db: AsyncSession,
    *,
    user: UserPreference,
) -> dict[str, Any]:
    state = _normalize_state(getattr(user, "learning_preferences_onboarding_json", None))
    profile = await _summarize_learning_profile(db, user=user, state=state)

    user.learning_preferences_status = "completed"
    user.learning_preferences_summary = _safe_str(profile.get("summary")) or None
    user.learning_preferences_prompt = _safe_str(profile.get("prompt_context")) or None
    user.learning_preferences_profile_json = {
        "version": ONBOARDING_VERSION,
        "preferences": profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {},
        "confidence": profile.get("confidence"),
        "answers_count": profile.get("answers_count"),
        "finalized_at": utcnow().isoformat(),
        "target_questions": TARGET_QUESTION_COUNT,
    }
    user.learning_preferences_completed_at = utcnow()
    user.learning_preferences_onboarding_json = {
        "version": ONBOARDING_VERSION,
        "phase": "finalized",
        "answers": state.get("answers") if isinstance(state.get("answers"), list) else [],
        "history": state.get("history") if isinstance(state.get("history"), list) else [],
        "dialogue": state.get("dialogue") if isinstance(state.get("dialogue"), list) else [],
        "finalized_at": utcnow().isoformat(),
        "target_questions": TARGET_QUESTION_COUNT,
    }

    await db.commit()
    await db.refresh(user)
    return _build_payload(user)


async def skip_learning_preferences_onboarding(
    db: AsyncSession,
    *,
    user: UserPreference,
    reason: str | None = None,
) -> dict[str, Any]:
    user.learning_preferences_status = "skipped"
    user.learning_preferences_summary = None
    user.learning_preferences_prompt = None
    user.learning_preferences_profile_json = None
    user.learning_preferences_completed_at = None
    user.learning_preferences_onboarding_json = {
        "version": ONBOARDING_VERSION,
        "phase": "skipped",
        "reason": _safe_str(reason) or "user_requested",
        "at": utcnow().isoformat(),
        "target_questions": TARGET_QUESTION_COUNT,
    }

    await db.commit()
    await db.refresh(user)
    return _build_payload(user)
