"""End-to-end smoke test using Flask's test client and a temporary SQLite DB.
Run locally after `pip install -r requirements.txt`:   python tests/test_flow.py
It simulates two interleaved participants and checks isolation, scoring, no-feedback, and CSV export."""
import os, sys, tempfile
os.environ.update(SECRET_KEY="test", ADMIN_USERNAME="a", ADMIN_PASSWORD="b", BREAK_SECONDS="0",
                  DATABASE_URL="sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
from models import Trial, ExpSession
c1, c2 = A.app.test_client(), A.app.test_client()

def start(c, pid):
    r = c.post("/api/start", json={"participant_id": pid, "consent": True}); assert r.status_code == 200
    return r.json["url"].split("/run/")[1]

def play(c, tok, phase, pm_targets=()):
    trials = c.get(f"/api/{tok}/trials/{phase}").json["trials"]
    assert not any(k in trials[0] for k in ("is_target", "trial_type", "target_type")), "target status leaked"
    if phase != "practice": assert "correct" not in trials[0], "correctness leaked"
    with A.app.app_context():
        s = ExpSession.query.filter_by(token=tok).one()
        truth = {t.trial_number: t for t in Trial.query.filter_by(session_id=s.id, phase=phase)}
        truth = {n: (t.match_type, t.is_pm_target_word) for n, t in truth.items()}
    last = None
    for t in trials:
        m, is_t = truth[t["trial_number"]]
        ev = [{"k": "y" if m == "match" else "n", "stage": "probe", "t": 650.0}]
        if phase == "pm_task" and is_t: ev.append({"k": "z", "stage": "iti", "t": 900.0})
        last = c.post(f"/api/{tok}/trial", json={"phase": phase, "trial_number": t["trial_number"], "events": ev, "timing": {}})
        assert last.status_code == 200
        assert set(last.json) <= {"ok", "stage", "duplicate"}, "unexpected fields (possible feedback)"
    return last.json["stage"]

t1, t2 = start(c1, "P1"), start(c2, "P2")
assert play(c1, t1, "practice") == "baseline" and c2.get(f"/api/{t2}/state").json["stage"] == "practice"
assert play(c2, t2, "practice") == "baseline"
assert play(c1, t1, "baseline") == "pm_training"
assert c1.get(f"/api/{t1}/trials/pm_task").status_code == 409          # cannot skip ahead
words = c1.get(f"/api/{t1}/training").json["words"]
assert c1.post(f"/api/{t1}/recall", json={"entered": words[:5], "study_ms": 1}).json["proceed"] is False
assert c1.post(f"/api/{t1}/recall", json={"entered": [w.lower() for w in words], "study_ms": 1}).json["proceed"] is True
assert c1.post(f"/api/{t1}/break/finish", json={}).json["stage"] == "pm_task"
assert play(c1, t1, "pm_task") == "done"
dup = c1.post(f"/api/{t1}/trial", json={"phase": "pm_task", "trial_number": 1, "events": []}); assert dup.status_code == 409
adm = A.app.test_client(); assert adm.get("/admin").status_code == 302
adm.post("/admin/login", data={"username": "a", "password": "b"})
for name in ("trials", "summary", "sessions", "recall", "targets"):
    r = adm.get(f"/admin/download/{name}.csv"); assert r.status_code == 200 and len(r.data) > 50, name
body = adm.get("/admin/download/summary.csv").data.decode(); assert "pm_hits" in body
with A.app.app_context():
    assert Trial.query.filter_by(completed=True, session_id=ExpSession.query.filter_by(participant_id="P1").one().id).count() == 6 + 62 + 62
    s1 = ExpSession.query.filter_by(participant_id="P1").one(); assert s1.status == "completed" and s1.summary.pm_hits == 6
    s2 = ExpSession.query.filter_by(participant_id="P2").one(); assert s2.stage == "baseline" and s1.list_order != s2.list_order
print("integration flow OK")
