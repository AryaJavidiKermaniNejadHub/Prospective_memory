"""Stimulus loading, validation and trial-list generation (pure Python, no DB/web deps)."""
import hashlib
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
STIMULI_PATH = os.environ.get("STIMULI_PATH", os.path.join(HERE, "stimuli.json"))


class StimulusError(Exception):
    pass


def load_stimuli(path=STIMULI_PATH, colors=("blue", "green", "red", "yellow", "white")):
    with open(path, "rb") as fh:
        raw = fh.read()
    data = json.loads(raw.decode("utf-8"))
    out = {"name": data.get("stimulus_set_name", "unnamed"),
           "is_placeholder": bool(data.get("is_placeholder", False)),
           "sha1": hashlib.sha1(raw).hexdigest()[:12], "lists": {}}
    seen = set()
    for lname in ("A", "B"):
        cats = data["lists"].get(lname)
        if not cats:
            raise StimulusError(f"List {lname} missing from stimuli file")
        targets, fillers = [], []
        for cat, spec in cats.items():
            targets.append({"word": spec["target"].strip().lower(), "category": cat})
            for w in spec["fillers"]:
                fillers.append({"word": w.strip().lower(), "category": cat})
        if len(targets) != 6:
            raise StimulusError(f"List {lname}: need exactly 6 targets (one per category), got {len(targets)}")
        if len(fillers) < 56:
            raise StimulusError(f"List {lname}: need at least 56 fillers, got {len(fillers)}")
        for item in targets + fillers:
            w = item["word"]
            if w in colors:
                raise StimulusError(f"'{w}' is a colour name; not allowed as a stimulus word")
            if w in seen:
                raise StimulusError(f"Duplicate word across/within lists: '{w}'")
            seen.add(w)
        out["lists"][lname] = {"targets": targets, "fillers": fillers}
    return out


def _balanced(rng, colors, n):
    """n colours, each used floor(n/k) times; the remainder colours are chosen at random."""
    base, rem = divmod(n, len(colors))
    lst = list(colors) * base + rng.sample(list(colors), rem)
    rng.shuffle(lst)
    return lst


def _squares_for(rng, colors, match, probe_color=None, omitted=None):
    if match:
        others = rng.sample([c for c in colors if c != probe_color], 3)
        squares = others + [probe_color]
        rng.shuffle(squares)
        return squares, probe_color
    squares = [c for c in colors if c != omitted]  # 4 distinct colours; the 5th is the probe colour
    rng.shuffle(squares)
    return squares, omitted


def make_phase(rng, colors, targets, fillers, n_trials, target_positions,
               n_target_match, n_filler_match):
    """Build one 62-trial phase. Returns list of dicts (server-side truth)."""
    n_targets = len(target_positions)
    n_fillers = n_trials - n_targets
    if len(targets) != n_targets:
        raise ValueError("number of targets must equal number of target positions")
    tflags = [True] * n_target_match + [False] * (n_targets - n_target_match)
    rng.shuffle(tflags)
    fflags = [True] * n_filler_match + [False] * (n_fillers - n_filler_match)
    rng.shuffle(fflags)
    tw = rng.sample(targets, n_targets)          # each target exactly once, random order
    fw = rng.sample(fillers, n_fillers)          # fillers without replacement
    n_match = n_target_match + n_filler_match
    match_colors = _balanced(rng, colors, n_match)
    nonmatch_colors = _balanced(rng, colors, n_trials - n_match)
    trials, ti, fi = [], 0, 0
    for pos in range(1, n_trials + 1):
        is_target = pos in target_positions
        match = tflags[ti] if is_target else fflags[fi]
        item = tw[ti] if is_target else fw[fi]
        if is_target: ti += 1
        else: fi += 1
        if match:
            squares, probe = _squares_for(rng, colors, True, probe_color=match_colors.pop())
        else:
            squares, probe = _squares_for(rng, colors, False, omitted=nonmatch_colors.pop())
        trials.append({
            "trial_number": pos, "is_target": is_target,
            "target_type": "target" if is_target else "filler",
            "match_type": "match" if match else "nomatch",
            "trial_type": f"{'target' if is_target else 'filler'}-{'match' if match else 'nomatch'}",
            "word": item["word"], "category": item["category"],
            "word_color": probe, "squares": squares,
        })
    return trials


def make_practice(rng, colors, fillers, n):
    flags = [True] * (n // 2) + [False] * (n - n // 2)
    rng.shuffle(flags)
    words = rng.sample(fillers, n)
    m_cols = _balanced(rng, colors, sum(flags))
    n_cols = _balanced(rng, colors, n - sum(flags))
    out = []
    for i, (m, item) in enumerate(zip(flags, words), start=1):
        sq, probe = (_squares_for(rng, colors, True, probe_color=m_cols.pop()) if m
                     else _squares_for(rng, colors, False, omitted=n_cols.pop()))
        out.append({"trial_number": i, "is_target": False, "target_type": "filler",
                    "match_type": "match" if m else "nomatch",
                    "trial_type": "filler-match" if m else "filler-nomatch",
                    "word": item["word"], "category": item["category"],
                    "word_color": probe, "squares": sq})
    return out


def build_session_plan(seed, group_number, stimuli, exp):
    """Everything randomised for one session, from one seed (reproducible)."""
    rng = random.Random(seed)
    order = "AB" if group_number % 2 == 1 else "BA"   # odd -> AB, even -> BA (as in Millisecond)
    base_list, pm_list = order[0], order[1]
    colors = exp["colors"]
    L = stimuli["lists"]
    kw = dict(n_trials=exp["n_trials"], target_positions=exp["target_positions"],
              n_target_match=exp["n_target_match"], n_filler_match=exp["n_filler_match"])
    return {
        "order": order,
        "practice": make_practice(rng, colors, L[base_list]["fillers"], exp["n_practice_trials"]),
        "baseline": make_phase(rng, colors, L[base_list]["targets"], L[base_list]["fillers"], **kw),
        "pm_task": make_phase(rng, colors, L[pm_list]["targets"], L[pm_list]["fillers"], **kw),
        "lists": {"baseline": base_list, "pm_task": pm_list, "practice": base_list},
        "pm_targets": L[pm_list]["targets"],
    }
