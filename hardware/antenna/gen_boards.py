"""
Generate the CRPA element and array-plate boards with KiCad's pcbnew API.

Run with KiCad's Python (not the system Python):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_boards.py

Reads design_params.json (from design_calc.py) and writes, one KiCad project each:
    feed_circular/   RO4350B feed board: dual probe, printed 2-section hybrid,
                     RHCP/LHCP selected by fitting R1/R4 or R2/R3 (see the fab notes)
    feed_linear/     RO4350B feed board: single probe straight to the SMA
    patch_lower/     FR4 carrier, probe-fed lower patch (1164-1300 MHz)
    patch_upper/     FR4 carrier, parasitic upper patch (1559-1610 MHz)
    array_plate/     aluminium ground plate outline and holes (export as DXF)

KiCad coordinates: x right, y DOWN, viewed from the top (= from the sky).
"""
import json
import math
from pathlib import Path

import pcbnew

HERE = Path(__file__).parent
P = json.loads((HERE / "design_params.json").read_text())
KICAD_FP = Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")

MM = pcbnew.FromMM
BOARD = P["board"]["size_mm"]
HALF = BOARD / 2
HOLE = P["board"]["mount_hole_offset_mm"]
MOUNT_HOLES = [(0, -HOLE), (HOLE, 0), (0, HOLE), (-HOLE, 0)]  # mid-edge, clear of patch corners
PROBE_OFF = P["patch"]["probe"]["offset_from_centre_mm"]
PROBE_DRILL = 1.4                       # 16 AWG (1.29 mm) solid copper probe wire
PROBE_PAD = 2.4
PROBE_ANTIPAD = 1.6                     # extra clearance to the ground plane
SMA_POS = (-54.0, 54.0)                 # identical on every feed board (plate hole pattern)

PROBE_X = (PROBE_OFF, 0.0)              # excites x
PROBE_Y = (0.0, -PROBE_OFF)             # excites +y (physical) = screen-up
LIN_ANGLES = (0, 60, 120)               # linear polarization angles (deg, CCW from +x seen from the sky)


def probe_at(angle_deg):
    """Probe position (KiCad coords) for linear polarization at angle_deg.

    A square patch has two degenerate modes; a probe on the ray at angle a excites both
    in phase with weights cos a / sin a, giving linear polarization along a. This sets
    the 0/60/120 deg orientations electrically, so every board stays axis-aligned
    (rotating a 124 mm board by 60 deg would hit its neighbours at 125 mm pitch).
    """
    a = math.radians(angle_deg)
    return (PROBE_OFF * math.cos(a), -PROBE_OFF * math.sin(a))

LINES = P["hybrid"]["lines"]
W50 = LINES["z50"]["width_mm"]


# --------------------------------------------------------------------------
# Small helpers around pcbnew
# --------------------------------------------------------------------------

def v(xy):
    return pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1]))


