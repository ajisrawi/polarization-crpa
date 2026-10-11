"""
First-cut RF design of the all-band GNSS CRPA element (1164-1610 MHz).

Produces design_params.json, which gen_boards.py turns into KiCad boards.

Element construction (air-spaced stacked patch):
    upper patch board  FR4 0.8 mm, copper on the bottom side  -> parasitic, 1559-1610 MHz
    air gap h2
    lower patch board  FR4 0.8 mm, copper on the bottom side  -> probe fed, 1164-1300 MHz
    air gap h1
    feed board         RO4350B 0.762 mm: F.Cu = ground plane, B.Cu = microstrip feed,
                       printed 2-section branch-line hybrid, RHCP/LHCP option resistors, SMA

All dimensions here come from closed-form models (Hammerstad microstrip, transmission-line
patch model, ideal-TL hybrid). They are starting values: the element MUST be tuned in a
full-wave EM solver (openEMS / CST / HFSS) before ordering boards.
"""
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

C0 = 299_792_458.0
HERE = Path(__file__).parent

BAND_LO = (1164e6, 1300e6)   # L5/E5a/B2a, E5b/B2b, G3, L2, G2, E6, B3
BAND_HI = (1559e6, 1610e6)   # B1I, L1/E1/B1C, G1
BAND = (BAND_LO[0], BAND_HI[1])

FEED_SUB = {"name": "RO4350B", "er": 3.66, "h_mm": 0.762, "t_mm": 0.035}
PATCH_SUB = {"name": "FR4", "er": 4.3, "h_mm": 0.8}


# --------------------------------------------------------------------------
# Microstrip (Hammerstad & Jensen, zero thickness)
# --------------------------------------------------------------------------

def ms_z0(w, h, er):
    u = w / h
    if u <= 1:
        eeff = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2)
        z = 60 / np.sqrt(eeff) * np.log(8 / u + u / 4)
    else:
        eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
        z = 120 * np.pi / (np.sqrt(eeff) * (u + 1.393 + 0.667 * np.log(u + 1.444)))
    return z, eeff


def ms_width(z_target, h, er):
    lo, hi = 0.01 * h, 20 * h
    for _ in range(100):
        mid = np.sqrt(lo * hi)
        if ms_z0(mid, h, er)[0] > z_target:
            lo = mid
        else:
            hi = mid
    return mid


# --------------------------------------------------------------------------
# Two-section branch-line hybrid (even/odd mode, ideal lines)
# --------------------------------------------------------------------------

def _abcd_line(z, theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 1j * z * s], [1j * s / z, c]])


def _abcd_shunt(y):
    return np.array([[1, 0], [y, 1]], dtype=complex)


def hybrid_s(f, za, zb, zc, f0, z0=50.0):
    """S11, S21 (through), S31 (coupled), S41 (isolated) of a 2-section branch-line."""
    out = []
    for fi in np.atleast_1d(f):
        t_series = np.pi / 2 * fi / f0
        t_stub = np.pi / 4 * fi / f0
        modes = {}
        for mode, stub in (("e", lambda z: 1j * np.tan(t_stub) / z),
                           ("o", lambda z: -1j / (np.tan(t_stub) * z))):
            m = _abcd_shunt(stub(za)) @ _abcd_line(zc, t_series) @ _abcd_shunt(stub(zb)) \
                @ _abcd_line(zc, t_series) @ _abcd_shunt(stub(za))
            a, b, c, d = m[0, 0], m[0, 1] / z0, m[1, 0] * z0, m[1, 1]
            den = a + b + c + d
            modes[mode] = ((a + b - c - d) / den, 2 / den)
        (ge, te), (go, to) = modes["e"], modes["o"]
        out.append(((ge + go) / 2, (te + to) / 2, (te - to) / 2, (ge - go) / 2))
    return np.array(out).T


def design_hybrid():
    f = np.linspace(*BAND, 61)

    def cost(p):
        za, zb, zc, f0 = p[0], p[1], p[2], p[3] * 1e9
        s11, s21, s31, s41 = hybrid_s(f, za, zb, zc, f0)
        amp = 20 * np.log10(np.abs(s21) / np.abs(s31))
        ph = np.degrees(np.angle(s31 / s21)) + 90
        return (np.mean(np.abs(s11) ** 2) + np.mean(np.abs(s41) ** 2)
                + 0.02 * np.mean(amp ** 2) + 1e-4 * np.mean(ph ** 2))

    best = minimize(cost, [120.0, 35.0, 37.0, 1.39], method="Nelder-Mead",
                    options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-9})
    za, zb, zc, f0 = best.x[0], best.x[1], best.x[2], best.x[3] * 1e9
    s11, s21, s31, s41 = hybrid_s(f, za, zb, zc, f0)
    perf = {
        "worst_return_loss_db": float(-20 * np.log10(np.abs(s11).max())),
        "worst_isolation_db": float(-20 * np.log10(np.abs(s41).max())),
        "amplitude_imbalance_db": float(np.max(np.abs(20 * np.log10(np.abs(s21) / np.abs(s31))))),
        "phase_error_deg": float(np.max(np.abs(np.degrees(np.angle(s31 / s21)) + 90))),
    }
    # axial ratio implied by the hybrid imbalance (perfect element)
    a = 10 ** (perf["amplitude_imbalance_db"] / 20)
    phase = np.radians(90 + perf["phase_error_deg"])  # phase difference between the two feeds
    root = np.sqrt(1 + a ** 4 + 2 * a ** 2 * np.cos(2 * phase))
    num, den = 1 + a ** 2 + root, 1 + a ** 2 - root
    perf["implied_axial_ratio_db"] = float(10 * np.log10(num / den))

    h, er = FEED_SUB["h_mm"], FEED_SUB["er"]
    geo = {}
    for key, z in (("z50", 50.0), ("za", za), ("zb", zb), ("zc", zc)):
        w = ms_width(z, h, er)
        eeff = ms_z0(w, h, er)[1]
        geo[key] = {"z_ohm": round(float(z), 2), "width_mm": round(float(w), 3),
                    "quarter_wave_mm": round(float(C0 / (f0 * np.sqrt(eeff)) / 4 * 1e3), 3)}
    return {"f0_hz": float(f0), "lines": geo, "performance": perf}, (f, s11, s21, s31, s41)


