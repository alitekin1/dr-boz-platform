# Telegram Bot Menu UX Audit

Source-simulated from `backend/app/bot.py` on 2026-04-23. This is a code-path audit, not a live Telegram session. The bot was not connected to Telegram, and no real updates were sent.

## Implementation Status (2026-04-23)

Implemented in `backend/app/bot.py` after this audit:

- Visible cancel controls in contact/name onboarding and account name edit flows.
- Learning onboarding cancel now persists a skipped state (`skip_learning_preferences_onboarding`).
- Learning tab `in_progress` rendering bug fixed.
- Chat list now filters by owner for non-admin users; `open_{chat_id}` now enforces access checks.
- Bot-created private chats now set `Chat.user_preference_id`.
- `doc_{id}` callbacks now resolve and show document details safely.
- Upload prompt now restores project keyboard for back navigation.
- Retry upload callback payload now respects Telegram 64-byte `callback_data` limit.
- Group opt-in panel has inline return to main menu (`cancel_main`).
- Group opt-in enable now verifies actual Telegram group membership.
- Group text turns require active payer membership before triggering billed group answers.
- `/group_usage` is restricted to admin or active billing members.
- Group setup duplicate announcements reduced by keeping `MY_CHAT_MEMBER` as canonical announcer.
- Admin provider/model lists now enforce admin checks.
- Admin provider/model/tool/binding deletes now use confirmation callbacks and catch `IntegrityError`.
- Admin provider/model creation flows now cancel safely on navigation and handle duplicate-save `IntegrityError`.
- Admin conversations now treat any command as cancel while the flow is active.
- Additional race-safe `IntegrityError` handling added for prompt default creation, admin prompt save, embedding save, tool save, and binding save.

Still open for future UX cleanup (not required for correctness/security):

- Add richer inline back-to-parent menus for some admin/project panels where reply keyboard remains the primary escape path.
- Add explicit end-to-end Telegram callback integration tests (current regression checks are helper/menu-shape checks).

## Scope

The audit follows every visible Telegram menu shape and callback path in the bot:

- Private `/start`, onboarding, contact sharing, account, wallet, learning preference flow.
- Main chat, chat list, model picker, projects, project files, uploads, photos, voice, retry buttons.
- Admin reply keyboard and admin inline menus for providers, models, prompts, tools, embeddings, users.
- Group setup, group opt-in, group trigger messages, and `/group_usage`.

For each menu, the same questions were asked:

- What does the user see?
- What happens if the user clicks each button?
- What happens if the user wants to go back?
- What stale state or access issue can survive after navigation?
- Which buttons are dead, destructive, or misleading?

## Menu Shapes

### Main Private Menu

Defined by `main_kb()` in `backend/app/bot.py`.

```text
[💬 چت جدید]      [📋 چت‌ها]
[📁 پروژه‌ها]     [🤖 مدل]
[👤 حساب کاربری]  [🔧 مدیریت]   admin only
```

Non-admin users only get `👤 حساب کاربری` on the last row.

### Project Menu

Defined by `project_kb()`.

```text
[💬 شروع گفتگو]  [📂 فایل‌ها]
[🔙 خروج پروژه]
```

This reply keyboard replaces the main keyboard after choosing or creating a project.

### Admin Menu

Defined by `ADMIN_KB`.

```text
[➕ پروایدر]       [➕ مدل]
[📋 پروایدرها]    [📋 مدل‌ها]
[🗑 حذف پروایدر]  [🗑 حذف مدل]
[📝 سیستم پرامپت] [👥 یوزرها]
[🧰 ابزارها]      [🔮 Embedding]
[🔙 منوی اصلی]
```

### Account Inline Menu

Defined by `_account_nav_kb()` and `_account_kb()`.

Base navigation:

```text
[👤/✅ خلاصه حساب]  [🧾/✅ پروفایل]
[💳/✅ کیف پول]     [🧠/✅ سبک یادگیری]
[📜/✅ تراکنش‌ها]   [🔄 بروزرسانی]
```

Extra buttons:

- Home/Profile: `[✏️ تغییر اسم] [📱 تغییر شماره]`
- Credit: `[➕ شارژ حساب]`
- Learning not started: `[▶️ شروع تنظیمات]`
- Learning in progress: `[💬 ادامه گفت‌وگو]`, `[⏭️ رد فعلاً] [🔄 شروع مجدد]`
- Learning completed: `[🔄 بازطراحی ترجیحات]`

