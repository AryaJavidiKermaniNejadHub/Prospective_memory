"""Prospective Memory colour-matching experiment (Flask + SQLAlchemy + PostgreSQL)."""
import csv, hmac, io, json, os, random, secrets, time
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   session as flask_session, url_for)
from sqlalchemy import func, text

import config
from config import EXPERIMENT as EXP
from models import (ExpSession, RecallAttempt, RecallItem, SessionSummary, SessionTarget, Trial, db, utcnow)
from scoring import PayloadError, clean_events, score_trial, summarize
from trialgen import build_session_plan, load_stimuli

STIMULI = load_stimuli(colors=tuple(EXP["colors"]))   # validated at import; fails loudly if malformed
PHASES = ("practice", "baseline", "pm_task")
NEXT_STAGE = {"practice": "baseline", "baseline": "pm_training"}


def create_app():
    app = Flask(__name__)
    app.config.from_object(config.Config)
    if not app.config["SECRET_KEY"]:
        if os.environ.get("RENDER"):
            raise RuntimeError("SECRET_KEY environment variable must be set in production")
        app.config["SECRET_KEY"] = secrets.token_hex(32)  # dev only; admin login resets on restart
        print("WARNING: SECRET_KEY not set; using a temporary development key.")
    if os.environ.get("RENDER"):
        app.config["SESSION_COOKIE_SECURE"] = True
    db.init_app(app)
    with app.app_context():
        init_db()
    register_routes(app)
    return app


def init_db():
    """Create tables if missing. On PostgreSQL an advisory lock stops multiple gunicorn workers racing."""
    is_pg = db.engine.dialect.name == "postgresql"
    with db.engine.begin() as conn:
        if is_pg:
            conn.execute(text("SELECT pg_advisory_xact_lock(918273645)"))
        db.metadata.create_all(bind=conn)


# ------------------------------------------------------------------ helpers
def public_config():
    return {k: EXP[k] for k in ("colors", "color_hex", "square_ms", "isi_ms", "iti_ms",
                                "practice_feedback_ms", "keys", "break_seconds")}


def get_session_or_404(token):
    s = ExpSession.query.filter_by(token=token).first()
    if s is None:
        abort(404)
    return s


def phase_progress(s, phase):
    q = Trial.query.filter_by(session_id=s.id, phase=phase)
    return q.filter_by(completed=True).count(), q.count()


def break_remaining(s):
    if not s.break_started_at:
        return EXP["break_seconds"]
    started = s.break_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, EXP["break_seconds"] - (utcnow() - started).total_seconds())


def assign_group():
    """Balanced assignment: odd group -> list order AB, even -> BA (as in the Millisecond script)."""
    if db.engine.dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(555001)"))
    n_ab = ExpSession.query.filter_by(list_order="AB").count()
    n_ba = ExpSession.query.filter_by(list_order="BA").count()
    return 1 if n_ab <= n_ba else 2


def create_session(pid, group=None):
    group = group or assign_group()
    seed = random.SystemRandom().randrange(1, 2**62)
    plan = build_session_plan(seed, group, STIMULI, EXP)
    s = ExpSession(
        token=secrets.token_urlsafe(24), participant_id=pid, group_number=group, list_order=plan["order"],
        rng_seed=seed, stage="practice", user_agent=(request.headers.get("User-Agent") or "")[:400],
        stimulus_set=STIMULI["name"], stimulus_sha1=STIMULI["sha1"],
        stimuli_are_placeholder=STIMULI["is_placeholder"], app_version=config.APP_VERSION,
        config_snapshot={"experiment": EXP, "require_id": config.REQUIRE_PARTICIPANT_ID},
        plan={"lists": plan["lists"], "order": plan["order"]})
    db.session.add(s)
    db.session.flush()
    for t in plan["pm_targets"]:
        db.session.add(SessionTarget(session_id=s.id, list_name=plan["lists"]["pm_task"], word=t["word"], category=t["category"]))
    for phase in PHASES:
        for t in plan[phase]:
            sq = t["squares"]
            db.session.add(Trial(
                session_id=s.id, phase=phase, trial_number=t["trial_number"], list_name=plan["lists"][phase],
                trial_type=t["trial_type"], target_type=t["target_type"], match_type=t["match_type"],
                is_pm_target_word=bool(t["is_target"] and phase == "pm_task"),
                word=t["word"], category=t["category"], word_color=t["word_color"],
                square_color_1=sq[0], square_color_2=sq[1], square_color_3=sq[2], square_color_4=sq[3]))
    db.session.commit()
    return s


