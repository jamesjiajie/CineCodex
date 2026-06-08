from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import v3_llm, v3_ppt, v3_subtitles, v3_tts
from .v3_projects import create_project as create_v3_project
from .v3_projects import list_projects as list_v3_projects
from .v3_projects import project_dir as v3_project_dir
from .v3_projects import public_project, read_project, save_project, write_json as write_v3_json


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
V3_SOURCE_EXTENSIONS = {".pptx"}
V3_SUBTITLE_EXTENSIONS = {".txt", ".srt", ".vtt"}

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
    button, label.button, a.button {
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
      text-decoration: none;
    }
    button.primary, a.button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button.blue, a.button.blue { background: var(--accent-2); border-color: var(--accent-2); color: white; }
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
    <div class="toolbar">
      <a class="button blue" href="/v3">Open V3 LLM Subtitle Workspace</a>
      <div class="muted" id="sessionLabel"></div>
    </div>
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


@app.get("/v3", response_class=HTMLResponse)
def v3_index() -> str:
    return """
<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CineCodex V3</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #687484;
      --line: #d8dee8;
      --accent: #0f766e;
      --blue: #2563eb;
      --warn: #9a3412;
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
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; }
    button, .button {
      height: 34px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      padding: 0 11px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      cursor: pointer;
      font-size: 13px;
      color: var(--ink);
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button.blue { background: var(--blue); border-color: var(--blue); color: white; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    input[type=file] { display: none; }
    main {
      min-height: calc(100vh - 58px);
      display: grid;
      grid-template-columns: 245px minmax(360px, 1fr) 390px;
    }
    aside, section {
      min-width: 0;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    section.preview { background: #f8fafc; }
    .pane-head {
      min-height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      gap: 8px;
    }
    h2 { font-size: 14px; margin: 0; }
    .body { padding: 14px; }
    .muted { color: var(--muted); font-size: 12px; }
    .stack { display: grid; gap: 10px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
    .field { display: grid; gap: 5px; font-size: 12px; color: var(--muted); }
    select, textarea, input[type=text], input[type=number] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 13px;
    }
    select, input[type=text], input[type=number] { height: 34px; padding: 0 9px; }
    textarea { min-height: 124px; padding: 9px; resize: vertical; line-height: 1.45; }
    .drop {
      border: 1px dashed #9aa4b2;
      border-radius: 8px;
      background: #fbfcfd;
      min-height: 128px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 18px;
    }
    .slide-list { display: grid; gap: 8px; }
    .slide-item {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 9px;
      background: #fff;
      cursor: pointer;
    }
    .slide-item.active { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
    .thumb {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #eef2f7;
    }
    .slide-title {
      margin-top: 7px;
      font-size: 12px;
      font-weight: 650;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .preview-img {
      width: 100%;
      max-height: 58vh;
      object-fit: contain;
      background: white;
      border-bottom: 1px solid var(--line);
    }
    .text-box {
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: white;
      padding: 10px;
      font-size: 13px;
      line-height: 1.45;
      min-height: 90px;
    }
    .warn { color: var(--warn); }
    .err { color: var(--danger); }
    .ok { color: var(--accent); }
    .path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      border: 1px solid var(--line);
      background: #f3f5f8;
      border-radius: 6px;
      padding: 8px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .control-group {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 10px;
      background: #fbfcfd;
    }
    .group-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
      font-weight: 650;
    }
    .check-row {
      min-height: 32px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }
    @media (max-width: 1040px) {
      main { grid-template-columns: 1fr; }
      aside, section { border-right: 0; border-bottom: 1px solid var(--line); }
      .preview-img { max-height: 44vh; }
    }
  </style>
</head>
<body>
  <header>
    <h1>CineCodex V3</h1>
    <div class="toolbar">
      <a class="button" href="/">V2.1</a>
      <button id="refreshBtn">Refresh</button>
    </div>
  </header>
  <main>
    <aside>
      <div class="pane-head">
        <h2>Projects</h2>
        <label class="button" for="pptFile">New PPTX</label>
      </div>
      <div class="body stack">
        <input id="pptFile" type="file" accept=".pptx" />
        <div class="drop" id="drop">
          <div>
            <div style="font-weight:650;margin-bottom:5px;">Drop PPTX</div>
            <div class="muted">V3 extracts slides first</div>
          </div>
        </div>
        <div class="slide-list" id="projectList"></div>
      </div>
    </aside>

    <section class="preview">
      <div class="pane-head">
        <h2 id="projectTitle">No project selected</h2>
        <div class="toolbar">
          <button id="extractBtn">Extract</button>
          <label class="button" for="subtitleFile">Import Subtitles</label>
        </div>
      </div>
      <input id="subtitleFile" type="file" accept=".txt,.srt,.vtt" />
      <div id="previewBody" class="stack">
        <div class="body muted">Create or select a V3 project.</div>
      </div>
    </section>

    <section>
      <div class="pane-head">
        <h2>Narration</h2>
        <button class="primary" id="saveSlideBtn">Save Slide</button>
      </div>
      <div class="body stack">
        <div class="control-group">
          <div class="group-title">
            <span>Subtitle Source</span>
            <label class="button" for="subtitleFile">Upload File</label>
          </div>
          <label class="field">Paste Subtitle Text
            <textarea id="pastedSubtitles" placeholder="Paste plain text, SRT, or VTT subtitles"></textarea>
          </label>
          <div class="toolbar">
            <select id="pastedSubtitleFormat" style="width:112px;">
              <option value=".txt" selected>Text</option>
              <option value=".srt">SRT</option>
              <option value=".vtt">VTT</option>
            </select>
            <button id="pasteSubtitleBtn">Use Pasted Text</button>
          </div>
        </div>
        <div class="control-group">
          <div class="group-title">LLM Processing</div>
          <label class="check-row"><input type="checkbox" id="useLlm" /> Call LLM after subtitle import</label>
          <label class="field">Mode
            <select id="llmMode">
              <option value="check">Check</option>
              <option value="polish" selected>Polish</option>
              <option value="rewrite">Rewrite</option>
            </select>
          </label>
          <label class="field">Provider
            <select id="llmProvider">
              <option value="mock" selected>Mock Local</option>
              <option value="openai_api">OpenAI API</option>
              <option value="mcp">MCP</option>
            </select>
          </label>
          <div class="toolbar">
            <button class="blue" id="autoBtn">Auto From PPT</button>
            <button class="blue" id="llmBtn">Run LLM Now</button>
          </div>
        </div>
        <label class="field">Narration
          <textarea id="narrationText"></textarea>
        </label>
        <label class="field">Subtitle
          <textarea id="subtitleText"></textarea>
        </label>
        <label class="field">Duration Seconds
          <input id="durationInput" type="number" min="2" max="120" step="0.5" />
        </label>
        <div class="toolbar">
          <select id="ttsEngine" style="width:128px;">
            <option value="silent" selected>Silent</option>
            <option value="say">macOS Say</option>
            <option value="edge">Edge TTS</option>
          </select>
          <button id="voiceBtn">Generate Voice</button>
          <button id="srtBtn">Export SRT</button>
        </div>
        <div id="message" class="muted">Ready</div>
        <div class="path" id="exportPath" style="display:none;"></div>
      </div>
    </section>
  </main>

  <script>
    let currentProject = null;
    let currentSlide = 0;
    const $ = (id) => document.getElementById(id);

    async function api(path, options) {
      const res = await fetch(path, options);
      const type = res.headers.get('content-type') || '';
      if (!res.ok) {
        let detail = res.statusText;
        if (type.includes('application/json')) detail = (await res.json()).detail || detail;
        throw new Error(detail);
      }
      return type.includes('application/json') ? res.json() : res.text();
    }

    function message(text, cls = 'muted') {
      $('message').textContent = text;
      $('message').className = cls;
    }

    async function refreshProjects() {
      const data = await api('/api/v3/projects');
      $('projectList').innerHTML = data.projects.map(p => `
        <div class="slide-item" data-project="${p.project_id}">
          <div style="font-weight:650;font-size:13px;">${p.project_id}</div>
          <div class="muted">${p.slide_count} slides · ${p.status || 'created'}</div>
        </div>`).join('') || '<div class="muted">No V3 projects yet</div>';
      document.querySelectorAll('[data-project]').forEach(el => {
        el.onclick = () => loadProject(el.dataset.project);
      });
    }

    async function createProject(file) {
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      form.append('language', 'zh-CN');
      form.append('llm_provider', $('llmProvider').value);
      message('Creating project...');
      currentProject = await api('/api/v3/projects', { method: 'POST', body: form });
      currentSlide = 0;
      await refreshProjects();
      renderProject();
      message('Project created. Extract slides next.', 'ok');
    }

    async function loadProject(id) {
      currentProject = await api(`/api/v3/projects/${id}`);
      currentSlide = 0;
      renderProject();
      message('Project loaded', 'ok');
    }

    function renderProject() {
      if (!currentProject) return;
      $('projectTitle').textContent = currentProject.project_id;
      const slides = currentProject.slides || [];
      if (!slides.length) {
        $('previewBody').innerHTML = '<div class="body muted">No slides extracted yet.</div>';
        clearEditor();
        return;
      }
      const slide = slides[currentSlide] || slides[0];
      currentSlide = slides.indexOf(slide);
      $('previewBody').innerHTML = `
        <img class="preview-img" src="/api/v3/projects/${currentProject.project_id}/slides/${slide.slide_number}/thumbnail?t=${Date.now()}" />
        <div class="body stack">
          <div class="toolbar">${slides.map((s, i) => `<button data-slide="${i}" class="${i === currentSlide ? 'primary' : ''}">${s.slide_number}</button>`).join('')}</div>
          <div>
            <div class="muted">Extracted Text</div>
            <div class="text-box">${(slide.extracted.raw_text || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</div>
          </div>
          ${(slide.warnings || []).map(w => `<div class="warn">${w}</div>`).join('')}
        </div>`;
      document.querySelectorAll('[data-slide]').forEach(btn => {
        btn.onclick = () => { currentSlide = Number(btn.dataset.slide); renderProject(); };
      });
      renderEditor(slide);
    }

    function clearEditor() {
      $('narrationText').value = '';
      $('subtitleText').value = '';
      $('durationInput').value = '';
    }

    function renderEditor(slide) {
      const narration = slide.narration || {};
      $('narrationText').value = narration.text || '';
      $('subtitleText').value = narration.subtitle || narration.text || '';
      $('durationInput').value = narration.duration_seconds || 6.5;
    }

    async function extract() {
      if (!currentProject) return;
      message('Extracting PPT...');
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/extract`, { method: 'POST' });
      currentSlide = 0;
      renderProject();
      message('Slides extracted', 'ok');
    }

    async function importSubtitles(file) {
      if (!currentProject || !file) return;
      const form = new FormData();
      form.append('file', file);
      message('Importing subtitles...');
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/subtitles/import`, { method: 'POST', body: form });
      renderProject();
      if ($('useLlm').checked) {
        await llmProcess();
        return;
      }
      message('Subtitle file imported and mapped', 'ok');
    }

    async function importPastedSubtitles() {
      if (!currentProject) return;
      const text = $('pastedSubtitles').value.trim();
      if (!text) {
        message('Paste subtitle text first', 'err');
        return;
      }
      message('Importing pasted subtitles...');
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/subtitles/paste`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text,
          format: $('pastedSubtitleFormat').value
        })
      });
      renderProject();
      if ($('useLlm').checked) {
        await llmProcess();
        return;
      }
      message('Pasted subtitles imported and mapped', 'ok');
    }

    async function autoNarration() {
      if (!currentProject) return;
      message('Generating draft narration...');
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/narration/auto`, { method: 'POST' });
      renderProject();
      message('Draft narration generated', 'ok');
    }

    async function llmProcess() {
      if (!currentProject) return;
      message('Processing with LLM provider...');
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/narration/llm`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ mode: $('llmMode').value, provider: $('llmProvider').value })
      });
      renderProject();
      message('LLM result applied', 'ok');
    }

    async function saveSlide() {
      if (!currentProject || !(currentProject.slides || []).length) return;
      const slide = currentProject.slides[currentSlide];
      currentProject = await api(`/api/v3/projects/${currentProject.project_id}/slides/${slide.slide_number}/narration`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text: $('narrationText').value,
          subtitle: $('subtitleText').value,
          duration_seconds: Number($('durationInput').value || 6.5)
        })
      });
      renderProject();
      message('Slide saved', 'ok');
    }

    async function generateVoice() {
      if (!currentProject) return;
      await saveSlide();
      message('Generating voice package...');
      const result = await api(`/api/v3/projects/${currentProject.project_id}/voiceover`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tts_engine: $('ttsEngine').value })
      });
      currentProject = result.project;
      $('exportPath').style.display = 'block';
      $('exportPath').textContent = result.export.zip;
      renderProject();
      message('Voice package generated', 'ok');
    }

    async function exportSrt() {
      if (!currentProject) return;
      const result = await api(`/api/v3/projects/${currentProject.project_id}/subtitles/export`, { method: 'POST' });
      $('exportPath').style.display = 'block';
      $('exportPath').textContent = result.path;
      message('SRT exported', 'ok');
    }

    $('pptFile').onchange = (e) => createProject(e.target.files[0]);
    $('subtitleFile').onchange = (e) => importSubtitles(e.target.files[0]);
    $('pasteSubtitleBtn').onclick = () => importPastedSubtitles().catch(err => message(err.message, 'err'));
    $('extractBtn').onclick = () => extract().catch(err => message(err.message, 'err'));
    $('autoBtn').onclick = () => autoNarration().catch(err => message(err.message, 'err'));
    $('llmBtn').onclick = () => llmProcess().catch(err => message(err.message, 'err'));
    $('saveSlideBtn').onclick = () => saveSlide().catch(err => message(err.message, 'err'));
    $('voiceBtn').onclick = () => generateVoice().catch(err => message(err.message, 'err'));
    $('srtBtn').onclick = () => exportSrt().catch(err => message(err.message, 'err'));
    $('refreshBtn').onclick = refreshProjects;
    const drop = $('drop');
    drop.ondragover = (e) => { e.preventDefault(); drop.style.borderColor = 'var(--accent)'; };
    drop.ondragleave = () => { drop.style.borderColor = '#9aa4b2'; };
    drop.ondrop = (e) => { e.preventDefault(); drop.style.borderColor = '#9aa4b2'; createProject(e.dataTransfer.files[0]).catch(err => message(err.message, 'err')); };
    refreshProjects().catch(err => message(err.message, 'err'));
  </script>
</body>
</html>
"""


