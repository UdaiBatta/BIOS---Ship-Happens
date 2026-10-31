/* EgoHand Twin viewer <-> local Django backend connector.
 *
 * Active only when the page is served over HTTP by the backend (`manage.py runserver`, then
 * open http://127.0.0.1:8000/). Opened as a local file (file://) it does nothing and makes no
 * network requests, so the offline prototype keeps working exactly as before.
 *
 * It reuses the viewer's own loaders (parseJsonl, loadFrames, addResultFile, afterResults),
 * so every check the viewer applies to local files also applies to backend data:
 *  - landmarks.jsonl            -> Load JSONL path
 *  - optional identity.json and lift summary/arrays -> Add results path (lift = EXPERIMENTAL, assumed lens)
 *  - proxy.mp4 (frame-exact H.264 of the selected frames) -> video element, offset by proxy metadata
 * Everything stays on this machine: the backend binds to 127.0.0.1.
 */
(() => {
  if (!/^https?:$/.test(location.protocol)) return;

  const params = new URLSearchParams(location.search);
  if (params.get('token')) sessionStorage.setItem('egohandToken', params.get('token'));
  const token = sessionStorage.getItem('egohandToken') || '';
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const withToken = (url) => (token ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : url);

  async function api(path, options = {}) {
    const response = await fetch(`/api/${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) {
      let message = `${response.status}`;
      try { message = (await response.json()).error || message; } catch { /* not JSON */ }
      throw new Error(message);
    }
    return response;
  }
  const json = async (path, options) => (await api(path, options)).json();
  const fileFrom = async (path, name) => new File([await (await api(path)).blob()], name);

  const bar = document.createElement('div');
  bar.className = 'controls';
  bar.setAttribute('role', 'toolbar');
  bar.setAttribute('aria-label', 'Local backend');
  bar.innerHTML = `
    <span class="note" title="Local EgoHand Twin backend on this machine">Backend:</span>
    <select class="btn" id="bkRuns" aria-label="Completed runs" style="max-width: 26rem"></select>
    <button class="btn" id="bkLoad" title="Load landmarks, side votes, experimental lift and the proxy video of this run">Load run</button>
    <button class="btn" id="bkRefresh" title="Refresh the run list">↻</button>
    <span class="sep"></span>
    <select class="btn" id="bkVideo" aria-label="Registered video"></select>
    <select class="btn" id="bkPreset" aria-label="Preset" title="recall: thresholds 0.3 + centre-crop rescue (chosen on dev, provisional labels). accurate: recall + a reverse-time pass, finds more hands, about 2x slower. baseline: MediaPipe defaults.">
      <option value="recall" selected>recall</option><option value="accurate">accurate (slower)</option><option value="baseline">baseline</option></select>
    <label class="note">start <input id="bkStart" type="number" value="0" min="0" step="1" style="width: 4.5em"> s</label>
    <label class="note">length <input id="bkDur" type="number" value="30" min="1" step="1" style="width: 4.5em"> s</label>
    <button class="btn" id="bkProcess" title="Queue a processing run on the local worker">Process</button>
    <span class="time" id="bkStatus">connecting…</span>`;
  const toolbar = document.querySelector('.controls');
  toolbar.after(bar);
  const status = (text) => { document.getElementById('bkStatus').textContent = text; };

  let runs = [];
  let videos = [];
  async function refresh(selectId) {
    [runs, videos] = await Promise.all([json('runs?status=complete').then((d) => d.runs), json('videos').then((d) => d.videos)]);
    const byId = Object.fromEntries(videos.map((v) => [v.id, v]));
    const runSelect = document.getElementById('bkRuns');
    runSelect.innerHTML = runs.length ? '' : '<option value="">no completed runs yet</option>';
    for (const r of runs) {
      const v = byId[r.video_id];
      const end = r.duration_s ? r.start_s + r.duration_s : v ? v.duration_s : null;
      const label = `${v ? v.name : 'video ' + r.video_id} · ${r.start_s}–${end != null ? end.toFixed(0) : '?'} s · ${r.preset} · ${r.id.slice(0, 8)}`;
      runSelect.append(Object.assign(document.createElement('option'), { value: r.id, textContent: label }));
    }
    if (selectId) runSelect.value = selectId;
    const videoSelect = document.getElementById('bkVideo');
    videoSelect.innerHTML = videos.length ? '' : '<option value="">no registered videos</option>';
    for (const v of videos) videoSelect.append(Object.assign(document.createElement('option'), { value: v.id, textContent: `${v.name} (${v.duration_s.toFixed(0)} s)` }));
  }

  async function loadRun(id) {
    const run = await json(`runs/${id}`);
    status(`loading run ${id.slice(0, 8)}…`);
    setPlaying(false);
    const bytes = await (await api(`runs/${id}/artifacts/landmarks.jsonl`)).arrayBuffer();
    const checksum = await landmarksSha256(bytes);
    const text = new TextDecoder().decode(bytes);
    const { out, bad, rule } = parseJsonl(text);
    if (!out.length) throw new Error('the run has no frame records');
    loadFrames(out, { synthetic: false, clipId: `${run.video.name} · ${run.preset} · run ${id.slice(0, 8)}` });
    S.landmarksSha256 = checksum;
    const messages = [];
    if (bad) messages.push(`${bad} lines skipped`);
    if (rule) messages.push(`${rule} predicted/lost hands carried 3D and are shown as 2D only`);
    // Side votes, then the lift summary before its arrays (the viewer needs the lens first).
    const extras = [];
    if (run.artifacts?.identity) extras.push([run.artifacts.identity, run.artifacts.identity]);
    if (run.artifacts?.lift) extras.push([run.artifacts.lift.summary, run.artifacts.lift.summary],
      [run.artifacts.lift.arrays, run.artifacts.lift.arrays]);
    for (const [artifact, name] of extras) {
      try { messages.push(`${name}: ${await addResultFile(await fileFrom(`runs/${id}/artifacts/${artifact}`, name))}`); }
      catch (error) { messages.push(`${name}: not loaded (${error.message})`); }
    }
    afterResults();
    const video = document.getElementById('video');
    if (video.src && video.src.startsWith('blob:')) URL.revokeObjectURL(video.src);
    if (run.proxy) {
      S.videoOffset = run.proxy.time_offset_s;
      video.src = withToken(`/api/runs/${id}/proxy.mp4`);
    } else {
      S.videoOffset = 0;
      video.removeAttribute('src'); video.load();
    }
    S.video = video;
    video.addEventListener('loadeddata', () => { seek(S.t); S.dirty = true; }, { once: true });
    document.getElementById('videoBadge').textContent = run.proxy
      ? `Proxy video from the local backend (${run.proxy.frames} selected frames)` : 'No frame-exact proxy is available for this run';
    document.getElementById('footer').textContent =
      `Loaded ${out.length} frames of run ${id.slice(0, 8)} (${run.preset}) from the local backend. Nothing leaves this machine. ` +
      'Coverage counts frames with a tracked wearer hand; that is coverage, not accuracy. Camera-space 3D uses an ASSUMED lens.';
    toast(messages.join(' · ') || 'Run loaded.');
    status(`run ${id.slice(0, 8)} loaded`);
  }

  async function processVideo() {
    const videoId = Number(document.getElementById('bkVideo').value);
    if (!videoId) { toast('Register a video first (POST /api/videos with a path under the allowed folder).'); return; }
    const body = { video_id: videoId, preset: document.getElementById('bkPreset').value,
      start_s: Number(document.getElementById('bkStart').value), duration_s: Number(document.getElementById('bkDur').value) };
    const run = await json('runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    status(`run ${run.id.slice(0, 8)} queued`);
    const queuedSince = Date.now();
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const current = await json(`runs/${run.id}`);
      const waiting = current.status === 'queued' && Date.now() - queuedSince > 10000
        ? ' (still queued: is the worker running? manage.py egohand_worker)' : '';
      status(`run ${run.id.slice(0, 8)}: ${current.stage} ${(current.progress * 100).toFixed(0)}%${waiting}`);
      if (current.status === 'complete') { await refresh(run.id); await loadRun(run.id); return; }
      if (['failed', 'cancelled'].includes(current.status)) { toast(`Run ${current.status}: ${current.error || ''}`); return; }
    }
  }

  const guard = (fn) => async (...args) => {
    try { await fn(...args); } catch (error) { status('error'); toast(`Backend: ${error.message}`); }
  };
  document.getElementById('bkLoad').addEventListener('click', guard(async () => {
    const id = document.getElementById('bkRuns').value;
    if (id) await loadRun(id); else toast('No completed run selected.');
  }));
  document.getElementById('bkRefresh').addEventListener('click', guard(() => refresh()));
  document.getElementById('bkProcess').addEventListener('click', guard(processVideo));
  // Loading a local video file must not keep the backend proxy's offset.
  document.getElementById('fileVideo').addEventListener('change', () => { S.videoOffset = 0; });

  guard(async () => {
    const health = await json('health');
    await refresh();
    status(`connected · ${runs.length} run(s)${health.auth_required && !token ? ' · token required (?token=…)' : ''}`);
  })();
})();