class Board:
    def __init__(self, title, thickness_mm):
        self.b = pcbnew.BOARD()
        self.nets = {}
        ds = self.b.GetDesignSettings()
        ds.SetBoardThickness(MM(thickness_mm))
        nc = ds.m_NetSettings.GetDefaultNetclass()
        nc.SetClearance(MM(0.2))
        nc.SetTrackWidth(MM(0.25))
        tb = self.b.GetTitleBlock()
        tb.SetTitle(title)
        tb.SetCompany("GNSS anti-jam CRPA")
        tb.SetRevision("A (pre-EM-tuning)")
        self.ref_count = {}

    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

    def outline_square(self, half):
        pts = [(-half, -half), (half, -half), (half, half), (-half, half)]
        for a, c in zip(pts, pts[1:] + pts[:1]):
            s = pcbnew.PCB_SHAPE(self.b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(v(a))
            s.SetEnd(v(c))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(MM(0.1))
            self.b.Add(s)

    def outline_rect(self, x0, y0, x1, y1):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for a, c in zip(pts, pts[1:] + pts[:1]):
            s = pcbnew.PCB_SHAPE(self.b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(v(a))
            s.SetEnd(v(c))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(MM(0.1))
            self.b.Add(s)

    def track(self, a, c, width, net, layer=pcbnew.B_Cu):
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(v(a))
        t.SetEnd(v(c))
        t.SetWidth(MM(width))
        t.SetLayer(layer)
        t.SetNet(self.net(net))
        self.b.Add(t)

    def path(self, pts, width, net, layer=pcbnew.B_Cu):
        for a, c in zip(pts, pts[1:]):
            self.track(a, c, width, net, layer)

    def via(self, xy, net, drill=0.4, dia=0.8):
        vi = pcbnew.PCB_VIA(self.b)
        vi.SetPosition(v(xy))
        vi.SetDrill(MM(drill))
        vi.SetWidth(MM(dia))
        vi.SetNet(self.net(net))
        self.b.Add(vi)

    def _ref(self, prefix):
        self.ref_count[prefix] = self.ref_count.get(prefix, 0) + 1
        return f"{prefix}{self.ref_count[prefix]}"

    def footprint(self, lib, name, xy, angle=0.0, bottom=False, ref_prefix="U", value="",
                  nets=None, ref=None):
        fp = pcbnew.FootprintLoad(str(KICAD_FP / f"{lib}.pretty"), name)
        if fp is None:
            raise RuntimeError(f"footprint {lib}:{name} not found")
        fp.SetReference(ref or self._ref(ref_prefix))
        fp.SetValue(value or name)
        self.b.Add(fp)
        fp.SetPosition(v(xy))
        if bottom:
            fp.Flip(v(xy), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(angle)
        for pad in fp.Pads():
            key = pad.GetNumber()
            if nets and key in nets and nets[key]:
                pad.SetNet(self.net(nets[key]))
        return fp

    def th_pad(self, xy, drill, dia, net, ref, clearance=None, value="probe"):
        fp = pcbnew.FOOTPRINT(self.b)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM)
        pad = pcbnew.PAD(fp)
        pad.SetNumber("1")
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I(MM(dia), MM(dia)))
        pad.SetDrillSize(pcbnew.VECTOR2I(MM(drill), MM(drill)))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        if clearance is not None:
            pad.SetLocalClearance(MM(clearance))
        fp.Add(pad)
        self.b.Add(fp)
        fp.SetPosition(v(xy))
        pad.SetNet(self.net(net))
        return fp

    def mount_holes(self, holes=MOUNT_HOLES, name="MountingHole_3.2mm_M3"):
        for xy in holes:
            fp = self.footprint("MountingHole", name, xy, ref_prefix="H", value="M3 nylon standoff")
            fp.Reference().SetVisible(False)

    def zone(self, layer, net, half, clearance=0.3, min_width=0.25, priority=0):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        z.SetLocalClearance(MM(clearance))
        z.SetMinThickness(MM(min_width))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(priority)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(-half, -half), (half, -half), (half, half), (-half, half)]:
            ol.Append(MM(x), MM(y))
        self.b.Add(z)
        return z

    def square_patch(self, half, layer, net):
        """Patch as a filled zone. A parasitic patch (net=None) is a no-net island by design."""
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        if net:
            z.SetNet(self.net(net))
        else:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        z.SetLocalClearance(MM(0.2))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(-half, -half), (half, -half), (half, half), (-half, half)]:
            ol.Append(MM(x), MM(y))
        self.b.Add(z)
        return z

    def text(self, s, xy, layer=pcbnew.F_SilkS, size=1.5, mirrored=False):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(v(xy))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(size * 0.15))
        if mirrored:
            t.SetMirrored(True)
        self.b.Add(t)

    def save(self, folder, name):
        out = HERE / folder
        out.mkdir(exist_ok=True)
        # zones are filled afterwards by `kicad-cli pcb drc --refill-zones --save-board`
        # (ZONE_FILLER crashes when pcbnew runs headless)
        path = out / f"{name}.kicad_pcb"
        pcbnew.SaveBoard(str(path), self.b)
        pro = out / f"{name}.kicad_pro"
        if not pro.exists():
            pro.write_text(json.dumps({"meta": {"filename": pro.name, "version": 1}}, indent=2))
        return path