### Model Inline Menu

The `🤖 مدل` button first shows active providers:

```text
[provider name]
[provider name]
...
```

Choosing a provider shows active models:

```text
[model name]
[model name]
[🔙 پروایدرها]
```

There is no inline return to the main menu.

### Chats Inline Menu

The `📋 چت‌ها` button shows paginated chat titles:

```text
[chat title]
[chat title]
...
[⬅️ قبلی] [📄 page/total] [بعدی ➡️]
```

The page indicator is a no-op callback.

### Projects Inline Menu

The `📁 پروژه‌ها` button shows projects:

```text
[project name]
[project name]
[➕ ساخت پروژه]  admin only
```

There is no inline back button. The main reply keyboard remains visible unless another flow replaced it.

### Project Files Inline Menu

The `📂 فایل‌ها` button shows:

```text
[📄 filename]
[📄 filename]
[📤 آپلود فایل]
```

If there are no documents:

```text
[📤 آپلود فایل]
```

### Admin Tools Inline Menu

Defined by `_tools_menu_kb()`.

```text
[📌 خلاصه]          [📊 گزارش کامل]
[🔗 بایندینگ‌ها]   [🔁 همگام‌سازی builtin]
[➕ ابزار جدید]    [➕ بایندینگ]
[🗑 حذف ابزار]     [🗑 حذف بایندینگ]
```

Tools submenus have some local back buttons, usually `🔙 منوی ابزارها` or `🔙 لیست ابزارها`.

### Prompt Inline Menu

Defined by `_build_prompt_admin_text_and_kb()`.

```text
[✏️ ویرایش پرامپت]
[⏸/▶️ راهنمای خودکار]
[compact] [detailed]
[✏️ تنظیم قالب راهنما] [♻️ حذف قالب]
[🔄 تازه‌سازی]
```

There is no inline back to the admin menu.

### Embedding Inline Menu

Defined by `admin_embedding()`.

```text
[✏️ تغییر مدل]
[✏️ تغییر API Key]
[✏️ تغییر Base URL]
```

There is no inline back/cancel button.

### Group Opt-In Inline Menu

Defined by `_group_optin_keyboard()`.

```text
[✅ فعال / فعال‌سازی پرداخت سهمی] [⛔ غیرفعال‌سازی]
[🔄 بروزرسانی]
```

There is no inline back to private main menu.

## Scenario Walkthrough

### `/start`

Path: `cmd_start()`.

- If payload starts with `groupoptin_`, private chat shows the group opt-in panel after onboarding.
- If the user is not onboarded, the bot prompts for phone/name.
- If the user is onboarded, the bot shows the main reply keyboard.
- If no active model exists, the bot says no model is configured and shows the main reply keyboard.

Back question:

- On the normal main menu, reply-keyboard navigation works.
- In onboarding, there is no visible back/cancel control. A user can send `/start` again, but that restarts the same decision path.
- If the group opt-in deep link hits onboarding first, the group intent is not resumed automatically after phone/name completion.

### Onboarding Contact And Name

Paths: `_prompt_onboarding()`, `share_contact_request`, `handle_contact()`, `asking_name` in `handle_message()`.

- Initial onboarding uses inline `[📱 شماره تماس]`.
- Clicking it deletes the prompt and shows a Telegram reply keyboard with only `[📱 شماره منو بفرست]`.
- Sending a valid own contact stores phone.
- If preferred name is missing, the bot asks free text: `حالا دوست داری چی صدات کنم؟`
- Sending a name stores it and returns to main menu.

Back question:

- The contact-sharing step has no visible `لغو`, `بازگشت`, or main-menu button.
- The name step also has no visible cancel/back button.
- Typed `❌ لغو` works globally in `handle_message()`, but the UI does not show it.
- When only the name is missing, `_prompt_onboarding()` still attaches the contact inline keyboard, which does not match the prompt.

Change needed:

- Use a different keyboard when only `need_name=True`.
- Add a visible cancel/back option for contact and name flows.
- Preserve and resume group opt-in payload after onboarding, or tell users to reopen the group link.

### Account Home/Profile/Credit/Transactions

Paths: `cmd_account()`, account callbacks.

