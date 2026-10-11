"""
Shared helpers for generating KiCad boards with the pcbnew API (run with KiCad's Python).

KiCad coordinates: x right, y DOWN, viewed from the top. All values in mm.
Zones are not filled here (ZONE_FILLER crashes headless); check_boards.ps1 fills them.
"""
import json
import math
from pathlib import Path

import pcbnew

KICAD_FP = Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
MM = pcbnew.FromMM


def v(xy):
    return pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1]))


def angle_of(a, c):
    """KiCad footprint orientation (deg, CCW positive on screen) along a -> c."""
    return -math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))


class Board:
    def __init__(self, title, thickness_mm, rev="B"):
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
        tb.SetRevision(f"{rev} (pre-EM-tuning)")
        self.ref_count = {}

    # ---- nets / primitives -------------------------------------------------
    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

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

    def outline_square(self, half):
        self.outline_rect(-half, -half, half, half)

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

    def text(self, s, xy, layer=pcbnew.F_SilkS, size=1.5, mirrored=False):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(v(xy))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(size * 0.15))
        t.SetMirrored(mirrored)
        self.b.Add(t)

    # ---- footprints ----------------------------------------------------------
    def _ref(self, prefix):
        self.ref_count[prefix] = self.ref_count.get(prefix, 0) + 1
        return f"{prefix}{self.ref_count[prefix]}"

    def footprint(self, lib, name, xy, angle=0.0, bottom=False, ref_prefix="U", value="",
                  nets=None, ref=None, hide_ref=False):
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
        if hide_ref:
            fp.Reference().SetVisible(False)
        for pad in fp.Pads():
            if nets and pad.GetNumber() in nets and nets[pad.GetNumber()]:
                pad.SetNet(self.net(nets[pad.GetNumber()]))
        return fp

    def custom_footprint(self, ref, value, xy, pads, angle=0.0, bottom=False, body=None):
        """pads: list of dicts {num, x, y, w, h, net, shape('rect'|'circle'), smd(bool), drill}."""
        fp = pcbnew.FOOTPRINT(self.b)
        fp.SetReference(ref)
        fp.SetValue(value)
        for p in pads:
            pad = pcbnew.PAD(fp)
            pad.SetNumber(p["num"])
            pad.SetShape(pcbnew.PAD_SHAPE_RECTANGLE if p.get("shape", "rect") == "rect"
                         else pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(MM(p["w"]), MM(p["h"])))
            if p.get("npth"):
                pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
                pad.SetDrillSize(pcbnew.VECTOR2I(MM(p["drill"]), MM(p["drill"])))
                pad.SetSize(pcbnew.VECTOR2I(MM(p["drill"]), MM(p["drill"])))
                pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
            elif p.get("smd", True):
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
            else:
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetDrillSize(pcbnew.VECTOR2I(MM(p["drill"]), MM(p["drill"])))
                pad.SetLayerSet(pcbnew.PAD.PTHMask())
            if "clearance" in p:
                pad.SetLocalClearance(MM(p["clearance"]))
            pad.SetFPRelativePosition(v((p["x"], p["y"])))
            fp.Add(pad)
        if body:
            w, h = body
            for a, c in (((-w / 2, -h / 2), (w / 2, -h / 2)), ((w / 2, -h / 2), (w / 2, h / 2)),
                         ((w / 2, h / 2), (-w / 2, h / 2)), ((-w / 2, h / 2), (-w / 2, -h / 2))):
                s = pcbnew.PCB_SHAPE(fp)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                s.SetStart(v(a))
                s.SetEnd(v(c))
                s.SetLayer(pcbnew.F_Fab)
                s.SetWidth(MM(0.1))
                fp.Add(s)
        self.b.Add(fp)
        fp.SetPosition(v(xy))
        if bottom:
            fp.Flip(v(xy), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(angle)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        by_num = {pad.GetNumber(): pad for pad in fp.Pads()}   # Flip() can reorder the pads
        for p in pads:
            if p.get("net"):
                by_num[p["num"]].SetNet(self.net(p["net"]))
        return fp

    def pad_position(self, fp, num):
        pad = next(p for p in fp.Pads() if p.GetNumber() == num)
        pos = pad.GetPosition()
        return (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))

    def hole(self, xy, drill, ref, value="hole"):
        """Plain unplated hole (machined plate holes)."""
        return self.custom_footprint(ref, value, xy, [
            {"num": "", "x": 0, "y": 0, "w": drill, "h": drill, "shape": "circle", "npth": True,
             "drill": drill}])

    def th_pad(self, xy, drill, dia, net, ref, clearance=None, value="probe"):
        return self.custom_footprint(ref, value, xy, [
            {"num": "1", "x": 0, "y": 0, "w": dia, "h": dia, "shape": "circle", "smd": False,
             "drill": drill, "net": net, **({"clearance": clearance} if clearance else {})}])

    # ---- zones ---------------------------------------------------------------
    def zone_rect(self, layer, net, x0, y0, x1, y1, clearance=0.3, priority=0, keep_islands=False):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        if net:
            z.SetNet(self.net(net))
        if keep_islands:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        z.SetLocalClearance(MM(clearance))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(priority)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            ol.Append(MM(x), MM(y))
        self.b.Add(z)
        return z

    def zone_square(self, layer, net, half, **kw):
        return self.zone_rect(layer, net, -half, -half, half, half, **kw)

    def save(self, out_dir, name):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{name}.kicad_pcb"
        pcbnew.SaveBoard(str(path), self.b)
        pro = out / f"{name}.kicad_pro"
        if not pro.exists():
            pro.write_text(json.dumps({"meta": {"filename": pro.name, "version": 1}}, indent=2))
        return path


# 0603 in series on a line, with the line ends kept inside the pads
PAD_CENTRE = 0.775
PAD_LEN = 0.9
R_FP = ("Resistor_SMD", "R_0603_1608Metric")
C_FP = ("Capacitor_SMD", "C_0603_1608Metric")


def series_part(bd, a, c, frac, lib, name, value, ref_prefix, net_a, net_c, width, ref=None):
    ux, uy = c[0] - a[0], c[1] - a[1]
    length = math.hypot(ux, uy)
    ux, uy = ux / length, uy / length
    mid = (a[0] + ux * length * frac, a[1] + uy * length * frac)
    pa = (mid[0] - ux * PAD_CENTRE, mid[1] - uy * PAD_CENTRE)
    pc = (mid[0] + ux * PAD_CENTRE, mid[1] + uy * PAD_CENTRE)
    inner = PAD_CENTRE - PAD_LEN / 2
    reach = max(PAD_CENTRE, inner + width / 2 + 0.02)
    assert reach < PAD_CENTRE + PAD_LEN / 2, "line too wide for the pad"
    bd.track(a, (mid[0] - ux * reach, mid[1] - uy * reach), width, net_a)
    bd.track((mid[0] + ux * reach, mid[1] + uy * reach), c, width, net_c)
    fp = bd.footprint(lib, name, mid, angle=angle_of(a, c), bottom=True, ref_prefix=ref_prefix,
                      value=value, nets={"1": net_a, "2": net_c}, ref=ref)
    p1 = bd.pad_position(fp, "1")
    if math.hypot(p1[0] - pa[0], p1[1] - pa[1]) > math.hypot(p1[0] - pc[0], p1[1] - pc[1]):
        fp.SetOrientationDegrees(fp.GetOrientationDegrees() + 180)
    return fp