# --------------------------------------------------------------------------
# Geometry of the printed hybrid
# --------------------------------------------------------------------------

AXIS = (-1 / math.sqrt(2), 1 / math.sqrt(2))   # from ports 2/3 toward ports 1/4 (lower-left)
PERP = (1 / math.sqrt(2), 1 / math.sqrt(2))    # +v side faces the X probe
R0 = 0.0                                       # axial position of the ports-2/3 nodes


def uv(u, vv):
    return (R0 * AXIS[0] + u * AXIS[0] + vv * PERP[0],
            R0 * AXIS[1] + u * AXIS[1] + vv * PERP[1])


def to_uv(xy):
    return (xy[0] * AXIS[0] + xy[1] * AXIS[1] - R0, xy[0] * PERP[0] + xy[1] * PERP[1])


def angle_of(a, c):
    """KiCad footprint orientation (deg, CCW positive on screen) along a -> c."""
    return -math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))


def hybrid_geometry():
    lc = LINES["zc"]["quarter_wave_mm"]       # series arms
    s = LINES["zb"]["quarter_wave_mm"]        # branch spacing = middle branch length
    la = LINES["za"]["quarter_wave_mm"]       # outer branches need la: add an outward jog
    jog = max(0.0, (la - s) / 2)
    half = s / 2
    nodes = {"p2": (0, half), "p3": (0, -half), "p1": (2 * lc, half), "p4": (2 * lc, -half)}
    return lc, s, jog, half, nodes


def draw_hybrid(bd):
    lc, s, jog, half, nodes = hybrid_geometry()
    wa, wb, wc = (LINES[k]["width_mm"] for k in ("za", "zb", "zc"))
    # series arms (top: p2 -> p1, bottom: p3 -> p4) split at the middle branch
    bd.path([uv(0, half), uv(lc, half), uv(2 * lc, half)], wc, "HYB_T")
    bd.path([uv(0, -half), uv(lc, -half), uv(2 * lc, -half)], wc, "HYB_B")
    # middle branch
    bd.track(uv(lc, half), uv(lc, -half), wb, "HYB_T")
    # outer branches with an outward jog so their length is the Za quarter wave
    inset = half - 3.0
    for u0, sign in ((0.0, -1.0), (2 * lc, 1.0)):
        pts = [uv(u0, half), uv(u0, inset), uv(u0 + sign * jog, inset),
               uv(u0 + sign * jog, -inset), uv(u0, -inset), uv(u0, -half)]
        bd.path(pts, wa, "HYB_T")
    return nodes


def merge_hybrid_nets(board):
    """The hybrid is one copper object; give every hybrid track the same net."""
    net = board.nets["HYB_T"]
    for t in board.b.GetTracks():
        if t.GetNetname() in ("HYB_T", "HYB_B"):
            t.SetNet(net)


# --------------------------------------------------------------------------
# Feed boards
# --------------------------------------------------------------------------

R_FP = ("Resistor_SMD", "R_0603_1608Metric")
C_FP = ("Capacitor_SMD", "C_0603_1608Metric")
PAD_CENTRE = 0.775        # 0603 pad centre offset
PAD_LEN = 0.9             # 0603 pad length along the part axis