- `👤 حساب کاربری` or `/account` shows account home.
- Inline navigation edits the same message for profile, credit, transactions, learning, or refresh.
- `✏️ تغییر اسم` deletes the account panel and asks for a new name.
- `📱 تغییر شماره` deletes the panel and switches to the one-button contact keyboard.
- `➕ شارژ حساب` only replies that top-up is coming soon.

Back question:

- Main reply keyboard may still be visible, but the inline account panel is deleted for name/contact changes.
- After changing phone from the account panel, the user returns to main menu, not the account panel.
- There is no visible inline "back to account" after entering free-text/contact mode.

Change needed:

- Keep account-return context for phone changes, matching `account_set_name_return`.
- Show a cancel/back control and redraw account home when canceled.

### Account Learning

Paths: `_account_learning_text()`, `_account_kb()`, `account_learning_*`, `learning_onboarding_active`.

- `▶️ شروع تنظیمات` starts or resumes a conversational learning onboarding session.
- The account panel is deleted and the bot asks natural-language questions.
- Text answers are stored until the service completes the profile.
- `⏭️ رد فعلاً` persists a skipped state.
- `🔄 شروع مجدد` restarts.
- `account_learning_finalize` exists in the dispatcher but no visible button emits it.

Back question:

- There is no visible cancel/back button during the chat-like learning session.
- Typed `❌ لغو` clears only transient Telegram state and returns to main menu. It does not persist a skipped/canceled learning state, so account may later resume as in progress.

Bug:

- `_account_learning_text()` has an unreachable `in_progress` branch because it is indented after a return in the completed branch. Active sessions can display the generic "not started" explanation while the keyboard shows in-progress controls.

Change needed:

- Move the `in_progress` branch outside the completed branch.
- Decide whether `❌ لغو` should call `skip_learning_preferences_onboarding()` or only pause. Then show that behavior explicitly.
- Remove or surface `account_learning_finalize`.

### New Chat

Path: `cmd_new()`.

- Clears transient state and pending uploads.
- Selects an active model if needed.
- Sets `current_chat_id=None`.
- Replies with main menu and greeting.
- The chat row is not created until the user sends a message.

Back question:

- Already on main menu. No issue.

Change needed:

- If chat ownership is enforced later, make sure auto-created chats set `user_preference_id`.

### Chat List

Paths: `cmd_chats()`, `_build_chats_page_text_and_kb()`, `open_`, `chats_page_*`.

- `📋 چت‌ها` shows a paginated inline list of chats with at least one user message.
- Previous/next edits the same list.
- Clicking a chat sets `current_chat_id` and replies with the title.

Back question:

- There is no inline back to main, but the main reply keyboard usually remains.

Bug/security issue:

- The chat list is global. It is not filtered by the current user.
- `open_{chat_id}` trusts arbitrary chat IDs and does not verify ownership.
- Bot-created chats do not consistently set `Chat.user_preference_id`, so ownership cannot be relied on from current bot writes.

Change needed:

- Set `Chat.user_preference_id=user.id` whenever the bot creates a chat.
- Filter chat list by current user.
- Reject `open_` callbacks for chats the user does not own or cannot access.

### Model Picker

Paths: `cmd_model()`, `mprov_*`, `model_*`, `mprov_back`.

- `🤖 مدل` shows provider buttons.
- Choosing a provider shows its model buttons.
- `🔙 پروایدرها` returns to provider list.
- Choosing a model stores it on the user and updates the active chat model if one is selected.

Back question:

- There is no inline main-menu back.
- The reply keyboard usually remains available.

UX issue:

- If deleting the picker message succeeds after `model_*`, there is no visible confirmation. The menu simply disappears.

Change needed:

- Send or edit a short confirmation after model selection.

### Projects

Paths: `cmd_projects()`, `proj_*`, `new_project`, `creating_project`.

- `📁 پروژه‌ها` lists every project.
- Clicking a project stores it as `current_project_id` and switches to the project reply keyboard.
- Admins see `➕ ساخت پروژه`.
- New project asks for free-text name, then creates and selects it.

Back question:

- Project list has no inline back. Main reply keyboard usually remains.
- Project creation has no visible cancel/back, unless the reply keyboard still has a back button.

Bug/security issue:

- Project list is global.
- `proj_{id}` trusts arbitrary project IDs.
- Non-admin users can select any project row that exists.

Change needed:

- Filter projects by ownership/sharing rules.
- Validate `proj_` callbacks against the same access rules.
- Add visible cancel/back for project creation.

### Project Mode And Files

Paths: `cmd_start_convo()`, `cmd_project_files()`, `upload_file`, `doc_*`, `handle_document()`, `cmd_exit_project()`.

- `💬 شروع گفتگو` creates a new project chat and sets it current.
- `📂 فایل‌ها` lists documents and upload button.
- `📤 آپلود فایل` deletes the file list and asks the user to send a file.
- Sending `pdf`, `txt`, or `md` inside a selected project downloads and indexes into RAG.
- Unsupported extensions are not indexed.
- `🔙 خروج پروژه` clears current project and returns to main menu.

Back question:

- Project reply keyboard gives `🔙 خروج پروژه`.
- The upload prompt itself does not show a cancel/back button.

Bug:

- Document buttons use callback data `doc_{id}`, but `button_callback()` has no `doc_` handler. Clicking a document button only acknowledges the callback and otherwise does nothing.

Change needed:

- Add a `doc_` handler showing document metadata/actions, or remove document buttons and render documents as text.
- Add visible cancel/back around upload prompt.

### Document Upload Outside Project

Path: `handle_document()` with no `current_project_id`.

- Supported files are downloaded and text is extracted.
- With caption, the caption becomes the question and the file content is injected into model context.
- Without caption, the bot stores `pending_file` and asks what the user wants to do next.

Back question:

- No visible cancel/back in the pending-file prompt.
- `pending_file` is popped only when the next generic text message reaches `handle_message()`.
- Some reply-keyboard navigation handlers do not clear pending media state, so a later normal text can be misinterpreted as a question about an old file.

Change needed:

- Clear pending file/photo state in every navigation handler, not just some.
- Show an explicit cancel action after file/photo pending prompts.

### Photo Upload

Path: `handle_photo()`.

- Requires an existing current chat. If none, replies `اول یه چت شروع کن! 💬`.
- With caption, answers using vision content.
- Without caption, stores `pending_photo` and asks what the user wants to know.
- `retry_photo` only asks the user to resend the photo.

Back question:

- No visible cancel/back in the pending-photo prompt.
- Same stale pending-state issue as files.

Change needed:

- Clear pending photo on all navigation.
- Add visible cancel/back.
- Consider auto-creating a chat for photos, matching document/text behavior.

### Voice Upload

Path: `handle_voice()`.

- Requires onboarding and active transcription config/API key.
- Estimates and checks credit.
- Downloads voice, transcribes with Gemini, charges the user, then treats transcript as a chat text turn.

Back question:

- No menu is entered. Failure states reply as text.

Change needed:

- No menu-specific change required, but errors could include main menu reply markup.

### Rating Prompt

Path: `_maybe_request_rating()`, `rate_*`.

- Occasionally asks `این پاسخ مفید بود؟`
- Inline buttons are `👍` and `👎`.
- Clicking stores feedback, removes buttons, replies thanks.

Back question:

- No back needed; optional prompt.

Change needed:

- No immediate menu change.

### Admin Panel

Path: `admin_panel()`.

- `🔧 مدیریت` shows counts, prompt preview, and `ADMIN_KB`.
- `🔙 منوی اصلی` returns to main keyboard.

Back question:

- Works from the admin menu.

Change needed:

- Ensure every admin submenu either keeps a visible admin reply keyboard or has inline back.

### Admin Provider/Model Add Conversations

Paths: `prov_conv`, `model_conv`.

- `➕ پروایدر` asks name, base URL, API key.
- `➕ مدل` asks model name, display name, provider ID, input price, output price, context window.
- `/cancel` or text starting with `🔙` cancels.

Back question:

- The bot does not visibly tell the admin that `/cancel` or `🔙` is the escape route.
- Because the conversation accepts all non-command text, clicking another reply-keyboard button mid-flow can be saved as a provider/model field instead of navigating.

Change needed:

- Add visible cancel/back button to every conversation step.
- Treat navigation texts as cancel before storing form fields.

### Admin Provider/Model List/Delete

Paths: `admin_list_providers()`, `admin_list_models()`, `admin_delete_provider()`, `admin_delete_model()`, `delprov_*`, `delmodel_*`.

- Lists providers/models as plain messages.
- Delete menus show one inline delete button per row.
- Clicking delete immediately deletes.

