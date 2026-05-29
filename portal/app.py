from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse


ROOT = Path("/Users/james/Document/Projects/CineCodex")
UPLOADS = ROOT / "uploads"
STAGING = UPLOADS / "staging"
COMMITTED = UPLOADS / "committed"
JOBS = ROOT / "outputs" / "jobs"

ALLOWED_EXTENSIONS = {
    ".ppt",
    ".pptx",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

app = FastAPI(title="CineCodex Portal")


def slugify(value: str) -> str:
    import re

    value = re.sub(r"[^\w\s.-]+", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[\s.]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "video-job"


def safe_name(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    return name


def session_dir(session_id: str) -> Path:
    path = STAGING / session_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    return path


def list_session_files(path: Path) -> list[dict]:
    files_dir = path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    return [
        {
            "name": item.name,
            "path": str(item),
            "size": item.stat().st_size,
            "type": item.suffix.lower(),
        }
        for item in sorted(files_dir.iterdir())
        if item.is_file()
    ]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CineCodex Portal</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #20242a;
      --muted: #68707d;
      --line: #d8dde5;
      --accent: #0f766e;
      --accent-2: #1d4ed8;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
      gap: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .section-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h2 { font-size: 15px; margin: 0; }
    .body { padding: 16px; }
    .drop {
      border: 1px dashed #9aa4b2;
      border-radius: 8px;
      min-height: 210px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 28px;
      background: #fbfcfd;
    }
    .drop.drag { border-color: var(--accent); background: #effaf8; }
    .muted { color: var(--muted); font-size: 13px; }
    input[type=file] { display: none; }
    button, label.button {
      appearance: none;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      height: 36px;
      border-radius: 6px;
      padding: 0 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button.blue { background: var(--accent-2); border-color: var(--accent-2); color: white; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      vertical-align: middle;
    }
    th { color: var(--muted); font-weight: 600; }
    tr:last-child td { border-bottom: 0; }
    .settings {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    label.field { display: grid; gap: 6px; font-size: 13px; color: var(--muted); }
    select, input[type=text] {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font-size: 13px;
      background: white;
      color: var(--ink);
      width: 100%;
    }
    .check {
      height: 36px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--ink);
    }
    .progress {
      height: 10px;
      border-radius: 999px;
      background: #e8edf3;
      overflow: hidden;
      margin: 10px 0 8px;
    }
    .bar { height: 100%; width: 0%; background: var(--accent); transition: width .25s ease; }
    .status {
      display: grid;
      gap: 12px;
    }
    .path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #f2f4f7;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .ok { color: var(--accent); }
    .err { color: var(--danger); }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; padding: 16px; }
      .settings { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>CineCodex Portal</h1>
    <div class="muted" id="sessionLabel"></div>
  </header>
  <main>
    <section>
      <div class="section-head">
        <h2>Upload Batch</h2>
        <div class="toolbar">
          <label class="button" for="files">Choose Files</label>
          <button id="clearBtn">Clear</button>
        </div>
      </div>
      <div class="body">
        <div id="drop" class="drop">
          <div>
            <div style="font-weight:650;margin-bottom:6px;">Drop PPT, PDF, or images here</div>
            <div class="muted">pptx, ppt, pdf, png, jpg, jpeg, webp, bmp, tif</div>
          </div>
        </div>
        <input id="files" type="file" multiple accept=".ppt,.pptx,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" />
        <div style="margin-top:16px; overflow:auto;">
          <table>
            <thead><tr><th>Name</th><th>Type</th><th>Size</th><th></th></tr></thead>
            <tbody id="fileList"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>Generate</h2>
        <button class="primary" id="commitBtn">Commit & Generate</button>
      </div>
      <div class="body status">
        <div class="settings">
          <label class="field">Voice
            <select id="voice">
              <option value="zh-HK-HiuMaanNeural">HiuMaan</option>
              <option value="zh-HK-HiuGaaiNeural">HiuGaai</option>
              <option value="zh-HK-WanLungNeural">WanLung</option>
            </select>
          </label>
          <label class="field">Rate
            <select id="rate">
              <option value="+0%">Normal</option>
              <option value="-8%">Slower</option>
              <option value="+8%">Faster</option>
            </select>
          </label>
          <label class="check"><input type="checkbox" id="subtitles" checked /> Burn subtitles</label>
        </div>

        <div>
          <div class="progress"><div class="bar" id="bar"></div></div>
          <div class="muted" id="message">Ready</div>
        </div>

        <div id="result" style="display:none;">
          <div id="resultTitle" style="font-weight:650;margin-bottom:8px;"></div>
          <div class="muted">Output folder</div>
          <div class="path" id="outputDir"></div>
          <div class="muted" style="margin-top:10px;">Final video</div>
          <div class="path" id="finalVideo"></div>
          <div class="muted" style="margin-top:10px;">Subtitles</div>
          <div class="path" id="subtitleFile"></div>
        </div>
      </div>
    </section>
  </main>

  <script>
    let sessionId = null;
    let jobId = null;
    let pollTimer = null;

    const $ = (id) => document.getElementById(id);
    const fmt = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(1)} MB`;

    async function api(path, options) {
      const res = await fetch(path, options);
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      return res.json();
    }

    async function init() {
      const data = await api('/api/sessions', { method: 'POST' });
      sessionId = data.session_id;
      $('sessionLabel').textContent = sessionId;
      await refreshFiles();
    }

    async function refreshFiles() {
      const data = await api(`/api/sessions/${sessionId}`);
      const rows = data.files.map(file => `
        <tr>
          <td>${file.name}</td>
          <td>${file.type}</td>
          <td>${fmt(file.size)}</td>
          <td><button data-remove="${file.name}">Remove</button></td>
        </tr>`).join('');
      $('fileList').innerHTML = rows || '<tr><td colspan="4" class="muted">No files staged</td></tr>';
      document.querySelectorAll('[data-remove]').forEach(btn => {
        btn.onclick = async () => { await api(`/api/sessions/${sessionId}/files/${encodeURIComponent(btn.dataset.remove)}`, { method: 'DELETE' }); await refreshFiles(); };
      });
    }

    async function uploadFiles(files) {
      if (!files.length) return;
      const form = new FormData();
      [...files].forEach(file => form.append('files', file));
      $('message').textContent = 'Uploading...';
      await api(`/api/sessions/${sessionId}/upload`, { method: 'POST', body: form });
      $('message').textContent = 'Ready';
      await refreshFiles();
    }

    async function commit() {
      $('commitBtn').disabled = true;
      $('result').style.display = 'none';
      const payload = {
        voice: $('voice').value,
        rate: $('rate').value,
        subtitles: $('subtitles').checked
      };
      const data = await api(`/api/sessions/${sessionId}/commit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      jobId = data.job_id;
      $('message').textContent = 'Committed. Waiting for n8n...';
      pollTimer = setInterval(pollStatus, 1200);
      await pollStatus();
    }

    async function pollStatus() {
      if (!jobId) return;
      const status = await api(`/api/jobs/${jobId}/status`);
      $('bar').style.width = `${status.progress || 0}%`;
      $('message').textContent = status.message || status.step || status.status;
      if (status.status === 'success') {
        clearInterval(pollTimer);
        $('commitBtn').disabled = false;
        $('result').style.display = 'block';
        $('resultTitle').textContent = 'Generated successfully';
        $('resultTitle').className = 'ok';
        $('outputDir').textContent = status.output_dir || status.job_dir;
        $('finalVideo').textContent = status.final_video || '';
        $('subtitleFile').textContent = status.subtitles || '';
      }
      if (status.status === 'failed') {
        clearInterval(pollTimer);
        $('commitBtn').disabled = false;
        $('result').style.display = 'block';
        $('resultTitle').textContent = 'Generation failed';
        $('resultTitle').className = 'err';
        $('outputDir').textContent = status.job_dir || '';
        $('finalVideo').textContent = status.error || status.message || '';
        $('subtitleFile').textContent = '';
      }
    }

    $('files').onchange = (e) => uploadFiles(e.target.files);
    $('commitBtn').onclick = commit;
    $('clearBtn').onclick = async () => { await api(`/api/sessions/${sessionId}`, { method: 'DELETE' }); await init(); };
    const drop = $('drop');
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('drag'); };
    drop.ondragleave = () => drop.classList.remove('drag');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('drag'); uploadFiles(e.dataTransfer.files); };
    init().catch(err => { $('message').textContent = err.message; });
  </script>
</body>
</html>
"""


@app.post("/api/sessions")
def create_session() -> dict:
    session_id = uuid.uuid4().hex[:12]
    path = STAGING / session_id / "files"
    path.mkdir(parents=True, exist_ok=True)
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    path = session_dir(session_id)
    return {"session_id": session_id, "files": list_session_files(path)}


@app.post("/api/sessions/{session_id}/upload")
async def upload_files(session_id: str, files: Annotated[list[UploadFile], File()]) -> dict:
    path = session_dir(session_id)
    files_dir = path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for upload in files:
        name = safe_name(upload.filename or "")
        target = files_dir / name
        index = 1
        while target.exists():
            stem = Path(name).stem
            suffix = Path(name).suffix
            target = files_dir / f"{stem}-{index}{suffix}"
            index += 1
        with target.open("wb") as fh:
            while chunk := await upload.read(1024 * 1024):
                fh.write(chunk)
        saved.append(target.name)
    return {"saved": saved, "files": list_session_files(path)}


@app.delete("/api/sessions/{session_id}/files/{filename}")
def delete_file(session_id: str, filename: str) -> dict:
    path = session_dir(session_id)
    target = path / "files" / Path(filename).name
    if target.exists():
        target.unlink()
    return {"files": list_session_files(path)}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    path = STAGING / session_id
    if path.exists():
        shutil.rmtree(path)
    return {"deleted": session_id}


@app.post("/api/sessions/{session_id}/commit")
def commit_session(session_id: str, options: dict) -> dict:
    path = session_dir(session_id)
    files = list_session_files(path)
    if not files:
        raise HTTPException(status_code=400, detail="No files staged")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    first_stem = slugify(Path(files[0]["name"]).stem)
    job_id = f"{first_stem}-{stamp}-{uuid.uuid4().hex[:6]}"
    committed = COMMITTED / job_id
    job_dir = JOBS / job_id
    committed_files = committed / "files"
    committed_files.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)

    committed_entries = []
    for file in files:
        source = Path(file["path"])
        target = committed_files / source.name
        shutil.copy2(source, target)
        committed_entries.append({"name": target.name, "path": str(target), "type": target.suffix.lower(), "size": target.stat().st_size})

    manifest = {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "files": committed_entries,
        "options": {
            "language": "yue-HK",
            "voice": options.get("voice", "zh-HK-HiuMaanNeural"),
            "rate": options.get("rate", "+0%"),
            "tts_engine": options.get("tts_engine", "edge"),
            "subtitles": bool(options.get("subtitles", True)),
            "cleanup_cache": bool(options.get("cleanup_cache", True)),
        },
    }
    write_json(job_dir / "status.json", {
        "status": "queued",
        "step": "queued",
        "progress": 1,
        "message": "Queued. Waiting for n8n automation.",
        "job_id": job_id,
        "job_dir": str(job_dir),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    manifest_path = committed / "manifest.json"
    write_json(manifest_path, manifest)
    shutil.rmtree(path)
    return {"job_id": job_id, "job_dir": str(job_dir), "manifest": str(manifest_path)}


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str) -> dict:
    status_path = JOBS / job_id / "status.json"
    if not status_path.exists():
        return {"status": "queued", "step": "queued", "progress": 1, "message": "Waiting for status file", "job_id": job_id}
    return json.loads(status_path.read_text(encoding="utf-8"))