# --------------------------------------------------------------------------
# Air-spaced patch (transmission-line model)
# --------------------------------------------------------------------------

def patch_length(f, h_air_mm, cover_h_mm=PATCH_SUB["h_mm"], cover_er=PATCH_SUB["er"]):
    """Square patch length for resonance f; air gap below, thin FR4 cover above."""
    h = h_air_mm + cover_h_mm
    er_eff_sub = h / (h_air_mm / 1.0 + cover_h_mm / cover_er)       # series-layer average
    lam = C0 / f * 1e3
    length = lam / 2
    for _ in range(50):
        w = length
        eeff = (er_eff_sub + 1) / 2 + (er_eff_sub - 1) / 2 * (1 + 12 * h / w) ** -0.5
        dl = 0.412 * h * (eeff + 0.3) * (w / h + 0.264) / ((eeff - 0.258) * (w / h + 0.8))
        length = lam / (2 * np.sqrt(eeff)) - 2 * dl
    return float(length), float(eeff)


def patch_feed_offset(length_mm, f, r_target=50.0):
    """Probe offset from the patch centre giving r_target (cosine-squared model)."""
    lam = C0 / f * 1e3
    k0w = 2 * np.pi * length_mm / lam
    g1 = (1 / 90) * (length_mm / lam) ** 2 if k0w < 1 else (1 / 120) * (length_mm / lam)
    r_edge = 1 / (2 * g1 * 1.3)          # 1.3: mutual conductance of the two slots
    x_edge = length_mm / np.pi * np.arccos(np.sqrt(min(1.0, r_target / r_edge)))
    return float(length_mm / 2 - x_edge), float(r_edge)


def probe_reactance(f, h_mm, d_mm):
    k0 = 2 * np.pi * f / C0
    return float(60 * k0 * h_mm * 1e-3 * np.log(C0 / f / (np.pi * d_mm * 1e-3)))


def design_patch(h1_mm=9.0, h2_mm=6.0, probe_d_mm=1.3):
    f_lo = np.sqrt(BAND_LO[0] * BAND_LO[1])
    f_hi = np.sqrt(BAND_HI[0] * BAND_HI[1])
    l_lo, e_lo = patch_length(f_lo, h1_mm)
    l_hi, e_hi = patch_length(f_hi, h2_mm)
    off, r_edge = patch_feed_offset(l_lo, f_lo)
    lam_lo = C0 / f_lo * 1e3
    bw_est = 3.77 * 0.1 / 1.05 * h1_mm / lam_lo * 4  # very rough, air-patch with stacked coupling
    return {
        "h1_air_mm": h1_mm, "h2_air_mm": h2_mm,
        "lower_patch": {"f_center_hz": float(f_lo), "length_mm": round(l_lo, 2), "eeff": round(e_lo, 3)},
        "upper_patch": {"f_center_hz": float(f_hi), "length_mm": round(l_hi, 2), "eeff": round(e_hi, 3)},
        "probe": {"diameter_mm": probe_d_mm, "offset_from_centre_mm": round(off, 2),
                  "edge_resistance_ohm": round(r_edge, 1),
                  "reactance_lo_ohm": round(probe_reactance(f_lo, h1_mm, probe_d_mm), 1),
                  "series_cap_to_cancel_pF": round(1e12 / (2 * np.pi * f_lo
                                                  * probe_reactance(f_lo, h1_mm, probe_d_mm)), 2)},
        "note": "Analytical starting point only; tune h1, h2, patch sizes and probe offset in an EM solver.",
    }


def main():
    hybrid, curves = design_hybrid()
    patch = design_patch()
    params = {
        "bands_hz": {"low": BAND_LO, "high": BAND_HI},
        "feed_substrate": FEED_SUB, "patch_substrate": PATCH_SUB,
        "hybrid": hybrid, "patch": patch,
        "board": {"size_mm": 124.0, "element_pitch_mm": 125.0, "mount_hole_offset_mm": 58.0},
    }
    (HERE / "design_params.json").write_text(json.dumps(params, indent=2))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f, s11, s21, s31, s41 = curves
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    db = lambda s: 20 * np.log10(np.abs(s))
    for s, lab in ((s11, "S11 return"), (s21, "S21 through"), (s31, "S31 coupled"), (s41, "S41 isolated")):
        ax[0].plot(f / 1e6, db(s), label=lab)
    ax[0].set(xlabel="MHz", ylabel="dB", title="2-section branch-line hybrid (ideal lines)", ylim=(-45, 0))
    ax[1].plot(f / 1e6, np.degrees(np.angle(s31 / s21)), color="C3")
    ax[1].set(xlabel="MHz", ylabel="deg", title="Phase S31 - S21 (ideal -90)")
    for a in ax:
        for lo, hi in (BAND_LO, BAND_HI):
            a.axvspan(lo / 1e6, hi / 1e6, color="g", alpha=0.08)
        a.grid(alpha=0.3)
    ax[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "hybrid_response.png", dpi=120)
    print(json.dumps(params, indent=2))


if __name__ == "__main__":
    main()
