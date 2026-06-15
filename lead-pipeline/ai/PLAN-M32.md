# M32 — Cloud Deployment: Fly.io + Anthropic SDK Migration + Pipeline Trigger UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy ALLEX to Fly.io with a canonical cloud SQLite DB, replace the Windows-only Claude CLI subprocess with the Anthropic Python SDK, and add dashboard buttons to trigger classify/enrich/backfill from the browser.

**Architecture:** A persistent Fly.io volume at `/data` holds `pipeline.db` — the single source of truth. The Python app runs `python pipeline.py dashboard --serve --port 8080` in the container. Pipeline jobs (classify, enrich, backfill) are triggered from a new "Pipeline" panel in the dashboard, run as background threads on the server, and polled for status from the browser. The Anthropic SDK replaces `claude -p` subprocess calls, removing the Node.js dependency from the container.

**Tech Stack:** Python 3.11, `anthropic` SDK (already in requirements.txt), `http.server.BaseHTTPRequestHandler` (existing), SQLite on Fly volume, Docker, Fly.io (`flyctl`).

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `src/utils/claude_client.py` | Shared `call_claude_text(prompt, model) -> str` via Anthropic SDK |
| Modify | `src/config/settings.py` | Add `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` settings |
| Modify | `src/pipeline/classify.py` | Replace `_call_claude_cli()` internals with `call_claude_text()` |
| Modify | `src/pipeline/backfill.py` | Replace `_call_claude_cli()` internals with `call_claude_text()` |
| Modify | `src/pipeline/enrich.py` | Replace `_enrich_gf_via_claude()` internals with `call_claude_text()` |
| Modify | `src/pipeline/dashboard.py` | Add `POST /api/run-job`, `GET /api/job-status/{id}`, Pipeline UI panel |
| Create | `Dockerfile` | Python 3.11-slim, pip install, serve entrypoint |
| Create | `.dockerignore` | Exclude pipeline.db, .env, __pycache__, data/ |
| Create | `.github/workflows/deploy.yml` | Auto-deploy to Fly.io on push to main |
| Create | `fly.toml` | App config, volume mount at /data, port 8080 |
| Create | `scripts/push-db.sh` | Upload local pipeline.db to Fly volume |
| Create | `scripts/pull-db.sh` | Download Fly volume pipeline.db to local |
| Create | `tests/utils/test_claude_client.py` | Unit tests for claude_client (mocked) |
| Create | `tests/pipeline/test_job_runner.py` | Unit tests for job runner endpoints |

---

## Task 1: Anthropic SDK client utility

**Files:**
- Create: `src/utils/claude_client.py`
- Create: `tests/utils/test_claude_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/utils/test_claude_client.py
import pytest
from unittest.mock import MagicMock, patch


def test_call_claude_text_returns_stripped_response():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="  hello world  ")]
    with patch("src.utils.claude_client.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from src.utils.claude_client import call_claude_text
        result = call_claude_text("test prompt", model="claude-haiku-4-5-20251001")
    assert result == "hello world"


def test_call_claude_text_retries_on_api_error():
    from anthropic import APIError
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    with patch("src.utils.claude_client.anthropic.Anthropic") as MockClient:
        client = MockClient.return_value
        client.messages.create.side_effect = [
            APIError("rate limit", request=MagicMock(), body=None),
            mock_response,
        ]
        with patch("src.utils.claude_client.time.sleep"):
            from importlib import reload
            import src.utils.claude_client as mod
            reload(mod)
            result = mod.call_claude_text("prompt")
    assert result == "ok"


def test_call_claude_text_raises_after_max_retries():
    from anthropic import APIError
    with patch("src.utils.claude_client.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = APIError(
            "fail", request=MagicMock(), body=None
        )
        with patch("src.utils.claude_client.time.sleep"):
            from importlib import reload
            import src.utils.claude_client as mod
            reload(mod)
            with pytest.raises(RuntimeError, match="Claude API failed"):
                mod.call_claude_text("prompt")
```

