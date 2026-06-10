from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(ffprobe: str, path: Path) -> float:
    for entry in ("format=duration", "stream=duration"):
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                entry,
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            value = line.strip()
            if value and value != "N/A":
                return float(value)
    raise ValueError(f"Could not determine media duration: {path}")


def srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_srt(slides: list[dict], durations: list[float], path: Path) -> None:
    cursor = 0.0
    blocks = []
    for index, (slide, duration) in enumerate(zip(slides, durations), start=1):
        start = cursor
        end = cursor + duration
        text = re.sub(r"\s+", " ", slide["text"]).strip()
        blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
        cursor = end
    path.write_text("\n".join(blocks), encoding="utf-8")


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]:
        path = Path(font_path)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    tokens = re.findall(r"[\u4e00-\u9fff]|[^\s\u4e00-\u9fff]+|\s+", text)
    for token in tokens:
        token = " " if token.isspace() else token
        candidate = current + token
        if draw.textlength(candidate, font=font) <= max_width or not current.strip():
            current = candidate
            continue
        lines.append(current.strip())
        current = token
    if current.strip():
        lines.append(current.strip())
    return lines[:3]


def draw_subtitle(frame: Image.Image, text: str) -> Image.Image:
    img = frame.convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    font = load_font(max(24, int(width * 0.032)))
    text = re.sub(r"\s+", " ", text).strip()
    lines = wrap_text(draw, text, font, int(width * 0.82))
    if not lines:
        return img

    line_height = int(font.size * 1.35) if hasattr(font, "size") else 40
    pad_x = int(width * 0.035)
    pad_y = int(height * 0.025)
    box_width = max(int(draw.textlength(line, font=font)) for line in lines) + pad_x * 2
    box_height = line_height * len(lines) + pad_y * 2
    x0 = (width - box_width) // 2
    y0 = height - box_height - int(height * 0.055)
    x1 = x0 + box_width
    y1 = y0 + box_height
    draw.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=(0, 0, 0, 190))

    y = y0 + pad_y
    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = (width - line_width) / 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height
    return img


def render_caption_frames(frames_dir: Path, slides: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, slide in enumerate(slides, start=1):
        source = frames_dir / f"slide_{index:02d}.png"
        target = output_dir / f"slide_{index:02d}.png"
        captioned = draw_subtitle(Image.open(source), slide["text"])
        captioned.save(target)
    return output_dir


async def synthesize(text: str, voice: str, rate: str, output: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output))


def synthesize_with_say(text: str, voice: str, rate: str, output: Path) -> None:
    run(["say", "-v", voice, "-r", rate, "-o", str(output), text])


def create_silence(ffmpeg: str, duration: float, output: Path) -> None:
    run([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{duration:.3f}",
        str(output),
    ])


