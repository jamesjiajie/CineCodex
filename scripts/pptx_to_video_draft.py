from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from textwrap import wrap
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass
class Picture:
    rel_id: str
    box: Box
    crop: dict[str, int]


@dataclass
class TextBox:
    text: str
    box: Box
    size: int | None
    bold: bool


def q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(zf.read(name))


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_box(el: ET.Element, scale_x: float, scale_y: float) -> Box | None:
    xfrm = el.find(".//a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return Box(
        int(int(off.get("x", "0")) * scale_x),
        int(int(off.get("y", "0")) * scale_y),
        int(int(ext.get("cx", "0")) * scale_x),
        int(int(ext.get("cy", "0")) * scale_y),
    )


def rel_targets(zf: zipfile.ZipFile, slide_no: int) -> dict[str, str]:
    rel_path = f"ppt/slides/_rels/slide{slide_no}.xml.rels"
    if rel_path not in zf.namelist():
        return {}
    root = read_xml(zf, rel_path)
    targets = {}
    for rel in root.findall("rel:Relationship", NS):
        rel_id = rel.get("Id")
        target = rel.get("Target", "")
        if rel_id and "relationships/image" in rel.get("Type", ""):
            targets[rel_id] = posixpath.normpath(posixpath.join("ppt/slides", target))
    return targets


def normalize_target(target: str) -> str:
    parts = []
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def extract_slide(root: ET.Element, scale_x: float, scale_y: float) -> tuple[list[TextBox], list[Picture]]:
    texts: list[TextBox] = []
    pictures: list[Picture] = []
    for child in root.findall(".//p:spTree/*", NS):
        name = local_name(child.tag)
        if name == "sp":
            box = get_box(child, scale_x, scale_y)
            runs = child.findall(".//a:r", NS)
            parts = []
            sizes = []
            bold = False
            for run in runs:
                text_el = run.find("a:t", NS)
                if text_el is None or text_el.text is None:
                    continue
                parts.append(text_el.text)
                rpr = run.find("a:rPr", NS)
                if rpr is not None:
                    if rpr.get("sz"):
                        sizes.append(int(rpr.get("sz", "0")) / 100)
                    if rpr.get("b") == "1":
                        bold = True
            text = clean_text("".join(parts))
            if box and text:
                size = int(max(sizes)) if sizes else None
                texts.append(TextBox(text=text, box=box, size=size, bold=bold))
        elif name == "pic":
            box = get_box(child, scale_x, scale_y)
            blip = child.find(".//a:blip", NS)
            if box is None or blip is None:
                continue
            rel_id = blip.get(q("r:embed"))
            if not rel_id:
                continue
            src = child.find(".//a:srcRect", NS)
            crop = {}
            if src is not None:
                for side in ("l", "t", "r", "b"):
                    if src.get(side):
                        crop[side] = int(src.get(side, "0"))
            pictures.append(Picture(rel_id=rel_id, box=box, crop=crop))
    return texts, pictures


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    if not text:
        return []
    lines = []
    current = ""
    for token in re.findall(r"[\u4e00-\u9fff]|[^\s\u4e00-\u9fff]+|\s+", text):
        if token.isspace():
            token = " "
        candidate = current + token
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def crop_image(img: Image.Image, crop: dict[str, int]) -> Image.Image:
    if not crop:
        return img
    w, h = img.size
    left = int(w * crop.get("l", 0) / 100000)
    top = int(h * crop.get("t", 0) / 100000)
    right = w - int(w * crop.get("r", 0) / 100000)
    bottom = h - int(h * crop.get("b", 0) / 100000)
    if right <= left or bottom <= top:
        return img
    return img.crop((left, top, right, bottom))


