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
    <span class="note" title="Local EgoHand Twin backend on this machine">Backend video:</span>
    <select class="btn" id="bkVideo" aria-label="Source video" style="max-width: 20rem" title="Source video. The run list shows only this video's runs; Process uses it."></select>
    <button class="btn" id="bkRefresh" title="Find videos added to the media folder and refresh the lists">↻ scan</button>
    <label class="btn" title="Upload a video into the backend's private upload folder">Upload…<input type="file" id="bkUpload" accept=".mp4,.mov,.mkv,.avi" hidden></label>
    <span class="sep"></span>
    <select class="btn" id="bkRuns" aria-label="Completed runs of this video" style="max-width: 20rem"></select>
    <button class="btn" id="bkLoad" title="Load landmarks, side votes, experimental lift and the proxy video of this run">Load run</button>
    <span class="sep"></span>
    <select class="btn" id="bkPreset" aria-label="Preset" title="recall: thresholds 0.3 + centre-crop rescue (chosen on dev, provisional labels). accurate: recall + a reverse-time pass, finds more hands, about 2x slower. baseline: MediaPipe defaults.">
      <option value="recall" selected>recall</option><option value="accurate">accurate (slower)</option><option value="baseline">baseline</option></select>
    <label class="note">start <input id="bkStart" type="number" value="0" min="0" step="1" style="width: 4.5em"> s</label>
    <label class="note">length <input id="bkDur" type="number" value="30" min="1" step="1" style="width: 4.5em"> s</label>
    <button class="btn" id="bkProcess" title="Queue a processing run on the local worker">Process</button>
    <label class="note" title="Track number, detection path and 3D source on each hand; turn off for presentation"><input type="checkbox" id="bkDebug" checked> debug labels</label>
    <span class="time" id="bkStatus">connecting…</span>`;
  const toolbar = document.querySelector('.controls');
  toolbar.after(bar);
  const status = (text) => { document.getElementById('bkStatus').textContent = text; };

  let runs = [];
  let videos = [];
  // The preset list comes from the RUNNING server, so the menu never offers a preset an
  // out-of-date server would reject.
  async function loadPresets() {
    const data = await json('presets');
    const select = document.getElementById('bkPreset');
    const current = select.value;
    select.innerHTML = '';
    for (const [name, info] of Object.entries(data.presets)) {
      const label = name === 'accurate' ? 'accurate (slower)' : name === 'hybrid' ? 'hybrid (experimental)' : name;
      select.append(Object.assign(document.createElement('option'), { value: name, textContent: label, title: `${info.description}. ${info.measured}` }));
    }
    select.value = data.presets[current] ? current : (data.default || 'recall');
    return Object.keys(data.presets);
  }
  // One source of truth: the selected VIDEO. The run list shows only that video's runs, so "Load run"
  // can no longer load a run of another video than the one shown (the reported mismatch).
  function fillRuns(selectId) {
    const videoId = Number(document.getElementById('bkVideo').value);
    const video = videos.find((v) => v.id === videoId);
    const mine = runs.filter((r) => r.video_id === videoId);
    const runSelect = document.getElementById('bkRuns');
    runSelect.innerHTML = mine.length ? '' : '<option value="">no completed runs for this video: Process it</option>';
    for (const r of mine) {
      const end = r.duration_s ? Math.min(r.start_s + r.duration_s, video ? video.duration_s : Infinity) : video ? video.duration_s : null;
      const label = `${r.start_s}–${end != null ? end.toFixed(0) : '?'} s · ${r.preset} · ${r.id.slice(0, 8)}`;
      runSelect.append(Object.assign(document.createElement('option'), { value: r.id, textContent: label }));
    }
    if (selectId && mine.some((r) => r.id === selectId)) runSelect.value = selectId;
  }
  async function refresh(selectId, videoId) {
    [runs, videos] = await Promise.all([json('runs?status=complete').then((d) => d.runs), json('videos').then((d) => d.videos)]);
    const videoSelect = document.getElementById('bkVideo');
    const keep = videoId ?? (runs.find((r) => r.id === selectId) || {}).video_id ?? Number(videoSelect.value);
    videoSelect.innerHTML = videos.length ? '' : '<option value="">no registered videos: add files to media/ and scan</option>';
    for (const v of videos) {
      videoSelect.append(Object.assign(document.createElement('option'), { value: v.id,
        textContent: `${v.name} (${v.duration_s.toFixed(0)} s source)${v.available === false ? ' · file missing' : ''}` }));
    }
    if (videos.some((v) => v.id === keep)) videoSelect.value = String(keep);
    fillRuns(selectId);
  }
  async function scan() {
    status('scanning media folders…');
    const report = await json('videos/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await refresh(undefined, report.registered.length ? report.registered[0].id : undefined);
    const failed = report.failed.map((f) => `${f.name}: ${f.error}`).join('; ');
    status(`${videos.length} video(s) · ${report.registered.length} new`);
    if (report.registered.length || failed) toast(`Scan: ${report.registered.length} new video(s)` + (failed ? ` · not registered: ${failed}` : ''));
  }
  function upload(file) {
    return new Promise((resolve, reject) => {
      const form = new FormData(); form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/videos/upload');
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) status(`uploading ${file.name}: ${(100 * e.loaded / e.total).toFixed(0)}%`); };
      xhr.onload = () => {
        let data = {}; try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
        if (xhr.status === 201) resolve(data); else reject(new Error(data.error || `upload failed (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error('upload failed (network)'));
      xhr.send(form);
    });
  }

  async function loadRun(id) {
    const run = await json(`runs/${id}`);
    status(`loading run ${id.slice(0, 8)}…`);
    if (Number(document.getElementById('bkVideo').value) !== run.video_id) {
      document.getElementById('bkVideo').value = String(run.video_id); fillRuns(id);
    }
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
    if (run.artifacts?.lift) {
      try { messages.push(liftReport(await json(`runs/${id}/artifacts/${run.artifacts.lift.summary}`))); }
      catch { /* the summary was already reported above */ }
    }
    // Solid hands: a surface generated from the lifted joints (not a fitted hand model).
    if (!window.EgoHandMesh) {
      messages.push('3D hand surfaces unavailable: the server is running older code. Close the worker window, stop the server (Ctrl+C) and start scripts/run_local again');
    } else if (run.artifacts?.lift) {
      try {
        messages.push(`hand surfaces: ${addGeneratedMeshes()}`);
        document.querySelector('#segMode [data-v="ours"]')?.click();   // meshes are drawn in camera space
      } catch (error) { messages.push(`hand surfaces: not built (${error.message})`); }
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

  function liftReport(summary) {
    const rejected = Object.entries(summary.rejections || {}).filter(([reason]) => reason !== 'ok')
      .sort((a, b) => b[1] - a[1]).map(([reason, n]) => `${reason.replaceAll('_', ' ')} ${n}`);
    return `camera-space 3D for ${summary.lifted} of ${summary.observed_hands} observed hands` +
      (rejected.length ? ` (rejected: ${rejected.join(', ')})` : '');
  }

  function addGeneratedMeshes() {
    const hands = [];
    for (const f of S.frames) for (const h of f.hands) {
      if (HAS_3D.has(h.state) && h.cam_xyz_m) hands.push({ frame_index: f.frame_index, track_id: h.track_id, joints: h.cam_xyz_m });
    }
    if (!hands.length) throw new Error('no observed hand has camera-space 3D');
    const message = applyMesh(EgoHandMesh.forHands(hands), 'lifted joints');
    S.mesh.label = 'hand surface generated from the 21 lifted joints (typical finger and palm thickness, scaled to the measured palm; not a fitted hand-shape model)';
    S.mesh.licence = 'same assumed-lens depth caveats as the camera-space 3D';
    return message;
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
  document.getElementById('bkRefresh').addEventListener('click', guard(scan));
  document.getElementById('bkVideo').addEventListener('change', () => fillRuns());
  document.getElementById('bkUpload').addEventListener('change', guard(async (e) => {
    const file = e.target.files[0]; e.target.value = '';
    if (!file) return;
    const video = await upload(file);
    await refresh(undefined, video.id);
    status(`uploaded ${video.name}`); toast(`Uploaded ${file.name} (${video.duration_s.toFixed(0)} s). Choose a segment and Process.`);
  }));
  document.getElementById('bkProcess').addEventListener('click', guard(processVideo));
  document.getElementById('bkDebug').addEventListener('change', (e) => { S.debugLabels = e.target.checked; S.dirty = true; });
  // Loading a local video file must not keep the backend proxy's offset.
  document.getElementById('fileVideo').addEventListener('change', () => { S.videoOffset = 0; });

  guard(async () => {
    const health = await json('health');
    const presets = await loadPresets();
    await refresh();
    try { await scan(); } catch (error) { toast(`Scan failed: ${error.message}`); }   // pick up new files
    if (!presets.includes('accurate')) toast('The server is running older code (no "accurate" preset). Stop it and the worker, then start scripts/run_local again.');
    status(`connected · ${runs.length} run(s)${health.auth_required && !token ? ' · token required (?token=…)' : ''}`);
  })();
})();
