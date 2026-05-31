# CineCodex V3 LLM Subtitle and Voiceover Design

## Goal

V3 turns CineCodex from a direct PPT-to-video runner into a reviewable narration workspace. A user can upload a PPT, choose how subtitles are sourced, optionally send the PPT context plus subtitles through an LLM or MCP provider, then generate subtitles, voiceover, and later a final MP4.

The first V3 milestone should stop at a dependable "subtitle + narration + voiceover package" flow. Final video assembly can reuse the existing V2.1 pipeline after the narration timeline is stable.

## User Modes

### Mode A: Auto From PPT

The user uploads a PPT and asks CineCodex to generate narration from slide content.

Inputs:

- PPT or PPTX file.
- Optional language, voice, tone, and target duration.
- Optional toggle for LLM enhancement.

Output:

- Per-slide narration.
- Per-slide subtitle text.
- Estimated duration per slide.
- TTS audio clips or a combined voiceover file.
- Exportable SRT/VTT.

### Mode B: Manual Subtitle Import

The user uploads a PPT and imports their own subtitles or script.

Inputs:

- PPT or PPTX file.
- Subtitle/script file: `.txt`, `.srt`, `.vtt`, or later `.docx`.
- Optional mapping mode: whole-script, slide-by-slide, or timestamped.

Output:

- Imported subtitles normalized into the CineCodex timeline.
- Editable per-slide narration/subtitle blocks.
- TTS audio generated from the imported text.

### Mode C: Manual Subtitle Import With LLM

The user uploads a PPT, imports subtitles, and asks CineCodex to call GPT API or an MCP provider to return a cleaned, aligned, or rewritten result.

Default behavior should be conservative: keep the user's intent and improve clarity unless the user explicitly chooses rewrite.

LLM options:

- `check`: fix spelling, punctuation, sentence breaks, terminology, and obvious mismatches.
- `polish`: preserve meaning while making the script sound natural as voiceover.
- `rewrite`: use the PPT as the source of truth and treat imported subtitles as reference.

## Recommended Workspace UI

Use one V3 workspace screen with three panels.

Left panel:

- Upload/session list.
- Slide thumbnails.
- Slide status: extracted, needs review, LLM warning, voice generated.

Center panel:

- Current slide preview.
- Extracted slide text.
- Speaker notes when available.
- Image/OCR summary later, if enabled.

Right panel:

- Mode selector: Auto, Import, Import + AI.
- Narration editor.
- Subtitle editor.
- Duration control.
- Voice selector.
- Actions: Generate subtitles, AI process, Generate voice, Export SRT, Export audio, Generate video.

The UI should always expose the intermediate text before generating voice or video. That keeps LLM output reviewable and avoids a black-box generation flow.

## Data Model

### NarrationProject

```json
{
  "project_id": "uuid",
  "source_file": "uploads/committed/<id>/deck.pptx",
  "created_at": "iso-datetime",
  "updated_at": "iso-datetime",
  "settings": {
    "language": "zh-CN",
    "voice": "zh-CN-XiaoxiaoNeural",
    "tone": "professional",
    "target_duration_seconds": 240,
    "llm_provider": "openai_api"
  },
  "slides": [],
  "imports": [],
  "llm_runs": [],
  "exports": []
}
```

### SlideRecord

```json
{
  "slide_number": 1,
  "thumbnail_path": "outputs/jobs/<id>/frames/slide_001.png",
  "extracted": {
    "title": "Slide title",
    "body": ["Bullet 1", "Bullet 2"],
    "speaker_notes": "",
    "raw_text": "..."
  },
  "narration": {
    "source": "llm",
    "text": "...",
    "subtitle": "...",
    "duration_seconds": 12,
    "status": "needs_review"
  },
  "voiceover": {
    "status": "pending",
    "audio_path": null
  },
  "warnings": []
}
```

### SubtitleImport

```json
{
  "import_id": "uuid",
  "filename": "script.srt",
  "format": "srt",
  "mode": "timestamped",
  "items": [
    {
      "index": 1,
      "start_seconds": 0.0,
      "end_seconds": 4.2,
      "text": "..."
    }
  ]
}
```

### LLMRun

```json
{
  "run_id": "uuid",
  "provider": "openai_api",
  "mode": "polish",
  "input_hash": "sha256",
  "status": "succeeded",
  "model": "configured-model-name",
  "warnings": [],
  "result_path": "outputs/jobs/<id>/llm/run.json"
}
```

## LLM Contract

The LLM layer should never return free-form text to the rest of the app. It should return validated JSON.

Request payload:

```json
{
  "task": "align_and_polish_narration",
  "mode": "polish",
  "language": "zh-CN",
  "tone": "professional",
  "target_duration_seconds": 240,
  "ppt_slides": [
    {
      "slide_number": 1,
      "title": "...",
      "body": ["..."],
      "speaker_notes": "...",
      "raw_text": "..."
    }
  ],
  "imported_subtitles": [
    {
      "index": 1,
      "start_seconds": 0.0,
      "end_seconds": 4.2,
      "text": "..."
    }
  ]
}
```

Response payload:

```json
{
  "slides": [
    {
      "slide_number": 1,
      "narration": "...",
      "subtitle": "...",
      "duration_seconds": 12,
      "confidence": "high",
      "warnings": []
    }
  ],
  "global_warnings": [],
  "summary": "..."
}
```

