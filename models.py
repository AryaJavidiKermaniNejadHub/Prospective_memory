"""Relational schema. Raw trial rows are authoritative; summaries are derived and can be recomputed."""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, UniqueConstraint, Index

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class ExpSession(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)  # secret URL token
    participant_id = db.Column(db.String(120), index=True)
    group_number = db.Column(db.Integer, nullable=False)
    list_order = db.Column(db.String(2), nullable=False)          # 'AB' or 'BA'
    rng_seed = db.Column(db.BigInteger, nullable=False)
    stage = db.Column(db.String(20), nullable=False, default="practice")
    status = db.Column(db.String(20), nullable=False, default="in_progress")  # in_progress | completed
    started_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at = db.Column(db.DateTime(timezone=True))
    break_started_at = db.Column(db.DateTime(timezone=True))
    user_agent = db.Column(db.String(400))
    client_info = db.Column(JSON)          # screen size, DPR, timezone, estimated frame interval, etc.
    resume_count = db.Column(db.Integer, default=0, nullable=False)
    stimulus_set = db.Column(db.String(200))
    stimulus_sha1 = db.Column(db.String(20))
    stimuli_are_placeholder = db.Column(db.Boolean, default=False)
    config_snapshot = db.Column(JSON)
    app_version = db.Column(db.String(20))
    plan = db.Column(JSON)                 # full generated trial plan (server-side truth)

    targets = db.relationship("SessionTarget", backref="session", cascade="all, delete-orphan")
    recall_attempts = db.relationship("RecallAttempt", backref="session", cascade="all, delete-orphan")
    summary = db.relationship("SessionSummary", backref="session", uselist=False, cascade="all, delete-orphan")


class SessionTarget(db.Model):
    """The six PM target words assigned to a session."""
    __tablename__ = "session_targets"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    list_name = db.Column(db.String(1), nullable=False)
    word = db.Column(db.String(60), nullable=False)
    category = db.Column(db.String(60))


class Trial(db.Model):
    __tablename__ = "trials"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    phase = db.Column(db.String(12), nullable=False)      # practice | baseline | pm_task
    trial_number = db.Column(db.Integer, nullable=False)
    list_name = db.Column(db.String(1))
    trial_type = db.Column(db.String(20))                 # target-match, filler-nomatch, ...
    target_type = db.Column(db.String(10))                # target | filler
    match_type = db.Column(db.String(10))                 # match | nomatch
    is_pm_target_word = db.Column(db.Boolean)             # word is one of the learned targets AND phase == pm_task
    word = db.Column(db.String(60))
    category = db.Column(db.String(60))
    word_color = db.Column(db.String(10))
    square_color_1 = db.Column(db.String(10)); square_color_2 = db.Column(db.String(10))
    square_color_3 = db.Column(db.String(10)); square_color_4 = db.Column(db.String(10))
    # --- participant responses & scoring (filled on submission) ---
    completed = db.Column(db.Boolean, default=False, nullable=False)
    yn_response = db.Column(db.String(1))
    correct_yn_response = db.Column(db.String(1))
    yn_correct = db.Column(db.Boolean)
    z_response = db.Column(db.Boolean)
    z_count = db.Column(db.Integer)
    response_sequence = db.Column(db.String(12))          # task only | task-PM | PM-task | PM only | none
    pm_expected = db.Column(db.Boolean)
    pm_correct = db.Column(db.Boolean)
    pm_hit = db.Column(db.Boolean)
    pm_false_alarm = db.Column(db.Boolean)
    rt_yn_ms = db.Column(db.Float)                        # from probe onset
    rt_z_ms = db.Column(db.Float)                         # from probe onset
    rt_task_manual_ms = db.Column(db.Float)               # Millisecond convention
    rt_pm_manual_ms = db.Column(db.Float)                 # Millisecond convention
    key_events = db.Column(JSON)                          # every y/n/z keydown, stage + ms rel. probe onset
    timing = db.Column(JSON)                              # measured onsets (ms rel. trial start), wall clock
    submitted_at = db.Column(db.DateTime(timezone=True))  # server time

    __table_args__ = (UniqueConstraint("session_id", "phase", "trial_number", name="uq_trial"),
                      Index("ix_trials_session_phase", "session_id", "phase"))


class RecallAttempt(db.Model):
    __tablename__ = "recall_attempts"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = db.Column(db.Integer, nullable=False)
    entered = db.Column(JSON)                             # raw strings typed
    n_correct = db.Column(db.Integer)
    all_correct = db.Column(db.Boolean)
    study_started_ms = db.Column(db.Float)                # self-paced study duration (ms) before this attempt
    submitted_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    items = db.relationship("RecallItem", backref="attempt", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("session_id", "attempt_no", name="uq_attempt"),)


class RecallItem(db.Model):
    __tablename__ = "recall_items"
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("recall_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = db.Column(db.Integer, nullable=False, index=True)
    target_word = db.Column(db.String(60), nullable=False)
    recalled = db.Column(db.Boolean, nullable=False)


class SessionSummary(db.Model):
    __tablename__ = "session_summaries"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    computed_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    duration_s = db.Column(db.Float)
    n_baseline_trials = db.Column(db.Integer); n_pm_trials = db.Column(db.Integer)
    prop_correct_filler_baseline = db.Column(db.Float)
    mean_rt_filler_baseline_ms = db.Column(db.Float)
    median_rt_filler_baseline_ms = db.Column(db.Float)
    prop_correct_filler_pm = db.Column(db.Float)
    mean_rt_filler_pm_ms = db.Column(db.Float)
    prop_correct_filler_pm_all_orders = db.Column(db.Float)
    rt_cost_ms = db.Column(db.Float)
    pm_hits = db.Column(db.Integer); prop_pm_hits = db.Column(db.Float)
    pm_false_alarms = db.Column(db.Integer); prop_false_alarms = db.Column(db.Float)
    prop_correct_yn_on_pm_targets = db.Column(db.Float)
    n_pm_first_order = db.Column(db.Integer); n_task_first_order = db.Column(db.Integer)
    recall_attempts = db.Column(db.Integer)
    recall_first_attempt_n_correct = db.Column(db.Integer)
    recall_criterion_met = db.Column(db.Boolean)
