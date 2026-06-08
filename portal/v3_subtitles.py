from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_timestamp(value: str) -> float:
    match = re.match(r"(?:(\d{2}):)?(\d{2}):(\d{2})[,.](\d{1,3})", value.strip())
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4).ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def format_timestamp(seconds: float) -> str:
    milliseconds = int(round(max(0, seconds) * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def parse_srt(text: str) -> list[dict[str, Any]]:
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    items: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        body = " ".join(lines[1:]).strip()
        if not body:
            continue
        items.append(
            {
                "index": len(items) + 1,
                "start_seconds": parse_timestamp(start_raw),
                "end_seconds": parse_timestamp(end_raw),
                "text": body,
            }
        )
    return items


def parse_vtt(text: str) -> list[dict[str, Any]]:
    text = re.sub(r"^\ufeff?WEBVTT.*?(\n\s*\n)", "", text.replace("\r\n", "\n"), flags=re.S)
    return parse_srt(text.replace(".", ","))


def parse_txt(text: str) -> list[dict[str, Any]]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if block.strip()]
    if not blocks:
        blocks = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    cursor = 0.0
    for block in blocks:
        duration = max(3.0, min(18.0, len(block) / 8))
        items.append(
            {
                "index": len(items) + 1,
                "start_seconds": cursor,
                "end_seconds": cursor + duration,
                "text": re.sub(r"\s+", " ", block).strip(),
            }
        )
        cursor += duration
    return items


def parse_subtitle_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    return parse_subtitle_text(text, path.suffix.lower())


def parse_subtitle_text(text: str, suffix: str = ".txt") -> dict[str, Any]:
    suffix = suffix.lower()
    if suffix == ".srt":
        items = parse_srt(text)
        fmt = "srt"
    elif suffix == ".vtt":
        items = parse_vtt(text)
        fmt = "vtt"
    elif suffix == ".txt":
        items = parse_txt(text)
        fmt = "txt"
    else:
        raise ValueError(f"Unsupported subtitle type: {suffix}")
    if not items:
        raise ValueError("No subtitle text could be parsed")
    return {"format": fmt, "items": items}


def write_srt(slides: list[dict[str, Any]], path: Path) -> Path:
    cursor = 0.0
    blocks = []
    for index, slide in enumerate(slides, start=1):
        narration = slide.get("narration") or {}
        text = (narration.get("subtitle") or narration.get("text") or "").strip()
        if not text:
            continue
        duration = float(narration.get("duration_seconds") or 6.5)
        blocks.append(f"{index}\n{format_timestamp(cursor)} --> {format_timestamp(cursor + duration)}\n{text}\n")
        cursor += duration
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def map_items_to_slides(items: list[dict[str, Any]], slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slides:
        return slides
    if len(items) == len(slides):
        groups = [[item] for item in items]
    else:
        groups = [[] for _ in slides]
        for index, item in enumerate(items):
            slide_index = min(len(slides) - 1, int(index * len(slides) / max(1, len(items))))
            groups[slide_index].append(item)

    for slide, group in zip(slides, groups):
        if not group:
            continue
        text = " ".join(item["text"] for item in group).strip()
        duration = max(3.0, sum(max(0.1, item["end_seconds"] - item["start_seconds"]) for item in group))
        slide["narration"] = {
            "source": "import",
            "text": text,
            "subtitle": text,
            "duration_seconds": round(duration, 2),
            "status": "needs_review",
        }
    return slides