Validation rules:

- Every returned slide number must exist in the project.
- Empty narration is invalid unless the slide is explicitly marked silent.
- Duration must be positive and should be bounded, for example 2 to 120 seconds per slide.
- Warnings must be preserved and shown in the UI.
- The original imported subtitle must remain recoverable.

## Provider Abstraction

Create one provider interface so V3 can support OpenAI API, MCP, and local mocks.

```text
LLMProvider
- process_narration(project, mode, settings) -> LLMResult

Providers:
- OpenAIAPIProvider
- MCPProvider
- MockProvider
```

Configuration:

```json
{
  "llm": {
    "provider": "openai_api",
    "model": "configured-model-name",
    "timeout_seconds": 90,
    "max_retries": 2
  }
}
```

The app should work with `provider: disabled` or `provider: mock` so local video generation remains available without network/API access.

## Backend Modules

Recommended modules:

- `portal/app.py`: HTTP routes and HTML shell only.
- `portal/projects.py`: project/session persistence.
- `portal/ppt_parser.py`: PPT extraction and slide metadata.
- `portal/subtitles.py`: `.txt`, `.srt`, `.vtt` import/export.
- `portal/llm.py`: provider abstraction and JSON validation.
- `portal/timeline.py`: slide narration timeline building and duration logic.
- `portal/tts.py`: voice generation wrapper around the existing Edge TTS path.
- `portal/video.py`: adapter to existing manifest-driven video job runner.

Existing scripts can remain usable during migration:

- `scripts/pptx_to_video_draft.py` can donate slide extraction/rendering logic.
- `scripts/edge_cantonese_voiceover.py` can remain the first TTS/subtitle muxing backend.
- `scripts/run_video_job.py` can consume the V3 timeline once the schema is stable.

## API Sketch

```text
POST /api/v3/projects
POST /api/v3/projects/{project_id}/files
POST /api/v3/projects/{project_id}/extract
POST /api/v3/projects/{project_id}/subtitles/import
POST /api/v3/projects/{project_id}/narration/auto
POST /api/v3/projects/{project_id}/narration/llm
PATCH /api/v3/projects/{project_id}/slides/{slide_number}/narration
POST /api/v3/projects/{project_id}/voiceover
GET  /api/v3/projects/{project_id}/exports/subtitles.srt
GET  /api/v3/projects/{project_id}/exports/voiceover.zip
POST /api/v3/projects/{project_id}/video
```

## Processing Flow

### Auto mode

1. Upload PPT.
2. Extract slide thumbnails, text, and notes.
3. Generate draft narration from extracted content.
4. Optionally send extracted slides to LLM.
5. Save structured slide narration.
6. User reviews and edits.
7. Generate TTS.
8. Export subtitle/audio or continue to video.

### Manual mode

1. Upload PPT.
2. Import subtitle/script.
3. Normalize subtitle format.
4. Map subtitle text to slides.
5. User reviews and edits.
6. Generate TTS.

### Manual + LLM mode

1. Upload PPT.
2. Import subtitle/script.
3. Extract PPT content.
4. Send PPT content and imported subtitles to LLM provider.
5. Validate JSON response.
6. Show original vs AI result.
7. User accepts per slide or accepts all.
8. Generate TTS.

## Error Handling

Important user-facing errors:

- PPT has no extractable text and OCR is disabled.
- Imported subtitles cannot be parsed.
- Imported subtitle duration does not match slide count.
- LLM provider is not configured.
- LLM returned invalid JSON.
- TTS network call failed.
- Video assembly failed after voiceover generation.

Each error should preserve the project state and offer a retry from the failed step.

## Privacy and Review

LLM processing sends slide content and imported subtitles outside the local app when using a remote API. The UI should make that explicit before the first LLM run.

Recommended consent copy:

```text
AI processing will send extracted PPT text and imported subtitles to the configured LLM provider. Source files and generated audio remain local unless your provider configuration sends them elsewhere.
```

## Implementation Phases

### Phase 1: V3 project schema and manual subtitle import

- Add `NarrationProject` persistence.
- Extract PPT slide text and thumbnails.
- Import `.txt` and `.srt`.
- Show editable per-slide narration and subtitle text.
- Export SRT.

### Phase 2: LLM provider and review loop

- Add provider abstraction with `mock` first.
- Add OpenAI API or MCP provider behind config.
- Validate structured JSON.
- Show original vs AI-processed text.
- Support accept/revert per slide.

### Phase 3: TTS package generation

- Generate per-slide audio.
- Save voiceover status on each slide.
- Export audio bundle.
- Keep existing silent-audio fallback for local tests.

### Phase 4: Video assembly

- Convert V3 timeline to the existing video job manifest.
- Burn subtitles and mux audio.
- Generate final MP4.
- Preserve only final deliverables when cleanup is enabled.

## Open Decisions

- Should V3 default language be Mandarin, Cantonese, or project-level selectable?
- Should imported `.txt` be treated as whole-script by default or split by blank lines into slides?
- Should the first remote LLM provider be OpenAI API directly, MCP, or both behind one config?
- Should video generation remain n8n-driven, or should V3 expose a direct local runner first?
- Should OCR be included in V3 Phase 1 or deferred until after LLM/TTS is stable?
