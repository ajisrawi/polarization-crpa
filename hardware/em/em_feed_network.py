"""
Rev C feed network, verified at circuit level on the simulated element S-parameters.

    tools\\emvenv\\Scripts\\python.exe hardware\\em\\em_feed_network.py [element_tag]

Chain (per circular element):
  probes 1,2 (patch A) -> 90deg hybrid LO -> port 1 (RHCP) -> diplexer LOW-PASS branch \
                                                                                        SMA
  probes 3,4 (patch C) -> 90deg hybrid HI -> port 1 (RHCP) -> diplexer HIGH-PASS branch /
  (the 1.5 pF series caps on probes 3,4 are already inside the EM model)
Both hybrids' isolated ports are terminated in 49.9 ohm.

Designs a 5th-order Chebyshev LC diplexer (LPF / HPF with separate cut-offs in the
1300-1559 MHz gap), applies standard-value rounding and 0402 parasitics, and reports
return loss and insertion loss at the SMA for every GNSS band.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
Z0 = 50.0
BANDS = {"L5/E5a/B2a": (1164e6, 1189e6), "E5b/B2b/G3": (1195e6, 1219e6), "L2": (1217e6, 1238e6),
         "G2": (1237e6, 1254e6), "E6/B3": (1258e6, 1300e6), "B1I": (1559e6, 1563e6),
         "L1/E1/B1C": (1563e6, 1588e6), "G1": (1593e6, 1610e6)}
E24 = np.array([1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6,
                6.2, 6.8, 7.5, 8.2, 9.1])


def nearest_std(v, unit):
    """Nearest E24 value (0402 RF inductors/caps come in ~E24 steps above 1 nH / 1 pF)."""
    x = v / unit
    dec = 10 ** np.floor(np.log10(x))
    cand = np.concatenate([E24 * dec / 10, E24 * dec, E24 * dec * 10])
    return float(cand[np.argmin(np.abs(cand - x))] * unit)


def cheb_g(n, ripple_db):
    beta = np.log(1 / np.tanh(ripple_db / 17.37))
    gam = np.sinh(beta / (2 * n))
    a = [np.sin((2 * k - 1) * np.pi / (2 * n)) for k in range(1, n + 1)]
    b = [gam ** 2 + np.sin(k * np.pi / n) ** 2 for k in range(1, n + 1)]
    g = [2 * a[0] / gam]
    for k in range(1, n):
        g.append(4 * a[k - 1] * a[k] / (b[k - 1] * g[k - 1]))
    return g


# ---------------- 2-port ABCD helpers ------------------------------------------
def series(z):
    return np.array([[1, z], [0, 1]], dtype=complex)


def shunt(y):
    return np.array([[1, 0], [y, 1]], dtype=complex)


def ind(L, w, q=40):
    return 1j * w * L + w * L / q          # 0402 wire-wound/thin-film Q ~ 40 at L-band


def cap(C, w, q=200):
    return 1 / (1j * w * C) + 1 / (w * C * q)


def lpf_abcd(vals, w):
    """series L, shunt C, series L, shunt C, series L"""
    m = np.eye(2, dtype=complex)
    for i, v in enumerate(vals):
        m = m @ (series(ind(v, w)) if i % 2 == 0 else shunt(1 / cap(v, w)))
    return m


def hpf_abcd(vals, w):
    """series C, shunt L, series C, shunt L, series C"""
    m = np.eye(2, dtype=complex)
    for i, v in enumerate(vals):
        m = m @ (series(cap(v, w)) if i % 2 == 0 else shunt(1 / ind(v, w)))
    return m


def abcd_to_s(m):
    a, b, c, d = m[0, 0], m[0, 1] / Z0, m[1, 0] * Z0, m[1, 1]
    den = a + b + c + d
    return np.array([[(a + b - c - d) / den, 2 * (a * d - b * c) / den], [2 / den, (-a + b - c + d) / den]])


def design(f_lp, f_hp, n=5, ripple=0.1):
    g = cheb_g(n, ripple)
    wl, wh = 2 * np.pi * f_lp, 2 * np.pi * f_hp
    lp = [g[i] * Z0 / wl if i % 2 == 0 else g[i] / (Z0 * wl) for i in range(n)]
    hp = [1 / (g[i] * Z0 * wh) if i % 2 == 0 else Z0 / (g[i] * wh) for i in range(n)]
    return lp, hp


def diplexer_s(lp, hp, f, gamma_lo=None, gamma_hi=None):
    """3-port S of the diplexer: port 0 = common (SMA), 1 = LPF branch, 2 = HPF branch.
    Returns reflection at the common port with the branches loaded by gamma_lo / gamma_hi,
    and the power transmitted into each branch load."""
    out = []
    for i, fv in enumerate(f):
        w = 2 * np.pi * fv
        res = {}
        for name, m, gl in (("lo", lpf_abcd(lp, w), gamma_lo), ("hi", hpf_abcd(hp, w), gamma_hi)):
            s = abcd_to_s(m)
            gl_i = 0 if gl is None else gl[i]
            # input reflection of the branch when its far end is loaded by gl
            g_in = s[0, 0] + s[0, 1] * s[1, 0] * gl_i / (1 - s[1, 1] * gl_i)
            res[name] = (g_in, s, gl_i)
        # parallel connection at the common node: admittances add
        y = sum((1 - r[0]) / (1 + r[0]) / Z0 for r in res.values())
        g_common = (1 / Z0 - y) / (1 / Z0 + y)
        # voltage at the node per unit incident wave, then power into each branch (into its input)
        v_node = 1 + g_common
        p = {}
        for name, (g_in, s, gl_i) in res.items():
            a_branch = v_node / (1 + g_in)                      # incident wave into the branch
            b2 = s[1, 0] * a_branch / (1 - s[1, 1] * gl_i)       # wave toward the load
            p[name] = float(np.abs(b2) ** 2 * (1 - np.abs(gl_i) ** 2))
        out.append((g_common, p["lo"], p["hi"]))
    return out


def element_gammas(tag):
    """RHCP reflection seen at each hybrid's input (EM element + ideal hybrid + 50 ohm loads)."""
    d = np.load(HERE / "results" / f"{tag}_full.npz")
    f, S = d["f"], d["S"]
    w = np.array([1, -1j]) / np.sqrt(2)
    g_lo = np.array([w @ S[0:2, 0:2, i] @ w for i in range(len(f))])
    g_hi = np.array([w @ S[2:4, 2:4, i] @ w for i in range(len(f))])
    # power that leaves the element through the OTHER band's probes (absorbed by its hybrid/diplexer)
    leak_lo_to_hi = np.array([np.linalg.norm(S[2:4, 0:2, i] @ w) ** 2 for i in range(len(f))])
    leak_hi_to_lo = np.array([np.linalg.norm(S[0:2, 2:4, i] @ w) ** 2 for i in range(len(f))])
    return f, g_lo, g_hi, leak_lo_to_hi, leak_hi_to_lo