def recompute_summary(s):
    rows = [r for r in Trial.query.filter_by(session_id=s.id, completed=True).all()]
    tdicts = [{c.name: getattr(r, c.name) for c in Trial.__table__.columns} for r in rows]
    attempts = [{"attempt_no": a.attempt_no, "n_correct": a.n_correct, "all_correct": a.all_correct}
                for a in s.recall_attempts]
    vals = summarize(tdicts, attempts)
    row = s.summary or SessionSummary(session_id=s.id)
    for k, v in vals.items():
        setattr(row, k, v)
    row.computed_at = utcnow()
    end = s.ended_at or utcnow()
    st = s.started_at if s.started_at.tzinfo else s.started_at.replace(tzinfo=timezone.utc)
    en = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    row.duration_s = (en - st).total_seconds()
    db.session.add(row)


def advance_if_phase_done(s, phase):
    done, total = phase_progress(s, phase)
    if done < total:
        return
    if phase == "pm_task":
        s.stage, s.status, s.ended_at = "done", "completed", utcnow()
        db.session.flush()
        recompute_summary(s)
    else:
        s.stage = NEXT_STAGE[phase]


# ------------------------------------------------------------------ routes
def register_routes(app):
    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.path.startswith("/api/") or request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/healthz")
    def healthz():
        db.session.execute(text("SELECT 1"))
        return {"ok": True}

    @app.get("/")
    def index():
        return render_template("index.html", pid=request.args.get("pid", "")[:120],
                               require_id=config.REQUIRE_PARTICIPANT_ID, group=request.args.get("group", ""))

    @app.post("/api/start")
    def api_start():
        data = request.get_json(silent=True) or {}
        pid = str(data.get("participant_id", "")).strip()[:120]
        if config.REQUIRE_PARTICIPANT_ID and not pid:
            return jsonify(error="Please enter your participant ID."), 400
        if not data.get("consent"):
            return jsonify(error="Consent is required to continue."), 400
        if not pid:
            pid = "auto-" + secrets.token_hex(4)
        group = data.get("group")
        group = int(group) if str(group).isdigit() and int(group) > 0 else None
        s = create_session(pid, group)
        return jsonify(url=url_for("run", token=s.token))

    @app.get("/run/<token>")
    def run(token):
        s = get_session_or_404(token)
        return render_template("run.html", token=s.token)

    @app.get("/api/<token>/state")
    def api_state(token):
        s = get_session_or_404(token)
        out = {"stage": s.stage, "config": public_config()}
        if s.stage in PHASES:
            out["done"], out["total"] = phase_progress(s, s.stage)
        if s.stage == "break":
            out["break_remaining_s"] = break_remaining(s)
        return jsonify(out)

    @app.post("/api/<token>/client_info")
    def api_client_info(token):
        s = get_session_or_404(token)
        data = request.get_json(silent=True) or {}
        info = {str(k)[:40]: (v if isinstance(v, (int, float, bool)) else str(v)[:200]) for k, v in list(data.items())[:30]}
        if s.stage != "practice" or Trial.query.filter_by(session_id=s.id, completed=True).count() > 0:
            s.resume_count = (s.resume_count or 0) + 1      # page (re)loaded after progress was made
        s.client_info = {**(s.client_info or {}), **info}
        db.session.commit()
        return jsonify(ok=True)

    @app.get("/api/<token>/trials/<phase>")
    def api_trials(token, phase):
        s = get_session_or_404(token)
        if phase not in PHASES or s.stage != phase:
            abort(409)
        rows = Trial.query.filter_by(session_id=s.id, phase=phase).order_by(Trial.trial_number).all()
        out = []
        for r in rows:
            d = {"trial_number": r.trial_number, "done": r.completed, "word": r.word.upper(),
                 "word_color": r.word_color,
                 "squares": [r.square_color_1, r.square_color_2, r.square_color_3, r.square_color_4]}
            if phase == "practice":            # practice-only feedback
                d["correct"] = "y" if r.match_type == "match" else "n"
            out.append(d)                        # NOTE: never includes target status for baseline / pm_task
        return jsonify(trials=out)

    @app.post("/api/<token>/trial")
    def api_trial(token):
        s = get_session_or_404(token)
        data = request.get_json(silent=True) or {}
        phase, num = data.get("phase"), data.get("trial_number")
        if phase != s.stage or phase not in PHASES or not isinstance(num, int):
            return jsonify(ok=False, stage=s.stage), 409
        row = Trial.query.filter_by(session_id=s.id, phase=phase, trial_number=num).first()
        if row is None:
            abort(404)
        if row.completed:                        # idempotent retry: first submission wins
            return jsonify(ok=True, stage=s.stage, duplicate=True)
        try:
            events = clean_events(data.get("events", []))
        except PayloadError:
            abort(400)
        sc = score_trial(phase, {"is_target": row.is_pm_target_word, "match_type": row.match_type}, events)
        for k, v in sc.items():
            setattr(row, k, v)
        timing = data.get("timing")
        row.timing = timing if isinstance(timing, dict) and len(json.dumps(timing)) < 4000 else None
        row.key_events, row.completed, row.submitted_at = events, True, utcnow()
        db.session.flush()
        advance_if_phase_done(s, phase)
        db.session.commit()
        return jsonify(ok=True, stage=s.stage)

    @app.get("/api/<token>/training")
    def api_training(token):
        s = get_session_or_404(token)
        if s.stage != "pm_training":
            abort(409)
        return jsonify(words=[t.word.upper() for t in s.targets], n=len(s.targets),
                       max_attempts=EXP["max_recall_attempts"])

    @app.post("/api/<token>/recall")
    def api_recall(token):
        s = get_session_or_404(token)
        if s.stage != "pm_training":
            return jsonify(error="wrong stage", stage=s.stage), 409
        data = request.get_json(silent=True) or {}
        entered = [str(x)[:60] for x in (data.get("entered") or [])][:len(s.targets)]
        norm = {x.strip().lower() for x in entered if x.strip()}
        n_prev = RecallAttempt.query.filter_by(session_id=s.id).count()
        att = RecallAttempt(session_id=s.id, attempt_no=n_prev + 1, entered=entered,
                            study_started_ms=float(data.get("study_ms") or 0))
        db.session.add(att)
        db.session.flush()
        n_ok = 0
        for t in s.targets:
            ok = t.word.lower() in norm
            n_ok += ok
            db.session.add(RecallItem(attempt_id=att.id, session_id=s.id, target_word=t.word, recalled=ok))
        att.n_correct, att.all_correct = n_ok, n_ok == len(s.targets)
        maxa = EXP["max_recall_attempts"]
        proceed = att.all_correct or (maxa and att.attempt_no >= maxa)
        if proceed:
            s.stage, s.break_started_at = "break", utcnow()
        db.session.commit()
        return jsonify(proceed=bool(proceed), stage=s.stage)   # deliberately no per-word feedback

    @app.get("/api/<token>/break")
    def api_break(token):
        s = get_session_or_404(token)
        if s.stage != "break":
            return jsonify(stage=s.stage, remaining_s=0)
        return jsonify(stage=s.stage, remaining_s=break_remaining(s))

    @app.post("/api/<token>/break/finish")
    def api_break_finish(token):
        s = get_session_or_404(token)
        if s.stage == "break" and break_remaining(s) <= 1:
            s.stage = "pm_task"
            db.session.commit()
        return jsonify(stage=s.stage, remaining_s=break_remaining(s) if s.stage == "break" else 0)

    register_admin(app)


