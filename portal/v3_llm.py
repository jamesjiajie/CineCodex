from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

from .v3_projects import now


VALID_MODES = {"check", "polish", "rewrite"}


def _input_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_payload(project: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "task": "align_and_polish_narration",
        "mode": mode,
        "language": project.get("settings", {}).get("language", "zh-CN"),
        "tone": project.get("settings", {}).get("tone", "professional"),
        "target_duration_seconds": project.get("settings", {}).get("target_duration_seconds", 240),
        "ppt_slides": [
            {
                "slide_number": slide["slide_number"],
                **(slide.get("extracted") or {}),
            }
            for slide in project.get("slides", [])
        ],
        "imported_subtitles": [
            item
            for import_record in project.get("imports", [])
            for item in import_record.get("items", [])
        ],
    }


def _polish_text(text: str, mode: str, title: str, raw_text: str) -> str:
    text = " ".join(text.split()).strip()
    if mode == "check":
        return text
    if mode == "rewrite":
        source = raw_text or title or text
        return f"这一页的重点是{source}。请结合画面内容，按这个逻辑向观众说明关键结论。"
    if text:
        return f"{text} 这部分可以用更自然的讲解节奏说明，让观众先理解背景，再抓住重点。"
    return f"这一页介绍{title}，建议用简洁的旁白说明核心信息。"


def mock_process(project: dict[str, Any], mode: str) -> dict[str, Any]:
    slides = []
    imported = [
        item
        for import_record in project.get("imports", [])
        for item in import_record.get("items", [])
    ]
    for index, slide in enumerate(project.get("slides", [])):
        extracted = slide.get("extracted") or {}
        narration = slide.get("narration") or {}
        imported_text = imported[index]["text"] if index < len(imported) else ""
        base = imported_text or narration.get("text") or extracted.get("raw_text") or extracted.get("title") or ""
        text = _polish_text(base, mode, extracted.get("title", ""), extracted.get("raw_text", ""))
        duration = max(4.0, min(45.0, len(text) / 7))
        warnings = []
        if imported_text and extracted.get("raw_text") and not any(token in extracted["raw_text"] for token in imported_text[:12].split()):
            warnings.append("Imported subtitle may not closely match the slide text")
        slides.append(
            {
                "slide_number": slide["slide_number"],
                "narration": text,
                "subtitle": text,
                "duration_seconds": round(duration, 2),
                "confidence": "medium" if warnings else "high",
                "warnings": warnings,
            }
        )
    return {"slides": slides, "global_warnings": [], "summary": "Processed with local mock LLM provider."}


def openai_process(payload: dict[str, Any], model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    prompt = (
        "Return only valid JSON matching this schema: "
        "{\"slides\":[{\"slide_number\":1,\"narration\":\"...\",\"subtitle\":\"...\","
        "\"duration_seconds\":12,\"confidence\":\"high\",\"warnings\":[]}],"
        "\"global_warnings\":[],\"summary\":\"...\"}. "
        "Process the following CineCodex narration task:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    body = json.dumps(
        {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "text": {"format": {"type": "json_object"}},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8") or str(exc)) from exc
    text = data.get("output_text")
    if not text:
        parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("text"):
                    parts.append(content["text"])
        text = "\n".join(parts)
    return json.loads(text)


def validate_result(project: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    known_slides = {int(slide["slide_number"]) for slide in project.get("slides", [])}
    cleaned = {"slides": [], "global_warnings": list(result.get("global_warnings") or []), "summary": result.get("summary", "")}
    for item in result.get("slides") or []:
        slide_number = int(item.get("slide_number"))
        if slide_number not in known_slides:
            continue
        narration = str(item.get("narration") or item.get("subtitle") or "").strip()
        subtitle = str(item.get("subtitle") or narration).strip()
        if not narration:
            raise ValueError(f"LLM returned empty narration for slide {slide_number}")
        duration = float(item.get("duration_seconds") or max(4.0, len(narration) / 7))
        cleaned["slides"].append(
            {
                "slide_number": slide_number,
                "narration": narration,
                "subtitle": subtitle,
                "duration_seconds": round(max(2.0, min(120.0, duration)), 2),
                "confidence": item.get("confidence", "medium"),
                "warnings": list(item.get("warnings") or []),
            }
        )
    if not cleaned["slides"]:
        raise ValueError("LLM did not return any usable slides")
    return cleaned


def process(project: dict[str, Any], mode: str, provider: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = mode if mode in VALID_MODES else "polish"
    provider = provider or project.get("settings", {}).get("llm_provider", "mock")
    payload = build_payload(project, mode)
    if provider == "mock":
        result = mock_process(project, mode)
        model = "mock"
    elif provider == "openai_api":
        model = os.environ.get("CINECODEX_OPENAI_MODEL", "gpt-4.1-mini")
        result = openai_process(payload, model)
    elif provider == "mcp":
        raise RuntimeError("MCP provider is configured but no MCP bridge command is set for this local portal")
    else:
        raise RuntimeError(f"Unsupported LLM provider: {provider}")

    result = validate_result(project, result)
    run = {
        "run_id": uuid.uuid4().hex[:12],
        "provider": provider,
        "mode": mode,
        "input_hash": _input_hash(payload),
        "status": "succeeded",
        "model": model if provider != "mcp" else "mcp",
        "warnings": result.get("global_warnings", []),
        "created_at": now(),
    }
    return result, run
