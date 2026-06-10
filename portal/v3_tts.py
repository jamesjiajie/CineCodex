from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import edge_tts

from .v3_subtitles import write_srt


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").exists() else None)


async def _edge(text: str, voice: str, rate: str, output: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output))


def _silent(duration: float, output: Path) -> None:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        output.write_bytes(b"")
        return
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            f"{duration:.3f}",
            str(output),
        ]
    )


def _say(text: str, voice: str, rate: str, output: Path) -> None:
    _run(["say", "-v", voice, "-r", rate, "-o", str(output), text])


def generate_voice_package(project: dict[str, Any], project_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    settings = {**project.get("settings", {}), **options}
    engine = settings.get("tts_engine", "say")
    voice = settings.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = settings.get("rate", "+0%")
    audio_dir = project_dir / "exports" / "voiceover"
    audio_dir.mkdir(parents=True, exist_ok=True)

    narration_json = {
        "source": project.get("source_file"),
        "language": settings.get("language", "zh-CN"),
        "slides": [],
    }
    audio_files = []
    for slide in project.get("slides", []):
        narration = slide.get("narration") or {}
        text = (narration.get("text") or narration.get("subtitle") or "").strip()
        if not text:
            continue
        slide_no = int(slide["slide_number"])
        duration = float(narration.get("duration_seconds") or 6.5)
        suffix = ".mp3" if engine == "edge" else ".aiff" if engine == "say" else ".wav"
        output = audio_dir / f"slide_{slide_no:02d}{suffix}"
        if engine == "edge":
            asyncio.run(_edge(text, voice, rate, output))
        elif engine == "say":
            default_say_voice = "Sinji" if settings.get("language") == "yue-HK" else "Tingting"
            _say(text, settings.get("say_voice", default_say_voice), str(settings.get("say_rate", "175")), output)
        else:
            _silent(duration, output)
        slide["voiceover"] = {"status": "generated", "audio_path": str(output)}
        narration_json["slides"].append({"slide": slide_no, "text": text, "duration_seconds": duration, "audio": str(output)})
        audio_files.append(output)

    narration_path = audio_dir / "narration.json"
    narration_path.write_text(json.dumps(narration_json, ensure_ascii=False, indent=2), encoding="utf-8")
    srt_path = write_srt(project.get("slides", []), audio_dir / "subtitles.srt")
    zip_path = project_dir / "exports" / f"{project['project_id']}_voiceover.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(narration_path, "narration.json")
        archive.write(srt_path, "subtitles.srt")
        for audio in audio_files:
            archive.write(audio, f"audio/{audio.name}")

    return {
        "engine": engine,
        "narration": str(narration_path),
        "subtitles": str(srt_path),
        "audio_files": [str(path) for path in audio_files],
        "zip": str(zip_path),
    }