Back question:

- Provider/model delete menus have no inline back.
- The admin reply keyboard usually remains visible.

Bug/security issue:

- `admin_list_providers()` and `admin_list_models()` do not check `ADMIN_ID`, even though their buttons are in the admin keyboard. A non-admin can send the exact text and receive provider/model inventory.
- Delete actions are one-tap destructive and do not catch database integrity errors.

Change needed:

- Add admin checks to provider/model list handlers.
- Add confirmation callbacks for delete.
- Catch `IntegrityError` and show a safe error.
- Add inline back to admin menu for delete screens.

### Admin Prompt

Paths: `admin_show_prompt()`, `edit_prompt`, `prompt_*`, `editing_prompt`, `editing_tool_guidance_template`.

- Shows prompt and tool-guidance settings.
- Edit prompt and edit template delete the panel and ask for free text.
- Toggle/style/reset/refresh edit the panel.

Back question:

- No inline back.
- Free-text edit modes do not show a cancel button.
- Some navigation texts can be swallowed or leave state active if handled by another admin menu handler before generic `handle_message()`.

Change needed:

- Add visible cancel/back to edit modes.
- Clear transient state at the start of all admin navigation handlers.

### Admin Tools

Paths: `admin_tools_menu()`, `tools_*`, tool creation modes, binding creation modes.

- Tools summary/report/bindings/sync all work via inline callbacks.
- Add custom tool asks name, description, display name, kind, implementation key, input schema JSON.
- Add binding asks tool, scope type, and optional scope ID.
- Delete tool/binding deletes immediately.
- Toggle binding flips enabled state.

Back question:

- Some tools screens have local inline back.
- Add tool/add binding free-text flows have no visible cancel/back.
- Navigation during those flows can leave stale state unless the specific navigation handler clears transient flags.

Change needed:

- Add cancel/back controls to every free-text step.
- Clear transient admin state on every admin menu command.
- Add confirmation before delete.

### Admin Embedding

Paths: `admin_embedding()`, `emb_set_model`, `emb_set_key`, `emb_set_url`, setting modes.

- Shows current embedding config.
- Each edit button deletes the panel and asks for one text value.

Back question:

- No visible cancel/back.
- API key is requested in Telegram chat text.

Change needed:

- Add cancel/back controls.
- Consider whether secret entry through Telegram chat is acceptable. If it remains, delete or redact the key message where possible.

### Group Bot Added

Paths: `handle_group_new_members()`, `handle_my_chat_member()`, `_send_group_setup_message()`.

- When the bot is added to a group, it creates/updates a `TelegramGroup`.
- It sends a setup message with a deep link to private opt-in.

Back question:

- Not applicable inside group setup message.

Bug:

- Both `NEW_CHAT_MEMBERS` and `MY_CHAT_MEMBER` handlers can send setup messages for the same add event, causing duplicate group activation messages.

Change needed:

- Make group setup message idempotent per group/join event.

### Group Opt-In

Paths: `/start groupoptin_{group_id}`, `_show_group_optin_panel()`, `groupopt_*`.

- Private deep link shows group name, current opt-in state, active payer count, and enable/disable/refresh buttons.
- Enable/disable toggles the caller's `TelegramGroupMember.shared_billing_enabled`.
- Refresh redraws the same panel.

Back question:

- No inline back/main-menu button.
- If onboarding interrupts the deep link, the bot does not resume the group opt-in panel afterward.

Bug/security issue:

- The callback does not verify that the user is actually a member of the Telegram group.
- Anyone with a valid link or guessed group ID can toggle themselves into that group's payer list.

Change needed:

- Verify group membership before opt-in, or require a fresh signed token tied to the deep link.
- Add inline return to main menu/account.
- Preserve deep-link intent through onboarding.

### Group Triggered Chat

Path: `_process_group_text_turn()`.

- In group chats, messages are ignored unless they begin with a configured trigger phrase.
- If trigger has no question, bot asks for a question after the trigger.
- Trigger user must be onboarded.
- Active payer count must meet minimum.
- Estimated split precheck must pass.
- Bot runs the model and charges active opted-in payers.

Back question:

- Not a menu flow.

Bug/billing issue:

- The triggering user does not have to be one of the opted-in payers. A non-paying onboarded member can trigger a response paid by other active payers.

Change needed:

