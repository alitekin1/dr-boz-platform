# OpenRouter Chirp-3 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate OpenRouter's `google/chirp-3` model as a voice-to-text provider, including audio conversion to WAV.

**Architecture:** Refactor `transcribe_audio_with_gemini` into a generic `transcribe_audio` dispatcher that supports both Google and OpenRouter providers. Use `ffmpeg` for audio conversion to WAV when using OpenRouter.

**Tech Stack:** Python (FastAPI), httpx, ffmpeg, React (TypeScript)

---

### Task 1: Update Schemas for OpenRouter Provider

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Update TranscriptionConfigBase and TranscriptionConfigUpdate**
Add "openrouter" to the Literal for provider.

```python
# backend/app/schemas.py

class TranscriptionConfigBase(BaseModel):
    name: str = "default"
    provider: Literal["google", "openrouter"] = "google"
    # ... rest
    
class TranscriptionConfigUpdate(BaseModel):
    # ...
    provider: Optional[Literal["google", "openrouter"]] = None
    # ...
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/schemas.py
git commit -m "feat: add openrouter to transcription provider schemas"
```

### Task 2: Implement Audio Conversion Utility

**Files:**
- Modify: `backend/app/llm.py`

- [ ] **Step 1: Add convert_to_wav helper**
This function will take audio bytes and return WAV bytes using ffmpeg.

```python
# backend/app/llm.py
import asyncio
import tempfile
import os

async def _convert_to_wav(audio_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as temp_in:
        temp_in.write(audio_bytes)
        temp_in_path = temp_in.name
    
    temp_out_path = temp_in_path + ".wav"
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", temp_in_path, "-ar", "16000", "-ac", "1", "-f", "wav", temp_out_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode != 0:
            raise RuntimeError("ffmpeg conversion failed")
            
        with open(temp_out_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(temp_in_path): os.remove(temp_in_path)
        if os.path.exists(temp_out_path): os.remove(temp_out_path)
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/llm.py
git commit -m "feat: add audio conversion utility for transcription"
```

### Task 3: Implement OpenRouter Transcription

**Files:**
- Modify: `backend/app/llm.py`

- [ ] **Step 1: Add transcribe_audio_with_openrouter**
Implement the API call to OpenRouter.

```python
# backend/app/llm.py

async def transcribe_audio_with_openrouter(
    config: TranscriptionConfig,
    *,
    audio_bytes: bytes,
    prompt: str | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = (config.api_key or "").strip()
    if not api_key:
        raise ValueError("OpenRouter API key is not configured")
    
    model = (config.model or "google/chirp-3").strip()
    wav_bytes = await _convert_to_wav(audio_bytes)
    
    payload = {
        "model": model,
        "input_audio": {
            "data": base64.b64encode(wav_bytes).decode("ascii"),
            "format": "wav"
        }
    }
    
    url = "https://openrouter.ai/api/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://jgpti.local",
        "X-Title": "JGPTi",
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
    transcript = (data.get("text") or "").strip()
    # OpenRouter audio API might have different usage structure, adapt as needed
    usage = {"total_tokens": 0} # Usage info might be in headers or different field
    return transcript, usage
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/llm.py
git commit -m "feat: implement OpenRouter transcription"
```

### Task 4: Refactor Dispatcher and Update Bot

**Files:**
- Modify: `backend/app/llm.py`
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Rename and create transcribe_audio dispatcher in llm.py**
Keep `transcribe_audio_with_gemini` but make `transcribe_audio` the main entry point.

```python
# backend/app/llm.py

async def transcribe_audio(
    config: TranscriptionConfig,
    *,
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    prompt: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if config.provider == "openrouter":
        return await transcribe_audio_with_openrouter(config, audio_bytes=audio_bytes, prompt=prompt)
    else:
        return await transcribe_audio_with_gemini(config, audio_bytes=audio_bytes, mime_type=mime_type, prompt=prompt)
```

- [ ] **Step 2: Update bot.py to use transcribe_audio**
Replace calls to `transcribe_audio_with_gemini` with `transcribe_audio`.

- [ ] **Step 3: Commit**
```bash
git add backend/app/llm.py backend/app/bot.py
git commit -m "refactor: use generic transcribe_audio dispatcher"
```

### Task 5: Update Frontend UI

**Files:**
- Modify: `frontend-v2/src/components/intelligence/TranscriptionForm.tsx`

- [ ] **Step 1: Add OpenRouter to provider dropdown**
Update the select options.

```tsx
<select
  value={formData.provider}
  onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
  // ...
>
  <option value="google">Google Gemini</option>
  <option value="openrouter">OpenRouter (Chirp-3)</option>
</select>
```

- [ ] **Step 2: Commit**
```bash
git add frontend-v2/src/components/intelligence/TranscriptionForm.tsx
git commit -m "feat: add OpenRouter option to transcription settings UI"
```

### Task 6: Verification

**Files:**
- Create: `backend/tests/test_chirp.py`

- [ ] **Step 1: Create a test script**
Write a script that mocks the DB config and calls the transcription logic.

- [ ] **Step 2: Run verification**
Run the test script.

- [ ] **Step 3: Commit**
```bash
git add backend/tests/test_chirp.py
git commit -m "test: add verification for chirp transcription"
```