def safe_v3_source(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    suffix = Path(name).suffix.lower()
    if suffix not in V3_SOURCE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"V3 currently supports PPTX sources only: {suffix}")
    return name


def safe_v3_subtitle(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    suffix = Path(name).suffix.lower()
    if suffix not in V3_SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported subtitle type: {suffix}")
    return name


def get_v3_project_or_404(project_id: str) -> dict:
    try:
        return read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="V3 project not found") from exc


def apply_v3_subtitle_import(project: dict, record: dict) -> dict:
    project.setdefault("imports", []).append(record)
    project["slides"] = v3_subtitles.map_items_to_slides(record["items"], project.get("slides", []))
    project["status"] = "subtitles_imported"
    save_project(project)
    return public_project(project)


@app.get("/api/v3/projects")
def api_v3_projects() -> dict:
    return {"projects": list_v3_projects()}


@app.post("/api/v3/projects")
async def api_v3_create_project(
    file: Annotated[UploadFile, File()],
    language: Annotated[str, Form()] = "zh-CN",
    voice: Annotated[str, Form()] = "zh-CN-XiaoxiaoNeural",
    tone: Annotated[str, Form()] = "professional",
    llm_provider: Annotated[str, Form()] = "mock",
) -> dict:
    name = safe_v3_source(file.filename or "")
    tmp_dir = STAGING / "v3_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex[:12]}-{name}"
    with tmp.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
    project = create_v3_project(
        tmp,
        {
            "language": language,
            "voice": voice,
            "tone": tone,
            "llm_provider": llm_provider,
        },
    )
    tmp.unlink(missing_ok=True)
    return public_project(project)


