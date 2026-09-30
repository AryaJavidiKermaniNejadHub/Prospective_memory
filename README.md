# Prospective Memory colour-matching experiment (web)

Browser version of the Millisecond "Prospective Memory Task – Color Matching" (after Smith & Bayen, 2006).
Read **COMPLIANCE.md** first: it says what could and could not be verified against the original paper.

**Stack:** Python 3.12, Flask, SQLAlchemy, PostgreSQL (SQLite only as a local-development fallback), gunicorn, vanilla JS (no build step).

## Files
| File | Purpose |
|---|---|
| `app.py` | Routes, session state machine, researcher/admin area, CSV export |
| `models.py` | Database schema |
| `trialgen.py` | Stimulus validation + randomisation (seeded, reproducible) |
| `scoring.py` | Correctness + summary measures (server-side only) |
| `config.py` | Env-var settings and design constants (timings, keys, 62 trials, positions, break) |
| `stimuli.json` | **Word lists. Placeholders. Replace them.** |
| `static/js/instructions.js` | Participant instruction text (not original to S&B; edit freely) |
| `static/js/experiment.js` | Trial engine and timing |
| `templates/index.html` | Start page: **paste your ethics-approved consent text here** |
| `tests/` | `test_logic.py` (runs anywhere), `test_flow.py` (end-to-end; needs dependencies) |

## Where to put the validated stimulus lists
Edit `stimuli.json`. Per list (`A` and `B`): 6 categories, each with one `target` and its `fillers`; exactly 6 targets and ≥ 56 fillers in total;
no colour names; no word repeated anywhere. The app refuses to start if this is violated. While `"is_placeholder": true`, the admin
dashboard shows a warning and each session records the set name and a hash of the file, so you can always tell which lists produced which data.
Set `"is_placeholder": false` and rename `stimulus_set_name` once you have inserted real lists.

## Run locally on Windows
1. Install Python 3.12 from python.org; tick **"Add python.exe to PATH"**.
2. Open PowerShell in the project folder:
   ```
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope Process Bypass
   pip install -r requirements.txt
   copy .env.example .env               # then edit .env: set SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
   python tests\test_logic.py
   python tests\test_flow.py            # end-to-end smoke test on a temp database
   python app.py
   ```
3. Open http://127.0.0.1:5000. Leave `DATABASE_URL` empty locally: a `local_dev.db` SQLite file is used. Keep `BREAK_SECONDS=5` for testing.
4. Test participant: enter any ID, tick consent, Start, and run the whole experiment (Y/N; Z on the studied words).
5. Check data: http://127.0.0.1:5000/admin → log in → session list, session detail, CSV downloads.
6. Multiple participants: open the start page in **two different browsers** (or one normal + one private window), start both, and run them at the same time. Each gets its own secret URL/session; the dashboard should show both, with alternating list orders.
7. (Optional) Test against PostgreSQL locally by setting `DATABASE_URL=postgresql://user:pass@localhost:5432/dbname`.
gunicorn does not run on Windows; `python app.py` is for local use only.

