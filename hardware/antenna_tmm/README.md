# Rev B antenna: compact all-band CRPA on Rogers TMM3

Rev B replaces rev A's air-spaced patches (`../antenna`) with stacked patches on Rogers
**TMM3**, a ceramic-thermoset laminate (er 3.45). It still covers **all GNSS bands from
1164 to 1610 MHz**.

| | Rev A (air) | **Rev B (TMM3)** |
|---|---|---|
| Patches | 105.5 / 81.9 mm | **64.3 / 57.9 / 48.1 mm** (3-layer stack) |
| Element module | 124 x 124 mm | **96 x 96 mm** |
| Element pitch | 125 mm (0.66 lambda at L1) | **100 mm (0.53 lambda)** |
| Array plate | 395 x 485 mm | **320 x 395 mm** (34 % less area) |
| Stack height above plate | 27 mm | 29 mm |
| Tallest point (jammer bracket) | ~150 mm | ~110 mm |
| Feed | 9 mm probe + series cap | probe to a **capacitive disk** (cancels the probe inductance) |
| 90 deg hybrid | printed, 63 x 31 mm | **SMD Electro-Photonics Q3XG-1500R**, 14.2 x 8.9 mm |
| Cavity under the feed board | nylon standoffs (resonance near 1.2 GHz) | **8 brass posts + stitched ground on both layers** |
| Linear 0/60/120 deg | rotated boards (collided) | probe angle, boards axis-aligned |

## Element stack (bottom to top; slabs bonded with thin bondply, no holes through radiators)

```
 slab C   TMM3 7.62 mm   patch C 48.1 mm (parasitic)                 1559-1610 MHz
 slab B   TMM3 3.175 mm  patch B 57.9 mm (parasitic, ~1275 MHz) \
 slab A2  TMM3 0.762 mm  patch A 64.3 mm (~1190 MHz)             } coupled pair: 1164-1300 MHz
 slab A1  TMM3 8.89 mm   2 x 7 mm feed disks (circular) or 1 (linear), probes from below
 feed     RO4350B 0.762  F.Cu ground | B.Cu: probe lines, Q3XG-1500R hybrid, JP1, SMA
 8 mm brass posts (8 per module) to the 3 mm aluminium plate
```

## Boards (all pass DRC with 0 errors; fab zips in each folder)

| Folder | Board | Used for |
|---|---|---|
| `feed_circular` | RO4350B feed: hybrid + polarization jumper JP1 | 3 RHCP + 3 tilted modules |
| `feed_linear_000/060/120` | RO4350B feed, single probe at 0/60/120 deg | 3 linear modules |
| `slab_A1_circ`, `slab_A1_lin000/060/120` | TMM3 8.89 mm with feed disks | matches the feed variant |
| `slab_A2`, `slab_B`, `slab_C` | TMM3 radiator slabs | every patch module |
| `array_plate` | 320 x 395 mm plate (DXF) | |

**Polarization (JP1 is a 3-pad alternate-fit jumper, one 0603 0 ohm):**
- **RHCP:** 0 ohm on A-C, R3 = 49.9 ohm.
- **LHCP:** 0 ohm on C-B, R1 = 49.9 ohm.
- These assume the usual hybrid port order. Confirm with an axial-ratio / handedness
  test on the first unit.

## Simulated with the real geometry (`python run_hardware_array.py B`)

Satellites tracked out of 9 (power inversion / MVDR):

| Scenario | Tilted = LHCP | Tilted = RHCP |
|---|---|---|
| 6 mixed jammers | 5 / 9 | 6 / 8 |
| RHCP jammer 80 dB | 5 / 9 | **9 / 9** |
| RHCP jammer 90 dB | 2 / 5 | **9 / 9** |
| 2 RHCP jammers | 9 / 9 | 8 / 9 |

## Must be done before ordering

1. **Hybrid land pattern.** U1 is a placeholder. Replace it with the Q3XG-1500R datasheet's
   recommended layout (and port map) before fabrication.
2. **EM simulation (required).** The bandwidth estimates are marginal:
   - lower band about 8-12 % against 11.1 % needed,
   - upper band about 3.1 % against 3.2 % needed.

   Tune slab thicknesses, patch sizes, the 10 mm probe offset and the 7 mm disk diameter
   in openEMS, CST or HFSS. Thicker slabs widen the bandwidth at the cost of height.
3. **TMM3 stock thicknesses.** 8.89 / 7.62 / 3.175 / 0.762 mm: confirm with Rogers or the
   fab, and adjust to the nearest standard.
4. **Bonding.** Use a thin low-loss bondply (for example Rogers 2929 / 3001). Probe tops
   must be flush with the A1 surface.
5. **The "verify" items** in `../README.md` still apply (ZED-X20P pins, SOM pinout,
   export control).

## Renders

`render3d/array_iso.png`, `array_jammer_side.png`, `array_top.png`, `element_exploded.png`,
plus `crpa_array_revB.glb` (opens in any 3D viewer) and `crpa_array_revB.blend`.
Rebuild:

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" hardware/antenna_tmm/gen_boards.py
powershell -File hardware/tools/check_boards.ps1 hardware/antenna_tmm
powershell -File hardware/tools/export_fab.ps1 hardware/antenna_tmm
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup --python hardware/antenna_tmm/render3d/build_array_scene.py
```