@app.get("/api/v3/projects/{project_id}")
def api_v3_get_project(project_id: str) -> dict:
    return public_project(get_v3_project_or_404(project_id))


@app.post("/api/v3/projects/{project_id}/extract")
def api_v3_extract(project_id: str) -> dict:
    project = get_v3_project_or_404(project_id)
    try:
        project["slides"] = v3_ppt.extract_pptx(Path(project["source_file"]), v3_project_dir(project_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    project["status"] = "extracted"
    save_project(project)
    return public_project(project)


@app.get("/api/v3/projects/{project_id}/slides/{slide_number}/thumbnail")
def api_v3_thumbnail(project_id: str, slide_number: int) -> FileResponse:
    project = get_v3_project_or_404(project_id)
    for slide in project.get("slides", []):
        if int(slide.get("slide_number", 0)) == slide_number:
            path = Path(slide.get("thumbnail_path") or "")
            if path.exists():
                return FileResponse(path)
    raise HTTPException(status_code=404, detail="Slide thumbnail not found")


@app.post("/api/v3/projects/{project_id}/subtitles/import")
async def api_v3_import_subtitles(project_id: str, file: Annotated[UploadFile, File()]) -> dict:
    project = get_v3_project_or_404(project_id)
    if not project.get("slides"):
        raise HTTPException(status_code=400, detail="Extract PPT slides before importing subtitles")
    name = safe_v3_subtitle(file.filename or "")
    import_dir = v3_project_dir(project_id) / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / name
    index = 1
    while target.exists():
        target = import_dir / f"{Path(name).stem}-{index}{Path(name).suffix}"
        index += 1
    with target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
    try:
        parsed = v3_subtitles.parse_subtitle_file(target)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = {
        "import_id": uuid.uuid4().hex[:12],
        "filename": target.name,
        "path": str(target),
        "format": parsed["format"],
        "mode": "timestamped" if parsed["format"] in {"srt", "vtt"} else "script",
        "items": parsed["items"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return apply_v3_subtitle_import(project, record)


@app.post("/api/v3/projects/{project_id}/subtitles/paste")
def api_v3_paste_subtitles(project_id: str, payload: Annotated[dict, Body()]) -> dict:
    project = get_v3_project_or_404(project_id)
    if not project.get("slides"):
        raise HTTPException(status_code=400, detail="Extract PPT slides before importing subtitles")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Paste subtitle text first")
    suffix = str(payload.get("format") or ".txt").strip().lower()
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    if suffix not in V3_SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported subtitle format: {suffix}")
    try:
        parsed = v3_subtitles.parse_subtitle_text(text, suffix)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import_dir = v3_project_dir(project_id) / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / f"pasted-subtitles-{uuid.uuid4().hex[:8]}{suffix}"
    target.write_text(text, encoding="utf-8")
    record = {
        "import_id": uuid.uuid4().hex[:12],
        "filename": target.name,
        "path": str(target),
        "format": parsed["format"],
        "mode": "timestamped" if parsed["format"] in {"srt", "vtt"} else "script",
        "items": parsed["items"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return apply_v3_subtitle_import(project, record)


@app.post("/api/v3/projects/{project_id}/narration/auto")
def api_v3_auto_narration(project_id: str) -> dict:
    project = get_v3_project_or_404(project_id)
    if not project.get("slides"):
        raise HTTPException(status_code=400, detail="Extract PPT slides first")
    for slide in project["slides"]:
        extracted = slide.get("extracted") or {}
        raw = extracted.get("raw_text") or extracted.get("title") or f"Slide {slide['slide_number']}"
        text = "这一页说明：" + "；".join([part for part in raw.splitlines() if part][:3]) + "。"
        slide["narration"] = {
            "source": "auto",
            "text": text,
            "subtitle": text,
            "duration_seconds": round(max(4.0, min(30.0, len(text) / 7)), 2),
            "status": "draft",
        }
    project["status"] = "auto_narration"
    save_project(project)
    return public_project(project)


@app.post("/api/v3/projects/{project_id}/narration/llm")
def api_v3_llm(project_id: str, options: Annotated[Optional[dict], Body()] = None) -> dict:
    options = options or {}
    project = get_v3_project_or_404(project_id)
    if not project.get("slides"):
        raise HTTPException(status_code=400, detail="Extract PPT slides first")
    provider = options.get("provider") or project.get("settings", {}).get("llm_provider", "mock")
    mode = options.get("mode", "polish")
    try:
        result, run = v3_llm.process(project, mode=mode, provider=provider)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    by_slide = {int(item["slide_number"]): item for item in result["slides"]}
    for slide in project["slides"]:
        item = by_slide.get(int(slide["slide_number"]))
        if not item:
            continue
        slide["narration"] = {
            "source": "llm",
            "text": item["narration"],
            "subtitle": item["subtitle"],
            "duration_seconds": item["duration_seconds"],
            "status": "needs_review",
            "confidence": item.get("confidence", "medium"),
        }
        slide["warnings"] = list(slide.get("warnings") or []) + list(item.get("warnings") or [])
    run_path = v3_project_dir(project_id) / "llm" / f"{run['run_id']}.json"
    write_v3_json(run_path, result)
    run["result_path"] = str(run_path)
    project.setdefault("llm_runs", []).append(run)
    project["settings"]["llm_provider"] = provider
    project["status"] = "llm_processed"
    save_project(project)
    return public_project(project)


@app.patch("/api/v3/projects/{project_id}/slides/{slide_number}/narration")
def api_v3_update_slide(project_id: str, slide_number: int, payload: Annotated[dict, Body()]) -> dict:
    project = get_v3_project_or_404(project_id)
    for slide in project.get("slides", []):
        if int(slide.get("slide_number", 0)) != slide_number:
            continue
        text = str(payload.get("text") or "").strip()
        subtitle = str(payload.get("subtitle") or text).strip()
        duration = float(payload.get("duration_seconds") or 6.5)
        slide["narration"] = {
            **(slide.get("narration") or {}),
            "source": "manual",
            "text": text,
            "subtitle": subtitle,
            "duration_seconds": round(max(2.0, min(120.0, duration)), 2),
            "status": "reviewed",
        }
        save_project(project)
        return public_project(project)
    raise HTTPException(status_code=404, detail="Slide not found")


@app.post("/api/v3/projects/{project_id}/subtitles/export")
def api_v3_export_subtitles(project_id: str) -> dict:
    project = get_v3_project_or_404(project_id)
    path = v3_subtitles.write_srt(project.get("slides", []), v3_project_dir(project_id) / "exports" / "subtitles.srt")
    export = {"type": "srt", "path": str(path), "created_at": datetime.now().isoformat(timespec="seconds")}
    project.setdefault("exports", []).append(export)
    save_project(project)
    return export


@app.get("/api/v3/projects/{project_id}/exports/subtitles.srt")
def api_v3_download_subtitles(project_id: str) -> FileResponse:
    path = v3_project_dir(project_id) / "exports" / "subtitles.srt"
    if not path.exists():
        project = get_v3_project_or_404(project_id)
        v3_subtitles.write_srt(project.get("slides", []), path)
    return FileResponse(path, media_type="application/x-subrip", filename="subtitles.srt")


@app.post("/api/v3/projects/{project_id}/voiceover")
def api_v3_voiceover(project_id: str, options: Annotated[Optional[dict], Body()] = None) -> dict:
    options = options or {}
    project = get_v3_project_or_404(project_id)
    if not project.get("slides"):
        raise HTTPException(status_code=400, detail="Extract PPT slides first")
    try:
        export = v3_tts.generate_voice_package(project, v3_project_dir(project_id), options)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    project.setdefault("exports", []).append({"type": "voiceover", **export, "created_at": datetime.now().isoformat(timespec="seconds")})
    project["status"] = "voiceover_generated"
    save_project(project)
    return {"project": public_project(project), "export": export}


@app.get("/api/v3/projects/{project_id}/exports/voiceover.zip")
def api_v3_download_voiceover(project_id: str) -> FileResponse:
    project = get_v3_project_or_404(project_id)
    exports = [item for item in project.get("exports", []) if item.get("type") == "voiceover" and item.get("zip")]
    if not exports:
        raise HTTPException(status_code=404, detail="Voiceover package not generated")
    path = Path(exports[-1]["zip"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Voiceover package not found")
    return FileResponse(path, media_type="application/zip", filename=path.name)


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