def evaluate(lp, hp, f, g_lo, g_hi):
    res = diplexer_s(lp, hp, f, g_lo, g_hi)
    rl = np.array([-20 * np.log10(abs(r[0])) for r in res])
    p_lo = np.array([r[1] for r in res])
    p_hi = np.array([r[2] for r in res])
    table = {}
    for k, (lo, hi) in BANDS.items():
        m = (f >= lo) & (f <= hi)
        upper = lo > 1.4e9
        p_ok = p_hi if upper else p_lo
        table[k] = {"RL_at_SMA_dB": round(float(rl[m].min()), 1),
                    "into_antenna_dB": round(float(10 * np.log10(p_ok[m].min() + 1e-12)), 2),
                    "into_wrong_branch_dB": round(float(10 * np.log10((p_lo if upper else p_hi)[m].max() + 1e-12)), 1)}
    return table, rl, p_lo, p_hi


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "air4_c9"
    f, g_lo, g_hi, leak_lh, leak_hl = element_gammas(tag)
    best = None
    for f_lp in np.arange(1.32e9, 1.46e9, 0.01e9):
        for f_hp in np.arange(1.40e9, 1.54e9, 0.01e9):
            if f_hp <= f_lp:
                continue
            lp, hp = design(f_lp, f_hp)
            t, *_ = evaluate(lp, hp, f, g_lo, g_hi)
            worst = min(min(v["RL_at_SMA_dB"] for v in t.values()), 99)
            loss = min(v["into_antenna_dB"] for v in t.values())
            score = min(worst, 15) + 10 * loss
            if best is None or score > best[0]:
                best = (score, f_lp, f_hp, lp, hp)
    _, f_lp, f_hp, lp, hp = best
    lp_std = [nearest_std(v, 1e-9 if i % 2 == 0 else 1e-12) for i, v in enumerate(lp)]
    hp_std = [nearest_std(v, 1e-12 if i % 2 == 0 else 1e-9) for i, v in enumerate(hp)]
    t_ideal, *_ = evaluate(lp, hp, f, g_lo, g_hi)
    t_std, rl, p_lo, p_hi = evaluate(lp_std, hp_std, f, g_lo, g_hi)
    result = {
        "element": tag,
        "lpf_cutoff_MHz": round(f_lp / 1e6), "hpf_cutoff_MHz": round(f_hp / 1e6),
        "lpf_parts": {"L1_nH": lp_std[0] * 1e9, "C2_pF": lp_std[1] * 1e12, "L3_nH": lp_std[2] * 1e9,
                      "C4_pF": lp_std[3] * 1e12, "L5_nH": lp_std[4] * 1e9},
        "hpf_parts": {"C1_pF": hp_std[0] * 1e12, "L2_nH": hp_std[1] * 1e9, "C3_pF": hp_std[2] * 1e12,
                      "L4_nH": hp_std[3] * 1e9, "C5_pF": hp_std[4] * 1e12},
        "bands_standard_values": t_std, "bands_exact_values": t_ideal,
        "cross_band_leak_dB": {"lower-band power into upper probes": round(float(10 * np.log10(leak_lh.max())), 1),
                               "upper-band power into lower probes": round(float(10 * np.log10(leak_hl.max())), 1)},
        "assumptions": "ideal 90deg hybrids; 0402 L Q=40, C Q=200; EM element incl. 1.5 pF series caps",
    }
    (HERE / "results" / f"{tag}_feed_network.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
    ax[0].plot(f / 1e6, -rl, label="return loss at SMA (element + hybrids + diplexer)")
    ax[0].axhline(-10, color="k", lw=0.8)
    ax[0].set(ylabel="dB", xlabel="MHz", title="RHCP match at the element connector", ylim=(-40, 0))
    ax[1].plot(f / 1e6, 10 * np.log10(p_lo + 1e-12), label="into lower-band probes (LPF)")
    ax[1].plot(f / 1e6, 10 * np.log10(p_hi + 1e-12), label="into upper-band probes (HPF)")
    ax[1].set(ylabel="dB", xlabel="MHz", title="where the power goes", ylim=(-40, 1))
    for a in ax:
        for lo, hi in BANDS.values():
            a.axvspan(lo / 1e6, hi / 1e6, color="g", alpha=0.07)
        a.grid(alpha=0.3)
        a.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "results" / f"{tag}_feed_network.png", dpi=120)


if __name__ == "__main__":
    main()