def draw_text_box(draw: ImageDraw.ImageDraw, tb: TextBox) -> None:
    is_title = tb.box.y < 170 and tb.box.h > 50
    font_size = max(16, min(58 if is_title else 28, int((tb.size or (34 if is_title else 18)) * 1.35)))
    font = load_font(font_size, tb.bold or is_title)
    color = (20, 24, 30)
    lines = fit_text(draw, tb.text, font, max(80, tb.box.w))
    line_h = int(font_size * 1.25)
    y = tb.box.y
    for line in lines[: max(1, tb.box.h // max(1, line_h))]:
        draw.text((tb.box.x, y), line, font=font, fill=color)
        y += line_h


def narration_for_slide(texts: list[TextBox]) -> str:
    raw = [t.text for t in texts if len(t.text) > 1]
    joined = "。".join(raw)
    if "Over 100" in joined:
        return "当前流程每天超过一百个案例，每个案例平均要十分钟，错误信息不清晰，也容易造成投诉和返工。"
    if "Sales places" in joined:
        return "这是当前 Noss Hyper Care 流程：销售下单后，异常订单交给 IT 检查，IT 排查修复后再通知施工师傅。"
    if "Hyper" in joined and "flow" in joined:
        return "这一页概览 Noss Hyper Care 的处理链路，以及各角色之间的交接方式。"
    if raw:
        return "这一页说明：" + "；".join(raw[:3]) + "。"
    return "这一页展示了流程中的关键步骤。"


def draw_subtitle(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    panel_h = 110
    draw.rectangle((0, img.height - panel_h, img.width, img.height), fill=(0, 0, 0, 178))
    font = load_font(30)
    lines = fit_text(draw, text, font, img.width - 180)
    y = img.height - panel_h + 22
    for line in lines[:2]:
        draw.text((90, y), line, font=font, fill=(255, 255, 255, 255))
        y += 40


def render(pptx: Path, out_dir: Path, draw_subtitles: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pptx) as zf:
        presentation = read_xml(zf, "ppt/presentation.xml")
        size_el = presentation.find("p:sldSz", NS)
        src_w = int(size_el.get("cx", "12192000")) if size_el is not None else 12192000
        src_h = int(size_el.get("cy", "6858000")) if size_el is not None else 6858000
        width, height = 1280, 720
        scale_x, scale_y = width / src_w, height / src_h
        slide_names = sorted(
            [n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
            key=lambda n: int(re.search(r"slide(\d+)", n).group(1)),
        )

        manifest = {"source": str(pptx), "slides": []}
        gif_frames: list[Image.Image] = []
        durations: list[int] = []

        for index, slide_name in enumerate(slide_names, start=1):
            root = read_xml(zf, slide_name)
            texts, pictures = extract_slide(root, scale_x, scale_y)
            targets = {k: normalize_target(v) for k, v in rel_targets(zf, index).items()}

            img = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(img)
            for pic in pictures:
                target = targets.get(pic.rel_id)
                if not target or target not in zf.namelist():
                    continue
                try:
                    pic_img = Image.open(BytesIO(zf.read(target))).convert("RGB")
                    pic_img = crop_image(pic_img, pic.crop)
                    pic_img = pic_img.resize((max(1, pic.box.w), max(1, pic.box.h)), Image.LANCZOS)
                    img.paste(pic_img, (pic.box.x, pic.box.y))
                except Exception:
                    continue
            for tb in texts:
                draw_text_box(draw, tb)

            narration = narration_for_slide(texts)
            if draw_subtitles:
                draw_subtitle(img, narration)
            frame_path = frames_dir / f"slide_{index:02d}.png"
            img.save(frame_path)
            gif_frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))
            durations.append(6500)
            manifest["slides"].append(
                {
                    "slide": index,
                    "frame": str(frame_path),
                    "text": [t.text for t in texts],
                    "narration": narration,
                }
            )

    gif_path = out_dir / "noss_hyper_care_draft.gif"
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    manifest_path = out_dir / "noss_hyper_care_script.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"gif": gif_path, "manifest": manifest_path, "frames": frames_dir}


def convert_to_mp4(gif_path: Path, mp4_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    frames_dir = gif_path.parent / "frames"
    if Path(ffmpeg).exists() and frames_dir.exists():
        cmd = [
            ffmpeg,
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
            str(mp4_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return mp4_path.exists()
        except Exception as exc:
            print(f"ffmpeg conversion failed: {exc}", file=sys.stderr)

    cmd = [
        "avconvert",
        "--source",
        str(gif_path),
        "--preset",
        "Preset1280x720",
        "--output",
        str(mp4_path),
        "--replace",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return mp4_path.exists()
    except Exception as exc:
        print(f"MP4 conversion failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Render PPTX slides to frames and draft video.")
    parser.add_argument("pptx")
    parser.add_argument("output_dir")
    parser.add_argument("--no-subtitles", action="store_true")
    args = parser.parse_args()

    pptx = Path(args.pptx).resolve()
    out_dir = Path(args.output_dir).resolve()
    result = render(pptx, out_dir, draw_subtitles=not args.no_subtitles)
    mp4_path = out_dir / "noss_hyper_care_draft.mp4"
    ok = convert_to_mp4(result["gif"], mp4_path)
    print(json.dumps({**{k: str(v) for k, v in result.items()}, "mp4": str(mp4_path), "mp4_ok": ok}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
