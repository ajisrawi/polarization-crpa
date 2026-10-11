"""
openEMS FDTD model of one CRPA element.

    tools\\emvenv\\Scripts\\python.exe hardware\\em\\em_element.py [params.json] --tag NAME [--quick]

Two element designs share one geometry description (param "design"):
  "air" (rev C, all-band): air-spaced stacked patch on thin FR4 carriers.
        feed ground (z=0) -- air h1 -- FR4 carrier with patch A on its BOTTOM and a capacitive
        feed disk on its TOP (probe passes a clearance hole in patch A) -- air h2 --
        FR4 carrier with parasitic patch C on its bottom.
  "tmm" (rev B, compact): TMM3 block with patches A/B/C and buried feed disks.
Both sit on a feed-board ground tied to the aluminium plate by metal posts.

--quick : probe 1 only, 0.8-2.2 GHz sweep, S11 + input impedance (locating resonances).
default : both probes, S-matrix + far fields, ideal 90-deg hybrid applied in post-processing.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ.setdefault("CSXCAD_INSTALL_PATH", str(ROOT / "tools" / "openEMS" / "openEMS"))

import numpy as np  # noqa: E402
from CSXCAD import ContinuousStructure  # noqa: E402
from openEMS import openEMS  # noqa: E402
from openEMS.physical_constants import C0, EPS0, Z0  # noqa: E402

BANDS = {"L5/E5a/B2a": (1164e6, 1189e6), "E5b/B2b/G3": (1195e6, 1219e6), "L2": (1217e6, 1238e6),
         "G2": (1237e6, 1254e6), "E6/B3": (1258e6, 1300e6), "B1I": (1559e6, 1563e6),
         "L1/E1/B1C": (1563e6, 1588e6), "G1": (1593e6, 1610e6)}

DEFAULTS = {
    "air": {"design": "air", "ground": 124.0, "posts": 58.0, "post_h": 8.762, "plate": 240.0,
            "h1": 12.0, "h2": 6.0, "t_fr4": 0.8, "er_fr4": 4.3, "tan_fr4": 0.02,
            "L_A": 102.0, "L_C": 80.0, "carrier": 124.0,
            "probe_off": 28.0, "probe_r": 0.65, "disk_d": 7.8, "hole_d": 4.0},
    "air4": {"design": "air4", "ground": 124.0, "posts": 58.0, "post_h": 8.762, "plate": 240.0,
             "h1": 12.0, "h2": 6.0, "t_fr4": 0.8, "er_fr4": 4.3, "tan_fr4": 0.02,
             "L_A": 102.0, "L_C": 72.0, "carrier": 124.0,
             "probe_off": 28.0, "probe_r": 0.65, "disk_d": 7.8, "hole_d": 4.0,
             "probe_off_hi": 14.0, "excite": 2},
    "tmm": {"design": "tmm", "ground": 96.0, "posts": 44.0, "post_h": 8.762, "plate": 200.0,
            "er": 3.45, "tan_d": 0.002, "t_A1": 8.89, "t_A2": 0.762, "t_B": 3.175, "t_C": 7.62,
            "L_A": 64.34, "L_B": 57.91, "L_C": 48.1, "slab": 80.0,
            "probe_off": 10.0, "probe_r": 0.65, "disk_d": 7.0},
}
DEFAULT = DEFAULTS["tmm"]


def r4(x):
    return round(float(x), 4)


MIN_CELL = 0.2   # mm. Lines closer than this create microscopic cells and a tiny timestep.


def merge_lines(exact, filler, min_cell=MIN_CELL, critical=()):
    """Build mesh lines with a priority order:
      1. critical lines (port positions, zero-thickness sheet planes) are ALWAYS kept,
         otherwise openEMS silently drops the port excitation / the sheet;
      2. exact geometry lines are kept if >= min_cell from every line kept so far;
      3. filler lines likewise.
    """
    out = sorted(set(round(float(x), 4) for x in critical))

    def add(values):
        for v in sorted(set(round(float(x), 4) for x in values)):
            i = int(np.searchsorted(out, v))
            near = [abs(out[j] - v) for j in (i - 1, i) if 0 <= j < len(out)]
            if not near or min(near) >= min_cell:
                out.insert(i, v)
    add(exact)
    add(filler)
    return out


def geometry(p, f0):
    """Primitive lists for either design. All z values rounded once (sheets must sit on mesh lines)."""
    g = {"sheets": [], "dielectrics": [], "disks": [], "holes": [], "z_marks": []}
    probes_xy = [(p["probe_off"], 0.0), (0.0, p["probe_off"])]
    g["probe_tops"] = None
    if p["design"] in ("air", "air4"):
        zA = r4(p["h1"])
        zA_top = r4(zA + p["t_fr4"])
        zC = r4(zA_top + p["h2"])
        zC_top = r4(zC + p["t_fr4"])
        kap = 2 * np.pi * f0 * EPS0 * p["er_fr4"] * p["tan_fr4"]
        c = p["carrier"] / 2
        g["dielectrics"] += [("FR4", p["er_fr4"], kap, (-c, -c, zA), (c, c, zA_top)),
                             ("FR4", p["er_fr4"], kap, (-c, -c, zC), (c, c, zC_top))]
        g["sheets"] += [(p["L_A"], zA), (p["L_C"], zC)]
        for x, y in probes_xy:
            g["holes"].append((x, y, p["hole_d"] / 2, zA))
            g["disks"].append((x, y, p["disk_d"] / 2, zA_top))
        g["probe_top"] = zA_top
        g["z_top"] = zC_top
        g["z_marks"] = [zA, zA_top, zC, zC_top] + list(np.linspace(0, zA, 6)) + list(np.linspace(zA_top, zC, 4))
        if p["design"] == "air4":
            hi = [(-p["probe_off_hi"], 0.0), (0.0, -p["probe_off_hi"])]
            probes_xy = probes_xy + hi
            if p.get("coax_hi"):
                # upper probes are semi-rigid coax: shield = PEC post ground -> patch A (near A's
                # centre, where the lower-band field is ~0); the port sits on patch A and only the
                # inner conductor spans patch A -> patch C. The 12 mm coax section is equal for
                # both probes, so it only adds a common phase (ignored).
                g["coax_posts"] = [(x, y, p.get("coax_r", 0.6), 0.0, zA) for x, y in hi]
                g["port_base"] = [0.0, 0.0, zA, zA]
                g["z_marks"] += [r4(zA + 0.5)]
            else:
                # upper-band probes: through clearance holes in patch A, soldered to patch C
                for x, y in hi:
                    g["holes"].append((x, y, p["hole_d"] / 2, zA))
            g["probe_tops"] = [zA_top, zA_top, zC, zC]
    else:
        zA1 = r4(p["t_A1"])
        zA = r4(zA1 + p["t_A2"])
        zB = r4(zA + p["t_B"])
        zC = r4(zB + p["t_C"])
        kap = 2 * np.pi * f0 * EPS0 * p["er"] * p["tan_d"]
        s = p["slab"] / 2
        g["dielectrics"].append(("TMM3", p["er"], kap, (-s, -s, 0), (s, s, zC)))
        g["sheets"] += [(p["L_A"], zA), (p["L_B"], zB), (p["L_C"], zC)]
        for x, y in probes_xy:
            g["disks"].append((x, y, p["disk_d"] / 2, zA1))
        g["probe_top"] = zA1
        g["z_top"] = zC
        g["z_marks"] = [zA1, zA, zB, zC] + list(np.linspace(0, zA1, 6)) + list(np.linspace(zB, zC, 4))
    g["probes"] = probes_xy
    return g


def build_and_run(p, port_on, sim_dir, f0=1.4e9, fc=0.35e9, end_db=-40):
    unit = 1e-3
    fdtd = openEMS(EndCriteria=10 ** (end_db / 10), NrTS=200000)
    fdtd.SetGaussExcite(f0, fc)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(unit)
    geo = geometry(p, f0)
    gnd = p["ground"] / 2
    zp = -r4(p["post_h"])
    post_xy = [(sx * p["posts"], sy * p["posts"]) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if (sx, sy) != (0, 0)]

    pec = csx.AddMetal("pec")
    pec.AddBox([-gnd, -gnd, 0], [gnd, gnd, 0], priority=10)
    pl = p["plate"] / 2
    pec.AddBox([-pl, -pl, zp], [pl, pl, zp], priority=10)
    for x, y in post_xy:
        pec.AddCylinder([x, y, zp], [x, y, 0], 2.75, priority=10)
    for name, er, kap, a, b in geo["dielectrics"]:
        csx.AddMaterial(f"{name}_{a[2]}", epsilon=er, kappa=kap).AddBox(list(a), list(b), priority=1)
    for L, z in geo["sheets"]:
        h = round(L / 2, 3)
        pec.AddBox([-h, -h, z], [h, h, z], priority=10)
    air = csx.AddMaterial("hole_air", epsilon=1.0)
    for x, y, r, z in geo["holes"]:                       # clearance ring in patch A
        air.AddCylinder([x, y, z - 0.01], [x, y, z + 0.01], r, priority=15)
    ports = []
    tops = geo["probe_tops"] or [geo["probe_top"]] * len(geo["probes"])
    bases = geo.get("port_base") or [0.0] * len(geo["probes"])
    for x, y, r, z0_, z1_ in geo.get("coax_posts", []):
        pec.AddCylinder([x, y, z0_], [x, y, z1_], r, priority=21)
    c_hi = p.get("series_c_hi_pF")                      # feed-board series cap on the upper probes
    for k, (x, y) in enumerate(geo["probes"]):
        zb = bases[k]
        z0 = zb + 0.5
        if c_hi and k >= 2:
            cap = csx.AddLumpedElement(f"Cser{k + 1}", ny=2, caps=True, C=c_hi * 1e-12, R=1e-3, LEtype=1)
            cap.AddBox([x, y, z0], [x, y, z0 + 0.5], priority=22)
            z0 += 0.5
        pr = p.get("inner_r", 0.2) if bases[k] > 0 else p["probe_r"]
        pec.AddCylinder([x, y, z0], [x, y, tops[k]], pr, priority=20)
        ports.append(fdtd.AddLumpedPort(k + 1, 50, [x, y, zb], [x, y, zb + 0.5], "z",
                                        excite=1.0 if k == port_on else 0.0, priority=25))
    for x, y, r, z in geo["disks"]:
        pec.AddCylinder([x, y, z - 0.035], [x, y, z], r, priority=20)

    # ---- mesh: fine over the element, air resolution outside -----------------
    lam_min = C0 / (f0 + fc) / unit
    er_max = max([d[1] for d in geo["dielectrics"]] + [1.0])
    res_air = lam_min / 20
    res_fine = lam_min / 20 / np.sqrt(er_max)
    pad = C0 / (f0 - fc) / unit / 4 + 10
    xy = [-gnd - pad, gnd + pad, -pl, pl, -gnd, gnd]
    for name, er, kap, a, b in geo["dielectrics"]:
        xy += [a[0], b[0]]
    for L, _ in geo["sheets"]:
        xy += [-round(L / 2, 3), round(L / 2, 3)]
    for x, y in geo["probes"]:
        for v in (x, y):
            xy += [v - p["probe_r"], v, v + p["probe_r"]]
    for x, y, r, _, _ in geo.get("coax_posts", []):
        xy += [x - r, x + r, y - r, y + r]
    for x, y, r, _ in geo["disks"] + geo["holes"]:
        xy += [x - r, x + r, y - r, y + r]
    for x, y in post_xy:
        xy += [x - 2.75, x + 2.75, y - 2.75, y + 2.75]
    xy_lines = merge_lines(xy, np.arange(-gnd, gnd + 1e-9, res_fine))
    for ax in "xy":
        mesh.AddLine(ax, xy_lines)
        mesh.SmoothMeshLines(ax, res_air, 1.4)
    z = [zp - pad, zp, 0, 0.5, geo["probe_top"], geo["z_top"], geo["z_top"] + pad]
    if p.get("series_c_hi_pF"):
        z.append(1.0)
    mesh.AddLine("z", merge_lines(z, geo["z_marks"]))
    mesh.SmoothMeshLines("z", res_air, 1.4)
    for ax in "xyz":
        d = np.diff(np.array(mesh.GetLines(ax)))
        if d.min() < MIN_CELL * 0.99:
            raise RuntimeError(f"mesh {ax}: smallest cell {d.min():.4f} mm < {MIN_CELL} mm")
    p["_min_cell_mm"] = {ax: round(float(np.diff(np.array(mesh.GetLines(ax))).min()), 3) for ax in "xyz"}
    nf2ff = fdtd.CreateNF2FFBox(opt_resolution=[res_air] * 3)
    n_cells = len(mesh.GetLines("x")) * len(mesh.GetLines("y")) * len(mesh.GetLines("z"))
    if p.get("write_xml_only"):
        csx.Write2XML(str(Path(sim_dir) / "geometry.xml"))
        return None, ports, nf2ff, n_cells, geo["z_top"]
    fdtd.Run(str(sim_dir), cleanup=True, verbose=0, numThreads=os.cpu_count())
    return fdtd, ports, nf2ff, n_cells, geo["z_top"]


def far_fields(nf2ff, sim_dir, freqs, theta, phi, centre):
    r = nf2ff.CalcNF2FF(str(sim_dir), freqs, theta, phi, center=centre, read_cached=False, verbose=0)
    return np.array(r.E_theta), np.array(r.E_phi)


def work_dir(tag):
    return Path(os.environ.get("EM_WORK", ROOT / "tools" / "em_runs")) / tag


def quick_sweep(p, tag, fmin=0.8e9, fmax=2.2e9):
    """Probe 1 only, wideband: S11, coupling and input impedance."""
    ex = int(p.get("excite", 0))
    work = work_dir(tag) / f"port{ex + 1}"
    work.mkdir(parents=True, exist_ok=True)
    fdtd, ports, nf2ff, n_cells, _ = build_and_run(p, ex, work, f0=(fmin + fmax) / 2, fc=(fmax - fmin) / 2,
                                                   end_db=-30)
    f = np.linspace(fmin, fmax, 561)
    for pt in ports:
        pt.CalcPort(str(work), f)
    s11 = ports[ex].uf_ref / ports[ex].uf_inc
    other = 1 if ex == 0 else 0
    s21 = ports[other].uf_ref / ports[ex].uf_inc
    zin = ports[ex].uf_tot / ports[ex].if_tot
    if len(ports) > 2:
        p["_coupling_to_ports_dB"] = {k + 1: round(float(np.median(20 * np.log10(np.abs(
            ports[k].uf_ref / ports[ex].uf_inc)))), 1) for k in range(len(ports)) if k != ex}
    out = HERE / "results"
    out.mkdir(parents=True, exist_ok=True)
    s11_db = 20 * np.log10(np.abs(s11))
    dips = [float(f[i]) for i in range(1, len(f) - 1)
            if s11_db[i] < s11_db[i - 1] and s11_db[i] < s11_db[i + 1] and s11_db[i] < -3]
    below10 = f[s11_db < -10]
    res = {"tag": tag, "params": p, "cells_M": round(n_cells / 1e6, 2),
           "s11_dips_MHz": [round(d / 1e6, 1) for d in dips],
           "s11_db_min": round(float(s11_db.min()), 2),
           "below_-10dB_MHz": [round(below10.min() / 1e6), round(below10.max() / 1e6)] if len(below10) else None,
           "band_worst_s11_db": {k: round(float(s11_db[(f >= lo) & (f <= hi)].max()), 2)
                                 for k, (lo, hi) in BANDS.items()}}
    (out / f"{tag}.json").write_text(json.dumps(res, indent=2))
    np.savez(out / f"{tag}.npz", f=f, s11=s11, s21=s21, zin=zin)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
    ax[0].plot(f / 1e6, s11_db, label="S11 (probe 1)")
    ax[0].plot(f / 1e6, 20 * np.log10(np.abs(s21)), ":", label="S21 coupling")
    ax[0].axhline(-10, color="k", lw=0.8)
    ax[1].plot(f / 1e6, zin.real, label="Re Zin")
    ax[1].plot(f / 1e6, zin.imag, label="Im Zin")
    ax[1].axhline(50, color="k", lw=0.8, ls=":")
    ax[1].set_ylim(-150, 250)
    for a in ax:
        for lo, hi in BANDS.values():
            a.axvspan(lo / 1e6, hi / 1e6, color="g", alpha=0.07)
        a.grid(alpha=0.3)
        a.legend(fontsize=8)
        a.set_xlabel("MHz")
    ax[0].set(ylabel="dB", title=f"{tag}: S11 / coupling", ylim=(-30, 0))
    ax[1].set(ylabel="ohm", title="input impedance at the probe port")
    fig.tight_layout()
    fig.savefig(out / f"{tag}.png", dpi=120)
    print(json.dumps(res, indent=1), flush=True)
    return res


def full(p, tag):
    """Both probes: S-matrix, ideal-hybrid RHCP match, gain, axial ratio, patterns."""
    out = HERE / "results"
    out.mkdir(parents=True, exist_ok=True)
    f = np.linspace(1.10e9, 1.70e9, 241)
    f_ff = np.array([1176.45e6, 1207.14e6, 1227.6e6, 1246e6, 1278.75e6, 1561.1e6, 1575.42e6, 1602e6])
    theta = np.arange(0, 91, 5.0)
    phi = np.array([0.0, 45.0, 90.0, 135.0])
    n_ports = 4 if p["design"] == "air4" else 2
    S = np.zeros((n_ports, n_ports, len(f)), complex)
    E, pinc = [], []
    for port_on in range(n_ports):
        sim_dir = work_dir(tag) / f"port{port_on + 1}"
        sim_dir.mkdir(parents=True, exist_ok=True)
        fdtd, ports, nf2ff, n_cells, z_top = build_and_run(p, port_on, sim_dir)
        for pt in ports:
            pt.CalcPort(str(sim_dir), f)
        a = ports[port_on].uf_inc
        for k, pt in enumerate(ports):
            S[k, port_on] = pt.uf_ref / a
        for pt in ports:
            pt.CalcPort(str(sim_dir), f_ff)
        pinc.append(np.real(ports[port_on].P_inc))
        E.append(far_fields(nf2ff, sim_dir, f_ff, theta, phi, [0, 0, z_top / 2 * 1e-3]))
        print(f"port {port_on + 1} done ({n_cells / 1e6:.2f} M cells)", flush=True)

    # per-band ideal hybrids (and an ideal diplexer selecting the band's probe pair):
    # RHCP input -> X probe 1/sqrt2, Y probe -j/sqrt2 (Y lags X by 90 deg)
    def weights(freq, hand):
        w = np.zeros(n_ports, complex)
        base = 2 if (n_ports == 4 and freq > 1.4e9) else 0
        w[base], w[base + 1] = 1 / np.sqrt(2), (-1j if hand == "R" else 1j) / np.sqrt(2)
        return w
    gamma_r = np.array([weights(fv, "R") @ S[:, :, i] @ weights(fv, "R") for i, fv in enumerate(f)])
    to_load = np.array([weights(fv, "L") @ S[:, :, i] @ weights(fv, "R") for i, fv in enumerate(f)])
    Wff = np.array([weights(fv, "R") for fv in f_ff])               # (F_ff, n_ports)
    Eth = sum(Wff[:, k][:, None, None] * E[k][0] / np.sqrt(pinc[k])[:, None, None] for k in range(n_ports))
    Eph = sum(Wff[:, k][:, None, None] * E[k][1] / np.sqrt(pinc[k])[:, None, None] for k in range(n_ports))
    e_r = (Eth + 1j * Eph) / np.sqrt(2)
    e_l = (Eth - 1j * Eph) / np.sqrt(2)
    g_r = 4 * np.pi * np.abs(e_r) ** 2 / (2 * Z0)
    g_l = 4 * np.pi * np.abs(e_l) ** 2 / (2 * Z0)
    ar = 20 * np.log10((np.abs(e_r) + np.abs(e_l)) / np.maximum(np.abs(np.abs(e_r) - np.abs(e_l)), 1e-12))
    db = lambda x: 10 * np.log10(np.maximum(x, 1e-12))
    rl = -20 * np.log10(np.abs(gamma_r))
    s11 = np.where(f > 1.4e9, 20 * np.log10(np.abs(S[-2, -2])), 20 * np.log10(np.abs(S[0, 0])))
    bands = {k: {"worst_RL_hybrid_dB": round(float(rl[(f >= lo) & (f <= hi)].min()), 1),
                 "worst_S11_probe_dB": round(float(s11[(f >= lo) & (f <= hi)].max()), 1)}
             for k, (lo, hi) in BANDS.items()}
    i10 = int(np.argmin(np.abs(theta - 80)))
    ff = {f"{fv / 1e6:.2f}": {"RHCP_gain_zenith_dBic": round(float(db(g_r[i, 0, 0])), 2),
                              "AR_zenith_dB": round(float(ar[i, 0, 0]), 2),
                              "RHCP_gain_el10_dBic_mean": round(float(db(g_r[i, i10].mean())), 2),
                              "LHCP_gain_zenith_dBic": round(float(db(g_l[i, 0, 0])), 2)}
          for i, fv in enumerate(f_ff)}
    result = {"tag": tag, "params": p, "cells_M": round(n_cells / 1e6, 2), "bands": bands, "far_field": ff}
    (out / f"{tag}.json").write_text(json.dumps(result, indent=2))
    np.savez(out / f"{tag}_full.npz", f=f, S=S, f_ff=f_ff, theta=theta, phi=phi, g_r=g_r, g_l=g_l, ar=ar)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    ax[0].plot(f / 1e6, -rl, label="RHCP input through ideal hybrid")
    ax[0].plot(f / 1e6, s11, "--", label="single probe S11")
    ax[0].plot(f / 1e6, 20 * np.log10(np.abs(S[1, 0])), ":", label="probe coupling S21")
    ax[0].plot(f / 1e6, 20 * np.log10(np.abs(to_load)), "-.", label="lost in hybrid load")
    ax[0].axhline(-10, color="k", lw=0.8)
    ax[0].set(xlabel="MHz", ylabel="dB", title=f"{tag}: impedance", ylim=(-35, 0))
    for lo, hi in BANDS.values():
        ax[0].axvspan(lo / 1e6, hi / 1e6, color="g", alpha=0.07)
    ax[0].legend(fontsize=7)
    ax[1].plot(f_ff / 1e6, db(g_r[:, 0, 0]), "o-", label="RHCP zenith")
    ax[1].plot(f_ff / 1e6, db(g_r[:, i10].mean(axis=1)), "s-", label="RHCP el 10 (mean)")
    ax[1].plot(f_ff / 1e6, db(g_l[:, 0, 0]), "x--", label="LHCP zenith")
    ax[1].set(xlabel="MHz", ylabel="dBic", title="realized gain")
    ax[1].legend(fontsize=7)
    for i, fv in enumerate(f_ff):
        ax[2].plot(90 - theta, db(g_r[i, :, 0]), label=f"{fv / 1e6:.0f}")
    ax[2].set(xlabel="elevation [deg]", ylabel="RHCP gain [dBic]", title="elevation cut, phi=0", ylim=(-25, 8))
    ax[2].legend(fontsize=7, ncol=2)
    for a in ax:
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{tag}.png", dpi=120)
    print(json.dumps({"bands": bands, "far_field": ff}, indent=1))


def main():
    args = sys.argv[1:]
    tag = "run"
    if "--tag" in args:
        i = args.index("--tag")
        tag = args[i + 1]
        del args[i:i + 2]
    quick = "--quick" in args
    if quick:
        args.remove("--quick")
    user = json.loads(Path(args[0]).read_text()) if args else {}
    p = dict(DEFAULTS[user.get("design", "tmm")])
    p.update(user)
    return quick_sweep(p, tag) if quick else full(p, tag)


if __name__ == "__main__":
    main()
