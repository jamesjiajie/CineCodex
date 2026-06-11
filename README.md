# CineCodex

CineCodex converts uploaded PPT/PDF/image batches into a subtitle-burned MP4 through the local portal and n8n.

## Current Structure

- `Start CineCodex Portal.command` - double-click launcher for the portal.
- `portal/` - FastAPI upload and generation UI.
- `portal/v3_*.py` - V3 narration workspace modules for PPT extraction, subtitle import, LLM processing, and voice package export.
- `scripts/start_portal.sh` - portal service entrypoint.
- `scripts/start_n8n.sh` - n8n service entrypoint.
- `scripts/import_n8n_workflow.sh` - imports the current V2.1 workflow.
- `scripts/run_manifest_from_n8n.sh` - n8n command wrapper.
- `scripts/run_video_job.py` - manifest-driven video job runner.
- `scripts/pptx_to_video_draft.py` - slide/frame renderer.
- `scripts/edge_cantonese_voiceover.py` - subtitle/audio muxer; defaults to safe local silent audio.
- `workflows/portal-video-generator-v2.1.json` - current n8n workflow.
- `uploads/` - runtime upload staging and committed manifests.
- `outputs/jobs/` - runtime job folders and final MP4s.

## Start

Start or import n8n first:

```bash
scripts/import_n8n_workflow.sh
scripts/start_n8n.sh
```

n8n must stay running while portal jobs are being processed.

Double-click:

```text
Start CineCodex Portal.command
```

The launcher starts on `127.0.0.1:8017` by default and automatically moves to the next free port if needed.

n8n editor:

```text
http://127.0.0.1:5678
```

## V4 Unified Workspace

The default portal page is now the unified V4 workflow:

```text
http://127.0.0.1:8017/
```

The workspace supports:

- Uploading `.pptx` files and extracting slide thumbnails/text.
- Auto-generating draft narration from PPT text.
- Importing `.txt`, `.srt`, or `.vtt` subtitles and mapping them to slides.
- Processing PPT context plus imported subtitles through a pluggable LLM provider.
- Reviewing narration, subtitles, and per-slide duration.
- Generating SRT exports, a voiceover ZIP package, or a final subtitle-burned MP4.

The default LLM provider is `mock`, so the workflow runs locally without API keys. To use the OpenAI API provider, set:

```bash
export OPENAI_API_KEY="..."
export CINECODEX_OPENAI_MODEL="gpt-4.1-mini"
```

The default V3 TTS engine is `silent` for safe local testing. Use `macOS Say` for local voice generation or `Edge TTS` when network TTS access is available.

## Input Limits

For good subtitles and voiceover, the PPT must contain extractable text or speaker notes. If a PPT is made from full-slide screenshots/images, CineCodex cannot read the text without OCR or a provided script, and the job will fail with a clear message instead of generating generic subtitles.

The default voice mode uses Edge TTS through n8n. This produces natural voiceover, but it requires network access to the TTS service.


## Runtime Cleanup

Portal jobs now default to `cleanup_cache: true`.

After a successful generation, CineCodex removes uploaded source copies, rendered frames, audio snippets, draft files, subtitles, logs, previews, and other intermediate artifacts. Each completed job keeps only:

- `outputs/jobs/<job_id>/deliverables/<job_id>_cantonese_subtitled.mp4`
- `outputs/jobs/<job_id>/status.json`

Failed jobs may keep their intermediate files so the error can be inspected.
