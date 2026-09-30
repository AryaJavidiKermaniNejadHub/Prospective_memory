"""Server-side scoring. Correctness is computed here and never sent to participants
(except practice trials, which are explicitly allowed feedback)."""
import math

VALID_KEYS = {"y", "n", "z"}
VALID_STAGES = {"squares", "probe", "iti"}


class PayloadError(ValueError):
    pass


def clean_events(events):
    if not isinstance(events, list) or len(events) > 60:
        raise PayloadError("bad events")
    out = []
    for e in events:
        k, st, t = e.get("k"), e.get("stage"), e.get("t")
        if k not in VALID_KEYS or st not in VALID_STAGES:
            raise PayloadError("bad event")
        if not isinstance(t, (int, float)) or not math.isfinite(t):
            raise PayloadError("bad time")
        out.append({"k": k, "stage": st, "t": round(float(t), 2)})  # t = ms since probe onset (negative before)
    return out


def score_trial(phase, truth, events):
    """truth: dict with is_target, match_type. events: cleaned list. Returns dict of columns."""
    pm_active = phase == "pm_task"
    yn_ev = next((e for e in events if e["k"] in ("y", "n") and e["stage"] == "probe"), None)
    z_ev = [e for e in events if e["k"] == "z" and e["stage"] in ("probe", "iti")] if pm_active else []
    yn = yn_ev["k"].upper() if yn_ev else None
    correct_yn = "Y" if truth["match_type"] == "match" else "N"
    z_made = bool(z_ev)
    z_first = z_ev[0] if z_ev else None
    if yn_ev and z_first:
        seq = "PM-task" if z_first["t"] < yn_ev["t"] else "task-PM"
    elif yn_ev:
        seq = "task only"
    elif z_first:
        seq = "PM only"
    else:
        seq = "none"
    rt_yn = yn_ev["t"] if yn_ev else None
    rt_z = z_first["t"] if z_first else None
    # Millisecond-style RTs: task RT measured from PM response if PM came first;
    # PM RT measured from task response if task came first.
    rt_task_m = (rt_yn - rt_z) if seq == "PM-task" else rt_yn
    rt_pm_m = (rt_z - rt_yn) if seq == "task-PM" else rt_z
    is_t = bool(truth["is_target"])
    return {
        "yn_response": yn, "correct_yn_response": correct_yn,
        "yn_correct": (yn == correct_yn) if yn else None,
        "z_response": z_made if pm_active else None,
        "z_count": len(z_ev) if pm_active else None,
        "response_sequence": seq,
        "pm_expected": is_t if pm_active else None,
        "pm_correct": (z_made == is_t) if pm_active else None,
        "pm_hit": (is_t and z_made) if pm_active else None,
        "pm_false_alarm": ((not is_t) and z_made) if pm_active else None,
        "rt_yn_ms": rt_yn, "rt_z_ms": rt_z,
        "rt_task_manual_ms": rt_task_m, "rt_pm_manual_ms": rt_pm_m,
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs: return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def summarize(trials, recall_attempts):
    """trials: list of dicts (column names as in Trial model), completed only.
    recall_attempts: list of dicts {attempt_no, n_correct, all_correct}."""
    base = [t for t in trials if t["phase"] == "baseline" and t["target_type"] == "filler"]
    pm = [t for t in trials if t["phase"] == "pm_task"]
    pm_f = [t for t in pm if t["target_type"] == "filler"]
    pm_t = [t for t in pm if t["target_type"] == "target"]

    def acc(ts): return _mean([1.0 if t["yn_correct"] else 0.0 for t in ts]) if ts else None
    def rt_correct(ts): return _mean([t["rt_yn_ms"] for t in ts if t["yn_correct"]])

    # Millisecond convention for PM-phase fillers: only trials where the task response came first / only
    pm_f_task_first = [t for t in pm_f if t["response_sequence"] in ("task only", "task-PM")]
    hits = sum(1 for t in pm_t if t["pm_hit"])
    fas = sum(1 for t in pm_f if t["pm_false_alarm"])
    ra = sorted(recall_attempts, key=lambda a: a["attempt_no"])
    fills_base, fills_pm = rt_correct(base), rt_correct(pm_f_task_first)
    return {
        "n_baseline_trials": len([t for t in trials if t["phase"] == "baseline"]),
        "n_pm_trials": len(pm),
        "prop_correct_filler_baseline": acc(base),
        "mean_rt_filler_baseline_ms": fills_base,
        "median_rt_filler_baseline_ms": _median([t["rt_yn_ms"] for t in base if t["yn_correct"]]),
        "prop_correct_filler_pm": acc(pm_f_task_first),
        "mean_rt_filler_pm_ms": fills_pm,
        "prop_correct_filler_pm_all_orders": acc(pm_f),
        "rt_cost_ms": (fills_pm - fills_base) if fills_pm is not None and fills_base is not None else None,
        "pm_hits": hits,
        "prop_pm_hits": hits / len(pm_t) if pm_t else None,
        "pm_false_alarms": fas,
        "prop_false_alarms": fas / len(pm_f) if pm_f else None,
        "prop_correct_yn_on_pm_targets": acc(pm_t),
        "n_pm_first_order": sum(1 for t in pm if t["response_sequence"] == "PM-task"),
        "n_task_first_order": sum(1 for t in pm if t["response_sequence"] == "task-PM"),
        "recall_attempts": len(ra),
        "recall_first_attempt_n_correct": ra[0]["n_correct"] if ra else None,
        "recall_criterion_met": bool(ra[-1]["all_correct"]) if ra else None,
    }
