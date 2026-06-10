# Design: Auto Routing Model

## Objective
Add an admin-configured `Auto Router` model type that users can select like any other chat model. When selected, the backend classifies each incoming message with a cheap router model, then sends the real chat completion to the configured target model for the detected task.

## User Behavior
- Users see `Auto` or any admin-named auto router in the normal model picker.
- Users do not choose a provider for Auto at chat time.
- Auto makes a fresh routing decision per message, using the latest user message and compact chat context.
- The final answer comes from the selected target model, not from the router model.

## Admin Behavior
Inside the existing Models admin page:
- Add `Model type: Normal / Auto Router`.
- Normal models keep the current provider, pricing, context, default, active, and vision settings.
- Auto Router models configure:
  - `router_model_id`: active normal model used for classification.
  - `easy_model_id`: short/simple/low-risk tasks.
  - `medium_model_id`: general multi-step and moderate analysis tasks.
  - `hard_model_id`: deep reasoning, coding, complex planning, long synthesis.
  - `vision_model_id`: image or visual-understanding requests.
  - `research_model_id`: current-information, source-heavy, web/search-oriented requests.
  - `fallback_model_id`: used when routing fails or a bucket has no model.

## Routing Criteria
The router prompt must classify with a bounded JSON result:
- `difficulty`: `easy`, `medium`, or `hard`.
- `task_type`: one of `chat`, `writing`, `coding`, `analysis`, `research`, `vision`, `math`, `file_generation`, or `other`.
- `needs_vision`: true when image input or visual analysis is needed.
- `needs_research`: true when the answer likely needs current/external/source-based information.
- `matched_criteria`: compact list of criteria such as `short_answer`, `multi_step`, `coding`, `current_info`, `image_input`, `file_generation`, `high_accuracy`.
- `reason`: short admin-facing explanation.

Selection precedence:
1. If `needs_vision`, use `vision_model_id`.
2. Else if `needs_research`, use `research_model_id`.
3. Else route by `difficulty` to easy/medium/hard.
4. If the chosen bucket is empty or invalid, use `fallback_model_id`.
5. If fallback is invalid, use the first valid configured target.
6. Auto Router models must not target another Auto Router model.

## Backend Design
- Store the router configuration in `models.capabilities.auto_router`.
- Add a lightweight discriminator in `capabilities.model_type` with values `normal` and `auto_router`.
- Keep normal provider access centralized in `backend/app/llm.py`.
- Add a resolver that turns a selected model into an execution provider/model pair:
  - Normal selected model returns itself.
  - Auto Router selected model calls the router model, parses JSON, validates the chosen target, and returns the target normal model.
- Web chat and Telegram chat should use the same resolver when selecting models.
- Title generation should use the actual target model for that turn.
- Tool call trace `provider_name` and `model_name` should record the final target model.

## Error Handling
- If an Auto Router model is missing a router model or all target models, admin save should fail.
- If runtime routing fails, use fallback or first valid target.
- If the final target does not support image input and the request includes images, preserve the existing unsupported-image handling and model suggestions.
- Router JSON parsing must tolerate markdown fences and malformed output by falling back safely.

## Frontend Design
- `frontend-v2/src/components/config/ModelForm.tsx` gains a model type selector.
- Auto Router mode hides direct provider/pricing/context fields that do not apply to a virtual model and shows target model selectors.
- `ModelList` shows an `Auto` badge and still displays Active/Default state.
- Type definitions in `frontend-v2/src/lib/types.ts` understand nullable provider IDs and auto router capabilities.

## Verification
- Backend unit tests cover router config detection, JSON parsing fallback, target selection precedence, and prevention of nested auto-router target models.
- Backend import/startup check must pass.
- Frontend lint/build should run for the admin UI change when dependencies are available.
