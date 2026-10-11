# polarization-crpa: 12-element polarization-diverse GNSS anti-jam array

This project studies a 12-channel GNSS CRPA (controlled reception pattern antenna)
that cancels jammers using **polarization and direction together**. It covers the
full chain:
- signal-level anti-jam simulation,
- antenna design checked with openEMS (FDTD),
- KiCad hardware for the antenna boards,
- schematics for the RF front-end, the RFSoC beamformer and the u-blox ZED-X20P receiver.

## Status (read before using anything here)

| Part | State |
|---|---|
| Anti-jam simulator (STAP, power inversion, MVDR, RF-chain mismatch and equalization) | Working, see below |
| **Antenna element rev C** (air-spaced dual-band stacked patch, 4 probes; [hardware/em](hardware/em)) | **openEMS-simulated:** +4.4 to +5.7 dBic at L5/E5/L2/G2/E6 and +7.8 to +8.1 dBic at L1/E1/B1/G1. Axial ratio 0.5-2.2 dB, except E6/B3 at 3.5 dB. |
| Full 12-element array in openEMS | Running / in progress |
| Rev C KiCad boards | Not yet updated (rev A and rev B boards are in `hardware/antenna*`) |
| Rev C active-element, front-end and DSP schematics | Pass ERC; candidate parts marked VERIFY |
| Built or measured hardware | **None.** Everything here is simulation or design data. |

Rev B (`hardware/antenna_tmm`, compact TMM3 ceramic element) was simulated and **rejected**:
its single resonance gives only about 3 % bandwidth, while the lower GNSS block needs 11 %.
The boards are kept for reference.

> **Disclaimer.** This is research and simulation work, not a validated product.
> - Pinouts, footprints and parts marked VERIFY must be checked against the datasheets.
> - The SMD hybrid land pattern is a placeholder.
> - The element must be prototyped and measured before any production.
>
> **Export control.** GNSS anti-jam / CRPA technology is dual-use and controlled in many
> jurisdictions (for example the Wassenaar Arrangement category 7, US EAR/ITAR). Anyone using,
> modifying or shipping these designs is responsible for complying with the export rules
> that apply to them.

- Hardware: [hardware/README.md](hardware/README.md)
- EM models: [hardware/em/em_element.py](hardware/em/em_element.py) (single element) and
  [hardware/em/em_array.py](hardware/em/em_array.py) (full array)
- `run_hardware_array.py` simulates the array exactly as laid out on the plate.
- To install openEMS for the EM scripts:
  1. Download `openEMS_x64_v0.37.0_msvc.zip` from github.com/thliebig/openEMS-Project.
  2. Extract it to `tools/openEMS/`.
  3. Create the Python environment: `uv venv tools/emvenv --python 3.13`.
  4. Install the bundled wheels: `uv pip install --python tools/emvenv/Scripts/python.exe --no-index --find-links tools/openEMS/openEMS/python openEMS`.

## Anti-jam simulator

A simulator for a 12-channel GNSS CRPA. It cancels jammers using **polarization
and direction together** (space-polarization-time adaptive processing, STAP).
Each run synthesizes the raw IQ samples of all 12 channels, runs the adaptive
beamformer on those samples, and scores the result on the true signal model.

```bash
python run_experiments.py
```

Figures and `results/summary.md` are written to `results/`. A full run takes
several minutes, and most of that time is the Monte Carlo in experiment 3.

## Files

| File | Contents |
|---|---|
| `crpa_model.py` | Antenna/port polarization models, array geometry, wideband signal generation, RF-chain mismatch, FIR channel equalizer |
| `crpa_dsp.py` | Space-time snapshots, covariance, power inversion (blind), MVDR (satellite beams), scoring, sky maps |
| `run_experiments.py` | The three array designs and three experiments |

## Arrays compared (12 RF channels each)

| | Design | Elements |
|---|---|---|
| A | Conventional CRPA | 12 RHCP patches, 4x3 grid, lambda/2 spacing |
| B | Your design | 3 RHCP + 3 LHCP + 3 linear "H" patches (0/60/120 deg) + 3 vertical monopoles, same 4x3 grid |
| C | Dual-pol CRPA | 6 dual-feed patches (centre + ring of 5, radius lambda/2), RHCP and LHCP ports both digitized |

## What the model includes

- **Full polarization.** Every port has a direction-dependent receive vector
  (E_theta, E_phi), and every wave has a Jones vector (RHCP satellites; linear,
  circular or elliptical jammers).
- **Physical element patterns.**
  - A patch's E-plane still radiates at grazing angles and its H-plane does not.
    A linear patch is therefore truly "horizontal" only in its H-plane.
  - RHCP patches lose about 12 dB toward the horizon.
  - Monopoles have a null at zenith and their peak at the horizon.
