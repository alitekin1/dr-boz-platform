# Design Spec: OpenRouter Chirp-3 Voice-to-Text Integration

**Status:** Draft
**Date:** 2026-05-07
**Author:** Gemini CLI

## 1. Overview
Integrate OpenRouter's `google/chirp-3` model as an alternative voice-to-text provider for the Telegram bot and project document indexing. This provides higher accuracy and multi-language support as requested by the user.

## 2. Architecture Changes

### 2.1 Backend Refactoring (`backend/app/llm.py`)
- **Generalized Dispatcher**: Introduce `transcribe_audio` as the main entry point.
- **Provider Implementations**:
    - `transcribe_audio_with_gemini`: (Existing) Handles direct Google Gemini API calls.
    - `transcribe_audio_with_openrouter`: (New) Handles OpenRouter transcription API calls.
- **Audio Conversion Utility**:
    - Use `ffmpeg` to convert incoming audio (typically `.ogg` from Telegram or `.m4a`/`.mp3` from uploads) to `.wav` format, as required by the Chirp-3 API on OpenRouter.
    - Implementation using `asyncio.create_subprocess_exec` for non-blocking conversion.

### 2.2 Configuration Management
- Leverage existing `TranscriptionConfig` model.
- Supported providers: `google` (default), `openrouter`.
- Admin UI update to allow selection of "OpenRouter" and specification of custom Model IDs (e.g., `google/chirp-3`).

### 2.3 Audio Processing Flow
1. Receive audio bytes and MIME type.
2. Determine transcription provider from database config.
3. If provider is `openrouter`:
    - Save temporary audio file.
    - Convert to WAV using `ffmpeg`.
    - Read WAV bytes and encode to base64.
    - Post to `https://openrouter.ai/api/v1/audio/transcriptions`.
4. Return transcript and usage metadata (consistent format across providers).

## 3. Implementation Details

### API Call (OpenRouter)
```python
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
payload = {
    "model": model_id,
    "input_audio": {
        "data": base64_wav_data,
        "format": "wav"
    }
}
```

### Conversion Command
```bash
ffmpeg -i input_file -ar 16000 -ac 1 output.wav
```

## 4. User Interface (`frontend-v2`)
- Update `TranscriptionForm.tsx` to include "OpenRouter" in the provider dropdown.
- Update helper text to reflect broader provider support.

## 5. Testing Strategy
- **Unit Tests**: Test the audio conversion utility with various input formats.
- **Integration Tests**: Mock OpenRouter API responses to verify the dispatcher and payload construction.
- **Manual Verification**: Use a sample `.ogg` file (simulating Telegram voice) and verify end-to-end transcription using a real OpenRouter API key.

## 6. Security Considerations
- Ensure temporary audio files are deleted immediately after processing or conversion.
- API keys continue to be stored securely in the database and handled only on the server.
