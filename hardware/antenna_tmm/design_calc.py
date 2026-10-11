r"""
Rev B element: compact all-band GNSS CRPA element on Rogers TMM3 ceramic-thermoset laminate.

Stack (bottom -> top), all slabs bonded (no clamp holes through the radiators):
    feed board  RO4350B 0.762 mm, 96 x 96 mm: F.Cu ground, B.Cu feed + SMD 90 deg hybrid + SMA,
                stitched B.Cu ground; tied to the array plate by 8 metal standoffs
    slab A1     TMM3 8.89 mm: probes from below end on copper FEED DISKS on its top face
    slab A2     TMM3 0.762 mm: patch A on top (fed capacitively by the disks)  ~1190 MHz \ coupled
    slab B      TMM3 3.175 mm: patch B on top (parasitic)                      ~1275 MHz / 1164-1300
    slab C      TMM3 7.62 mm:  patch C on top (parasitic)                      ~1585 MHz   1559-1610

The capacitive disk cancels the probe inductance of the 8.9 mm probe, so the fed layer can
be thick enough for the 11 % lower band.

Closed-form models only (transmission-line patch, Hammerstad microstrip). The bandwidth
numbers below are ROUGH single-patch estimates; stacked coupling normally widens them.
Treat every dimension as an EM-simulation starting point.
"""
import json
from pathlib import Path

import numpy as np

C0 = 299_792_458.0
HERE = Path(__file__).parent

BANDS = {
    "lower (L5/E5a/B2a .. E6/B3)": (1164e6, 1300e6),
    "upper (B1I/L1/E1/B1C/G1)": (1559e6, 1610e6),
}
TMM3 = {"name": "Rogers TMM3", "er": 3.45, "tan_d": 0.002}     # design Dk
FEED = {"name": "Rogers RO4350B", "er": 3.66, "h_mm": 0.762}
SLABS = {"A1": 8.89, "A2": 0.762, "B": 3.175, "C": 7.62}


def patch_length(f, h_mm, er):
    lam = C0 / f * 1e3
    length = lam / (2 * np.sqrt(er))
    for _ in range(60):
        w = length
        eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h_mm / w) ** -0.5
        dl = 0.412 * h_mm * (eeff + 0.3) * (w / h_mm + 0.264) / ((eeff - 0.258) * (w / h_mm + 0.8))
        length = lam / (2 * np.sqrt(eeff)) - 2 * dl
    return float(length), float(eeff)


def edge_resistance(length_mm, f, er):
    lam = C0 / f * 1e3
    w = length_mm
    g1 = (w / lam) ** 2 / 90 if w < lam else w / (120 * lam)
    return 1 / (2 * g1 * 1.3)


def feed_offset(length_mm, f, er, r_target=50.0):
    r_edge = edge_resistance(length_mm, f, er)
    x_edge = length_mm / np.pi * np.arccos(np.sqrt(min(1.0, r_target / r_edge)))
    return float(length_mm / 2 - x_edge), float(r_edge)


def bandwidth(f, h_mm, er):
    """Jackson & Alexopoulos thin-patch VSWR<2 bandwidth (fraction)."""
    return 3.77 * (er - 1) / er ** 2 * (h_mm * 1e-3) / (C0 / f)


def main():
    er = TMM3["er"]
    hA = SLABS["A1"] + SLABS["A2"]
    hB, hC = SLABS["B"], SLABS["C"]
    fA, fB, fC = 1190e6, 1275e6, 1585e6
    lA, eA = patch_length(fA, hA, er)
    lB, eB = patch_length(fB, hA + hB, er)      # parasitic: field spans A+B to the ground
    lC, eC = patch_length(fC, hC, er)           # top patch sees B/A as its ground at L1
    off, r_edge = feed_offset(lA, fA, er)
    k0 = 2 * np.pi * fA / C0
    # probe now only spans slab A1; the disk-to-patch capacitance (gap = A2) cancels it
    x_probe = 60 * k0 * SLABS["A1"] * 1e-3 * np.log(C0 / fA / (np.pi * 1.3e-3))
    c_need = 1 / (2 * np.pi * fA * x_probe)
    eps0 = 8.854e-12
    disk_r = np.sqrt(c_need * SLABS["A2"] * 1e-3 / (eps0 * er * np.pi)) * 1e3
    lower_single = bandwidth(np.sqrt(BANDS["lower (L5/E5a/B2a .. E6/B3)"][0] * 1300e6), hA + hB, er)
    upper_single = bandwidth(fC, hC, er)
    need_lo = (1300 - 1164) / np.sqrt(1300 * 1164)
    need_hi = (1610 - 1559) / np.sqrt(1610 * 1559)
    params = {
        "rev": "B (TMM3 compact)",
        "substrates": {"slab": TMM3, "feed": FEED, "slab_thickness_mm": SLABS},
        "patches_mm": {"A": round(lA, 2), "B": round(lB, 2), "C": round(lC, 2)},
        "resonances_hz": {"A": fA, "B": fB, "C": fC},
        "probe": {"offset_from_centre_mm": round(off, 2), "edge_resistance_ohm": round(r_edge, 1),
                  "reactance_ohm": round(float(x_probe), 1),
                  "series_cap_to_cancel_pF": round(c_need * 1e12, 2),
                  "feed_disk_diameter_mm": round(2 * float(disk_r), 2)},
        "stack_height_mm": round(FEED["h_mm"] + sum(SLABS.values()), 2),
        "bandwidth_estimate": {
            "lower_needed_pct": round(100 * need_lo, 1),
            "lower_single_patch_pct": round(100 * lower_single, 1),
            "lower_stacked_pair_pct_typical": f"{100 * 2 * lower_single:.0f}-{100 * 3 * lower_single:.0f}",
            "upper_needed_pct": round(100 * need_hi, 1),
            "upper_single_patch_pct": round(100 * upper_single, 1),
            "note": "Hybrid-fed CP widens impedance bandwidth (reflections go to the terminated port) "
                    "at the cost of efficiency. EM simulation decides whether h must grow.",
        },
        "board": {"feed_size_mm": 96.0, "slab_size_mm": 80.0, "element_pitch_mm": 100.0,
                  "post_holes_mm": 44.0},
        "hybrid": {"part": "Electro-Photonics Q3XG-1500R (1000-2000 MHz, 14.2 x 8.9 mm)",
                   "land_pattern": "PLACEHOLDER - replace with the datasheet recommended layout"},
    }
    (HERE / "design_params.json").write_text(json.dumps(params, indent=2))
    print(json.dumps(params, indent=2))


if __name__ == "__main__":
    main()
