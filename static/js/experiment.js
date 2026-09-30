// Browser experiment engine. Timing: requestAnimationFrame + performance.now()/KeyboardEvent.timeStamp.
// This is NOT laboratory-grade timing (see README, "Browser timing limitations").
(() => {
  'use strict';
  const TOKEN = window.TOKEN, I = window.INSTR;
  const $ = (id) => document.getElementById(id);
  const screen = $('screen'), stage = $('stage'), sq = $('square'), probe = $('probe'), fb = $('feedback');
  const responseButtons = $('response-buttons'), btnY = $('btn-y'), btnN = $('btn-n'), btnZ = $('btn-z');
  let cfg = null, frameMs = 16.7, hidden = false;
  document.addEventListener('visibilitychange', () => { if (document.hidden) hidden = true; });

  async function api(path, body) {
    const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(`/api/${TOKEN}/${path}`, opt);
    if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { status: r.status });
    return r.json();
  }

  // ---------- generic UI ----------
  function show(html) { stage.style.display = 'none'; screen.style.display = 'flex'; screen.innerHTML = `<div class="card">${html}</div>`; }
  function clickNext() {
    return new Promise((res) => {
      const btn = $('next'); const h = (e) => { if (e.type === 'click' || e.code === 'Space') { e.preventDefault(); cleanup(); res(); } };
      const cleanup = () => { btn.removeEventListener('click', h); window.removeEventListener('keydown', h); };
      btn.addEventListener('click', h); window.addEventListener('keydown', h);
    });
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---------- frame-locked timing ----------
  function nextFrame() { return new Promise((r) => requestAnimationFrame(r)); }
  function waitUntil(t) {                       // resolves in the rAF callback of the first frame at/after t
    const tol = frameMs * 0.45;
    return new Promise((res) => { const tick = (ts) => (ts >= t - tol ? res(ts) : requestAnimationFrame(tick)); requestAnimationFrame(tick); });
  }
  async function measureFrame() {
    const ts = []; for (let i = 0; i < 40; i++) ts.push(await nextFrame());
    const d = ts.slice(1).map((v, i) => v - ts[i]).sort((a, b) => a - b); return d[Math.floor(d.length / 2)] || 16.7;
  }
  const evTime = (e) => (e.timeStamp > 1e12 ? performance.now() : e.timeStamp);

  // ---------- reliable, sequential result upload ----------
  // Every trial is saved and acknowledged by the server BEFORE the next
  // trial starts. This prevents concurrent-upload races and section replay.
  async function upload(payload) {
    let lastError = null;
    for (let a = 0; a < 8; a++) {
      try {
        const r = await fetch(`/api/${TOKEN}/trial`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true
        });
        if (r.ok || r.status === 409) return;
        lastError = new Error('HTTP ' + r.status);
      } catch (e) {
        lastError = e;
      }
      await sleep(Math.min(8000, 500 * 2 ** a));
    }
    throw lastError || new Error('Could not save trial');
  }

  // ---------- one trial ----------
  async function runTrial(tr, phase) {
    const events = [], on = {}; let probeOn = null, cur = 'squares', gotYN = false, t0 = 0, resolveYN;
    const ynDone = new Promise((r) => (resolveYN = r));
    const hex = cfg.color_hex, K = cfg.keys;

    const recordResponse = (rawKey, timestamp) => {
      const k = rawKey.toLowerCase();
      if (k !== K.yes && k !== K.no && k !== K.pm) return;
      const t = timestamp ?? performance.now();
      let st = cur;
      if (st === 'probe' && (probeOn === null || t < probeOn)) st = 'squares';
      events.push({ k: k === K.yes ? 'y' : k === K.no ? 'n' : 'z', stage: st, t: st === 'squares' ? t - t0 : t - probeOn });
      if (st === 'probe' && !gotYN && (k === K.yes || k === K.no)) {
        gotYN = true;
        resolveYN(k);
      } else if (phase === 'pm_task' && st === 'probe' && !gotYN && k === K.pm) {
        // Allow a Z-only response to finish a PM-task trial. This records
        // the trial as "PM only" when no Y/N response was given.
        gotYN = true;
        resolveYN(null);
      }
    };

    const onKey = (e) => {
      if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = (e.key || '').toLowerCase(); if (k === ' ') e.preventDefault();
      recordResponse(k, evTime(e));
    };
    const buttonDown = (k) => (e) => {
      e.preventDefault();
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      recordResponse(k, performance.now());
    };
    const by = buttonDown(K.yes), bn = buttonDown(K.no), bz = buttonDown(K.pm);
    btnY.addEventListener('pointerdown', by); btnN.addEventListener('pointerdown', bn); btnZ.addEventListener('pointerdown', bz);
    window.addEventListener('keydown', onKey, true);
    let T = await waitUntil(performance.now()); t0 = T; hidden = false;
    for (let i = 0; i < 4; i++) {
      const s = await waitUntil(T); sq.style.background = hex[tr.squares[i]]; sq.style.display = 'block'; on['sq' + (i + 1)] = s - t0;
      const b = await waitUntil(s + cfg.square_ms); sq.style.display = 'none'; on['blank' + (i + 1)] = b - t0; T = b + cfg.isi_ms;
    }
    const p = await waitUntil(T); probe.textContent = tr.word; probe.style.color = hex[tr.word_color]; probe.style.opacity = '1'; probe.style.display = 'block';
    probeOn = p; cur = 'probe'; on.probe = p - t0;
    const key = await ynDone;

    // Smith & Bayen: the word disappears after the Y/N response, followed by
    // a 1-second blank interval. The short fade is purely visual and begins
    // at the response; it does not wait for a response from the participant.
    probe.classList.add('probe-fade');
    const fadeEnd = performance.now() + 100;
    await sleep(100);
    probe.style.display = 'none'; probe.classList.remove('probe-fade'); probe.style.opacity = '1';
    cur = 'iti';
    on.probe_off = fadeEnd - t0;
    let itiStart = fadeEnd;
    if (phase === 'practice' && key !== tr.correct) {          // practice-only feedback; never in baseline / PM task
      fb.textContent = 'Incorrect'; fb.style.display = 'block';
      const f = await waitUntil(fadeEnd + cfg.practice_feedback_ms); fb.style.display = 'none'; itiStart = f;
    }
    const end = await waitUntil(itiStart + cfg.iti_ms); on.trial_end = end - t0;
    window.removeEventListener('keydown', onKey, true);
    btnY.removeEventListener('pointerdown', by); btnN.removeEventListener('pointerdown', bn); btnZ.removeEventListener('pointerdown', bz);
    on.wall_start_ms = Date.now() - (performance.now() - t0); on.frame_ms = frameMs; on.hidden = hidden;
    return { phase, trial_number: tr.trial_number, events, timing: on };
  }

  async function runPhase(phase) {
    const { trials } = await api('trials/' + phase);
    show(I.ready); await clickNext();
    screen.style.display = 'none'; stage.style.display = 'block';
    responseButtons.style.display = phase === 'pm_task' ? 'flex' : 'flex';
    btnZ.style.display = phase === 'pm_task' ? 'block' : 'none';
    await sleep(cfg.iti_ms);
    // Save each trial before allowing the next trial to begin.
    for (const tr of trials) {
      if (tr.done) continue;
      const result = await runTrial(tr, phase);
      stage.style.display = 'none';
      responseButtons.style.display = 'none';
      show('<p>Saving…</p>');
      await upload(result);
      if (tr !== trials[trials.length - 1]) {
        screen.style.display = 'none';
        stage.style.display = 'block';
        responseButtons.style.display = 'flex';
        btnZ.style.display = phase === 'pm_task' ? 'block' : 'none';
      }
    }
    stage.style.display = 'none';
    responseButtons.style.display = 'none';
  }

  // ---------- PM training + recall ----------
  async function training() {
    show(I.training); await clickNext();
    const info = await api('training'); let attempt = 0;
    for (;;) {
      attempt++; if (attempt > 1) { show(I.restudy); await clickNext(); }
      show(I.study(info.words)); const t = performance.now(); await clickNext(); const studyMs = performance.now() - t;
      show(I.recall(info.n, attempt));
      const boxes = $('boxes'); boxes.innerHTML = Array.from({ length: info.n }, (_, i) => `<input type="text" class="rb" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="word ${i + 1}">`).join('');
      boxes.firstChild.focus();
      await new Promise((res) => { $('next').addEventListener('click', res); });
      const entered = [...document.querySelectorAll('.rb')].map((e) => e.value);
      const r = await api('recall', { entered, study_ms: studyMs });
      if (r.proceed) return;
    }
  }

  async function breakPhase() {
    show(I.breakScreen);
    for (;;) {
      const b = await api('break'); if (b.stage !== 'break') return;
      const rem = Math.ceil(b.remaining_s); const m = String(Math.floor(rem / 60)).padStart(2, '0'), s = String(rem % 60).padStart(2, '0');
      $('timer').textContent = `${m}:${s}`;
      if (rem <= 0) break; await sleep(1000);
    }
    $('next').disabled = false; await clickNext(); await api('break/finish', {});
  }

  // ---------- main loop ----------
  async function main() {
    let st = await api('state'); cfg = st.config; frameMs = await measureFrame();
    api('client_info', { screen_w: screen.clientWidth, screen_h: screen.clientHeight, dpr: window.devicePixelRatio, win_w: innerWidth,
      win_h: innerHeight, tz: Intl.DateTimeFormat().resolvedOptions().timeZone, lang: navigator.language, platform: navigator.platform, frame_ms: Math.round(frameMs * 100) / 100 }).catch(() => {});
    document.documentElement.style.setProperty('--c-blue', cfg.color_hex.blue); ['green', 'red', 'yellow', 'white'].forEach((c) => document.documentElement.style.setProperty('--c-' + c, cfg.color_hex[c]));
    for (;;) {
      st = await api('state');
      const resumed = st.done > 0 && st.done < st.total;
      if (st.stage === 'practice') { if (resumed) { show(I.resume); await clickNext(); } else { show(I.practice); await clickNext(); } await runPhase('practice'); }
      else if (st.stage === 'baseline') { show(resumed ? I.resume : I.baseline); await clickNext(); await runPhase('baseline'); }
      else if (st.stage === 'pm_training') await training();
      else if (st.stage === 'break') await breakPhase();
      else if (st.stage === 'pm_task') { show(resumed ? I.resume : I.pm); await clickNext(); await runPhase('pm_task'); }
      else if (st.stage === 'done') { show(I.done); return; }
    }
  }
  main().catch((e) => { show(`<h2>Something went wrong</h2><p>Please reload this page. Your progress is saved. (${e.message})</p>`); });
})();
