/* EgoHand Twin: a solid hand surface generated from the 21 lifted 3D joints.
 *
 * What it is: rounded, tapered capsules along the finger bones plus a thick palm slab,
 * placed exactly on the camera-space joints the pipeline lifted (lift_*.npz). It makes the
 * 3D view read as a hand instead of a stick figure.
 * What it is NOT: a fitted hand-shape model (MANO / WiLoR / HaMeR). Finger thickness and
 * palm thickness are typical adult sizes scaled by the measured palm length; nothing about
 * this surface is observed beyond the joints, and it inherits the joints' depth caveats
 * (assumed lens, unvalidated depth).
 *
 * The topology is fixed (same vertex count and faces for every hand), and every part is a
 * closed surface wound outward, so the viewer's back-face culling and shading work.
 * Works in the browser (window.EgoHandMesh) and in Node (module.exports) for tests.
 */
(function (root) {
  'use strict';
  const SIDES = 6;                                   // low poly: vertices around each capsule ring
  const LATITUDES = [-50, 0];                        // low poly: start-cap rings (degrees); end cap mirrors them
  const PALM_LENGTH_M = 0.09;                        // typical wrist -> middle-finger knuckle length
  const PALM_THICKNESS_M = 0.024;
  // [from joint, to joint, radius at start (m), radius at end (m), ends at a fingertip]
  const BONES = [
    [0, 1, 0.017, 0.013, false], [1, 2, 0.0125, 0.011, false], [2, 3, 0.0105, 0.0095, false], [3, 4, 0.0095, 0.008, true],
    [5, 6, 0.0095, 0.0088, false], [6, 7, 0.0088, 0.0078, false], [7, 8, 0.0078, 0.0068, true],
    [9, 10, 0.0098, 0.009, false], [10, 11, 0.009, 0.008, false], [11, 12, 0.008, 0.007, true],
    [13, 14, 0.0092, 0.0085, false], [14, 15, 0.0085, 0.0075, false], [15, 16, 0.0075, 0.0066, true],
    [17, 18, 0.0082, 0.0075, false], [18, 19, 0.0075, 0.0067, false], [19, 20, 0.0067, 0.006, true],
  ];
  const RINGS = LATITUDES.length * 2;
  const CAPSULE_VERTS = 2 + RINGS * SIDES;
  const PALM_POINTS = 7;                             // wrist (thumb side), 1, 5, 9, 13, 17, wrist (little-finger side)
  const PALM_VERTS = 2 * PALM_POINTS + 2;
  const VERTEX_COUNT = BONES.length * CAPSULE_VERTS + PALM_VERTS;

  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const len = (a) => Math.sqrt(dot(a, a));
  const unit = (a, fallback) => { const l = len(a); return l > 1e-9 ? mul(a, 1 / l) : fallback; };

  // ---- fixed topology (local indices per part, then offset) ----
  function capsuleFaces(base) {
    const f = [], ring = (r, s) => base + 1 + r * SIDES + (s % SIDES), south = base, north = base + 1 + RINGS * SIDES;
    for (let s = 0; s < SIDES; s++) f.push([south, ring(0, s + 1), ring(0, s)]);
    for (let r = 0; r < RINGS - 1; r++) for (let s = 0; s < SIDES; s++) {
      f.push([ring(r, s), ring(r, s + 1), ring(r + 1, s + 1)], [ring(r, s), ring(r + 1, s + 1), ring(r + 1, s)]);
    }
    for (let s = 0; s < SIDES; s++) f.push([north, ring(RINGS - 1, s), ring(RINGS - 1, s + 1)]);
    return f;
  }
  function palmFaces(base) {
    const f = [], top = (i) => base + (i % PALM_POINTS), bottom = (i) => base + PALM_POINTS + (i % PALM_POINTS);
    const topC = base + 2 * PALM_POINTS, bottomC = topC + 1;
    for (let i = 0; i < PALM_POINTS; i++) {
      f.push([topC, top(i), top(i + 1)], [bottomC, bottom(i + 1), bottom(i)]);
      f.push([top(i), bottom(i), bottom(i + 1)], [top(i), bottom(i + 1), top(i + 1)]);
    }
    return f;
  }
  const PARTS = [];                                  // [first vertex, vertex count, faces]
  BONES.forEach((_, b) => { const base = b * CAPSULE_VERTS; PARTS.push([base, CAPSULE_VERTS, capsuleFaces(base)]); });
  PARTS.push([BONES.length * CAPSULE_VERTS, PALM_VERTS, palmFaces(BONES.length * CAPSULE_VERTS)]);

  // ---- geometry ----
  function capsule(out, offset, a, b, r0, r1, tip) {
    let axis = sub(b, a);
    const length = len(axis);
    axis = unit(axis, [0, 0, 1]);
    if (tip && length > r1) b = sub(b, mul(axis, r1));   // the fingertip surface ends at the tip landmark
    const helper = Math.abs(axis[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
    const u = unit(cross(axis, helper), [1, 0, 0]), v = cross(axis, u);
    let k = offset;
    const put = (p) => { out[3 * k] = p[0]; out[3 * k + 1] = p[1]; out[3 * k + 2] = p[2]; k++; };
    put(sub(a, mul(axis, r0)));                                      // south pole
    const rings = [...LATITUDES.map((d) => [a, r0, d]), ...LATITUDES.map((d) => [b, r1, -d]).reverse()];
    for (const [centre, r, deg] of rings) {
      const phi = deg * Math.PI / 180, c = add(centre, mul(axis, r * Math.sin(phi))), rr = r * Math.cos(phi);
      for (let s = 0; s < SIDES; s++) {
        const t = 2 * Math.PI * s / SIDES;
        put(add(c, add(mul(u, rr * Math.cos(t)), mul(v, rr * Math.sin(t)))));
      }
    }
    put(add(b, mul(axis, r1)));                                      // north pole
  }
  function palm(out, offset, j, scale) {
    const across = sub(j[5], j[17]);
    const outline = [add(j[0], mul(across, 0.3)), j[1], j[5], j[9], j[13], j[17], add(j[0], mul(across, -0.3))];
    const centre = mul(outline.reduce(add, [0, 0, 0]), 1 / PALM_POINTS);
    const normal = unit(cross(sub(j[5], j[0]), sub(j[17], j[0])), [0, 0, 1]);
    const half = mul(normal, PALM_THICKNESS_M * scale / 2);
    let k = offset;
    const put = (p) => { out[3 * k] = p[0]; out[3 * k + 1] = p[1]; out[3 * k + 2] = p[2]; k++; };
    for (const p of outline) put(add(p, half));
    for (const p of outline) put(sub(p, half));
    put(add(centre, half)); put(sub(centre, half));
  }
  function signedVolume(v, faces) {
    let vol = 0;
    for (const [a, b, c] of faces) {
      const A = [v[3 * a], v[3 * a + 1], v[3 * a + 2]], B = [v[3 * b], v[3 * b + 1], v[3 * b + 2]], C = [v[3 * c], v[3 * c + 1], v[3 * c + 2]];
      vol += dot(A, cross(B, C));
    }
    return vol / 6;
  }

  // Every part is wound outward by construction: each capsule's ring frame (u, v, axis) is
  // right-handed, and the palm outline turns the same way around its own normal for left and
  // right hands, so one shared face list fits every hand (tests check left and right hands).
  const FACES = Uint32Array.from(PARTS.flatMap(([, , partFaces]) => partFaces).flat());

  /** Vertices (Float32Array, VERTEX_COUNT*3, camera metres) for one hand; null if joints are invalid. */
  function build(joints) {
    if (!Array.isArray(joints) || joints.length !== 21 || !joints.every((p) => p && p.length >= 3 && [0, 1, 2].every((i) => Number.isFinite(p[i])))) return null;
    const scale = Math.min(1.5, Math.max(0.6, len(sub(joints[9], joints[0])) / PALM_LENGTH_M));
    const v = new Float32Array(VERTEX_COUNT * 3);
    BONES.forEach(([i, j, r0, r1, tip], b) => capsule(v, b * CAPSULE_VERTS, joints[i], joints[j], r0 * scale, r1 * scale, tip));
    palm(v, BONES.length * CAPSULE_VERTS, joints, scale);
    return v;
  }

  /** Mesh set in the viewer's format: { faces, nv, records: [{ frame_index, track_id, v }] }. */
  function forHands(hands) {
    const records = [];
    for (const { frame_index, track_id, joints } of hands) {
      const v = build(joints);
      if (v) records.push({ frame_index, track_id, ok: true, v, gap_m: null });
    }
    return { backend: 'skeleton-skinned', faces: FACES, nv: VERTEX_COUNT, records };
  }

  /** Signed volume of each closed part (all > 0 when wound outward). For tests. */
  function partVolumes(v) {
    return PARTS.map(([, , partFaces]) => signedVolume(v, partFaces));
  }

  const api = { build, forHands, partVolumes, FACES, VERTEX_COUNT, BONES };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EgoHandMesh = api;
})(typeof window !== 'undefined' ? window : globalThis);