## Deploy to Render
1. Put the project in a **private** GitHub repository (`.env` is git-ignored; never commit secrets).
2. Render dashboard → **New → PostgreSQL**. Choose a plan (check Render's current pricing: free databases have been time-limited, so use a paid plan for real data collection) and the **same region** as the web service. Copy the **Internal Database URL**.
3. **New → Web Service** → select the repo. Runtime: Python 3. Build: `pip install -r requirements.txt`. Start: `gunicorn app:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT --timeout 60`. Health check path: `/healthz`. (`render.yaml` does all of this as a Blueprint.)
4. Environment variables:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Internal Database URL |
   | `SECRET_KEY` | output of `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `ADMIN_USERNAME` / `ADMIN_PASSWORD` | your choice (long password) |
   | `PYTHON_VERSION` | `3.12.8` |
   | `BREAK_SECONDS` | `5` while testing, then `600` (or your design value) |
5. Deploy. Tables are created automatically on first start (advisory-locked so two workers cannot collide).
6. Test the deployed app: run one full session on a computer, open `https://<your-app>.onrender.com/admin`, confirm the session and its 130 trials appear, download the CSVs. Then set `BREAK_SECONDS` to the real value and redeploy.
7. Give participants `https://<your-app>.onrender.com/` (optionally `/?pid=ID` or `/?group=1|2` to force a list order). Free web services sleep when idle; use a paid plan for scheduled sessions.
8. Schema changes later: this project uses `create_all`, which only creates missing tables. If you change columns after collecting data, adopt Flask-Migrate/Alembic first. Back up regularly by downloading the CSVs.

## Getting the data
`/admin` (login) → download **trials.csv** (raw, one row per completed trial, authoritative), **summary.csv**, **sessions.csv**, **recall.csv**, **targets.csv**.
"Recompute all summaries" rebuilds summaries from raw trials. Text cells starting with `= + - @` are prefixed with `'` to prevent spreadsheet formula injection.

## Database
`sessions` (one per participant run; seed, list order, stage, browser info, stimulus-set hash) · `session_targets` (the 6 PM words) ·
`trials` (planned stimuli + responses + scoring + raw `key_events` + measured `timing`; unique on session/phase/trial) ·
`recall_attempts` + `recall_items` · `session_summaries` (derived). The complete randomised plan is generated server-side at session start,
so the browser never receives target status or correct answers (except practice).

**Key columns.** `key_events`: every Y/N/Z keydown, `stage` ∈ squares/probe/iti; `t` is ms since probe onset (for `squares`, ms since trial start).
`rt_yn_ms`/`rt_z_ms`: from probe onset. `rt_task_manual_ms`/`rt_pm_manual_ms`: Millisecond convention (task RT from Z if Z came first; PM RT from Y/N if Y/N came first).
Y/N = first Y/N press while the probe is visible. Z = any Z press while the probe is visible or during the 1000 ms ITI that follows the Y/N press (PM phase only);
Z in the squares stream or in baseline is logged but not scored. `response_sequence`: task only / task-PM / PM-task.
Baseline rows with `target_type=target` are slot labels; only `is_pm_target_word=1` rows are learned PM targets.

## Concurrency, integrity, security
Each participant has an unguessable URL token; no shared state between sessions. Trial uploads are idempotent (first write wins), retried on network failure, order-enforced by stage, and validated server-side.
Admin: env-var credentials, signed session cookie, CSRF on POST, login throttling, `noindex`. Participant data is never publicly listed. Use HTTPS (Render provides it).

## Browser timing limitations (versus Inquisit)
- Display timing is frame-locked via `requestAnimationFrame` (durations are quantised to the monitor refresh, e.g. 16.7 ms at 60 Hz); actual onsets and the estimated frame interval are stored per trial. Onset is the frame's callback time, not a photodiode measurement.
- Key times use `KeyboardEvent.timeStamp`; keyboard/OS/browser polling adds latency and jitter (typically several ms to tens of ms), varying across participants' devices. Compare within-person, not to lab absolutes.
- Participants control their own screen, colours (calibrate nothing), viewing distance, and environment; background tabs, notifications and slow devices can distort timing (tab-hidden events are flagged in `timing.hidden`).
- Colours are fixed hex values, not Inquisit's; luminance differs across monitors.
- Supports physical keyboards and touch-screen Y/N/Z response buttons on phones and tablets.
- Refreshing mid-phase resumes at the next unfinished trial (counted in `resume_count`); decide whether to exclude such sessions.
- Not tested in a real browser by me; run a full pilot (Windows local run, then the deployed Render URL, on the browsers/devices your participants will use) before collecting data.


### Render database driver

This build uses **psycopg 3** explicitly. Render/PostgreSQL URLs are normalized to `postgresql+psycopg://...` at startup, and `psycopg[binary]` is included in `requirements.txt`. This avoids the `ModuleNotFoundError: No module named 'psycopg'` failure that occurs when SQLAlchemy receives a `postgresql+psycopg` URL but only `psycopg2-binary` is installed.