# ------------------------------------------------------------------ admin
_fail = defaultdict(list)


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD):
            return Response("Admin disabled: set ADMIN_USERNAME and ADMIN_PASSWORD environment variables.", 503)
        if not flask_session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrapper


def csrf_ok():
    tok = flask_session.get("csrf")
    return bool(tok) and hmac.compare_digest(tok, request.form.get("csrf", ""))


def safe_cell(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v          # neutralise spreadsheet formula injection
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def csv_response(name, header, rows):
    rows = list(rows)      # materialise inside the request/app context

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header); yield buf.getvalue(); buf.seek(0); buf.truncate()
        for r in rows:
            w.writerow([safe_cell(c) for c in r]); yield buf.getvalue(); buf.seek(0); buf.truncate()
    return Response(gen(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


SESSION_COLS = ["id", "participant_id", "group_number", "list_order", "rng_seed", "stage", "status", "started_at",
                "ended_at", "resume_count", "stimulus_set", "stimulus_sha1", "stimuli_are_placeholder",
                "app_version", "user_agent", "client_info"]
TRIAL_COLS = ["phase", "trial_number", "list_name", "trial_type", "target_type", "match_type", "is_pm_target_word",
              "word", "category", "word_color", "square_color_1", "square_color_2", "square_color_3", "square_color_4",
              "yn_response", "correct_yn_response", "yn_correct", "z_response", "z_count", "response_sequence",
              "pm_expected", "pm_correct", "pm_hit", "pm_false_alarm", "rt_yn_ms", "rt_z_ms",
              "rt_task_manual_ms", "rt_pm_manual_ms", "key_events", "timing", "submitted_at"]
SUMMARY_COLS = [c.name for c in SessionSummary.__table__.columns if c.name not in ("id", "session_id")]


def register_admin(app):
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD):
            return Response("Admin disabled: set ADMIN_USERNAME and ADMIN_PASSWORD.", 503)
        ip, err = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(), None
        if request.method == "POST":
            now = time.time()
            _fail[ip] = [t for t in _fail[ip] if now - t < 600]
            if len(_fail[ip]) >= 10:
                return Response("Too many attempts. Try again later.", 429)
            ok_u = hmac.compare_digest(request.form.get("username", ""), config.ADMIN_USERNAME)
            ok_p = hmac.compare_digest(request.form.get("password", ""), config.ADMIN_PASSWORD)
            if ok_u and ok_p:
                flask_session.clear()
                flask_session["admin"], flask_session["csrf"] = True, secrets.token_hex(16)
                return redirect(url_for("admin_dashboard"))
            _fail[ip].append(now); time.sleep(1); err = "Invalid credentials."
        return render_template("admin_login.html", error=err)

    @app.post("/admin/logout")
    def admin_logout():
        flask_session.clear()
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        total = ExpSession.query.count()
        done = ExpSession.query.filter_by(status="completed").count()
        by_group = dict(db.session.query(ExpSession.list_order, func.count()).group_by(ExpSession.list_order).all())
        rows = ExpSession.query.order_by(ExpSession.started_at.desc()).limit(300).all()
        dup = dict(db.session.query(ExpSession.participant_id, func.count()).group_by(ExpSession.participant_id).all())
        prog = {}
        for r in rows:
            prog[r.id] = Trial.query.filter_by(session_id=r.id, completed=True).count()
        return render_template("admin_dashboard.html", total=total, done=done, by_group=by_group, rows=rows,
                               dup=dup, prog=prog, placeholder=STIMULI["is_placeholder"], sname=STIMULI["name"],
                               csrf=flask_session["csrf"])

    @app.get("/admin/session/<int:sid>")
    @admin_required
    def admin_session(sid):
        s = db.session.get(ExpSession, sid) or abort(404)
        trials = Trial.query.filter_by(session_id=sid, completed=True).order_by(Trial.phase.desc(), Trial.trial_number).all()
        order = {"practice": 0, "baseline": 1, "pm_task": 2}
        trials.sort(key=lambda t: (order[t.phase], t.trial_number))
        items = ([(c, getattr(s.summary, c)) for c in SUMMARY_COLS] if s.summary else [])
        return render_template("admin_session.html", s=s, trials=trials, attempts=s.recall_attempts,
                               targets=s.targets, summary_items=items)

    @app.get("/admin/download/<name>.csv")
    @admin_required
    def admin_download(name):
        if name == "trials":
            q = (db.session.query(Trial, ExpSession).join(ExpSession, Trial.session_id == ExpSession.id)
                 .filter(Trial.completed.is_(True)).order_by(ExpSession.id, Trial.phase, Trial.trial_number))
            header = ["session_id", "participant_id", "group_number", "list_order"] + TRIAL_COLS
            rows = ([s.id, s.participant_id, s.group_number, s.list_order] + [getattr(t, c) for c in TRIAL_COLS] for t, s in q.yield_per(500))
        elif name == "sessions":
            header = SESSION_COLS
            rows = ([getattr(s, c) for c in SESSION_COLS] for s in ExpSession.query.order_by(ExpSession.id).yield_per(500))
        elif name == "summary":
            q = db.session.query(SessionSummary, ExpSession).join(ExpSession, SessionSummary.session_id == ExpSession.id).order_by(ExpSession.id)
            header = ["session_id", "participant_id", "group_number", "list_order", "status"] + SUMMARY_COLS
            rows = ([s.id, s.participant_id, s.group_number, s.list_order, s.status] + [getattr(m, c) for c in SUMMARY_COLS] for m, s in q)
        elif name == "recall":
            q = (db.session.query(RecallItem, RecallAttempt, ExpSession)
                 .join(RecallAttempt, RecallItem.attempt_id == RecallAttempt.id)
                 .join(ExpSession, RecallAttempt.session_id == ExpSession.id).order_by(ExpSession.id, RecallAttempt.attempt_no))
            header = ["session_id", "participant_id", "attempt_no", "target_word", "recalled", "attempt_n_correct", "attempt_all_correct", "attempt_entered_raw"]
            rows = ([s.id, s.participant_id, a.attempt_no, i.target_word, i.recalled, a.n_correct, a.all_correct, a.entered] for i, a, s in q)
        elif name == "targets":
            q = db.session.query(SessionTarget, ExpSession).join(ExpSession, SessionTarget.session_id == ExpSession.id).order_by(ExpSession.id)
            header = ["session_id", "participant_id", "list_name", "target_word", "category"]
            rows = ([s.id, s.participant_id, t.list_name, t.word, t.category] for t, s in q)
        else:
            abort(404)
        return csv_response(f"pm_{name}.csv", header, rows)

    @app.post("/admin/recompute")
    @admin_required
    def admin_recompute():
        if not csrf_ok():
            abort(400)
        for s in ExpSession.query.filter_by(status="completed").all():
            recompute_summary(s)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
