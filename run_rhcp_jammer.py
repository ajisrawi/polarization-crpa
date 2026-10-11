"""
RHCP jammer study (a SkyShield-type GNSS jammer uses RHCP helices).

Question: with 3 RHCP antennas facing the satellites and 3 LHCP antennas
tilted so they face the jammer, does the array reject an RHCP jammer better?

Arrays (all 12 channels, same 4x3 grid unless noted):
  A   12x RHCP, all facing zenith
  B   your design, all facing zenith
  B1  your proposal: RHCP facing the satellites (zenith), LHCP facing the jammer
  B2  alternative: the 3 tilted elements are RHCP instead of LHCP
      (co-polarized "jammer reference" antennas)
  C   6x dual-pol R+L, all facing zenith

Run:  python run_rhcp_jammer.py      (writes results/rhcp_*.png and results/rhcp_summary.md)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from crpa_model import ArrayConfig, Emitter, Port, jones_lhcp, jones_linear, jones_rhcp
from run_experiments import (OUT, TRACK_DB_HZ, _grid_4x3, array_dualpol6, array_rhcp12,
                             array_user_mixed, make_rx, run_processor, satellites_default)

JAM_EL, JAM_AZ = 10.0, 0.0
LAYOUT = ["H", "V", "R", "L",
          "L", "R", "H", "V",
          "R", "H", "V", "L"]


def _user_variant(name, tilted_kind):
    """Your 4x3 layout with the three LHCP slots tilted to face the jammer."""
    h_orient = iter([0.0, 60.0, 120.0])
    ports = []
    for k, p in zip(LAYOUT, _grid_4x3()):
        if k == "L":
            ports.append(Port(tilted_kind, p, boresight_el_deg=JAM_EL, boresight_az_deg=JAM_AZ))
        else:
            ports.append(Port(k, p, next(h_orient) if k == "H" else 0.0))
    return ArrayConfig(name, ports, ref_port=5)


def arrays():
    return [array_rhcp12(),
            array_user_mixed(),
            _user_variant("B1: your proposal (LHCP face jammer)", "L"),
            _user_variant("B2: RHCP ref. antennas face jammer", "R"),
            array_dualpol6()]


def element_table():
    """What a single element of each kind/pointing receives."""
    cases = [("RHCP, facing zenith", "R", 90.0),
             ("LHCP, facing zenith", "L", 90.0),
             ("LHCP, facing the jammer", "L", JAM_EL),
             ("RHCP, facing the jammer", "R", JAM_EL),
             ("Linear H patch, facing zenith", "H", 90.0),
             ("Vertical monopole", "V", 90.0)]
    lines = ["| Element | RHCP jammer (el 10) | satellite at zenith | satellite at el 45 | jammer minus zenith sat |",
             "|---|---|---|---|---|"]
    for label, kind, bel in cases:
        cfg = ArrayConfig(label, [Port(kind, (0, 0), orient_deg=90.0,
                                       boresight_el_deg=bel, boresight_az_deg=JAM_AZ)])
        db = lambda el, az: 20 * np.log10(abs(cfg.pol_gain(el, az, jones_rhcp())[0]) + 1e-9)
        j, s0, s45 = db(JAM_EL, JAM_AZ), db(90, 0), db(45, 180)
        lines.append(f"| {label} | {j:.1f} dB | {s0:.1f} dB | {s45:.1f} dB | {j - s0:+.1f} dB |")
    return lines


def rhcp_jammer(power_db, el=JAM_EL, az=JAM_AZ, label="RHCP jammer"):
    return Emitter(el, az, jones_rhcp(), power_db, bw_hz=8e6, label=label)


def sweep():
    sats = satellites_default()
    powers = np.arange(40, 91, 10)
    rng = np.random.default_rng(40)
    res = {}
    for cfg in arrays():
        rx = make_rx(cfg, n_samples=2 ** 14)
        for algo in ("PI", "MVDR"):
            tracked, inr = [], []
            for p in powers:
                _, ev = run_processor(rx, [rhcp_jammer(p)], sats, algo, 5, rng)
                tracked.append(int((ev["cn0"] >= TRACK_DB_HZ).sum()))
                inr.append(ev["inr_out_db"])
            res[(cfg.name, algo)] = (tracked, inr)

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for k, cfg in enumerate(arrays()):
        for a, algo in zip(ax, ("PI", "MVDR")):
            a.plot(powers, res[(cfg.name, algo)][0], "o-", color=f"C{k}", label=cfg.name)
    for a, algo in zip(ax, ("Power inversion (blind)", "MVDR (satellite beams)")):
        a.set(title=f"One RHCP jammer at el {JAM_EL:g} deg - {algo}, 5 taps",
              xlabel="Jammer J/N in a 0 dBic antenna [dB]", ylim=(-0.3, 9.3))
        a.grid(True, alpha=0.3)
    ax[0].set_ylabel(f"Satellites with C/N0 >= {TRACK_DB_HZ:g} dB-Hz (of 9)")
    ax[1].legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "rhcp_jammer_power_sweep.png", dpi=130)
    plt.close(fig)

    lines = ["| Array | Processing | " + " | ".join(f"{p} dB" for p in powers) + " |",
             "|---|---|" + "---|" * len(powers)]
    for (name, algo), (tracked, inr) in res.items():
        lines.append(f"| {name} | {algo} | " + " | ".join(
            f"{t} sats ({i:+.0f})" for t, i in zip(tracked, inr)) + " |")
    return lines


def two_jammers():
    """Second RHCP jammer from another direction: the tilted elements do not face it."""
    sats = satellites_default()
    jams = [rhcp_jammer(65, label="J1 RHCP, el 10 az 0 (the one the elements face)"),
            rhcp_jammer(60, el=6, az=150, label="J2 RHCP, el 6 az 150")]
    rng = np.random.default_rng(41)
    lines = ["| Array | Processing | Worst output J/N [dB] | Satellites tracked | C/N0 per satellite [dB-Hz] |",
             "|---|---|---|---|---|"]
    for cfg in arrays():
        rx = make_rx(cfg, n_samples=2 ** 14)
        for algo in ("PI", "MVDR"):
            _, ev = run_processor(rx, jams, sats, algo, 5, rng)
            lines.append(f"| {cfg.name} | {algo} | {ev['inr_out_db']:.1f} | "
                         f"{int((ev['cn0'] >= TRACK_DB_HZ).sum())} / 9 | "
                         + ", ".join(f"{c:.0f}" for c in ev["cn0"]) + " |")
    return lines


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    report = ["# RHCP jammer study", "",
              f"Jammer: RHCP, 8 MHz wideband, at elevation {JAM_EL:g} deg, azimuth {JAM_AZ:g} deg.", "",
              "## 1. What one element receives (RHCP waves; gain relative to an RHCP patch at zenith)", ""]
    report += element_table()
    report += ["", "## 2. Jammer power sweep - satellites tracked (worst output J/N in brackets)", ""]
    report += sweep()
    report += ["", "## 3. Two RHCP jammers (65 dB at az 0, 60 dB at az 150)", ""]
    report += two_jammers()
    (OUT / "rhcp_summary.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
