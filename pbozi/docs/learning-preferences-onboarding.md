# Learning Preferences Onboarding (AI-Driven)

## Goals

Build a skippable, conversational onboarding flow that:

1. collects user learning preferences via focused AI questions,
2. analyzes answers into a structured learner profile,
3. stores the profile in the database,
4. injects a personalization prompt into future LLM requests.

---

## Research Summary (Evidence-Based)

### 1) Active engagement improves outcomes
- Freeman et al. (PNAS, 2014) meta-analysis reports higher performance under active learning (`+0.47 SD`) and lower failure risk versus lecture-heavy modes.
- Design implication: onboarding should ask about interaction, check-ins, and active practice preference, not just passive content format.
- Source: https://math.stanford.edu/~conrad/papers/PNAS.pdf

### 2) Practice testing and spacing are broadly effective
- Dunlosky et al. (PSPI, 2013) rated `practice testing` and `distributed practice` as high-utility techniques across populations and settings.
- Design implication: onboarding must explicitly measure whether the user benefits from quizzes/checkpoints and repeated retrieval moments.
- Source: https://devblog.learnquebec.org/files/2021/02/Dunlosky-et-al.-2013.-Improving-Students-Learning-with-Effective-Learning-Techniques.pdf

### 3) “Learning styles” matching is weakly supported
- Pashler et al. conclude evidence is insufficient for strong learning-style matching claims; the literature has methodological weakness for meshing-style validation.
- Design implication: profile should avoid rigid labels (e.g., visual/auditory “types”) and focus on actionable instructional preferences (depth, sequencing, examples, practice, feedback cadence).
- Source: https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Pashler_McDaniel_Rohrer_Bjork_2009_PSPI.pdf

### 4) Perceived learning can differ from actual learning
- Deslauriers et al. (PNAS, 2019) show active methods can feel harder even while producing better learning.
- Design implication: onboarding analysis should not treat “easy/comfortable” as the only target; keep adaptive cognitive challenge where appropriate.
- Source: https://e.math.cornell.edu/sites/activelearn/active-learning-resources/active_learning_Deslauriers_et_al.pdf

### 5) Feedback quality matters
- Wisniewski et al. (Frontiers, 2020) meta-analysis shows medium overall effect of feedback (`d ~ 0.48`) with strong moderation by feedback type/information content.
- Design implication: include onboarding questions about preferred feedback frequency and granularity.
- Source: https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.03087/full

### 6) Self-explanation prompts have meaningful effect
- Bisra et al. (Educational Psychology Review, 2018) meta-analysis reports positive effect for prompted self-explanation (`g ~ 0.55`).
- Design implication: when user prefers this style, assistant can include reflective prompts (“why does this step work?”).
- Source: https://gwern.net/doc/psychology/spaced-repetition/2018-bisra.pdf

---

## Onboarding Question Structure

Current implementation uses five dimensions:

1. `real_world_examples`
2. `depth_preference`
3. `practice_preference`
4. `sequencing_preference`
5. `interaction_preference`

Behavior:
- ask one focused question at a time,
- allow free-text response,
- allow skip at any point,
- auto-finalize after enough coverage (`>=4`) and completion conditions,
- hard cap to avoid long onboarding (`<=6` answers).

---

## Analysis Logic

At finalize:
1. onboarding transcript is analyzed by LLM with strict JSON schema,
2. generated profile includes:
   - concise summary sentence,
   - prompt context for future personalization,
   - structured preferences map,
   - confidence score,
3. fallback heuristic profile is generated if LLM/provider is unavailable.

This guarantees deterministic behavior even without model access.

---

## Data Model Additions

`user_preferences` new fields:
- `learning_preferences_status`
- `learning_preferences_summary`
- `learning_preferences_prompt`
- `learning_preferences_profile_json`
- `learning_preferences_onboarding_json`
- `learning_preferences_completed_at`

`chats` new field:
- `user_preference_id` (optional link for persistent web personalization)

SQLite compatibility migration adds these columns automatically in `init_db`.

---

## API Flow

Account API endpoints:

- `GET /api/account/learning-preferences/by-telegram/{telegram_user_id}`
- `POST /api/account/learning-preferences/by-telegram/{telegram_user_id}/start`
- `POST /api/account/learning-preferences/by-telegram/{telegram_user_id}/turn`
- `POST /api/account/learning-preferences/by-telegram/{telegram_user_id}/skip`
- `POST /api/account/learning-preferences/by-telegram/{telegram_user_id}/finalize`

Also:
- `GET /api/account/learning-preferences/{user_id}`

`turn` request body:
```json
{ "message": "..." }
```

Skip request body (optional):
```json
{ "reason": "..." }
```

---

## Prompt Injection Runtime

`get_effective_system_prompt(...)` now appends a personalization block when:
- `user.learning_preferences_status == "completed"`, and
- summary/prompt fields exist.

Applied in:
- web chat path (`main_routes.py`) when user context is known,
- Telegram path (`bot.py`) via existing user object.

This makes personalization automatic for subsequent requests.

---

## Notes

- Onboarding is intentionally skippable.
- Profile is adaptive and revisitable (`start?restart=true`).
- The implementation avoids hard “learning style type” labels and prioritizes actionable instructional controls.