- [ ] **Step 2: Run tests — expect FAIL (module does not exist)**

```bash
cd "C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\lead-pipeline"
pytest tests/utils/test_claude_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.utils.claude_client'`

- [ ] **Step 3: Create `src/utils/claude_client.py`**

```python
"""Shared Anthropic SDK client — replaces claude CLI subprocess."""
from __future__ import annotations

import logging
import time

import anthropic

from src.config import settings

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_S = 2.0
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def call_claude_text(prompt: str, model: str | None = None) -> str:
    """Send prompt to Claude API, return raw text response (stripped).

    Retries up to _MAX_RETRIES times on transient API errors.
    Raises RuntimeError after all retries exhausted.
    """
    if model is None:
        model = settings.CLAUDE_MODEL
    client = _get_client()

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except anthropic.APIError as exc:
            log.warning("Claude API error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
        except Exception as exc:
            log.warning("Claude call failed (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)

    raise RuntimeError(f"Claude API failed after {_MAX_RETRIES} attempts")
```

- [ ] **Step 4: Update `src/config/settings.py` — add API key + model**

Find the block of settings constants and add after `CLAUDE_CMD`:

```python
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/utils/test_claude_client.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/utils/claude_client.py src/config/settings.py tests/utils/test_claude_client.py
git commit -m "feat(m32): add Anthropic SDK client utility, replace CLI subprocess"
```

---

## Task 2: Migrate classify.py to SDK

**Files:**
- Modify: `src/pipeline/classify.py:243-285` (the `_call_claude_cli` function)

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_classify_sdk.py
from unittest.mock import patch


def test_classify_uses_sdk_not_subprocess():
    """_call_claude_cli must not call subprocess.run — it should use call_claude_text."""
    import subprocess
    from src.pipeline import classify
    with patch("src.utils.claude_client.call_claude_text", return_value='{"klass":"D","services_score":0,"service_flag":false,"distributor_flag":false,"ssb_flag":false,"leistung_category":"medizinprodukt-handler","mehrwerte":"test","reason_code":"Unpassende_Branche","reasoning":"test"}') as mock_sdk:
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run called")):
            result = classify._call_claude_cli("test prompt")
    mock_sdk.assert_called_once()
    assert result["klass"] == "D"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/pipeline/test_classify_sdk.py -v
