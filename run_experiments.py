"""
Adaptive polarization + spatial nulling for a 12-channel GNSS CRPA.

Compares, with the same 12 RF channels:
  A. Conventional CRPA       : 12 RHCP patches            (space only)
  B. Your mixed design       : 3 RHCP + 3 LHCP + 3 H + 3 V (space + polarization)
  C. Dual-polarized CRPA     : 6 patches x (RHCP + LHCP)  (space + polarization)

Experiments
  1. Jammer tilt sweep: one linear jammer and a satellite in almost the same direction.
  2. Full scenario: 9 satellites, 6 mixed jammers (wideband, CW, an RHCP "smart" jammer).
  3. Monte Carlo: number of jammers 1..14 -> how many satellites stay trackable.

Run:  python run_experiments.py      (figures and summary go to ./results)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from crpa_model import (LAMBDA_L1, ArrayConfig, Emitter, Port, Receiver, jones_elliptical,
                        jones_linear, jones_rhcp)
from crpa_dsp import (evaluate, mvdr, power_inversion, sample_covariance, sky_gain, snapshots,
                      st_steering, unprotected)

OUT = Path(__file__).parent / "results"
TRACK_DB_HZ = 28.0  # typical C/N0 needed to keep tracking a GPS L1 C/A signal
D = LAMBDA_L1 / 2


# --------------------------------------------------------------------------
# Array configurations (all 12 channels)
# --------------------------------------------------------------------------

def _grid_4x3():
    return [((ix - 1.5) * D, (1 - iy) * D) for iy in range(3) for ix in range(4)]


def array_rhcp12():
    ports = [Port("R", p) for p in _grid_4x3()]
    return ArrayConfig("A: 12x RHCP (space only)", ports, ref_port=5)


def array_user_mixed():
    layout = ["H", "V", "R", "L",
              "L", "R", "H", "V",
              "R", "H", "V", "L"]
    h_orient = iter([0.0, 60.0, 120.0])
    ports = [Port(k, p, next(h_orient) if k == "H" else 0.0) for k, p in zip(layout, _grid_4x3())]
    return ArrayConfig("B: 3R+3L+3H+3V (your design)", ports, ref_port=5)


def array_dualpol6():
    pos = [(0.0, 0.0)] + [(D * np.cos(a), D * np.sin(a))
                          for a in np.radians(90 + 72 * np.arange(5))]
    ports = [Port(k, p) for p in pos for k in ("R", "L")]
    return ArrayConfig("C: 6x dual-pol R+L (space + pol)", ports, ref_port=0)


ARRAYS = [array_rhcp12, array_user_mixed, array_dualpol6]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def satellites_default():
    sky = [(75, 40), (55, 150), (40, 260), (30, 10), (25, 95),
           (15, 120), (20, 300), (10, 200), (45, 330)]
    return [Emitter(el, az, jones_rhcp(), label=f"G{i + 1:02d}") for i, (el, az) in enumerate(sky)]


def make_rx(cfg, n_samples=2 ** 15, equalized=True):
    """Receiver for an array; by default the RF chains are equalized from a cal injection."""
    rx = Receiver(cfg, n_samples=n_samples)
    return rx.equalize() if equalized else rx


def run_processor(rx, jammers, sats, algo, taps, rng):
    x = rx.generate(jammers, rng)
    r = sample_covariance(snapshots(x, taps))
    if algo == "PI":
        w = power_inversion(r, rx.array.ref_port, taps)
    elif algo == "MVDR":
        c = np.stack([st_steering(rx.assumed_steering(s), taps) for s in sats], axis=1)
        w = mvdr(r, c)
    else:
        raise ValueError(algo)
    return w, evaluate(rx, w, taps, jammers, sats)


# --------------------------------------------------------------------------
# Experiment 1: tilt sweep, jammer and satellite almost co-located
# --------------------------------------------------------------------------

def experiment_tilt_sweep():
    tilts = np.array([0, 0.5, 1, 2, 5, 10, 20, 30, 45, 60, 90])
    sat = Emitter(12, 3, jones_rhcp(), label="sat 3 deg from jammer")
    rng = np.random.default_rng(10)

    configs = {
        "Fixed H antenna, no DSP": ArrayConfig(
            "fixed H", [Port("H", (0, 0), orient_deg=0.0)]),  # jammer lies in its H-plane
        "1 dual-pol patch, adaptive pol only": ArrayConfig(
            "1x dual", [Port("R", (0, 0)), Port("L", (0, 0))]),
    }
    for make in ARRAYS:
        cfg = make()
        configs[cfg.name] = cfg

    res = {name: {"inr": [], "cn0": []} for name in configs}
    for t in tilts:
        jam = [Emitter(10, 0, jones_linear(t), 60, bw_hz=8e6, label="J")]
        for name, cfg in configs.items():
            rx = make_rx(cfg, n_samples=2 ** 14)
            if cfg.n == 1:
                w, taps = np.ones(1, complex), 1
                ev = evaluate(rx, w, taps, jam, [sat])
            else:
                _, ev = run_processor(rx, jam, [sat], "PI", 5, rng)
            res[name]["inr"].append(ev["inr_out_db"])
            res[name]["cn0"].append(ev["cn0"][0])
    base = unprotected(Receiver(array_rhcp12(), n_samples=2 ** 14), [], [sat])

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    xs = np.maximum(tilts, 0.2)
    for name, r in res.items():
        ax[0].semilogx(xs, r["inr"], "o-", label=name)
        ax[1].semilogx(xs, r["cn0"], "o-", label=name)
    ax[0].axhline(0, color="k", lw=0.8, ls=":")
    ax[0].set(title="Residual jammer at the output (60 dB J/N, 8 MHz)",
              xlabel="Jammer tilt away from vertical [deg] (0 plotted at 0.2)",
              ylabel="Jammer-to-noise ratio at output [dB]")
    ax[1].axhline(TRACK_DB_HZ, color="r", lw=1, ls="--", label="tracking threshold")
    ax[1].axhline(base["cn0_clean"][0], color="g", lw=1, ls=":", label="single RHCP patch, no jammer")
    ax[1].set(title="C/N0 of the satellite 3 deg away from the jammer",
              xlabel="Jammer tilt away from vertical [deg] (0 plotted at 0.2)",
              ylabel="C/N0 [dB-Hz]", ylim=(-10, 55))
    for a in ax:
        a.grid(True, which="both", alpha=0.3)
    ax[1].legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "exp1_tilt_sweep.png", dpi=130)
    plt.close(fig)

    lines = ["## Experiment 1 - jammer tilt sweep (jammer el 10 / az 0, satellite el 12 / az 3)", "",
             "Power inversion, 5 taps. Values: output J/N [dB] / satellite C/N0 [dB-Hz].", "",
             "| Tilt [deg] | " + " | ".join(res) + " |",
             "|---|" + "---|" * len(res)]
    for i, t in enumerate(tilts):
        cells = [f"{r['inr'][i]:.1f} / {r['cn0'][i]:.1f}" for r in res.values()]
        lines.append(f"| {t:g} | " + " | ".join(cells) + " |")
    return lines


# --------------------------------------------------------------------------
# Experiment 2: full scenario
# --------------------------------------------------------------------------

def jammers_default():
    return [
        Emitter(5, 30, jones_linear(5), 65, bw_hz=8e6, label="J1 linear wideband"),
        Emitter(12, 122, jones_linear(20), 60, bw_hz=8e6, label="J2 linear, next to G06"),
        Emitter(8, 200, jones_linear(70), 60, bw_hz=4e6, f0_hz=1e6, label="J3 near-horizontal, next to G08"),
        Emitter(20, 280, jones_rhcp(), 55, bw_hz=2e6, label="J4 RHCP smart jammer"),
        Emitter(3, 330, jones_linear(0), 70, cw=True, f0_hz=0.3e6, label="J5 CW"),
        Emitter(30, 75, jones_elliptical(35, 15), 55, bw_hz=8e6, label="J6 elliptical"),
    ]


def experiment_full_scenario():
    sats, jams = satellites_default(), jammers_default()
    rng = np.random.default_rng(20)
    runs = [("PI", 1, True), ("PI", 5, True), ("MVDR", 5, True), ("MVDR", 5, False)]
    table, results = [], {}
    base = unprotected(Receiver(array_rhcp12()), jams, sats)
    for make in ARRAYS:
        cfg = make()
        receivers = {True: make_rx(cfg), False: make_rx(cfg, equalized=False)}
        for algo, taps, eq in runs:
            rx = receivers[eq]
            w, ev = run_processor(rx, jams, sats, algo, taps, rng)
            if eq:
                results[(cfg.name, algo, taps)] = (rx, w, ev)
            proc = f"{algo}, {taps} taps" + ("" if eq else ", **no channel equalization**")
            table.append((cfg.name, proc, ev["inr_out_db"],
                          int((ev["cn0"] >= TRACK_DB_HZ).sum()), ev["cn0"]))

    # bar chart of C/N0 per satellite (MVDR, 5 taps)
    fig, ax = plt.subplots(figsize=(12, 4.8))
    width = 0.2
    idx = np.arange(len(sats))
    ax.bar(idx - 1.5 * width, base["cn0_clean"], width, color="0.8", label="single RHCP patch, no jamming")
    for k, make in enumerate(ARRAYS):
        name = make().name
        ax.bar(idx + (k - 0.5) * width, results[(name, "MVDR", 5)][2]["cn0"], width, label=name)
    ax.axhline(TRACK_DB_HZ, color="r", ls="--", lw=1, label="tracking threshold")
    ax.set_xticks(idx, [f"{s.label}\nel {s.el_deg:g}" for s in sats])
    ax.set(ylabel="C/N0 [dB-Hz]", ylim=(0, 62),
           title=f"Per-satellite C/N0 with 6 jammers (MVDR, 5 taps). Unprotected receiver: "
                 f"J/N = {base['inr_in_db']:.0f} dB, every satellite lost")
    ax.legend(fontsize=8, ncol=3, loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "exp2_cn0_per_satellite.png", dpi=130)
    plt.close(fig)

    # sky maps of the blind power-inversion pattern
    el_g, az_g = np.linspace(0, 90, 46), np.linspace(0, 360, 181)
    fig, axes = plt.subplots(2, 3, figsize=(14, 9.5), subplot_kw={"projection": "polar"})
    for col, make in enumerate(ARRAYS):
        name = make().name
        rx, w, _ = results[(name, "PI", 5)]
        for row, (pol, jones) in enumerate([("RHCP waves (satellites)", jones_rhcp()),
                                            ("vertical linear waves", jones_linear(0))]):
            a = axes[row, col]
            g = sky_gain(rx, w, 5, jones, el_g, az_g)
            m = a.pcolormesh(np.radians(az_g), 90 - el_g, g, vmin=-40, vmax=15, cmap="viridis",
                             shading="auto")
            for j in jams:
                a.plot(np.radians(j.az_deg), 90 - j.el_deg, "rx", ms=10, mew=2.5)
            for s in sats:
                a.plot(np.radians(s.az_deg), 90 - s.el_deg, "o", mfc="none", mec="w", ms=8, mew=1.5)
            a.set_theta_zero_location("N")
            a.set_theta_direction(-1)
            a.set_rlim(0, 90)
            a.set_yticklabels([])
            a.set_title(f"{name}\nresponse to {pol}", fontsize=9)
    fig.colorbar(m, ax=axes, shrink=0.6, label="output SNR gain [dB]")
    fig.suptitle("Power-inversion patterns (x = jammer, o = satellite). Centre = zenith, edge = horizon")
    fig.savefig(OUT / "exp2_sky_maps.png", dpi=120)
    plt.close(fig)

    lines = ["## Experiment 2 - 9 satellites, 6 jammers", "",
             "| Jammer | el / az | Polarization | J/N [dB] |", "|---|---|---|---|"]
    for j in jams:
        lines.append(f"| {j.label} | {j.el_deg:g} / {j.az_deg:g} | "
                     f"({j.jones[0]:.2f}, {j.jones[1]:.2f}) | {j.power_db:g} |")
    lines += ["", f"Unprotected single RHCP patch: in-band J/N = {base['inr_in_db']:.1f} dB, "
                  f"satellites tracked = {int((base['cn0'] >= TRACK_DB_HZ).sum())} / {len(sats)}", "",
              "| Array | Processing | Worst output J/N [dB] | Satellites tracked | C/N0 per satellite [dB-Hz] |",
              "|---|---|---|---|---|"]
    for name, proc, inr, n_ok, cn0 in table:
        lines.append(f"| {name} | {proc} | {inr:.1f} | {n_ok} / {len(sats)} | "
                     + ", ".join(f"{c:.0f}" for c in cn0) + " |")
    return lines


# --------------------------------------------------------------------------
# Experiment 3: Monte Carlo over the number of jammers
# --------------------------------------------------------------------------

def experiment_jammer_count(trials=25):
    sats = satellites_default()
    counts = np.arange(1, 15)
    rng = np.random.default_rng(30)
    stats, raw = {}, {}
    for make in ARRAYS:
        cfg = make()
        rx_eq = make_rx(cfg, n_samples=2 ** 13)
        rx_raw = make_rx(cfg, n_samples=2 ** 13, equalized=False)
        tracked = np.zeros((len(counts), trials))
        tracked_raw = np.zeros((len(counts), trials))
        for ci, nj in enumerate(counts):
            for t in range(trials):
                jams = [Emitter(rng.uniform(0, 25), rng.uniform(0, 360),
                                jones_elliptical(rng.uniform(0, 180), rng.uniform(-10, 10)),
                                rng.uniform(50, 70), bw_hz=8e6) for _ in range(nj)]
                _, ev = run_processor(rx_eq, jams, sats, "MVDR", 5, rng)
                tracked[ci, t] = (ev["cn0"] >= TRACK_DB_HZ).sum()
                _, ev = run_processor(rx_raw, jams, sats, "MVDR", 5, rng)
                tracked_raw[ci, t] = (ev["cn0"] >= TRACK_DB_HZ).sum()
        stats[cfg.name], raw[cfg.name] = tracked, tracked_raw

    fig, ax = plt.subplots(figsize=(9, 5))
    for k, (name, tr) in enumerate(stats.items()):
        color = f"C{k}"
        ax.plot(counts, np.median(tr, axis=1), "o-", color=color, label=name + ", equalized")
        ax.fill_between(counts, np.percentile(tr, 25, axis=1), np.percentile(tr, 75, axis=1),
                        color=color, alpha=0.15)
        ax.plot(counts, np.median(raw[name], axis=1), "x--", color=color, alpha=0.7,
                label=name + ", raw channels")
    ax.axvline(11, color="k", ls=":", lw=1)
    ax.text(11.1, 0.5, "N-1 = 11\nspatial-pol DoF", fontsize=8)
    ax.set(xlabel="Number of jammers (random direction, near-linear polarization, 50-70 dB J/N)",
           ylabel=f"Satellites with C/N0 >= {TRACK_DB_HZ:g} dB-Hz (of {len(sats)})",
           title=f"Monte Carlo, {trials} trials per point, MVDR 5 taps (median, IQR shaded)",
           ylim=(-0.3, len(sats) + 0.3))
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "exp3_jammer_count.png", dpi=130)
    plt.close(fig)

    lines = ["## Experiment 3 - number of jammers (median satellites tracked of 9, MVDR 5 taps)", "",
             "Each cell: equalized channels / raw channels.", "",
             "| Jammers | " + " | ".join(stats) + " |", "|---|" + "---|" * len(stats)]
    for ci, nj in enumerate(counts):
        lines.append(f"| {nj} | " + " | ".join(
            f"{np.median(stats[n][ci]):.0f} / {np.median(raw[n][ci]):.0f}" for n in stats) + " |")
    return lines


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    report = ["# CRPA simulation results", ""]
    for exp in (experiment_tilt_sweep, experiment_full_scenario, experiment_jammer_count):
        print(f"running {exp.__name__} ...", flush=True)
        report += exp() + [""]
    (OUT / "summary.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