def series_part(bd, a, c, frac, lib, name, value, ref_prefix, net_a, net_c, width, ref=None):
    """Place an 0603 in series on the line a->c at fraction frac; draw both line pieces.

    The line pieces stop just inside the outer edge of each pad, so the round end of a
    wide 50-ohm line never reaches the opposite pad.
    """
    ux, uy = c[0] - a[0], c[1] - a[1]
    length = math.hypot(ux, uy)
    ux, uy = ux / length, uy / length
    mid = (a[0] + ux * length * frac, a[1] + uy * length * frac)
    pa = (mid[0] - ux * PAD_CENTRE, mid[1] - uy * PAD_CENTRE)
    pc = (mid[0] + ux * PAD_CENTRE, mid[1] + uy * PAD_CENTRE)
    # end point e: its round cap (radius width/2) must not pass the pad's inner edge,
    # and e itself must stay on the pad so KiCad sees the connection
    inner = PAD_CENTRE - PAD_LEN / 2
    reach = max(PAD_CENTRE, inner + width / 2 + 0.02)
    assert reach < PAD_CENTRE + PAD_LEN / 2, "line too wide for the pad"
    ea = (mid[0] - ux * reach, mid[1] - uy * reach)
    ec = (mid[0] + ux * reach, mid[1] + uy * reach)
    bd.track(a, ea, width, net_a)
    bd.track(ec, c, width, net_c)
    fp = bd.footprint(lib, name, mid, angle=angle_of(a, c), bottom=True, ref_prefix=ref_prefix,
                      value=value, nets={"1": net_a, "2": net_c}, ref=ref)
    # flipping mirrors the footprint: make sure pad 1 really sits on the net_a side
    pad1 = next(p for p in fp.Pads() if p.GetNumber() == "1")
    pos = pad1.GetPosition()
    d_a = math.hypot(pcbnew.ToMM(pos.x) - pa[0], pcbnew.ToMM(pos.y) - pa[1])
    d_c = math.hypot(pcbnew.ToMM(pos.x) - pc[0], pcbnew.ToMM(pos.y) - pc[1])
    if d_a > d_c:
        fp.SetOrientationDegrees(fp.GetOrientationDegrees() + 180)
    return pa, pc


def place_sma(bd, net):
    return bd.footprint("Connector_Coaxial", "SMA_Amphenol_132134_Vertical", SMA_POS, bottom=True,
                        ref_prefix="J", value="SMA vertical (Amphenol 132134)",
                        nets={"1": net, "2": "GND"}, ref="J1")


def feed_circular():
    bd = Board("CRPA element feed board - circular (RHCP/LHCP selectable)", 0.762)
    bd.outline_square(HALF)
    bd.mount_holes()
    nodes = draw_hybrid(bd)
    lc, s, jog, half, _ = hybrid_geometry()

    # probes and the two phase-matched feed lines (mirror images about the hybrid axis)
    for probe, port, net_line, net_probe, ref, cref in (
            (PROBE_X, "p2", "HYB_T", "PROBE_X", "P1", "C1"),
            (PROBE_Y, "p3", "HYB_B", "PROBE_Y", "P2", "C2")):
        bd.th_pad(probe, PROBE_DRILL, PROBE_PAD, net_probe, ref, clearance=PROBE_ANTIPAD)
        start = uv(*nodes[port])
        knee = uv(nodes[port][0] - 3.0, nodes[port][1])     # leave the hybrid along -u
        bd.track(start, knee, W50, net_line)
        series_part(bd, knee, probe, 0.7, *C_FP, "0R / ~2.2pF probe tune", "C",
                    net_line, net_probe, W50, ref=cref)

    # outputs: port 1 = RHCP, port 4 = LHCP. Each port: shunt 49.9R termination option,
    # then a series 0R option right next to the common junction (tiny stub when unused).
    tap_u = 2 * lc + 2.5
    turn_u = 2 * lc + 7.0           # >= 6 mm from the outer branch to limit coupling
    junction = uv(turn_u, 0.0)
    for port, sign, pol, rt, rs in (("p1", 1, "RHCP", "R1", "R2"), ("p4", -1, "LHCP", "R3", "R4")):
        net = "HYB_T" if port == "p1" else "HYB_B"
        vv = nodes[port][1]
        node, tap, turn = uv(*nodes[port]), uv(tap_u, vv), uv(turn_u, vv)
        bd.path([node, tap, turn], W50, net)
        t_end = uv(tap_u, vv + sign * (W50 / 2 + 2.6))
        series_part(bd, tap, t_end, 0.55, *R_FP, f"49.9R if {pol} not used, else DNP", "R",
                    net, "GND", 0.5, ref=rt)
        via_at = uv(tap_u, vv + sign * (W50 / 2 + 4.0))
        bd.track(t_end, via_at, 0.5, "GND")
        bd.via(via_at, "GND")
        series_part(bd, turn, junction, (abs(vv) - 1.9) / abs(vv), *R_FP, f"0R for {pol}, else DNP",
                    "R", net, "RF_OUT", W50, ref=rs)
    # junction -> SMA: last segment horizontal so it passes between the SMA ground pins
    corner = (junction[0], SMA_POS[1])
    bd.path([junction, corner, SMA_POS], W50, "RF_OUT")
    place_sma(bd, "RF_OUT")

    merge_hybrid_nets(bd)
    for fp in bd.b.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == "HYB_B":
                pad.SetNet(bd.net("HYB_T"))

    bd.zone(pcbnew.F_Cu, "GND", HALF - 0.5)
    bd.text("CRPA FEED - CIRCULAR  rev A", (-20, -HALF + 8), pcbnew.F_SilkS, 2.0)
    bd.text("RHCP: R2=0R R3=49.9R  |  LHCP: R4=0R R1=49.9R", (25, 50), pcbnew.B_SilkS, 1.2, mirrored=True)
    return bd.save("feed_circular", "feed_circular")


