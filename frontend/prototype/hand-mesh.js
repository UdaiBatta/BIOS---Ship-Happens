/* EgoHand Twin: an anatomically shaped low-poly hand surface generated from the 21 lifted 3D joints.
 *
 * What it is: a procedural skin placed exactly on the camera-space joints the pipeline lifted
 * (lift_*.npz):
 *  - finger segments: 8-sided tubes that taper towards the tip, narrow slightly between joints
 *    (so knuckles read as bulges) and close with rounded caps; fingertips end at the tip landmark;
 *  - thumb: its own thicker segments from the carpometacarpal joint, following the thumb joints;
 *  - palm: a domed slab (thicker in the middle, thinner at the edges) whose 10-point contour has a
 *    thenar bulge on the thumb side, a web between thumb and index finger, and a hypothenar edge.
 * What it is NOT: a fitted hand-shape model (MANO / WiLoR / HaMeR). Thickness and palm shape are
 * typical adult proportions scaled by the hand's measured palm length (one scale per track, so the
 * hand does not change size from frame to frame). Nothing about this surface is observed beyond the
 * joints, and it inherits the joints' depth caveats (assumed lens, unvalidated depth).
 * Left and right hands differ because the surface follows each hand's own joints (thumb side,
 * palm normal); there is no mirrored template.
 *
 * Topology is fixed (same vertex count and faces for every hand and frame): only vertex positions
 * change per frame. Every part is a closed surface wound outward (checked by tests for left and right
 * hands), so the viewer's back-face culling and Lambert shading work.
 * Budget: 1,872 triangles and 970 vertices per hand.
 * Works in the browser (window.EgoHandMesh) and in Node (module.exports) for tests.
 */
