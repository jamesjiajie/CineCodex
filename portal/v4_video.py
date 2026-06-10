from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/james/Document/Projects/CineCodex")
JOBS = ROOT / "outputs" / "jobs"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_status(job_dir: Path, status: str, step: str, progress: int, message: str, **extra: Any) -> None:
    write_json(
        job_dir / "status.json",
        {
            "status": status,
            "step": step,
            "progress": progress,
            "message": message,
            "job_id": job_dir.name,
            "job_dir": str(job_dir),
            "updated_at": now(),
            **extra,
        },
    )


def create_video_job(project: dict[str, Any]) -> dict[str, Any]:
    job_id = f"v4-{project['project_id']}-{uuid.uuid4().hex[:6]}"
    job_dir = JOBS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    update_status(job_dir, "queued", "queued", 1, "Video generation queued")
    return {"job_id": job_id, "job_dir": str(job_dir)}


def generate_project_video(
    project: dict[str, Any],
    job_id: str,
    options: dict[str, Any] | None = None,
) -> None:
    options = options or {}
    job_dir = JOBS / Path(job_id).name
    frames_dir = job_dir / "work" / "frames"
    docs_dir = job_dir / "docs"
    deliverables_dir = job_dir / "deliverables"
    for directory in (frames_dir, docs_dir, deliverables_dir):
        directory.mkdir(parents=True, exist_ok=True)

    try:
        slides = project.get("slides") or []
        if not slides:
            raise RuntimeError("Extract PPT slides before generating video")

        update_status(job_dir, "running", "preparing", 10, "Preparing reviewed slides and subtitles")
        narration_slides = []
        for index, slide in enumerate(slides, start=1):
            source_frame = Path(slide.get("thumbnail_path") or "")
            if not source_frame.exists():
                raise RuntimeError(f"Slide {index} frame is missing")
            target_frame = frames_dir / f"slide_{index:02d}.png"
            shutil.copy2(source_frame, target_frame)

            narration = slide.get("narration") or {}
            text = str(narration.get("subtitle") or narration.get("text") or "").strip()
            if not text:
                raise RuntimeError(f"Slide {index} has no reviewed subtitle or narration")
            narration_slides.append(
                {
                    "slide": index,
                    "text": text,
                    "duration_seconds": float(narration.get("duration_seconds") or 6.5),
                }
            )

        settings = {**project.get("settings", {}), **options}
        narration_path = docs_dir / "reviewed_narration.json"
        write_json(
            narration_path,
            {
                "source": project.get("source_file"),
                "language": settings.get("language", "zh-CN"),
                "seconds_per_slide": 6.5,
                "slides": narration_slides,
            },
        )

        update_status(job_dir, "running", "rendering", 35, "Generating voiceover and timed video")
        final_video = deliverables_dir / f"{project['project_id']}_final.mp4"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "edge_cantonese_voiceover.py"),
            "--narration",
            str(narration_path),
            "--output-dir",
            str(job_dir),
            "--output-video",
            str(final_video),
            "--voice",
            settings.get("voice", "zh-CN-XiaoxiaoNeural"),
            "--rate",
            settings.get("rate", "+0%"),
            "--tts-engine",
            settings.get("tts_engine", "say"),
            "--say-voice",
            settings.get("say_voice", "Sinji" if settings.get("language") == "yue-HK" else "Tingting"),
            "--subtitles" if settings.get("subtitles", True) else "--no-subtitles",
        ]
        log_path = job_dir / "generation.log"
        with log_path.open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=str(ROOT), check=True, stdout=log, stderr=subprocess.STDOUT)

        generated_subtitles = job_dir / "work" / "edge_cantonese_audio" / "cantonese_subtitles.srt"
        subtitle_file = deliverables_dir / f"{project['project_id']}_subtitles.srt"
        if generated_subtitles.exists():
            shutil.copy2(generated_subtitles, subtitle_file)

        if not final_video.exists():
            raise RuntimeError("Video renderer completed without creating an MP4")

        update_status(
            job_dir,
            "success",
            "complete",
            100,
            "Video generated successfully",
            final_video=str(final_video),
            subtitles=str(subtitle_file) if subtitle_file.exists() else None,
            narration=str(narration_path),
            logs=str(log_path),
        )
    except Exception as exc:
        update_status(
            job_dir,
            "failed",
            "error",
            100,
            str(exc),
            error=str(exc),
            logs=str(job_dir / "generation.log"),
        )
