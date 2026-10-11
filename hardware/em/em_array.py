"""
openEMS full-array model: 12 elements of the tuned rev C design on the rev A plate layout.

    tools\\emvenv\\Scripts\\python.exe hardware\\em\\em_array.py [--elements 0,1,..] [--check]

Elements (hardware/antenna/array_plate/element_positions.json, 125 mm pitch):
  R  : rev C circular element (lower pair disk-fed on patch A, upper pair coax-fed on patch C),
       RHCP: Y probes delayed by a quarter period at each band centre
  H  : rev C linear element: one lower + one upper probe on the pol_deg ray
  V  : 51 mm brass monopole on the plate
  L_tilted : rev C circular element, LHCP, mounted on a vertical bracket facing az 0.
       MODEL SIMPLIFICATION: boresight at 0 deg elevation (90 deg rotation, keeps every
       primitive on the rectilinear grid) instead of the hardware's 10 deg.
One run per element (all of its ports driven together, the 90 deg via an excitation delay),
all other ports terminated in 50 ohm. Saves per-element embedded far fields + coupling.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ.setdefault("CSXCAD_INSTALL_PATH", str(ROOT / "tools" / "openEMS" / "openEMS"))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from CSXCAD import ContinuousStructure  # noqa: E402
from openEMS import openEMS  # noqa: E402
from openEMS.physical_constants import C0, EPS0  # noqa: E402

import em_element as em  # noqa: E402

P = dict(em.DEFAULTS["air4"])
P.update(json.loads((HERE / "params" / "air4_c9.json").read_text()))
ELEMENTS = json.loads((ROOT / "hardware" / "antenna" / "array_plate" / "element_positions.json").read_text())
PLATE_X, PLATE_Y = (-197.5, 197.5), (-197.5, 287.5)        # model coords (y = north)
Z_PLATE = -P["post_h"]
F_LO, F_HI = 1.23e9, 1.585e9
F_FF = np.array([1176.45e6, 1227.6e6, 1278.75e6, 1575.42e6, 1602e6])
ARRAY_MIN_CELL = float(os.environ.get("ARRAY_MIN_CELL", 0.4))   # mm; 0.2 mm would make each run ~2.5 h
PORT_LEN = float(os.environ.get("ARRAY_PORT_LEN", 0.4))           # mm; port and series-cap sections (12.0 / 12.4 / 12.8 mm planes)
ARRAY_RES_FINE = 6.0      # mm over each element footprint (lambda/20 in air at 1.75 GHz is 8.6 mm)


class Placement:
    """Local element coords -> global. Flat: translate. Tilted: rotate -90 deg about x, so
    local z (boresight) -> global +y and local y -> global -z; everything stays axis-aligned."""

    def __init__(self, x0, y0, z0=0.0, tilted=False):
        self.o = np.array([x0, y0, z0])
        self.tilted = tilted

    def pt(self, p):
        x, y, z = p
        v = np.array([x, z, -y]) if self.tilted else np.array([x, y, z])
        return list(np.round(self.o + v, 4))

    def axis(self, local_axis):
        return {"x": "x", "y": "z", "z": "y"}[local_axis] if self.tilted else local_axis

    def ny(self, local_ny):
        return {0: 0, 1: 2, 2: 1}[local_ny] if self.tilted else local_ny


def add_element(csx, fdtd, pec, kind, pl, port_nr, excite, pol_deg=0.0, hand="R"):
    """Add one element; returns (ports, mesh-line dict)."""
    lines = {"x": [], "y": [], "z": []}       # exact geometry lines
    fill = {"x": [], "y": [], "z": []}        # fine-resolution filler lines
    crit = {"x": [], "y": [], "z": []}        # must-keep lines: ports, sheet planes

    def mark(pts, critical=False):
        for p in pts:
            for ax, v in zip("xyz", p):
                (crit if critical else lines)[ax].append(v)

    ports = []
    if kind == "V":
        x0, y0 = pl.o[0], pl.o[1]
        pec.AddCylinder([x0, y0, Z_PLATE + 0.5], [x0, y0, Z_PLATE + 51.0], 3.175, priority=20)
        ports.append(fdtd.AddLumpedPort(port_nr, 50, [x0, y0, Z_PLATE], [x0, y0, Z_PLATE + 0.5], "z",
                                        excite=1.0 if excite else 0.0, priority=25))
        mark([[x0 - 3.175, y0 - 3.175, Z_PLATE], [x0 + 3.175, y0 + 3.175, Z_PLATE + 51.0]])
        mark([[x0, y0, Z_PLATE], [x0, y0, Z_PLATE + 0.5]], critical=True)
        return ports, lines, fill, crit

    p = dict(P)
    if kind == "H":
        a = np.radians(pol_deg)
        lo = (p["probe_off"] * np.cos(a), p["probe_off"] * np.sin(a))
        hi = (-p["probe_off_hi"] * np.cos(a), -p["probe_off_hi"] * np.sin(a))
    geo = em.geometry(p, 1.4e9)
    if kind == "H":
        geo["probes"] = [lo, hi]
        geo["disks"] = [(lo[0], lo[1], p["disk_d"] / 2, geo["disks"][0][3])]
        geo["coax_posts"] = [(hi[0], hi[1], p["coax_r"], 0.0, geo["coax_posts"][0][4])]
        geo["port_base"] = [0.0, geo["port_base"][2]]
        geo["probe_tops"] = [geo["probe_tops"][0], geo["probe_tops"][2]]
    g = p["ground"] / 2

    def box(prop, a, b, prio):
        A, B = pl.pt(a), pl.pt(b)
        prop.AddBox(A, B, priority=prio)
        for i, ax in enumerate("xyz"):
            if abs(A[i] - B[i]) < 1e-9:          # zero-thickness sheet: its plane is critical
                crit[ax].append(A[i])
            else:
                lines[ax] += [A[i], B[i]]

    def cyl(prop, a, b, r, prio, plane=None):
        """plane: for thin cylinders (holes, disks) register only this local-z plane on the
        mesh, not both end caps (end caps 0.02 mm apart would knock the sheet plane out)."""
        A, B = pl.pt(a), pl.pt(b)
        prop.AddCylinder(A, B, r, priority=prio)
        if plane is None:
            mark([A, B])
        else:
            mark([pl.pt((a[0], a[1], plane))], critical=True)
        ax = [i for i in range(3) if abs(A[i] - B[i]) > 1e-9]
        for i in range(3):
            if not ax or i != ax[0]:
                lines["xyz"[i]] += [A[i] - r, A[i] + r]

    box(pec, (-g, -g, 0), (g, g, 0), 10)                                   # feed-board ground
    for sx in (-1, 0, 1):
        for sy in (-1, 0, 1):
            if (sx, sy) != (0, 0):
                cyl(pec, (sx * p["posts"], sy * p["posts"], -p["post_h"]), (sx * p["posts"], sy * p["posts"], 0), 2.75, 10)
    for name, er, kap, a, b in geo["dielectrics"]:
        box(csx.AddMaterial(f"{name}_{port_nr}_{a[2]}", epsilon=er, kappa=kap), a, b, 1)
    for L, z in geo["sheets"]:
        h = round(L / 2, 3)
        box(pec, (-h, -h, z), (h, h, z), 10)
    for x, y, r, z0_, z1_ in geo.get("coax_posts", []):
        cyl(pec, (x, y, z0_), (x, y, z1_), r, 21)
    for k, (x, y) in enumerate(geo["probes"]):
        upper = geo["port_base"][k] > 0
        zb = geo["port_base"][k]
        z0 = zb + PORT_LEN
        if upper and p.get("series_c_hi_pF"):
            cap = csx.AddLumpedElement(f"C{port_nr + k}", ny=pl.ny(2), caps=True,
                                       C=p["series_c_hi_pF"] * 1e-12, R=1e-3, LEtype=1)
            box(cap, (x, y, z0), (x, y, z0 + PORT_LEN), 22)
            z0 += PORT_LEN
        pr = p["inner_r"] if upper else p["probe_r"]
        cyl(pec, (x, y, z0), (x, y, geo["probe_tops"][k]), pr, 20)
        # quarter-period delay on the Y probe of each band pair -> circular polarization
        delay = 0.0
        if kind in ("R", "L_tilted") and k in (1, 3):
            f_c = F_HI if upper else F_LO
            delay = 0.25 / f_c if hand == "R" else 0.0
        if kind in ("R", "L_tilted") and k in (0, 2) and hand == "L":
            delay = 0.25 / (F_HI if upper else F_LO)
        A, B = pl.pt((x, y, zb)), pl.pt((x, y, zb + PORT_LEN))
        ports.append(fdtd.AddLumpedPort(port_nr + k, 50, A, B, pl.axis("z"),
                                        excite=1.0 if excite else 0.0, delay=delay, priority=25))
        mark([A, B], critical=True)
    for x, y, r, z in geo["disks"]:
        cyl(pec, (x, y, z - 0.035), (x, y, z), r, 20, plane=z)
    for x, y, r, z in geo.get("holes", []):
        cyl(csx.AddMaterial(f"hole_{port_nr}_{x}_{y}", epsilon=1.0), (x, y, z - 0.01), (x, y, z + 0.01), r, 15,
            plane=z)
    # fine cells over the element footprint and through the stack
    c = pl.pt((0, 0, 0))
    span = np.arange(-g, g + 1e-9, ARRAY_RES_FINE)
    if pl.tilted:
        fill["x"] += list(c[0] + span)
        fill["z"] += list(c[2] + span)
        crit["y"] += [c[1] + v for v in geo["z_marks"][:4]]
        fill["y"] += [c[1] + v for v in geo["z_marks"][4:]]
    else:
        fill["x"] += list(c[0] + span)
        fill["y"] += list(c[1] + span)
        crit["z"] += list(geo["z_marks"][:4])
        fill["z"] += list(geo["z_marks"][4:])
    return ports, lines, fill, crit


def build(active, sim_dir, check=False):
    fdtd = openEMS(EndCriteria=10 ** (-30 / 10), NrTS=150000)
    fdtd.SetGaussExcite(1.4e9, 0.35e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    pec = csx.AddMetal("pec")
    pec.AddBox([PLATE_X[0], PLATE_Y[0], Z_PLATE], [PLATE_X[1], PLATE_Y[1], Z_PLATE], priority=10)
    exact = {"x": list(PLATE_X), "y": list(PLATE_Y), "z": []}
    filler = {"x": [], "y": [], "z": []}
    critical = {"x": [], "y": [], "z": [Z_PLATE, 0.0]}
    all_ports, port_owner, port_nr = [], [], 1
    tilted_y = None
    only = os.environ.get("ARRAY_ONLY")              # debugging: build a subset of elements
    for i, e in enumerate(ELEMENTS):
        if only is not None and str(i) not in only.split(","):
            continue
        x, y = e["x"], -e["y"]
        if e["kind"] == "L_tilted":
            pl = Placement(x, y, 64.0, tilted=True)
            tilted_y = y
            hand = "L"
            kind = "L_tilted"
        else:
            pl = Placement(x, y)
            hand = "R"
            kind = e["kind"]
        ports, lines, fill, crit = add_element(csx, fdtd, pec, kind, pl, port_nr, i == active,
                                               pol_deg=e.get("pol_deg", 0.0), hand=hand)
        for ax in "xyz":
            exact[ax] += lines[ax]
            filler[ax] += fill[ax]
            critical[ax] += crit[ax]
        all_ports += ports
        port_owner += [i] * len(ports)
        port_nr += len(ports)
    # vertical bracket face behind the tilted modules (their local plate plane)
    yb = None
    if tilted_y is not None:
        yb = tilted_y - P["post_h"]
        pec.AddBox([-260.0, yb, Z_PLATE], [260.0, yb, 64.0 + 75.0], priority=10)
        critical["y"].append(yb)
        exact["x"] += [-260.0, 260.0]
        exact["z"].append(139.0)

    if check:
        print("NEAR z=12:", sorted(v for v in set(np.round(exact["z"], 4)) if 11.5 < v < 12.5), flush=True)
        print("NEAR y=244.5:", sorted(v for v in set(np.round(exact["y"], 4)) if 244.0 < v < 245.0), flush=True)
    pad = C0 / 1.05e9 * 1e3 / 4 + 10
    res_air = C0 / 1.75e9 * 1e3 / 20
    for ax, (lo, hi) in (("x", (PLATE_X[0] - pad, PLATE_X[1] + pad)), ("y", (PLATE_Y[0] - pad, PLATE_Y[1] + pad)),
                         ("z", (Z_PLATE - pad, 139.0 + pad))):
        mesh.AddLine(ax, em.merge_lines(exact[ax] + [lo, hi], filler[ax], min_cell=ARRAY_MIN_CELL,
                                        critical=critical[ax]))
        # any two critical lines closer than ARRAY_MIN_CELL set the timestep: report them
        cl = np.diff(sorted(set(np.round(critical[ax], 4))))
        if len(cl) and cl.min() < ARRAY_MIN_CELL:
            print(f"note: critical {ax}-lines only {cl.min():.3f} mm apart", flush=True)
        mesh.SmoothMeshLines(ax, res_air, 1.4)
    n = [len(mesh.GetLines(a)) for a in "xyz"]
    min_cell = {a: round(float(np.diff(np.array(mesh.GetLines(a))).min()), 3) for a in "xyz"}
    nf2ff = fdtd.CreateNF2FFBox(opt_resolution=[res_air] * 3)
    info = {"cells": int(np.prod(n)), "grid": n, "min_cell_mm": min_cell, "ports": len(all_ports)}
    if check:
        ylines = np.array(mesh.GetLines("y"))
        zlines = np.array(mesh.GetLines("z"))
        want_y = [tilted_y + v for v in (0.0, P["h1"], P["h1"] + P["t_fr4"] + P["h2"])]
        info["tilted_sheet_planes_on_mesh"] = {round(v, 3): bool(np.min(np.abs(ylines - v)) < 1e-6) for v in want_y}
        info["flat_sheet_planes_on_mesh"] = {v: bool(np.min(np.abs(zlines - v)) < 1e-6)
                                             for v in (0.0, P["h1"], round(P["h1"] + P["t_fr4"] + P["h2"], 4))}
        info["plate_on_mesh"] = bool(np.min(np.abs(zlines - Z_PLATE)) < 1e-6)
        info["bracket_on_mesh"] = bool(np.min(np.abs(ylines - yb)) < 1e-6)
    if os.environ.get("ARRAY_XML_ONLY"):
        csx.Write2XML(str(Path(sim_dir) / "array.xml"))
        return all_ports, port_owner, nf2ff, info
    fdtd.Run(str(sim_dir), cleanup=True, verbose=0, numThreads=os.cpu_count())
    return all_ports, port_owner, nf2ff, info


def run_element(i, out_dir, work):
    sim_dir = work / f"elem{i:02d}"
    sim_dir.mkdir(parents=True, exist_ok=True)
    ports, owner, nf2ff, info = build(i, sim_dir)
    f = np.linspace(1.10e9, 1.70e9, 121)
    for pt in ports:
        pt.CalcPort(str(sim_dir), f)
    mine = [k for k, o in enumerate(owner) if o == i]
    p_inc = sum(np.real(ports[k].P_inc) for k in mine)
    # coupling: reflected wave at every port per sqrt(W) incident on the driven element
    b = np.array([ports[k].uf_ref / np.sqrt(50) for k in range(len(ports))]) / np.sqrt(np.maximum(p_inc, 1e-30))
    for pt in ports:
        pt.CalcPort(str(sim_dir), F_FF)
    p_ff = sum(np.real(ports[k].P_inc) for k in mine)
    theta = np.arange(0, 91, 5.0)
    phi = np.arange(0, 360, 15.0)
    r = nf2ff.CalcNF2FF(str(sim_dir), F_FF, theta, phi, center=[0, 0.045, 0.02], read_cached=False, verbose=0)
    eth = np.array(r.E_theta) / np.sqrt(p_ff)[:, None, None]
    eph = np.array(r.E_phi) / np.sqrt(p_ff)[:, None, None]
    np.savez(out_dir / f"elem{i:02d}.npz", f=f, b=b, owner=np.array(owner), f_ff=F_FF, theta=theta, phi=phi,
             e_theta=eth, e_phi=eph, element=json.dumps(ELEMENTS[i]))
    print(f"element {i} ({ELEMENTS[i]['kind']}) done: {info}", flush=True)
    return info


def main():
    args = sys.argv[1:]
    out_dir = HERE / "results" / "array"
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(os.environ.get("EM_WORK", ROOT / "tools" / "em_runs")) / "array"
    if "--check" in args:
        global openEMS
        real = openEMS
        openEMS = lambda **kw: real(EndCriteria=1e-4, NrTS=10)  # noqa: E731
        d = work / "check"
        d.mkdir(parents=True, exist_ok=True)
        _, owner, _, info = build(0, d)
        print("CHECK", json.dumps(info), flush=True)
        return
    sel = list(range(len(ELEMENTS)))
    if "--elements" in args:
        sel = [int(v) for v in args[args.index("--elements") + 1].split(",")]
    for i in sel:
        if (out_dir / f"elem{i:02d}.npz").exists():
            print(f"element {i} already done, skipping", flush=True)
            continue
        run_element(i, out_dir, work)


if __name__ == "__main__":
    main()
