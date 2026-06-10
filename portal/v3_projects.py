from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/james/Document/Projects/CineCodex")
V3_ROOT = ROOT / "outputs" / "v3_projects"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s.-]+", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[\s.]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "narration-project"


def project_dir(project_id: str) -> Path:
    safe = Path(project_id).name
    return V3_ROOT / safe


def project_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_project(project_id: str) -> dict[str, Any]:
    path = project_path(project_id)
    if not path.exists():
        raise FileNotFoundError(project_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_project(project: dict[str, Any]) -> dict[str, Any]:
    project["updated_at"] = now()
    write_json(project_path(project["project_id"]), project)
    return project


def create_project(source: Path, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_id = f"{slugify(source.stem)}-{stamp}-{uuid.uuid4().hex[:6]}"
    base = project_dir(project_id)
    source_dir = base / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    target = source_dir / source.name
    shutil.copy2(source, target)

    project = {
        "project_id": project_id,
        "source_file": str(target),
        "created_at": now(),
        "updated_at": now(),
        "settings": {
            "language": "yue-HK",
            "voice": "zh-HK-HiuMaanNeural",
            "say_voice": "Sinji",
            "tone": "professional",
            "target_duration_seconds": 240,
            "llm_provider": "mock",
            "tts_engine": "say",
            **(settings or {}),
        },
        "slides": [],
        "imports": [],
        "llm_runs": [],
        "exports": [],
        "status": "created",
        "warnings": [],
    }
    save_project(project)
    return project


def list_projects() -> list[dict[str, Any]]:
    V3_ROOT.mkdir(parents=True, exist_ok=True)
    projects: list[dict[str, Any]] = []
    for path in sorted(V3_ROOT.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        projects.append(
            {
                "project_id": project.get("project_id"),
                "source_file": project.get("source_file"),
                "created_at": project.get("created_at"),
                "updated_at": project.get("updated_at"),
                "status": project.get("status"),
                "slide_count": len(project.get("slides") or []),
            }
        )
    return projects


def delete_project(project_id: str) -> bool:
    path = project_dir(project_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def public_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        **project,
        "project_dir": str(project_dir(project["project_id"])),
    }
