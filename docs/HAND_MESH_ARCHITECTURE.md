# Hand mesh architecture

**What it is:** a procedural low-poly skin on the 21 lifted joints (`frontend/prototype/hand-mesh.js`), labelled in the viewer as *joint-skinned, not a fitted hand-shape model*. No MANO, WiLoR or HaMeR is integrated (see [EXPERIMENTAL_3D_STATUS](EXPERIMENTAL_3D_STATUS.md)).

**Topology (fixed for every hand and frame):** 970 vertices, 1,872 triangles per hand.
- **16 finger segments**, 8-sided: start cap (2 rings), joint, waist (0.9×, so knuckles read as bulges), joint, end cap (2 rings). Segments taper towards the tip, and fingertips end on the tip landmark.
- **Thumb:** its own thicker segments from the carpometacarpal joint (0 → 1 → 2 → 3 → 4), following the thumb joints rather than running parallel to the fingers.
- **Palm:** a domed slab (thicker in the middle, thinner at the rim) with a 10-point contour: wrist (thumb side), thenar bulge, thumb CMC, thumb–index web, four knuckles, hypothenar edge, wrist (little-finger side).
- **Normals:** every part is a closed surface wound outward. Checked on 80 real and mirrored hands and in `tests/test_hand_mesh.py`, so back-face culling and Lambert shading are correct.

**Stability per track:**
- one size (median palm length);
- **bone-length calibration:** each bone's length is the median over the track's frames, and each frame keeps its own bone directions (test: constant fingertip-bone length, directions unchanged).

Left and right hands differ because the surface follows each hand's own joints; there is no mirrored template.

**Rendering:** canvas 2D painter's algorithm, about 1.6 ms per frame for two hands (software rendering). Faces are shared and only vertex positions change. Controls: skeleton / mesh / both, wireframe, opacity, camera reset.

**Not done:** quaternion joint rotations and true skinning weights. The mesh is rebuilt from calibrated joint positions each frame.