def feed_linear(angle_deg):
    bd = Board(f"CRPA element feed board - linear {angle_deg} deg", 0.762)
    bd.outline_square(HALF)
    bd.mount_holes()
    probe = probe_at(angle_deg)
    bd.th_pad(probe, PROBE_DRILL, PROBE_PAD, "PROBE", "P1", clearance=PROBE_ANTIPAD)
    corner = (probe[0], SMA_POS[1])           # straight down, then horizontal into the SMA
    series_part(bd, probe, corner, 0.25, *C_FP, "0R / ~2.2pF probe tune", "C",
                "PROBE", "RF_OUT", W50, ref="C1")
    bd.track(corner, SMA_POS, W50, "RF_OUT")
    place_sma(bd, "RF_OUT")
    bd.zone(pcbnew.F_Cu, "GND", HALF - 0.5)
    bd.text(f"CRPA FEED - LINEAR {angle_deg:03d} deg  rev A", (-20, -HALF + 8), pcbnew.F_SilkS, 2.0)
    bd.text("E-field along the centre->probe direction", (20, -HALF + 12), pcbnew.F_SilkS, 1.2)
    name = f"feed_linear_{angle_deg:03d}"
    return bd.save(name, name)


# --------------------------------------------------------------------------
# Patch carriers
# --------------------------------------------------------------------------

def patch_board(folder, title, half_patch, probes):
    bd = Board(title, P["patch_substrate"]["h_mm"])
    bd.outline_square(HALF)
    bd.mount_holes()
    bd.square_patch(half_patch, pcbnew.B_Cu, "PATCH" if probes else None)
    for i, xy in enumerate(probes, 1):
        bd.th_pad(xy, PROBE_DRILL, PROBE_PAD, "PATCH", f"P{i}")
    bd.text(title, (-15, -HALF + 8), pcbnew.F_SilkS, 1.6)
    bd.text("patch copper on BOTTOM side, faces the feed board", (15, HALF - 8),
            pcbnew.F_SilkS, 1.2)
    return bd.save(folder, folder)


# --------------------------------------------------------------------------
# Array plate (3x3 grid facing the sky + 3 tilted LHCP modules toward the jammer)
# --------------------------------------------------------------------------

PITCH = P["board"]["element_pitch_mm"]
GRID = [["R", "H", "V"],
        ["V", "R", "H"],
        ["H", "V", "R"]]
TILT_STRIP = 90.0                               # depth of the jammer-facing strip (mm)