- Require trigger user to be opted in, or explicitly allow sponsor-pool behavior and say so in group setup text.

### `/group_usage`

Path: `cmd_group_usage()`.

- Only checks that the command is sent inside a group.
- Returns group request count, total group cost, active payer count, caller share, and recent events.

Back question:

- Not a menu flow.

Security/visibility issue:

- Any group member can view group billing totals unless Telegram command visibility is separately restricted.

Change needed:

- Decide intended audience. If private, require group admin or active payer status.

## Back/Cancel Matrix

| Flow | Current back/cancel behavior | Problem |
| --- | --- | --- |
| Main menu | Reply keyboard navigation | Fine |
| Project mode | `🔙 خروج پروژه` | Fine for project exit |
| Contact sharing | No visible back; only resend `/start` or type hidden cancel | User can feel stuck |
| Name entry | Hidden `❌ لغو`; no visible cancel | User can feel stuck |
| Account learning session | Hidden `❌ لغو`; does not persist skip/cancel | State can resume unexpectedly |
| Model picker | Provider back only | No main inline back; selection can silently disappear |
| Chat list | No inline back | Usually okay only if main reply keyboard remains |
| Project list | No inline back | Usually okay only if main reply keyboard remains |
| Upload file prompt | No visible cancel/back | User can feel stuck |
| Pending file/photo question | Hidden cancel; stale state can survive navigation | Later text can target old media |
| Admin provider/model conversations | `/cancel` or `🔙`, not shown clearly | Other menu buttons can become form values |
| Admin prompt/template/embedding/tool free-text modes | Hidden cancel/back, inconsistent state clearing | Back can look dead; stale mode can survive |
| Delete provider/model/tool/binding | No confirmation; immediate delete | Accidental destructive action |
| Group opt-in | No inline back/main | Deep-link panel is not self-contained |

## Highest Priority Changes

1. Enforce chat ownership:
   - Set `Chat.user_preference_id` when the bot creates chats.
   - Filter `📋 چت‌ها` by the current user.
   - Validate `open_` callbacks against ownership/access.

2. Enforce project access:
   - Filter `📁 پروژه‌ها` by owner/share permissions.
   - Validate `proj_` callbacks before setting `current_project_id`.

3. Fix group billing authorization:
   - Verify group membership before `groupopt_*`.
   - Decide whether non-payers can trigger shared-billing responses; if not, require trigger user to be an active payer.
   - Restrict `/group_usage` if billing totals are not public to the whole group.

4. Fix admin exposure:
   - Add `ADMIN_ID` checks to `admin_list_providers()` and `admin_list_models()`.
   - Add confirmation and integrity-error handling for destructive delete callbacks.

5. Fix learning tab bug:
   - Move `_account_learning_text()` in-progress branch outside the completed branch.

6. Add a unified cancel/back pattern:
   - Add visible `❌ لغو` or `🔙 بازگشت` controls to contact/name/upload/admin free-text modes.
   - On cancel, redraw the previous panel when possible.
   - Clear transient state at the beginning of every reply-keyboard navigation handler, not just some.

7. Fix dead document buttons:
   - Implement `doc_{id}` callback handling or remove those inline buttons.

8. Make group setup idempotent:
   - Avoid duplicate setup messages when Telegram sends both member-update types.

9. Improve callback data safety:
   - Avoid putting raw filenames in retry callback data because Telegram callback data is limited to 64 bytes.

## Suggested Implementation Shape

- Add small helpers:
  - `_cancel_to_main(update, context, text=...)`
  - `_cancel_to_account(update, context, user_id, section=...)`
  - `_clear_navigation_state(context)` used by all reply-keyboard handlers.
  - `_user_can_access_chat(db, user, chat_id)`
  - `_user_can_access_project(db, user, project_id)`

- Add explicit inline cancel buttons for text-entry modes:
  - `cancel_main`
  - `cancel_account_home`
  - `cancel_admin`
  - `cancel_project`

- Treat reply-keyboard navigation as a state transition:
  - Before any admin/main/project command executes, clear pending file/photo and admin transient flags unless that handler intentionally continues the active flow.

- Add regression checks around pure helpers first:
  - `_account_learning_text()` in-progress output.
  - Access filtering for chat/project query builders after they are extracted.
  - Callback dispatch for `doc_`, `cancel_*`, and destructive confirmation.
