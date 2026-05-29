from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/james/Document/Projects/CineCodex")
PYTHON = "/Users/james/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

SUPPORTED_PRESENTATIONS = {".pptx"}
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_PDFS = {".pdf"}


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s.-]+", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[\s.]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "video-job"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_status(job_dir: Path, status: str, step: str, progress: int, message: str, **extra) -> None:
    payload = {
        "status": status,
        "step": step,
        "progress": progress,
        "message": message,
        "updated_at": now(),
        "job_dir": str(job_dir),
        **extra,
    }
    write_json(job_dir / "status.json", payload)


def run(cmd: list[str], cwd: Path = ROOT, log_path: Path | None = None) -> None:
    if log_path:
        with log_path.open("a", encoding="utf-8") as log:
            log.write("$ " + " ".join(cmd) + "\n")
            subprocess.run(cmd, cwd=str(cwd), check=True, stdout=log, stderr=subprocess.STDOUT)
    else:
        subprocess.run(cmd, cwd=str(cwd), check=True)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in re.findall(r"[\u4e00-\u9fff]|[^\s\u4e00-\u9fff]+|\s+", text):
        token = " " if token.isspace() else token
        candidate = current + token
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
        else:
            lines.append(current.strip())
            current = token
    if current.strip():
        lines.append(current.strip())
    return lines


def render_image_frame(source: Path, frame_path: Path, title: str) -> None:
    width, height = 1280, 720
    canvas = Image.new("RGB", (width, height), "white")
    image = Image.open(source).convert("RGB")
    image.thumbnail((width - 120, height - 170), Image.LANCZOS)
    x = (width - image.width) // 2
    y = 80 + (height - 170 - image.height) // 2
    canvas.paste(image, (x, y))

    draw = ImageDraw.Draw(canvas)
    font = load_font(24)
    draw.text((60, 34), title, font=font, fill=(35, 39, 47))
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(frame_path)


def render_pdf_thumbnail(source: Path, target_png: Path, scratch_dir: Path) -> bool:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        run(["qlmanage", "-t", "-s", "1280", "-o", str(scratch_dir), str(source)])
    except Exception:
        return False
    candidates = sorted(scratch_dir.glob(source.name + "*.png")) + sorted(scratch_dir.glob("*.png"))
    if not candidates:
        return False
    shutil.copy2(candidates[0], target_png)
    return True


def text_preview(items: list[str], limit: int = 3) -> str:
    cleaned: list[str] = []
    for item in items:
        item = re.sub(r"\s+", " ", item).strip()
        if not item or item.isdigit():
            continue
        if item not in cleaned:
            cleaned.append(item)
    return "；".join(cleaned[:limit])


def has_extractable_text(slides: list[dict]) -> bool:
    for slide in slides:
        if text_preview(slide.get("text") or [], limit=1):
            return True
    return False


def cantonese_for_slide(slide: dict) -> str:
    texts = slide.get("text") or []
    joined = "。".join(texts)
    if "Over 100" in joined or "每天超过100" in joined:
        return "而家每日有超過一百個案例，每個平均要花大約十分鐘處理。錯誤訊息唔夠清楚，大家唔知應該搵邊個跟進，效率低之餘，仲容易引起投訴同返工。"
    if "Sales places" in joined or "销售下施工单" in joined:
        return "呢一頁係 Noss Hyper Care 而家嘅流程。銷售落單之後，如果張單有異常，就會交畀 IT 檢查；IT 排查同修復完成之後，再通知施工師傅繼續處理。"
    preview = text_preview(texts)
    if preview:
        return f"呢一頁主要講：{preview}。我哋可以先睇重點，再按流程逐步跟進。"
    return "呢一頁展示流程入面嘅關鍵步驟，我哋可以用嚟理解整體操作同角色分工。"


