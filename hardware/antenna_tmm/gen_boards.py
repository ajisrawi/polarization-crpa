"""
Rev B (compact TMM3) CRPA element and array-plate boards.

Run with KiCad's Python:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/antenna_tmm/gen_boards.py

Changes from rev A (hardware/antenna):
  * radiators on Rogers TMM3 (er 3.45) -> 64 / 58 / 48 mm patches instead of 105 / 82 mm
  * element pitch 100 mm (0.53 lambda at L1) instead of 125 mm
  * capacitively coupled feed disks cancel the probe inductance
  * SMD 90-degree hybrid (Q3XG-1500R) replaces the printed one (too big for a 96 mm board)
  * stitched ground on both feed-board layers + 8 plated holes for METAL standoffs to the
    plate, which kills the parallel-plate cavity under the feed board
  * linear 0/60/120 deg set by the probe angle, every board axis-aligned
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbnew  # noqa: E402
from pcb_gen import Board, C_FP, R_FP, series_part  # noqa: E402

P = json.loads((HERE / "design_params.json").read_text())
FEED_HALF = P["board"]["feed_size_mm"] / 2          # 48
SLAB_HALF = P["board"]["slab_size_mm"] / 2          # 40
POST = P["board"]["post_holes_mm"]                  # 44
PITCH = P["board"]["element_pitch_mm"]              # 100
T = P["substrates"]["slab_thickness_mm"]
PATCH = P["patches_mm"]

PROBE_OFF = 10.0      # mm from centre (EM-tunable; the cos^2 model's 6.4 mm puts the disks too close)
DISK_D = 7.0          # capacitive feed disk diameter (EM-tunable; model value 8.8 mm)
PROBE_DRILL, PROBE_PAD, PROBE_ANTIPAD = 1.4, 2.4, 1.6
W50 = 1.681           # 50 ohm microstrip on RO4350B 0.762 mm
LINE_CLEAR = 1.6      # B.Cu ground pour keeps >= 2h from the microstrip (stays microstrip, not CPW)
SMA_POS = (-36.0, 36.0)
POSTS = [(sx * POST, sy * POST) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if (sx, sy) != (0, 0)]
LIN_ANGLES = (0, 60, 120)

# hybrid placeholder land pattern (VERIFY against the Q3XG-1500R datasheet)
HYB_BODY = (14.2, 8.9)
HYB_PORTS = {"1": (-6.1, -3.2), "2": (6.1, -3.2), "3": (6.1, 3.2), "4": (-6.1, 3.2)}
HYB_CENTRE_R = 18.0                                  # along the (-1, 1)/sqrt2 axis
AXIS = (-1 / math.sqrt(2), 1 / math.sqrt(2))         # toward the SMA corner


def probe_at(angle_deg):
    a = math.radians(angle_deg)
    return (PROBE_OFF * math.cos(a), -PROBE_OFF * math.sin(a))


def add(p, d, s=1.0):
    return (p[0] + d[0] * s, p[1] + d[1] * s)


def common_feed(bd):
    bd.outline_square(FEED_HALF)
    for i, xy in enumerate(POSTS, 1):
        bd.custom_footprint(f"H{i}", "M3 plated hole for brass standoff to plate", xy, [
            {"num": "1", "x": 0, "y": 0, "w": 6.0, "h": 6.0, "shape": "circle", "smd": False,
             "drill": 3.2, "net": "GND"}])
    # ground stitching ring between the two ground pours
    n = 14
    for k in range(n):
        t = -FEED_HALF + 2.5 + k * (2 * FEED_HALF - 5) / (n - 1)
        for xy in ((t, -FEED_HALF + 2.5), (t, FEED_HALF - 2.5), (-FEED_HALF + 2.5, t), (FEED_HALF - 2.5, t)):
            if all(math.hypot(xy[0] - p[0], xy[1] - p[1]) > 4.5 for p in POSTS):
                bd.via(xy, "GND")


def finish_feed(bd):
    bd.zone_square(pcbnew.F_Cu, "GND", FEED_HALF - 0.5)
    bd.zone_square(pcbnew.B_Cu, "GND", FEED_HALF - 0.5, clearance=LINE_CLEAR)


def place_sma(bd):
    return bd.footprint("Connector_Coaxial", "SMA_Amphenol_132134_Vertical", SMA_POS, bottom=True,
                        value="SMA vertical (Amphenol 132134)", nets={"1": "RF_OUT", "2": "GND"}, ref="J1")


def feed_circular():
    bd = Board("CRPA rev B feed board - circular (RHCP/LHCP selectable)", 0.762)
    common_feed(bd)
    centre = add((0, 0), AXIS, HYB_CENTRE_R)
    pads = [{"num": k, "x": x, "y": y, "w": 1.6, "h": 1.2, "net": f"HYB{k}"} for k, (x, y) in HYB_PORTS.items()]
    pads.append({"num": "5", "x": 0, "y": 0, "w": 8.0, "h": 4.0, "net": "GND"})
    hyb = bd.custom_footprint("U1", "Q3XG-1500R 90deg hybrid - LAND PATTERN PLACEHOLDER, VERIFY",
                              centre, pads, angle=45.0, bottom=True, body=HYB_BODY)
    pos = {k: bd.pad_position(hyb, k) for k in HYB_PORTS}
    for dx, dy in ((-2.5, 0), (2.5, 0), (0, 0)):
        bd.via(add(centre, (dx * 0.707 + dy, -dx * 0.707 + dy)), "GND")

    # feed lines: the port nearer each probe drives it; both lines are mirror images
    px, py = probe_at(0), probe_at(90)
    near_x = min(("2", "3"), key=lambda k: math.dist(pos[k], px))
    near_y = "3" if near_x == "2" else "2"
    for probe, port, ref, cref in ((px, near_x, "P1", "C1"), (py, near_y, "P2", "C2")):
        bd.th_pad(probe, PROBE_DRILL, PROBE_PAD, f"PROBE_{ref}", ref, clearance=PROBE_ANTIPAD)
        series_part(bd, pos[port], probe, 0.75, *C_FP, "0R (disk feed) / tune", "C",
                    f"HYB{port}", f"PROBE_{ref}", W50, ref=cref)

    # which input port gives which hand (ports: 1 in, 2 thru -90, 3 coupled -180, 4 isolated):
    # input 1 -> port2 -90, port3 -180; the X probe must LEAD the Y probe by 90 deg for RHCP
    x_from_1 = -90 if near_x == "2" else -180
    y_from_1 = -180 if near_x == "2" else -90
    hand_port1 = "RHCP" if x_from_1 - y_from_1 == 90 else "LHCP"
    hand = {"1": hand_port1, "4": "LHCP" if hand_port1 == "RHCP" else "RHCP"}

    # polarization select: 3-pad alternate-fit jumper JP1 (pads A-C-B, output on C).
    # Fit one 0603 0R across A-C (port 1) or C-B (port 4); terminate the other port with 49.9R.
    junction = add((0, 0), AXIS, HYB_CENTRE_R + 15.0)
    perp_axis = (AXIS[1], -AXIS[0])
    jp = bd.custom_footprint("JP1", "polarization select: 0R on A-C or C-B", junction, [
        {"num": "A", "x": -1.55, "y": 0, "w": 0.9, "h": 0.95, "net": "HYB1"},
        {"num": "C", "x": 0.0, "y": 0, "w": 0.9, "h": 0.95, "net": "RF_OUT"},
        {"num": "B", "x": 1.55, "y": 0, "w": 0.9, "h": 0.95, "net": "HYB4"}],
        angle=-math.degrees(math.atan2(perp_axis[1], perp_axis[0])), bottom=True, body=(4.4, 1.6))
    jpos = {k: bd.pad_position(jp, k) for k in "ACB"}
    # make sure pad A sits on the port-1 side
    if math.dist(jpos["A"], pos["1"]) > math.dist(jpos["B"], pos["1"]):
        jpos["A"], jpos["B"] = jpos["B"], jpos["A"]
        for pad in jp.Pads():
            pad.SetNet(bd.net({"A": "HYB4", "B": "HYB1", "C": "RF_OUT"}[pad.GetNumber()]))
    refs = {"1": "R1", "4": "R3"}
    for port, pad in (("1", "A"), ("4", "B")):
        start = pos[port]
        tap = add(start, AXIS, 3.0)
        side = (start[0] - centre[0], start[1] - centre[1])
        perp = (-AXIS[1], AXIS[0]) if side[0] * -AXIS[1] + side[1] * AXIS[0] > 0 else (AXIS[1], -AXIS[0])
        bd.track(start, tap, W50, f"HYB{port}")
        t_end = add(tap, perp, W50 / 2 + 2.6)
        series_part(bd, tap, t_end, 0.55, *R_FP, f"49.9R if {hand[port]} not used, else DNP", "R",
                    f"HYB{port}", "GND", 0.5, ref=refs[port])
        neck = add(jpos[pad], AXIS, -1.6)              # 0.8 mm neck into the small jumper pads
        bd.track(tap, neck, W50, f"HYB{port}")
        bd.track(neck, jpos[pad], 0.8, f"HYB{port}")
    out_neck = add(jpos["C"], AXIS, 1.6)
    corner = (out_neck[0], SMA_POS[1])
    bd.track(jpos["C"], out_neck, 0.8, "RF_OUT")
    bd.path([out_neck, corner, SMA_POS], W50, "RF_OUT")
    place_sma(bd)
    finish_feed(bd)
    rh = "A-C" if hand["1"] == "RHCP" else "C-B"
    lh = "C-B" if rh == "A-C" else "A-C"
    t_rh = "R3" if rh == "A-C" else "R1"
    t_lh = "R1" if t_rh == "R3" else "R3"
    bd.text(f"JP1  RHCP: 0R {rh}, {t_rh}=49.9R  |  LHCP: 0R {lh}, {t_lh}=49.9R  (verify by AR test)",
            (8, 30), pcbnew.B_SilkS, 1.0, mirrored=True)
    bd.text("CRPA rev B FEED - CIRCULAR", (0, -FEED_HALF + 10), pcbnew.F_SilkS, 1.6)
    path = bd.save(HERE / "feed_circular", "feed_circular")
    return path, {"rhcp": f"JP1 0R on {rh}, {t_rh}=49.9R", "lhcp": f"JP1 0R on {lh}, {t_lh}=49.9R"}


def feed_linear(angle):
    bd = Board(f"CRPA rev B feed board - linear {angle} deg", 0.762)
    common_feed(bd)
    probe = probe_at(angle)
    bd.th_pad(probe, PROBE_DRILL, PROBE_PAD, "PROBE", "P1", clearance=PROBE_ANTIPAD)
    corner = (probe[0], SMA_POS[1])
    series_part(bd, probe, corner, 0.2, *C_FP, "0R (disk feed) / tune", "C", "PROBE", "RF_OUT", W50, ref="C1")
    bd.track(corner, SMA_POS, W50, "RF_OUT")
    place_sma(bd)
    finish_feed(bd)
    bd.text(f"CRPA rev B FEED - LINEAR {angle:03d} deg", (0, -FEED_HALF + 10), pcbnew.F_SilkS, 1.6)
    name = f"feed_linear_{angle:03d}"
    return bd.save(HERE / name, name)


def slab(name, title, thickness, patch_mm=None, disks=()):
    bd = Board(title, thickness)
    bd.outline_square(SLAB_HALF)
    if patch_mm:
        bd.zone_square(pcbnew.F_Cu, None, patch_mm / 2, keep_islands=True)
    for i, xy in enumerate(disks, 1):
        bd.th_pad(xy, PROBE_DRILL, DISK_D, f"DISK{i}", f"D{i}", value="feed disk")
    bd.text(title, (0, SLAB_HALF - 3), pcbnew.F_SilkS, 1.0)
    return bd.save(HERE / name, name)


# --------------------------------------------------------------------------
# Array plate
# --------------------------------------------------------------------------

GRID = [["R", "H", "V"], ["V", "R", "H"], ["H", "V", "R"]]
STRIP = 75.0


def array_layout():
    elems, h_iter = [], iter(LIN_ANGLES)
    for r, row in enumerate(GRID):
        for c, kind in enumerate(row):
            e = {"kind": kind, "x": (c - 1) * PITCH, "y": (r - 1) * PITCH, "rot_deg": 0.0,
                 "boresight_el_deg": 90.0}
            if kind == "H":
                e["pol_deg"] = float(next(h_iter))
                e["board"] = f"feed_linear_{int(e['pol_deg']):03d} + slab_A1_lin{int(e['pol_deg']):03d}"
            elif kind == "R":
                e["board"] = "feed_circular (RHCP) + slab_A1_circ"
            else:
                e["board"] = "brass monopole on SMA bulkhead"
            elems.append(e)
    for c in range(3):
        elems.append({"kind": "L_tilted", "x": (c - 1) * PITCH, "y": -1.5 * PITCH - STRIP / 2,
                      "rot_deg": 0.0, "boresight_el_deg": 10.0, "boresight_az_deg": 0.0,
                      "board": "feed_circular (LHCP per spec; RHCP recommended) + slab_A1_circ"})
    return elems


def array_plate():
    bd = Board("CRPA rev B array ground plate (6061-T6, 3 mm) - export DXF", 3.0)
    x0, x1 = -1.5 * PITCH - 10, 1.5 * PITCH + 10
    y0, y1 = -1.5 * PITCH - STRIP - 10, 1.5 * PITCH + 10
    bd.outline_rect(x0, y0, x1, y1)
    elems = array_layout()
    n = iter(range(1, 1000))
    for e in elems:
        cx, cy = e["x"], e["y"]
        if e["kind"] in ("R", "H"):
            for xy in POSTS:
                bd.hole((cx + xy[0], cy + xy[1]), 3.2, f"H{next(n)}", "M3 brass standoff")
            bd.hole((cx + SMA_POS[0], cy + SMA_POS[1]), 10.0, f"H{next(n)}", "SMA cable plug pass-through")
        elif e["kind"] == "V":
            bd.hole((cx, cy), 6.4, f"H{next(n)}", "SMA bulkhead (monopole)")
        else:
            bd.hole((cx, cy + 22), 10.0, f"H{next(n)}", "cable pass-through")
    for x in (-120.0, -40.0, 40.0, 120.0):          # one continuous bracket, 4 x M4
        bd.hole((x, -1.5 * PITCH - STRIP / 2 + 22), 4.3, f"H{next(n)}", "bracket M4")
    bd.text("JAMMER SIDE (az 0, el 10)", (0, y0 + 6), pcbnew.F_SilkS, 4.0)
    path = bd.save(HERE / "array_plate", "array_plate")
    (HERE / "array_plate" / "element_positions.json").write_text(json.dumps(elems, indent=2))
    return path, (x1 - x0, y1 - y0)


if __name__ == "__main__":
    out = []
    p, hand = feed_circular()
    out.append(p)
    out += [feed_linear(a) for a in LIN_ANGLES]
    out.append(slab("slab_A1_circ", "TMM3 8.89mm slab A1 - feed disks 0/90 deg", T["A1"],
                    disks=[probe_at(0), probe_at(90)]))
    for a in LIN_ANGLES:
        out.append(slab(f"slab_A1_lin{a:03d}", f"TMM3 8.89mm slab A1 - feed disk {a} deg", T["A1"],
                        disks=[probe_at(a)]))
    out.append(slab("slab_A2", "TMM3 0.762mm slab A2 - patch A (1164-1215 MHz)", T["A2"], PATCH["A"]))
    out.append(slab("slab_B", "TMM3 3.175mm slab B - patch B (1215-1300 MHz)", T["B"], PATCH["B"]))
    out.append(slab("slab_C", "TMM3 7.62mm slab C - patch C (1559-1610 MHz)", T["C"], PATCH["C"]))
    p, size = array_plate()
    out.append(p)
    for p in out:
        print("wrote", p)
    print("polarization jumpers:", hand)
    print(f"array plate: {size[0]:.0f} x {size[1]:.0f} mm")
