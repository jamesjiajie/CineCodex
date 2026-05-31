from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from scripts.pptx_to_video_draft import render


def extract_pptx(source: Path, project_dir: Path) -> list[dict[str, Any]]:
    if source.suffix.lower() != ".pptx":
        raise ValueError("V3 extraction currently supports .pptx files. Convert .ppt to .pptx first.")

    work_dir = project_dir / "work" / "ppt_render"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    result = render(source, work_dir, draw_subtitles=False)
    manifest_path = Path(result["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slides = []
    for entry in manifest.get("slides", []):
        slide_no = int(entry.get("slide") or len(slides) + 1)
        text_items = [str(item).strip() for item in entry.get("text") or [] if str(item).strip()]
        title = text_items[0] if text_items else f"Slide {slide_no}"
        body = text_items[1:] if len(text_items) > 1 else text_items
        narration_text = (entry.get("narration") or "").strip()
        slides.append(
            {
                "slide_number": slide_no,
                "thumbnail_path": entry.get("frame"),
                "extracted": {
                    "title": title,
                    "body": body,
                    "speaker_notes": "",
                    "raw_text": "\n".join(text_items),
                },
                "narration": {
                    "source": "auto",
                    "text": narration_text,
                    "subtitle": narration_text,
                    "duration_seconds": 6.5,
                    "status": "draft",
                },
                "voiceover": {
                    "status": "pending",
                    "audio_path": None,
                },
                "warnings": [] if text_items else ["No extractable text found on this slide"],
            }
        )
    if not slides:
        raise ValueError("No slides could be extracted from this PPTX")
    return slides