(function (root) {
  'use strict';
  const SIDES = 8;
  const PALM_LENGTH_M = 0.09;                        // typical wrist -> middle-finger knuckle length
  const PALM_THICKNESS_M = 0.026;
  // [from joint, to joint, radius at start (m), radius at end (m), ends at a fingertip]
  const BONES = [
    [0, 1, 0.018, 0.0135, false], [1, 2, 0.013, 0.0115, false], [2, 3, 0.011, 0.0098, false], [3, 4, 0.0098, 0.0082, true],
    [5, 6, 0.0098, 0.009, false], [6, 7, 0.009, 0.008, false], [7, 8, 0.008, 0.0068, true],
    [9, 10, 0.01, 0.0093, false], [10, 11, 0.0093, 0.0082, false], [11, 12, 0.0082, 0.007, true],
    [13, 14, 0.0094, 0.0087, false], [14, 15, 0.0087, 0.0077, false], [15, 16, 0.0077, 0.0066, true],
    [17, 18, 0.0084, 0.0076, false], [18, 19, 0.0076, 0.0068, false], [19, 20, 0.0068, 0.006, true],
  ];
  // Ring profile along a segment: start cap (2 latitudes), joint, waist, joint, end cap (2 latitudes).
  const CAP = [-62, -28];                            // degrees, start cap; the end cap mirrors it
  const WAIST = 0.9;                                 // mid-segment radius relative to the joints
  const RINGS = 2 * CAP.length + 3;
  const SEG_VERTS = 2 + RINGS * SIDES;
  const PALM_N = 10;                                 // contour points
  const PALM_VERTS = 4 * PALM_N + 2;                 // outer/inner rings, top/bottom, two centres
  const VERTEX_COUNT = BONES.length * SEG_VERTS + PALM_VERTS;

  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
  const lerp = (a, b, t) => add(a, mul(sub(b, a), t));
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const len = (a) => Math.sqrt(dot(a, a));
  const unit = (a, fallback) => { const l = len(a); return l > 1e-9 ? mul(a, 1 / l) : fallback; };

  // ---- fixed topology ----
  function segmentFaces(base) {
    const f = [], ring = (r, s) => base + 1 + r * SIDES + (s % SIDES), south = base, north = base + 1 + RINGS * SIDES;
    for (let s = 0; s < SIDES; s++) f.push([south, ring(0, s + 1), ring(0, s)]);
    for (let r = 0; r < RINGS - 1; r++) for (let s = 0; s < SIDES; s++) {
      f.push([ring(r, s), ring(r, s + 1), ring(r + 1, s + 1)], [ring(r, s), ring(r + 1, s + 1), ring(r + 1, s)]);
    }
    for (let s = 0; s < SIDES; s++) f.push([north, ring(RINGS - 1, s), ring(RINGS - 1, s + 1)]);
    return f;
  }
  function palmFaces(base) {
    const n = PALM_N, w = (i) => i % n;
    const OT = (i) => base + w(i), IT = (i) => base + n + w(i), OB = (i) => base + 2 * n + w(i), IB = (i) => base + 3 * n + w(i);
    const CT = base + 4 * n, CB = CT + 1, f = [];
    for (let i = 0; i < n; i++) {
      f.push([CT, IT(i), IT(i + 1)], [IT(i), OT(i), OT(i + 1)], [IT(i), OT(i + 1), IT(i + 1)]);       // top dome
      f.push([CB, IB(i + 1), IB(i)], [IB(i), OB(i + 1), OB(i)], [IB(i), IB(i + 1), OB(i + 1)]);       // bottom dome
      f.push([OT(i), OB(i), OB(i + 1)], [OT(i), OB(i + 1), OT(i + 1)]);                              // rim
    }
    return f;
  }
  const PARTS = [];                                  // [first vertex, vertex count, faces]
  BONES.forEach((_, b) => { const base = b * SEG_VERTS; PARTS.push([base, SEG_VERTS, segmentFaces(base)]); });
  PARTS.push([BONES.length * SEG_VERTS, PALM_VERTS, palmFaces(BONES.length * SEG_VERTS)]);
  // Every part is wound outward by construction (right-handed ring frames; the palm contour turns the
  // same way around its own normal for left and right hands), so one face list fits every hand.
  const FACES = Uint32Array.from(PARTS.flatMap(([, , partFaces]) => partFaces).flat());

  // ---- geometry ----
  function segment(out, offset, a, b, r0, r1, tip) {
    let axis = sub(b, a);
    const length = len(axis);
    axis = unit(axis, [0, 0, 1]);
    if (tip && length > r1) b = sub(b, mul(axis, r1));          // the fingertip surface ends at the tip landmark
    const helper = Math.abs(axis[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
    const u = unit(cross(axis, helper), [1, 0, 0]), v = cross(axis, u);
    let k = offset;
    const put = (p) => { out[3 * k] = p[0]; out[3 * k + 1] = p[1]; out[3 * k + 2] = p[2]; k++; };
    const ring = (c, rr) => {
      for (let s = 0; s < SIDES; s++) {
        const t = 2 * Math.PI * (s + 0.5) / SIDES;
        put(add(c, add(mul(u, rr * Math.cos(t)), mul(v, rr * Math.sin(t)))));
      }
    };
    put(sub(a, mul(axis, r0)));                                   // start pole
    for (const d of CAP) { const p = d * Math.PI / 180; ring(add(a, mul(axis, r0 * Math.sin(p))), r0 * Math.cos(p)); }
    ring(a, r0);                                                  // joint (knuckle)
    ring(lerp(a, b, 0.5), WAIST * (r0 + r1) / 2);                 // waist between joints
    ring(b, r1);                                                  // next joint
    for (const d of [...CAP].reverse()) { const p = -d * Math.PI / 180; ring(add(b, mul(axis, r1 * Math.sin(p))), r1 * Math.cos(p)); }
    put(add(b, mul(axis, r1)));                                   // end pole
  }
  function palm(out, offset, j, scale) {
    const across = sub(j[5], j[17]);
    const centre0 = mul([j[0], j[5], j[9], j[13], j[17]].reduce(add, [0, 0, 0]), 1 / 5);
    const bulge = (p, k) => add(p, mul(sub(p, centre0), k));
    // Contour, turning from the thumb side of the wrist round to the little-finger side.
    const contour = [
      add(j[0], mul(across, 0.32)),                               // wrist, thumb side
      bulge(lerp(j[0], j[1], 0.5), 0.22),                         // thenar eminence
      j[1],                                                       // thumb CMC
      lerp(lerp(j[1], j[5], 0.5), j[2], 0.4),                     // thumb-index web
      j[5], j[9], j[13], j[17],                                   // knuckles
      bulge(lerp(j[17], j[0], 0.5), 0.12),                        // hypothenar edge
      add(j[0], mul(across, -0.32)),                              // wrist, little-finger side
    ];
    const centre = mul(contour.reduce(add, [0, 0, 0]), 1 / PALM_N);
    const normal = unit(cross(sub(j[5], j[0]), sub(j[17], j[0])), [0, 0, 1]);
    const T = PALM_THICKNESS_M * scale;
    const at = (p, h) => add(p, mul(normal, h));
    let k = offset;
    const put = (p) => { out[3 * k] = p[0]; out[3 * k + 1] = p[1]; out[3 * k + 2] = p[2]; k++; };
    for (const p of contour) put(at(p, 0.3 * T));                            // outer, top (thin edge)
    for (const p of contour) put(at(lerp(centre, p, 0.55), 0.5 * T));        // inner, top (dome)
    for (const p of contour) put(at(p, -0.3 * T));                           // outer, bottom
    for (const p of contour) put(at(lerp(centre, p, 0.55), -0.5 * T));       // inner, bottom
    put(at(centre, 0.56 * T)); put(at(centre, -0.56 * T));
  }
  function signedVolume(v, faces) {
    let vol = 0;
    for (const [a, b, c] of faces) {
      const A = [v[3 * a], v[3 * a + 1], v[3 * a + 2]], B = [v[3 * b], v[3 * b + 1], v[3 * b + 2]], C = [v[3 * c], v[3 * c + 1], v[3 * c + 2]];
      vol += dot(A, cross(B, C));
    }
    return vol / 6;
  }
  const validJoints = (joints) => Array.isArray(joints) && joints.length === 21 &&
    joints.every((p) => p && p.length >= 3 && [0, 1, 2].every((i) => Number.isFinite(p[i])));
  const palmScale = (joints) => Math.min(1.5, Math.max(0.6, len(sub(joints[9], joints[0])) / PALM_LENGTH_M));

  /** Vertices (Float32Array, VERTEX_COUNT*3, camera metres) for one hand; null if joints are invalid.
   *  ``scale``: hand size relative to a typical adult hand; defaults to this frame's palm length. */
  function build(joints, scale) {
    if (!validJoints(joints)) return null;
    const s = scale ?? palmScale(joints);
    const v = new Float32Array(VERTEX_COUNT * 3);
    BONES.forEach(([i, j, r0, r1, tip], b) => segment(v, b * SEG_VERTS, joints[i], joints[j], r0 * s, r1 * s, tip));
    palm(v, BONES.length * SEG_VERTS, joints, s);
    return v;
  }

  // Bone-length calibration. PARENT[i] is joint i's parent in the 21-joint hand (MediaPipe order).
  const PARENT = [-1, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19];
  const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  /** Per-track bone lengths: the median of each bone over the track's frames (robust to bad frames). */
  function boneLengths(jointSets) {
    const L = new Array(21).fill(0);
    for (let i = 1; i < 21; i++) L[i] = median(jointSets.map((j) => len(sub(j[i], j[PARENT[i]]))));
    return L;
  }
  /** Joints with calibrated lengths: each bone keeps this frame's DIRECTION, gets the track's median LENGTH. */
  function calibrate(joints, L) {
    const out = new Array(21); out[0] = joints[0].slice(0, 3);
    for (let i = 1; i < 21; i++) {
      const p = PARENT[i], dir = unit(sub(joints[i], joints[p]), [0, 0, 1]);
      out[i] = add(out[p], mul(dir, L[i]));
    }
    return out;
  }

  /** Mesh set in the viewer's format: { faces, nv, records: [{ frame_index, track_id, v }] }.
   *  Per track: one size (median palm length) and calibrated bone lengths (median per bone), so a
   *  hand keeps its proportions and finger lengths from frame to frame. The skeleton overlay still
   *  shows the estimated joints; only this visual surface is calibrated. */
  function forHands(hands) {
    const byTrack = new Map();
    for (const h of hands) if (validJoints(h.joints)) {
      if (!byTrack.has(h.track_id)) byTrack.set(h.track_id, []);
      byTrack.get(h.track_id).push(h.joints);
    }
    const lengths = new Map([...byTrack].map(([k, sets]) => [k, boneLengths(sets)]));
    const scales = new Map([...byTrack].map(([k, sets]) => [k, median(sets.map(palmScale))]));
    const records = [];
    for (const { frame_index, track_id, joints } of hands) {
      if (!validJoints(joints)) continue;
      const v = build(calibrate(joints, lengths.get(track_id)), scales.get(track_id));
      if (v) records.push({ frame_index, track_id, ok: true, v, gap_m: null });
    }
    return { backend: 'joint-skinned', faces: FACES, nv: VERTEX_COUNT, records };
  }

  /** Signed volume of each closed part (all > 0 when wound outward). For tests. */
  function partVolumes(v) {
    return PARTS.map(([, , partFaces]) => signedVolume(v, partFaces));
  }

  const api = { build, forHands, partVolumes, calibrate, boneLengths, FACES, VERTEX_COUNT, BONES };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EgoHandMesh = api;
})(typeof window !== 'undefined' ? window : globalThis);
