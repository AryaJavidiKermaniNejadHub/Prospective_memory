import collections, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EXPERIMENT as E
from trialgen import load_stimuli, build_session_plan
from scoring import score_trial, summarize, clean_events

S = load_stimuli()

def check_phase(tr):
    assert len(tr) == 62
    assert [t["trial_number"] for t in tr if t["is_target"]] == [10, 20, 30, 40, 50, 60]
    c = collections.Counter(t["trial_type"] for t in tr)
    assert c["target-match"] == 3 and c["target-nomatch"] == 3
    assert c["filler-match"] == 28 and c["filler-nomatch"] == 28
    assert len({t["word"] for t in tr}) == 62
    mc, nc = collections.Counter(), collections.Counter()
    for t in tr:
        assert len(set(t["squares"])) == 4
        inn = t["word_color"] in t["squares"]
        assert inn == (t["match_type"] == "match")
        (mc if inn else nc)[t["word_color"]] += 1
    assert max(mc.values()) - min(mc.values()) <= 1 and len(mc) == 5, mc
    assert max(nc.values()) - min(nc.values()) <= 1 and len(nc) == 5, nc

for seed in range(300):
    g = seed % 4 + 1
    p = build_session_plan(seed, g, S, E)
    check_phase(p["baseline"]); check_phase(p["pm_task"])
    assert p["order"] == ("AB" if g % 2 else "BA")
    pm_words = {t["word"] for t in p["pm_targets"]}
    assert not pm_words & {t["word"] for t in p["baseline"]}, "PM targets leaked into baseline"
    assert {t["word"] for t in p["pm_task"] if t["is_target"]} == pm_words
    assert len(p["practice"]) == 6 and sum(t["match_type"] == "match" for t in p["practice"]) == 3
assert build_session_plan(5, 1, S, E) == build_session_plan(5, 1, S, E)
print("trial generation OK (300 seeds)")

ev = lambda *a: clean_events([{"k": k, "stage": s, "t": t} for k, s, t in a])
tgt = {"is_target": True, "match_type": "match"}; fil = {"is_target": False, "match_type": "nomatch"}
r = score_trial("pm_task", tgt, ev(("y", "probe", 700), ("z", "iti", 1100)))
assert r["yn_correct"] and r["pm_hit"] and r["response_sequence"] == "task-PM" and r["rt_pm_manual_ms"] == 400
r = score_trial("pm_task", tgt, ev(("z", "probe", 500), ("y", "probe", 900)))
assert r["response_sequence"] == "PM-task" and r["rt_task_manual_ms"] == 400 and r["pm_correct"]
r = score_trial("pm_task", tgt, ev(("y", "probe", 700)))
assert r["pm_correct"] is False and r["pm_hit"] is False
r = score_trial("pm_task", fil, ev(("n", "probe", 600), ("z", "iti", 900)))
assert r["pm_false_alarm"] and r["yn_correct"]
r = score_trial("baseline", tgt, ev(("y", "probe", 650), ("z", "iti", 900)))
assert r["z_response"] is None and r["pm_correct"] is None and r["response_sequence"] == "task only"
r = score_trial("pm_task", fil, ev(("z", "squares", -300), ("n", "probe", 600)))
assert r["z_response"] is False
for bad in ([{"k": "q", "stage": "probe", "t": 1}], [{"k": "y", "stage": "probe", "t": float("nan")}]):
    try:
        clean_events(bad); raise SystemExit("should reject")
    except ValueError:
        pass
print("scoring OK")

rng = random.Random(1); plan = build_session_plan(1, 1, S, E); trials = []
for ph in ("baseline", "pm_task"):
    for t in plan[ph]:
        events = ev(("y" if t["match_type"] == "match" else "n", "probe", 600 + rng.random() * 100))
        if ph == "pm_task" and t["is_target"] and t["trial_number"] <= 30:
            events = events + ev(("z", "iti", 900))
        trials.append({**t, **score_trial(ph, t, events), "phase": ph})
s = summarize(trials, [{"attempt_no": 1, "n_correct": 5, "all_correct": False},
                       {"attempt_no": 2, "n_correct": 6, "all_correct": True}])
assert s["pm_hits"] == 3 and s["prop_pm_hits"] == 0.5 and s["pm_false_alarms"] == 0
assert s["prop_correct_filler_baseline"] == 1.0 and s["recall_criterion_met"] and s["recall_first_attempt_n_correct"] == 5
print("summary OK")