def valid_media(ffprobe: str, path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        return ffprobe_duration(ffprobe, path) > 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate natural Cantonese narration with edge-tts and mux it into video.")
    parser.add_argument("--narration", default="outputs/noss_hyper_care_video/docs/cantonese_narration.json")
    parser.add_argument("--output-video", default="outputs/noss_hyper_care_video/deliverables/noss_hyper_care_edge_cantonese.mp4")
    parser.add_argument("--output-dir", default="outputs/noss_hyper_care_video")
    parser.add_argument("--voice", default="zh-HK-HiuMaanNeural")
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--tts-engine", choices=["edge", "say", "silent"], default="edge")
    parser.add_argument("--say-voice", default="Tingting")
    parser.add_argument("--say-rate", default="175")
    parser.add_argument("--seconds-per-slide", type=float, default=6.5)
    parser.add_argument("--tail-pad", type=float, default=0.35)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--subtitles", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reuse-audio", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ffmpeg", default="/opt/homebrew/bin/ffmpeg")
    parser.add_argument("--ffprobe", default="/opt/homebrew/bin/ffprobe")
    args = parser.parse_args()

    narration = json.loads(Path(args.narration).read_text(encoding="utf-8"))
    minimum_seconds_per_slide = float(narration.get("seconds_per_slide", args.seconds_per_slide))
    out_dir = Path(args.output_dir).resolve()
    frames_dir = out_dir / "work" / "frames"
    audio_dir = out_dir / "work" / "edge_cantonese_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    padded_files: list[Path] = []
    durations: list[float] = []
    slides = narration["slides"]
    for slide in slides:
        slide_no = int(slide["slide"])
        text = slide["text"]
        slide_minimum_seconds = float(slide.get("duration_seconds", minimum_seconds_per_slide))
        raw_audio = audio_dir / f"slide_{slide_no:02d}.mp3"
        if args.tts_engine == "say":
            raw_audio = audio_dir / f"slide_{slide_no:02d}.aiff"
        padded_wav = audio_dir / f"slide_{slide_no:02d}_padded.wav"

        if args.tts_engine == "silent":
            print(f"Creating silent audio for slide {slide_no}...")
            duration = slide_minimum_seconds
            durations.append(duration)
            create_silence(args.ffmpeg, duration, padded_wav)
            padded_files.append(padded_wav)
            continue

        if args.reuse_audio and valid_media(args.ffprobe, raw_audio):
            print(f"Reusing slide {slide_no} audio...")
        else:
            if args.tts_engine == "say":
                print(f"Synthesizing slide {slide_no} locally with macOS say...")
                synthesize_with_say(text, args.say_voice, args.say_rate, raw_audio)
            else:
                print(f"Synthesizing slide {slide_no} with {args.voice}...")
                asyncio.run(synthesize(text, args.voice, args.rate, raw_audio))

        raw_duration = ffprobe_duration(args.ffprobe, raw_audio)
        duration = max(slide_minimum_seconds, raw_duration + args.tail_pad)
        durations.append(duration)
        if raw_duration <= 0:
            print(f"Audio for slide {slide_no} was empty; using silence.")
            create_silence(args.ffmpeg, duration, padded_wav)
            padded_files.append(padded_wav)
            continue
        run([
            args.ffmpeg,
            "-y",
            "-i",
            str(raw_audio),
            "-af",
            f"apad=pad_dur={duration}",
            "-t",
            f"{duration:.3f}",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(padded_wav),
        ])
        padded_files.append(padded_wav)

    concat_audio = audio_dir / "concat_audio.txt"
    concat_audio.write_text("\n".join(f"file '{path.as_posix()}'" for path in padded_files) + "\n", encoding="utf-8")
    combined_wav = audio_dir / "noss_hyper_care_edge_cantonese.wav"
    run([args.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_audio), "-c", "copy", str(combined_wav)])

    subtitle_path = audio_dir / "cantonese_subtitles.srt"
    if args.subtitles:
        write_srt(slides, durations, subtitle_path)

    video_frames_dir = frames_dir
    if args.subtitles:
        video_frames_dir = render_caption_frames(frames_dir, slides, audio_dir / "captioned_frames")

    frame_concat = audio_dir / "frames_concat.txt"
    frame_concat.write_text(
        "".join(
            f"file '{(video_frames_dir / f'slide_{index:02d}.png').as_posix()}'\n"
            f"duration {duration:.3f}\n"
            for index, duration in enumerate(durations, start=1)
        )
        + f"file '{(video_frames_dir / f'slide_{len(durations):02d}.png').as_posix()}'\n",
        encoding="utf-8",
    )
    timed_video = audio_dir / "noss_hyper_care_timed_video.mp4"
    video_filter = f"fps={args.fps},format=yuv420p"
    run([
        args.ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(frame_concat),
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(timed_video),
    ])

    output_video = Path(args.output_video).resolve()
    run([
        args.ffmpeg,
        "-y",
        "-i",
        str(timed_video),
        "-i",
        str(combined_wav),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_video),
    ])
    print(output_video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