- **Finite cross-polarization isolation** of every port (25 dB by default).
- **Exact wideband array response.** True time delays across the aperture are
  modelled at 10 MS/s complex baseband around L1.
- **RF-chain mismatch** per channel: gain, phase, about 1 ns of delay spread,
  and filter ripple.
- **Channel equalization.** A 64-tap FIR per channel is fitted to a
  calibration-noise injection.
- **Jammer types:** wideband noise jammers (2-8 MHz), CW, and an RHCP "smart" jammer.
- **Satellite C/N0.** In-band jammer power is treated as extra white noise. The
  reference is 45 dB-Hz at 0 dBic, and the tracking threshold is 28 dB-Hz.

## What the model does NOT include

The following are not modelled, so read the results as a comparison between the
designs, not as absolute hardware predictions:

- mutual coupling between elements,
- platform and ground multipath,
- ADC quantization and AGC,
- satellite code and carrier tracking loops (C/N0 is computed analytically),
- errors in attitude and ephemeris.

## Algorithms

- **Power inversion (PI).** Minimizes the output power with unit gain on one
  RHCP reference channel. It is blind: it needs no satellite directions,
  attitude or antenna calibration.
- **MVDR.** Forms one beam per satellite, with unit gain toward that satellite's
  space-polarization steering vector and minimum output power. It needs a
  calibrated array manifold (residual calibration error is modelled at
  0.2 dB / 2 deg), plus attitude and ephemeris.
- Both run as STAP with 1 or 5 taps per channel. A diagonal loading of
  0.1 x noise is applied.

## RHCP jammer study (`python run_rhcp_jammer.py`)

A SkyShield-type GNSS jammer transmits RHCP. This study tests tilting
elements toward the jammer (`Port.boresight_el_deg` / `boresight_az_deg`).
Results are in `results/rhcp_summary.md`.

- **An LHCP antenna aimed at an RHCP jammer rejects it.** It is
  cross-polarized, so only about -25 dB of leakage gets through.
  - It also still sees the satellites at about -16 dB, so the
    jammer-to-satellite contrast becomes *worse* (-8.7 dB).
  - The same LHCP patch facing zenith has a contrast of +8.7 dB, because a
    patch's polarization turns almost linear near the horizon.
- **Your proposal (LHCP tilted toward the jammer) is the weakest variant of
  your design.** It drops to 6/9 satellites at 90 dB J/N.
- **RHCP reference antennas aimed at the jammer are the strongest variant.**
  They keep 9/9 satellites up to 90 dB J/N with both algorithms.
- **Below about 80 dB J/N, pointing makes no difference.** Every array removes
  one or two RHCP jammers by spatial nulling alone.

## Key findings

The full tables are in `results/summary.md`.

1. **A fixed cross-polarized antenna doesn't work against a strong jammer.**
   An H antenna facing a perfectly vertical 60 dB jammer still leaves +24 dB of
   jammer at the output. The limits are the element's 25 dB cross-pol
   isolation and the antenna's low gain near the horizon. At a 10 deg tilt the
   residual is +36 dB.
2. **Adaptive polarization works at any jammer tilt.** One dual-pol patch with
   two digitized ports pushes the jammer below the noise floor for every tilt
   from 0 to 90 deg. A satellite 3 deg from the jammer keeps 29.5 dB-Hz.
3. **Space-only nulling loses satellites close to a jammer.** The
   conventional 12x RHCP array also removes the jammer, but the satellite
   3 deg away drops to about 10 dB-Hz and is lost.
4. **Your mixed design works.**
   - Full scenario (6 jammers, including an RHCP smart jammer and two jammers
     right next to satellites): it tracks 9/9 satellites with MVDR. The
     12x RHCP array tracks 7/9 and the dual-pol array 9/9.
   - Monte Carlo: it holds all 9 satellites up to 6 jammers, the best of the
     three designs.
5. **Channel matching is the hidden requirement.** With raw, mismatched RF
   chains (about 1 ns delay spread, 0.4 dB ripple), every design collapses
   after about 6 jammers. Your mixed design collapses hardest: it drops to 0
   satellites at 7 jammers. With per-channel FIR equalization from a cal
   injection, the designs still keep 6-7 of 9 satellites at 8 jammers and
   degrade gradually toward the 11-null limit.
6. **Power inversion vs MVDR.** Blind power inversion keeps 5-7 of 9
   satellites in the full scenario. Satellite-steered MVDR keeps 7-9 of 9 and
   adds up to about 10 dB of array gain, but it needs calibration, attitude
   and ephemeris.
