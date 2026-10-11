"""
Size the feed-board matching part for a simulated probe impedance.

    tools\\emvenv\\Scripts\\python.exe hardware\\em\\em_match.py <tag> [band]

band: "upper" (1559-1610 MHz, default) or "lower" (1164-1300 MHz).
Tries a series capacitor (the 0603 position in each probe line) and reports the value
that minimizes the worst |S11| over the band, plus the E12/E24-style nearest RF value.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BANDS = {"upper": (1559e6, 1610e6), "lower": (1164e6, 1300e6)}
RF_CAPS_PF = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
              3.3, 3.9, 4.7, 5.6, 6.8, 8.2, 10.0]


def s11(z):
    return (z - 50) / (z + 50)


def main():
    tag = sys.argv[1]
    band = sys.argv[2] if len(sys.argv) > 2 else "upper"
    d = np.load(HERE / "results" / f"{tag}.npz")
    f, z = d["f"], d["zin"]
    lo, hi = BANDS[band]
    m = (f >= lo) & (f <= hi)
    w = 2 * np.pi * f[m]
    best = None
    for c in np.linspace(0.2e-12, 12e-12, 1200):
        zc = z[m] - 1j / (w * c)
        worst = 20 * np.log10(np.abs(s11(zc)).max())
        if best is None or worst < best[1]:
            best = (c, worst)
    c_opt, worst = best
    std = min(RF_CAPS_PF, key=lambda v: abs(v - c_opt * 1e12))
    zc = z[m] - 1j / (w * std * 1e-12)
    worst_std = 20 * np.log10(np.abs(s11(zc)).max())
    res = {"tag": tag, "band": band,
           "unmatched_worst_S11_dB": round(float(20 * np.log10(np.abs(s11(z[m])).max())), 2),
           "series_C_opt_pF": round(c_opt * 1e12, 3), "worst_S11_opt_dB": round(float(worst), 2),
           "series_C_std_pF": std, "worst_S11_std_dB": round(float(worst_std), 2),
           "R_band_ohm": [round(float(z[m].real.min()), 1), round(float(z[m].real.max()), 1)]}
    print(json.dumps(res, indent=1))
    (HERE / "results" / f"{tag}_match_{band}.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