def array_layout():
    """Element list: kind, centre (x, y) on the plate, polarization angle, boresight.

    All boards are mounted axis-aligned (rot_deg 0). Linear elements get their
    polarization angle from the feed-board variant (pol_deg).
    """
    elems, h_iter = [], iter(LIN_ANGLES)
    for r, row in enumerate(GRID):
        for c, kind in enumerate(row):
            x, y = (c - 1) * PITCH, (r - 1) * PITCH
            e = {"kind": kind, "x": x, "y": y, "rot_deg": 0.0, "boresight_el_deg": 90.0}
            if kind == "H":
                e["pol_deg"] = float(next(h_iter))
                e["board"] = f"feed_linear_{int(e['pol_deg']):03d}"
            elif kind == "R":
                e["board"] = "feed_circular (RHCP jumpers)"
            else:
                e["board"] = "brass monopole on SMA bulkhead"
            elems.append(e)
    y_t = -1.5 * PITCH - TILT_STRIP / 2           # strip on the jammer side (screen-up = north)
    for c in range(3):
        elems.append({"kind": "L_tilted", "x": (c - 1) * PITCH, "y": y_t, "rot_deg": 0.0,
                      "boresight_el_deg": 10.0, "boresight_az_deg": 0.0,
                      "board": "feed_circular (LHCP jumpers; RHCP recommended)"})
    return elems


def array_plate():
    bd = Board("CRPA array ground plate (6061-T6 aluminium, 3 mm) - export Edge.Cuts as DXF", 3.0)
    x0, x1 = -1.5 * PITCH - 10, 1.5 * PITCH + 10
    y0, y1 = -1.5 * PITCH - TILT_STRIP - 10, 1.5 * PITCH + 10
    bd.outline_rect(x0, y0, x1, y1)
    elems = array_layout()
    for e in elems:
        cx, cy = e["x"], e["y"]
        if e["kind"] in ("R", "H"):
            rot = math.radians(e["rot_deg"])
            def tr(p):
                return (cx + p[0] * math.cos(rot) + p[1] * math.sin(rot),
                        cy - p[0] * math.sin(rot) + p[1] * math.cos(rot))
            bd.mount_holes([tr(h) for h in MOUNT_HOLES])
            bd.footprint("MountingHole", "MountingHole_8.4mm_M8", tr(SMA_POS), ref_prefix="H",
                         value="SMA pass-through 8.4 mm").Reference().SetVisible(False)
        elif e["kind"] == "V":
            bd.footprint("MountingHole", "MountingHole_6.4mm_M6", (cx, cy), ref_prefix="H",
                         value="SMA bulkhead for monopole (6.4 mm D-hole)").Reference().SetVisible(False)
        else:  # tilted LHCP: bracket with two M4 holes and a cable hole
            for dx in (-30.0, 30.0):
                bd.footprint("MountingHole", "MountingHole_4.3mm_M4", (cx + dx, cy + 20), ref_prefix="H",
                             value="bracket M4").Reference().SetVisible(False)
            bd.footprint("MountingHole", "MountingHole_8.4mm_M8", (cx, cy + 20), ref_prefix="H",
                         value="cable pass-through").Reference().SetVisible(False)
        bd.text(f"{e['kind']}", (cx, cy + 8), pcbnew.F_SilkS, 4.0)
    bd.text("JAMMER SIDE (boresight az 0, el 10)", (0, y0 + 6), pcbnew.F_SilkS, 5.0)
    path = bd.save("array_plate", "array_plate")
    (HERE / "array_plate" / "element_positions.json").write_text(json.dumps(elems, indent=2))
    return path


if __name__ == "__main__":
    lp = P["patch"]["lower_patch"]["length_mm"] / 2
    up = P["patch"]["upper_patch"]["length_mm"] / 2
    # one lower-patch part for every module: probe holes at 0, 60, 90 and 120 deg
    # (circular uses 0 + 90; a linear module uses the one matching its feed board)
    lower_holes = [probe_at(a) for a in (0, 60, 90, 120)]
    for p in (feed_circular(), *(feed_linear(a) for a in LIN_ANGLES),
              patch_board("patch_lower", "CRPA LOWER PATCH (1164-1300 MHz) rev A", lp, lower_holes),
              patch_board("patch_upper", "CRPA UPPER PATCH (1559-1610 MHz) rev A", up, []),
              array_plate()):
        print("wrote", p)