def convert_frames_to_draft(frames_dir: Path, draft_video: Path) -> None:
    run([
        FFMPEG,
        "-y",
        "-framerate",
        "1/6.5",
        "-i",
        str(frames_dir / "slide_%02d.png"),
        "-vf",
        "fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(draft_video),
    ])


def normalize_file_entry(entry: dict | str) -> Path:
    value = entry.get("path") if isinstance(entry, dict) else entry
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def cleanup_after_success(job_dir: Path, manifest_path: Path, final_video: Path) -> None:
    for directory in ("source", "docs", "work", "previews"):
        shutil.rmtree(job_dir / directory, ignore_errors=True)

    for item in job_dir.iterdir():
        if item.name in {"status.json"}:
            continue
        if item.is_dir() and item.name == "deliverables":
            for deliverable in item.iterdir():
                if deliverable.resolve() != final_video.resolve():
                    if deliverable.is_dir():
                        shutil.rmtree(deliverable, ignore_errors=True)
                    else:
                        deliverable.unlink(missing_ok=True)
            continue
        if item.is_file():
            item.unlink(missing_ok=True)
        elif item.is_dir():
            shutil.rmtree(item, ignore_errors=True)

    committed_dir = manifest_path.parent
    if committed_dir.parent == ROOT / "uploads" / "committed":
        shutil.rmtree(committed_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a manifest-driven PPT/image/PDF to Cantonese video job.")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job_dir = Path(manifest["job_dir"]).resolve()
    source_dir = job_dir / "source"
    docs_dir = job_dir / "docs"
    work_dir = job_dir / "work"
    frames_dir = work_dir / "frames"
    deliverables_dir = job_dir / "deliverables"
    previews_dir = job_dir / "previews"
    log_path = job_dir / "logs.txt"
    for directory in (source_dir, docs_dir, work_dir, frames_dir, deliverables_dir, previews_dir):
        directory.mkdir(parents=True, exist_ok=True)

    try:
        update_status(job_dir, "running", "preparing", 5, "正在準備素材")
        files = [normalize_file_entry(item) for item in manifest.get("files", [])]
        files = [path for path in files if path.exists()]
        if not files:
            raise RuntimeError("No existing files in manifest")

        copied: list[Path] = []
        for path in files:
            target = source_dir / path.name
            if path.resolve() != target.resolve():
                shutil.copy2(path, target)
            copied.append(target)

        presentations = [p for p in copied if p.suffix.lower() in SUPPORTED_PRESENTATIONS]
        images = [p for p in copied if p.suffix.lower() in SUPPORTED_IMAGES]
        pdfs = [p for p in copied if p.suffix.lower() in SUPPORTED_PDFS]

        update_status(job_dir, "running", "rendering", 20, "正在渲染 PPT / 圖片素材")
        slides: list[dict] = []
        if presentations:
            primary = presentations[0]
            run([PYTHON, "scripts/pptx_to_video_draft.py", str(primary), str(work_dir), "--no-subtitles"], log_path=log_path)
            source_manifest = work_dir / "noss_hyper_care_script.json"
            slides = json.loads(source_manifest.read_text(encoding="utf-8")).get("slides", [])
        else:
            frames_dir.mkdir(parents=True, exist_ok=True)

        next_slide = len(list(frames_dir.glob("slide_*.png"))) + 1
        for image_path in images:
            frame = frames_dir / f"slide_{next_slide:02d}.png"
            render_image_frame(image_path, frame, image_path.name)
            slides.append({"slide": next_slide, "frame": str(frame), "text": [image_path.name], "narration": ""})
            next_slide += 1

        for pdf_path in pdfs:
            frame = frames_dir / f"slide_{next_slide:02d}.png"
            thumb = work_dir / "pdf_thumbnails" / f"{pdf_path.stem}.png"
            if render_pdf_thumbnail(pdf_path, thumb, work_dir / "pdf_thumbnails"):
                render_image_frame(thumb, frame, pdf_path.name)
                slides.append({"slide": next_slide, "frame": str(frame), "text": [pdf_path.name], "narration": ""})
                next_slide += 1

        if not slides:
            raise RuntimeError("No renderable PPTX, image, or PDF files were found")
        if presentations and not has_extractable_text(slides):
            raise RuntimeError(
                "This PPT appears to contain image-only slides with no extractable text. "
                "CineCodex cannot generate reliable subtitles or voiceover without OCR or a provided script."
            )

        for index, slide in enumerate(slides, start=1):
            slide["slide"] = index
            slide["frame"] = str(frames_dir / f"slide_{index:02d}.png")

        slide_script = {"source": [str(path) for path in copied], "slides": slides}
        write_json(docs_dir / "slide_script.json", slide_script)

        draft_video = deliverables_dir / f"{slugify(job_dir.name)}_draft.mp4"
        convert_frames_to_draft(frames_dir, draft_video)

        update_status(job_dir, "running", "narration", 40, "正在生成粵語講稿")
        narration = {
            "source": [str(path) for path in copied],
            "language": "yue-HK",
            "seconds_per_slide": 6.5,
            "slides": [{"slide": slide["slide"], "text": cantonese_for_slide(slide)} for slide in slides],
        }
        narration_path = docs_dir / "cantonese_narration.json"
        write_json(narration_path, narration)

        update_status(job_dir, "running", "voiceover", 58, "正在生成自然粵語旁白")
        final_video = deliverables_dir / f"{slugify(job_dir.name)}_cantonese_subtitled.mp4"
        voice = manifest.get("options", {}).get("voice", "zh-HK-HiuMaanNeural")
        rate = manifest.get("options", {}).get("rate", "+0%")
        subtitles = manifest.get("options", {}).get("subtitles", True)
        tts_engine = manifest.get("options", {}).get("tts_engine", "edge")
        cleanup_cache = manifest.get("options", {}).get("cleanup_cache", True)
        run(
            [
                PYTHON,
                "scripts/edge_cantonese_voiceover.py",
                "--narration",
                str(narration_path),
                "--output-dir",
                str(job_dir),
                "--output-video",
                str(final_video),
                "--voice",
                voice,
                "--rate",
                rate,
                "--tts-engine",
                tts_engine,
                "--subtitles" if subtitles else "--no-subtitles",
            ],
            log_path=log_path,
        )
        subtitle_file = None
        generated_subtitles = job_dir / "work" / "edge_cantonese_audio" / "cantonese_subtitles.srt"
        if subtitles and generated_subtitles.exists():
            subtitle_file = deliverables_dir / f"{slugify(job_dir.name)}_subtitles.srt"
            shutil.copy2(generated_subtitles, subtitle_file)

        update_status(job_dir, "running", "preview", 92, "正在生成預覽圖")
        preview = previews_dir / "preview.jpg"
        run([FFMPEG, "-y", "-ss", "3", "-i", str(final_video), "-frames:v", "1", "-update", "1", str(preview)], log_path=log_path)

        result = {
            "job_id": manifest.get("job_id", job_dir.name),
            "status": "success",
            "output_dir": str(job_dir),
            "final_video": str(final_video),
            "draft_video": str(draft_video),
            "preview": str(preview),
            "narration": str(narration_path),
            "subtitles": str(subtitle_file) if subtitle_file else None,
            "logs": str(log_path),
        }
        if cleanup_cache:
            result.update({
                "draft_video": None,
                "preview": None,
                "narration": None,
                "subtitles": None,
                "logs": None,
            })
        write_json(job_dir / "result.json", result)
        status_result = {key: value for key, value in result.items() if key != "status"}
        update_status(job_dir, "success", "complete", 100, "視頻已成功生成", **status_result)
        if cleanup_cache:
            cleanup_after_success(job_dir, manifest_path, final_video)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        update_status(job_dir, "failed", "error", 100, str(exc), error=str(exc), logs=str(log_path))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