```
Expected: `AssertionError: subprocess.run called`

- [ ] **Step 3: Replace `_call_claude_cli` body in `classify.py`**

Replace the entire `_call_claude_cli` function (lines 243–285) with:

```python
def _call_claude_cli(prompt: str) -> dict:
    """Call Claude API and return parsed classification JSON."""
    from src.utils.claude_client import call_claude_text

    for attempt in range(_MAX_RETRIES):
        try:
            raw = call_claude_text(prompt, model=settings.CLAUDE_MODEL)
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
        except RuntimeError as exc:
            logger.warning("Claude error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
    raise RuntimeError(f"classify: Claude failed after {_MAX_RETRIES} attempts")
```

Also remove `import subprocess` and `import os` from classify.py if they are no longer used (check with grep first).

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/pipeline/test_classify_sdk.py tests/pipeline/test_classify.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/classify.py tests/pipeline/test_classify_sdk.py
git commit -m "feat(m32): classify — SDK replaces CLI subprocess"
```

---

## Task 3: Migrate backfill.py to SDK

**Files:**
- Modify: `src/pipeline/backfill.py:179-210` (the `_call_claude_cli` function)

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_backfill_sdk.py
import subprocess
from unittest.mock import patch


def test_backfill_uses_sdk_not_subprocess():
    from src.pipeline import backfill
    with patch("src.utils.claude_client.call_claude_text", return_value="some text") as mock_sdk:
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run called")):
            result, err = backfill._call_claude_cli("test prompt")
    mock_sdk.assert_called_once()
    assert err is None
    assert result == "some text"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/pipeline/test_backfill_sdk.py -v
```
Expected: `AssertionError: subprocess.run called`

- [ ] **Step 3: Replace `_call_claude_cli` body in `backfill.py`**

Replace the entire `_call_claude_cli` function (lines 179–210) with:

```python
def _call_claude_cli(prompt: str) -> tuple[Optional[str], Optional[str]]:
    """Call Claude API. Returns (text, error_type). error_type is None on success."""
    from src.utils.claude_client import call_claude_text
    try:
        text = call_claude_text(prompt, model=settings.CLAUDE_MODEL)
        return text, None
    except RuntimeError as exc:
        logger.warning("Claude API failed: %s", exc)
        return None, "api_error"
    except Exception as exc:
        logger.warning("Claude call exception: %s", exc)
        return None, "exception"
```

Also remove `import subprocess` and `import os` from backfill.py if no longer used.

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/pipeline/test_backfill_sdk.py tests/pipeline/test_backfill.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/backfill.py tests/pipeline/test_backfill_sdk.py
git commit -m "feat(m32): backfill — SDK replaces CLI subprocess"
```

---

## Task 4: Migrate enrich.py GF extraction to SDK

**Files:**
- Modify: `src/pipeline/enrich.py` — `_enrich_gf_via_claude` function (~line 2206)

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_enrich_sdk.py
import subprocess
from unittest.mock import patch


def test_enrich_gf_uses_sdk_not_subprocess():
    from src.pipeline import enrich
    with patch("src.utils.claude_client.call_claude_text", return_value="Dr. Hans Müller") as mock_sdk:
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run called")):
            result = enrich._enrich_gf_via_claude("Geschäftsführer: Dr. Hans Müller")
    mock_sdk.assert_called_once()
    assert result == "Dr. Hans Müller"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/pipeline/test_enrich_sdk.py -v
```
Expected: `AssertionError: subprocess.run called`

- [ ] **Step 3: Replace `_enrich_gf_via_claude` in `enrich.py`**

Find `_enrich_gf_via_claude` (~line 2206) and replace its body:

```python
def _enrich_gf_via_claude(impressum_text: str) -> Optional[str]:
    """Extract Geschäftsführer name from impressum text via Claude API."""
    from src.utils.claude_client import call_claude_text
    prompt = (
        "Extract the Geschäftsführer (managing director) full name from this German impressum text. "
        "Return ONLY the name, nothing else. If not found, return 'NOT_FOUND'.\n\n"
        f"{impressum_text[:1000]}"
    )
    try:
        result = call_claude_text(prompt, model=settings.CLAUDE_MODEL)
        if result == "NOT_FOUND" or not result:
            return None
        return result
    except RuntimeError:
        return None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/pipeline/test_enrich_sdk.py tests/pipeline/test_enrich.py -v
```
Expected: all pass.

- [ ] **Step 5: Full suite — verify nothing broken**

```bash
pytest tests/ -v --tb=short
```
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/enrich.py tests/pipeline/test_enrich_sdk.py
git commit -m "feat(m32): enrich GF extraction — SDK replaces CLI subprocess"
```

---

## Task 5: Job runner backend in dashboard.py

**Files:**
- Modify: `src/pipeline/dashboard.py` — add job state dict, `_run_job` handler, `_get_job_status` handler
- Create: `tests/pipeline/test_job_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipeline/test_job_runner.py
import json
import threading
import time
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch


class MockRequest:
    def __init__(self, method: str, path: str, body: bytes = b""):
        self._method = method
        self._path = path
        self._body = body
        self.makefile_calls = []

    def makefile(self, mode, bufsize=-1):
        if "rb" in mode:
            return BytesIO(self._body)
        return BytesIO()


def _make_handler(method: str, path: str, body: bytes = b""):
    from src.pipeline.dashboard import _DashboardHandler, _jobs
    _jobs.clear()
    request = MockRequest(method, path, body)
    server = MagicMock()
    handler = _DashboardHandler.__new__(_DashboardHandler)
    handler.request = request
    handler.client_address = ("127.0.0.1", 9999)
    handler.server = server
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.command = method
    handler.path = path
    return handler, handler.wfile


def test_run_job_returns_job_id_for_valid_job():
    from src.pipeline.dashboard import _jobs
    body = json.dumps({"job": "classify", "limit": 5}).encode()
    handler, wfile = _make_handler("POST", "/api/run-job", body)

    sent_responses = []
    def mock_send_response(code):
        sent_responses.append(code)
    def mock_send_header(k, v): pass
    def mock_end_headers(): pass

    handler.send_response = mock_send_response
    handler.send_header = mock_send_header
    handler.end_headers = mock_end_headers

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        handler._run_job()

    assert 200 in sent_responses
    wfile.seek(0)
    response = json.loads(wfile.read())
    assert "job_id" in response
    job_id = response["job_id"]
    assert job_id in _jobs


def test_run_job_rejects_unknown_job():
    body = json.dumps({"job": "rm -rf /"}).encode()
    handler, wfile = _make_handler("POST", "/api/run-job", body)
    error_calls = []
    handler.send_error = lambda code, msg=None: error_calls.append(code)
    handler._run_job()
    assert 400 in error_calls


def test_get_job_status_returns_status():
    from src.pipeline.dashboard import _jobs
    fake_id = "test-job-123"
    _jobs[fake_id] = {"status": "done", "lines": ["line1", "line2"], "returncode": 0}
    handler, wfile = _make_handler("GET", f"/api/job-status/{fake_id}")

    sent_responses = []
    handler.send_response = lambda code: sent_responses.append(code)
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None
    handler._get_job_status(fake_id)

    assert 200 in sent_responses
    wfile.seek(0)
    result = json.loads(wfile.read())
    assert result["status"] == "done"
    assert result["lines"] == ["line1", "line2"]
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/pipeline/test_job_runner.py -v
```
Expected: `AttributeError` — `_jobs`, `_run_job`, `_get_job_status` don't exist yet.

- [ ] **Step 3: Add job runner to `dashboard.py`**

At the top of `dashboard.py`, after existing imports, add:

```python
import subprocess
import threading
import uuid
```

After the `_WRITEBACK_FIELDS` constant, add:

```python
# Job runner state — keyed by job_id
_jobs: dict[str, dict] = {}
_ALLOWED_JOBS = {"classify", "enrich", "backfill", "normalize"}
```

In `_DashboardHandler.do_POST`, add routing before existing handlers:

```python
if self.path == "/api/run-job":
    self._run_job()
    return
```

In `_DashboardHandler.do_GET`, add routing before existing handlers:

```python
if self.path.startswith("/api/job-status/"):
    job_id = self.path[len("/api/job-status/"):]
    self._get_job_status(job_id)
    return
```

Add these two methods to `_DashboardHandler`:

```python
def _run_job(self) -> None:
    length = int(self.headers.get("Content-Length", 0))
    payload = json.loads(self.rfile.read(length))
    job = payload.get("job", "")
    limit = payload.get("limit")

    if job not in _ALLOWED_JOBS:
        self.send_error(400, f"Unknown job '{job}'. Allowed: {sorted(_ALLOWED_JOBS)}")
        return

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "lines": [], "returncode": None}

    def _worker():
        cmd = ["python", "pipeline.py", job]
        if limit:
            cmd += ["--limit", str(int(limit))]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            for line in proc.stdout:
                _jobs[job_id]["lines"].append(line.rstrip())
            proc.wait()
            _jobs[job_id]["returncode"] = proc.returncode
            _jobs[job_id]["status"] = "done" if proc.returncode == 0 else "error"
        except Exception as exc:
            _jobs[job_id]["lines"].append(f"ERROR: {exc}")
            _jobs[job_id]["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps({"job_id": job_id}).encode())

def _get_job_status(self, job_id: str) -> None:
    job = _jobs.get(job_id)
    if not job:
        self.send_error(404, f"Job {job_id} not found")
        return
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps({
        "status": job["status"],
        "lines": job["lines"][-100:],
        "returncode": job["returncode"],
    }).encode())
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/pipeline/test_job_runner.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/dashboard.py tests/pipeline/test_job_runner.py
git commit -m "feat(m32): job runner backend — POST /api/run-job + GET /api/job-status"
```

---

## Task 6: Pipeline trigger UI in dashboard

**Files:**
- Modify: `src/pipeline/dashboard.py` — `_render_html()` function, add Pipeline panel HTML + JS

- [ ] **Step 1: Find the HTML template section**

The dashboard HTML is built inside `_render_html()` or equivalent. Locate the sidebar nav items (look for `nav` or tab-switching JS). The v2 dashboard has a sidebar with nav items.

Run:
```bash
grep -n "sidebar\|nav-item\|data-tab\|pipeline\|Pipeline" src/pipeline/dashboard.py | head -20
```

Note the pattern used for existing nav items — match it exactly.

- [ ] **Step 2: Add "Pipeline" nav item to sidebar**

In the sidebar nav HTML string, add a Pipeline entry after the last existing nav item. Follow the exact same HTML pattern as existing items. Example (adapt to actual pattern):

```html
<li class="nav-item" data-tab="pipeline">
  <span class="nav-icon">⚙</span>
  <span class="nav-label">Pipeline</span>
</li>
```

- [ ] **Step 3: Add Pipeline panel HTML**

Add a new panel div (hidden by default, shown when Pipeline nav item is active). Insert after the last existing panel:

```html
<div id="tab-pipeline" class="tab-panel" style="display:none; padding:24px;">
  <h2 style="margin-top:0;">Pipeline</h2>
  <p style="color:#888; font-size:13px;">Trigger pipeline stages on the server. Results write to the shared DB.</p>

  <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px;">
    <div>
      <label style="font-size:12px; color:#888;">Limit (optional)</label><br>
      <input id="job-limit" type="number" placeholder="all" min="1"
             style="width:100px; padding:6px 8px; border:1px solid #333; background:#1a1a1a; color:#fff; border-radius:4px;">
    </div>
    <button class="pipeline-btn" data-job="classify"
            style="align-self:flex-end; padding:8px 20px; background:#0d9488; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:14px;">
      Classify
    </button>
    <button class="pipeline-btn" data-job="enrich"
            style="align-self:flex-end; padding:8px 20px; background:#6366f1; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:14px;">
      Enrich
    </button>
    <button class="pipeline-btn" data-job="backfill"
            style="align-self:flex-end; padding:8px 20px; background:#f59e0b; color:#111; border:none; border-radius:4px; cursor:pointer; font-size:14px;">
      Backfill
    </button>
  </div>

  <div id="job-status-bar" style="display:none; margin-bottom:8px; font-size:13px; color:#94a3b8;">
    <span id="job-status-label">Running...</span>
  </div>
  <pre id="job-log"
       style="background:#0f172a; color:#94a3b8; padding:16px; border-radius:6px; font-size:12px;
              height:320px; overflow-y:auto; white-space:pre-wrap; word-break:break-word;">
Ready.
  </pre>
</div>
```

- [ ] **Step 4: Add Pipeline JS**

In the dashboard JS block (where other tab/panel logic lives), add:

```javascript
// Pipeline trigger
(function() {
  var logEl = document.getElementById('job-log');
  var statusBar = document.getElementById('job-status-bar');
  var statusLabel = document.getElementById('job-status-label');
  var pollInterval = null;
  var currentJobId = null;

  function appendLog(text) {
    logEl.textContent += text + '\n';
    logEl.scrollTop = logEl.scrollHeight;
  }

  function pollStatus(jobId) {
    fetch('/api/job-status/' + jobId)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        logEl.textContent = data.lines.join('\n');
        logEl.scrollTop = logEl.scrollHeight;
        statusLabel.textContent = data.status === 'running'
          ? 'Running...'
          : (data.status === 'done' ? 'Done ✓' : 'Error ✗');
        if (data.status !== 'running') {
          clearInterval(pollInterval);
          pollInterval = null;
          document.querySelectorAll('.pipeline-btn').forEach(function(b) {
            b.disabled = false;
          });
        }
      });
  }

  document.querySelectorAll('.pipeline-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var job = btn.getAttribute('data-job');
      var limit = document.getElementById('job-limit').value;
      var body = { job: job };
      if (limit) body.limit = parseInt(limit);

      logEl.textContent = 'Starting ' + job + '...\n';
      statusBar.style.display = 'block';
      statusLabel.textContent = 'Running...';
      document.querySelectorAll('.pipeline-btn').forEach(function(b) {
        b.disabled = true;
      });

      fetch('/api/run-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        currentJobId = data.job_id;
        pollInterval = setInterval(function() { pollStatus(currentJobId); }, 2000);
      });
    });
  });
})();
```

- [ ] **Step 5: Manual smoke test — verify UI renders**

```bash
cd "C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\lead-pipeline"
python pipeline.py dashboard --serve --port 8081
```
Open `http://localhost:8081`, click Pipeline nav item. Verify panel appears with 3 buttons and log area.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard.py
git commit -m "feat(m32): pipeline trigger UI — classify/enrich/backfill buttons + log panel"
```

---

## Task 7: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

No tests for infra files — verified at deploy time.

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY profiles/ profiles/
COPY pipeline.py .

# DB and data directories — pipeline.db lives on /data volume at runtime
RUN mkdir -p /data data/input data/staging data/output

# Set DB path to persistent volume
ENV PIPELINE_DB_PATH=/data/pipeline.db

EXPOSE 8080

CMD ["python", "pipeline.py", "dashboard", "--serve", "--port", "8080"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.env
*.db
pipeline.db
data/
__pycache__
**/__pycache__
*.pyc
.git
tests/
ai/
docs/
scripts/
*.md
*.xlsx
*.docx
*.pdf
*.csv
*.png
*.jpg
```

- [ ] **Step 3: Build image locally to verify**

```bash
cd "C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\lead-pipeline"
docker build -t allex-pipeline .
```
Expected: build completes, no errors.

- [ ] **Step 4: Test container runs**

```bash
docker run --rm -e ANTHROPIC_API_KEY=test -e PIPELINE_DB_PATH=/data/pipeline.db \
  -v "$(pwd)/pipeline.db:/data/pipeline.db" \
  -p 8082:8080 allex-pipeline
```
Open `http://localhost:8082` — dashboard should load (it'll error on missing data tables but server must start).

- [ ] **Step 5: Create `.github/workflows/deploy.yml`**

```yaml
name: Deploy to Fly.io

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

This deploys **code only** on every push to main. The database on the Fly volume is never touched by deploys — it persists independently.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore .github/workflows/deploy.yml
git commit -m "feat(m32): Dockerfile + GitHub Actions deploy workflow"
git push
```

---

## Task 8: Fly.io setup + DB upload + sync scripts

> **Important:** Code and DB are completely separate in this deployment.
> - Code: lives in GitHub → auto-deploys to Fly on every push to `main`
> - DB: lives on a Fly persistent volume at `/data/pipeline.db` — never in git, never touched by code deploys

**Files:**
- Create: `fly.toml`
- Create: `scripts/push-db.sh`
- Create: `scripts/pull-db.sh`

Prerequisites: `flyctl` installed (`winget install flyctl` or `scoop install flyctl`). Run `fly auth login` once.

- [ ] **Step 1: Create `fly.toml`**

```toml
app = "repuro-allex"
primary_region = "fra"  # Frankfurt — closest to Berlin

[build]
  dockerfile = "Dockerfile"

[env]
  PIPELINE_DB_PATH = "/data/pipeline.db"

[[mounts]]
  source = "pipeline_data"
  destination = "/data"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
```

- [ ] **Step 2: Create Fly app and persistent volume (one-time, manual)**

```bash
flyctl apps create repuro-allex --org personal
flyctl volumes create pipeline_data --app repuro-allex --region fra --size 1
```
Expected: app created, 1GB volume created in Frankfurt. This volume persists forever — code deploys never delete it.

- [ ] **Step 3: Set API secrets in Fly (one-time, manual)**

```bash
flyctl secrets set ANTHROPIC_API_KEY="<value from .env>" --app repuro-allex
flyctl secrets set OPENREGISTER_API_KEY="<value from .env>" --app repuro-allex
```
These are injected as env vars at runtime, never in git.

- [ ] **Step 4: Add FLY_API_TOKEN to GitHub (one-time, manual)**

```bash
# Get your Fly deploy token
flyctl tokens create deploy -x 999999h --app repuro-allex
```
Copy the output. Go to github.com/pavlovs/allex → Settings → Secrets → Actions → New secret:
- Name: `FLY_API_TOKEN`
- Value: the token from above

After this, every `git push` to `main` triggers an auto-deploy.

- [ ] **Step 5: ONE-TIME DB UPLOAD — upload current pipeline.db to Fly volume**

The DB is not in git and is not deployed with code. It must be uploaded manually once to seed the volume.

```bash
# First deploy the app so the volume is mounted
flyctl deploy --app repuro-allex

# Then upload your local pipeline.db to the volume
flyctl sftp put pipeline.db /data/pipeline.db --app repuro-allex
```
Expected: DB is now on the Fly volume at `/data/pipeline.db`. All subsequent code deploys leave it untouched. Flo can now access the dashboard and see live data.

- [ ] **Step 6: Create `scripts/push-db.sh`**

For ongoing syncs after Roman runs pipeline commands locally:

```bash
#!/usr/bin/env bash
# Push local pipeline.db to Fly.io volume (Roman's machine → cloud)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="$SCRIPT_DIR/../pipeline.db"

echo "Pushing $DB_PATH to Fly.io /data/pipeline.db..."
flyctl sftp put "$DB_PATH" /data/pipeline.db --app repuro-allex
echo "Done. Cloud DB updated."
```

- [ ] **Step 7: Create `scripts/pull-db.sh`**

For pulling Flo's edits back to Roman's machine before a pipeline run:

```bash
#!/usr/bin/env bash
# Pull pipeline.db from Fly.io volume to local (cloud → Roman's machine)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="$SCRIPT_DIR/../pipeline.db"

echo "Pulling /data/pipeline.db from Fly.io to $DB_PATH..."
flyctl sftp get /data/pipeline.db "$DB_PATH" --app repuro-allex
echo "Done. Local DB updated."
```

- [ ] **Step 8: Make scripts executable and commit**

```bash
chmod +x scripts/push-db.sh scripts/pull-db.sh
git add fly.toml scripts/push-db.sh scripts/pull-db.sh
git commit -m "feat(m32): fly.toml + DB sync scripts"
git push
```

---

## Task 9: Deploy + smoke test

- [ ] **Step 1: Full deploy**

```bash
cd "C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\lead-pipeline"
flyctl deploy --app repuro-allex
```
Expected: build → push → deploy, machine starts, health check passes.

- [ ] **Step 2: Get app URL**

```bash
flyctl status --app repuro-allex
```
Note the URL: `https://repuro-allex.fly.dev`

- [ ] **Step 3: Smoke test — dashboard loads**

Open `https://repuro-allex.fly.dev` in browser.
Expected: dashboard loads, data visible (same as local DB since we pushed it).

- [ ] **Step 4: Smoke test — Pipeline panel**

Click Pipeline nav item → classify button with `--limit 3`.
Expected: job starts, log panel shows classify output lines, status changes to "Done ✓".

- [ ] **Step 5: Smoke test — PATCH write-back**

Open a record in the dashboard, edit a field, save.
Expected: field saves without error, persists on page reload.

- [ ] **Step 6: Verify Flo can access**

Send URL to Flo. Confirm dashboard loads on his machine.

- [ ] **Step 7: Update ROADMAP.md**

In `ai/ROADMAP.md`:
- Mark M32 ✅ in the Delivered table with summary
- Remove M32 spec block from Next Milestones
- Update Current State block: "Cloud deployment live at repuro-allex.fly.dev. Canonical DB on Fly volume. Pipeline triggerable from dashboard."

- [ ] **Step 8: Final commit**

```bash
git add ai/ROADMAP.md
git commit -m "docs(m32): mark complete, update current state"
git push
```

---

## Self-Review

**Spec coverage:**
- ✅ Cloud canonical DB (Fly volume, /data/pipeline.db)
- ✅ Flo browser access (served via fly.dev URL)
- ✅ Claude CLI → SDK (Tasks 1-4)
- ✅ Dashboard pipeline trigger buttons (Tasks 5-6)
- ✅ Classify, enrich, backfill jobs supported
- ✅ Push/pull sync scripts for Roman's local workflow
- ✅ Dockerfile with no Node.js dependency

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `call_claude_text` returns `str` consistently. `_call_claude_cli` in classify returns `dict` (parses JSON internally). `_call_claude_cli` in backfill returns `tuple[Optional[str], Optional[str]]`. Both delegate to `call_claude_text` for the API call — interfaces unchanged from callers' perspective.

**One known gap:** No auth on the dashboard endpoint. URL is public once deployed. For Repuro-internal use this is acceptable short-term — add HTTP Basic Auth (1 env var + 10 lines in `_DashboardHandler.do_GET/do_POST`) before any external user gets the URL.

---

## Execution Results — 2026-05-03

**Pivot during implementation:** Roman has no Anthropic API key. SDK migration (Tasks 1–4), job runner (Task 5), and Pipeline trigger UI (Task 6) were implemented then fully reverted. Only infrastructure tasks (7–8) and additional fixes were delivered.

### Delivered
- [x] `Dockerfile` — python:3.12-slim, `CMD ["python", "pipeline.py", "dashboard", "--serve", "--port", "8080"]`, `ENV PIPELINE_DB_PATH=/data/pipeline.db`
- [x] `fly.toml` — app=allex-pipeline, fra region, 512MB, persistent volume at `/data`
- [x] `.github/workflows/deploy.yml` — push to `main` → `flyctl deploy --remote-only`
- [x] `scripts/push-db.sh` / `scripts/pull-db.sh` — DB sync (PowerShell-compatible via flyctl sftp)
- [x] `_ThreadedHTTPServer` in `dashboard.py` — concurrent request handling
- [x] Empty-DB cold-start handling in `dashboard.py` — creates empty SQLite + serves empty dashboard on Fly before DB upload
- [x] `src/data/region_mapping.json` (486 cities) — extracted once from Excel, `region_lookup.py` rewritten to read JSON (no runtime Excel dependency in container)
- [x] Dashboard live at `https://allex-pipeline.fly.dev` with 5MB real DB uploaded — confirmed working
- [x] Flo can access and edit records; writes back to Fly volume `/data/pipeline.db`

### Reverted (blocked on Anthropic API key)
- [ ] Tasks 1–4: `src/utils/claude_client.py`, SDK wiring in classify/backfill/enrich
- [ ] Task 5: `POST /api/run-job`, `GET /api/job-status/{id}`, background job threads
- [ ] Task 6: Pipeline trigger UI panel in dashboard

### Additional issues encountered and fixed
- `pipeline.db` 0-byte placeholder on OneDrive root — real DB at `data/pipeline.db` (5MB)
- `flyctl sftp` MSYS2 path translation bug on Windows — resolved via `powershell.exe -Command "flyctl.exe ..."` directly
- Docker build context 3600s+ from OneDrive — resolved by cloning repo to local disk (`C:/Users/X1/allex-deploy`)
- Empty schema crash on cold start — `_load_data()` wrapped in `try/except sqlite3.OperationalError`
