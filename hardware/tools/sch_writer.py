"""
Minimal KiCad schematic writer.

Places library symbols and connects their pins by net name: every pin gets a short
wire stub ending in a net label, a power symbol, or a no-connect flag. This keeps the
generated schematics readable and lets KiCad's ERC check the connectivity.

Symbols come from the official KiCad libraries (copied into lib_symbols) or from a
project library built with box_symbol(), which is also written to <project>.kicad_sym.
"""
import math
import re
import uuid
from pathlib import Path

KICAD_SYM = Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols")
SCH_VERSION = "20250114"
GRID = 2.54
STUB = 2.54
POWER_NETS = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "+12V": "power:+12V"}


def uid():
    return str(uuid.uuid4())


def _extract_block(text, start):
    """Return the balanced (...) block starting at index start."""
    depth, i, in_str = 0, start, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced block")


PIN_RE = re.compile(r'\(pin (\w+) (\w+)\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)\s*\(length ([-\d.]+)\)'
                    r'[\s\S]*?\(name "((?:[^"\\]|\\.)*)"[\s\S]*?\(number "((?:[^"\\]|\\.)*)"')


class LibSymbol:
    def __init__(self, lib_id, text, power=False):
        self.lib_id = lib_id
        self.text = text
        self.power = power
        self.pins = []   # (number, name, type, x, y, angle)
        name = lib_id.split(":")[1]
        for m in re.finditer(r'\(symbol "' + re.escape(name) + r'_(\d+)_(\d+)"', text):
            unit, style = int(m.group(1)), int(m.group(2))
            if unit not in (0, 1) or style not in (0, 1):
                continue
            sub = _extract_block(text, m.start())
            for p in PIN_RE.finditer(sub):
                self.pins.append((p.group(8), p.group(7), p.group(1),
                                  float(p.group(3)), float(p.group(4)), float(p.group(5))))


def load_library_symbol(lib, name):
    text = (KICAD_SYM / f"{lib}.kicad_sym").read_text(encoding="utf-8")
    m = re.search(r'\n\t\(symbol "' + re.escape(name) + r'"\s', text)
    if not m:
        raise KeyError(f"{lib}:{name}")
    block = _extract_block(text, m.start() + 2)
    if "(extends " in block[:400]:
        raise ValueError(f"{lib}:{name} is a derived symbol; pick its parent")
    block = block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
    return LibSymbol(f"{lib}:{name}", block, power=lib == "power")


def _fmt(x):
    return f"{x:.4f}".rstrip("0").rstrip(".")


def box_symbol(lib, name, left=(), right=(), top=(), bottom=(), width=20.32, ref="U",
               description=""):
    """
    Build a rectangular symbol. Each side is a list of (number, name, type).
    Returns (LibSymbol for lib_symbols, library text for the project .kicad_sym).
    """
    n_v = max(len(left), len(right), 1)
    n_h = max(len(top), len(bottom), 1)
    width = max(width, (n_h + 1) * GRID)
    h = (n_v + 1) * GRID
    w = math.ceil(width / GRID / 2) * GRID * 2
    pins = []
    for i, (num, pname, ptype) in enumerate(left):
        pins.append((num, pname, ptype, -w / 2 - GRID, h / 2 - GRID * (i + 1), 0))
    for i, (num, pname, ptype) in enumerate(right):
        pins.append((num, pname, ptype, w / 2 + GRID, h / 2 - GRID * (i + 1), 180))
    for i, (num, pname, ptype) in enumerate(top):
        pins.append((num, pname, ptype, -w / 2 + GRID * (i + 1), h / 2 + GRID, 270))
    for i, (num, pname, ptype) in enumerate(bottom):
        pins.append((num, pname, ptype, -w / 2 + GRID * (i + 1), -h / 2 - GRID, 90))

    def body(full_name):
        pin_txt = "\n".join(
            f'\t\t\t(pin {t} line (at {_fmt(x)} {_fmt(y)} {int(a)}) (length {GRID})'
            f' (name "{pn}" (effects (font (size 1.016 1.016))))'
            f' (number "{num}" (effects (font (size 1.016 1.016)))))'
            for num, pn, t, x, y, a in pins)
        return (f'\t(symbol "{full_name}" (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
                f'\t\t(property "Reference" "{ref}" (at 0 {_fmt(h / 2 + 3.81)} 0) (effects (font (size 1.27 1.27))))\n'
                f'\t\t(property "Value" "{name}" (at 0 {_fmt(-h / 2 - 3.81)} 0) (effects (font (size 1.27 1.27))))\n'
                f'\t\t(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
                f'\t\t(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
                f'\t\t(property "Description" "{description}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
                f'\t\t(symbol "{name}_0_1" (rectangle (start {_fmt(-w / 2)} {_fmt(h / 2)}) (end {_fmt(w / 2)} {_fmt(-h / 2)})'
                f' (stroke (width 0.254) (type default)) (fill (type background))))\n'
                f'\t\t(symbol "{name}_1_1"\n{pin_txt})\n\t)')
    sym = LibSymbol(f"{lib}:{name}", body(f"{lib}:{name}"))
    return sym, body(name)


class Schematic:
    def __init__(self, project, title, paper="A1", rev="A"):
        self.project = project
        self.root = uid()
        self.title = title
        self.paper = paper
        self.rev = rev
        self.libs = {}
        self.items = []
        self.refs = {}
        self.pwr_count = 0
        self.net_pins = {}          # net -> list of pin electrical types
        self.flag_points = []

    def use(self, sym):
        self.libs[sym.lib_id] = sym
        return sym

    def _next_ref(self, prefix):
        self.refs[prefix] = self.refs.get(prefix, 0) + 1
        return f"{prefix}{self.refs[prefix]}"

    def _instance(self, sym, ref, value, x, y, fields=None, hide_ref=False, dnp=False):
        fields = dict(fields or {})
        props = [("Reference", ref, (x, y - 5.08), hide_ref), ("Value", value, (x, y + 5.08), False),
                 ("Footprint", fields.pop("Footprint", ""), (x, y), True),
                 ("Datasheet", fields.pop("Datasheet", ""), (x, y), True)]
        props += [(k, val, (x, y), True) for k, val in fields.items()]
        ptxt = "\n".join(
            f'\t\t(property "{k}" "{val}" (at {_fmt(px)} {_fmt(py)} 0)'
            f' (effects (font (size 1.27 1.27)){" (hide yes)" if hidden else ""}))'
            for k, val, (px, py), hidden in props)
        pins = "\n".join(f'\t\t(pin "{p[0]}" (uuid "{uid()}"))' for p in sym.pins)
        return (f'\t(symbol (lib_id "{sym.lib_id}") (at {_fmt(x)} {_fmt(y)} 0) (unit 1)\n'
                f'\t\t(exclude_from_sim no) (in_bom {"no" if sym.power else "yes"}) (on_board yes)'
                f' (dnp {"yes" if dnp else "no"})\n'
                f'\t\t(uuid "{uid()}")\n{ptxt}\n{pins}\n'
                f'\t\t(instances (project "{self.project}" (path "/{self.root}"'
                f' (reference "{ref}") (unit 1))))\n\t)')

    def _wire(self, a, c):
        self.items.append(f'\t(wire (pts (xy {_fmt(a[0])} {_fmt(a[1])}) (xy {_fmt(c[0])} {_fmt(c[1])}))'
                          f' (stroke (width 0) (type default)) (uuid "{uid()}"))')

    def _label(self, net, at, angle):
        just = "right bottom" if angle in (180, 270) else "left bottom"
        self.items.append(f'\t(label "{net}" (at {_fmt(at[0])} {_fmt(at[1])} {angle})'
                          f' (effects (font (size 1.27 1.27)) (justify {just})) (uuid "{uid()}"))')

    def _power(self, net, at, angle):
        sym = self.use(load_library_symbol("power", POWER_NETS[net].split(":")[1]))
        self.pwr_count += 1
        txt = self._instance(sym, f"#PWR{self.pwr_count:03d}", net, at[0], at[1], hide_ref=True)
        txt = txt.replace(f'(at {_fmt(at[0])} {_fmt(at[1])} 0) (unit 1)',
                          f'(at {_fmt(at[0])} {_fmt(at[1])} {angle}) (unit 1)', 1)
        self.items.append(txt)

    def no_connect(self, at):
        self.items.append(f'\t(no_connect (at {_fmt(at[0])} {_fmt(at[1])}) (uuid "{uid()}"))')

    def text(self, s, at, size=2.0):
        s = s.replace('"', "'")
        self.items.append(f'\t(text "{s}" (exclude_from_sim no) (at {_fmt(at[0])} {_fmt(at[1])} 0)'
                          f' (effects (font (size {size} {size})) (justify left bottom)) (uuid "{uid()}"))')

    def place(self, sym, ref_prefix, value, at, nets, fields=None, ref=None, dnp=False):
        """
        Place a symbol at `at` (snapped to grid). `nets` maps pin number (or pin name)
        to a net name, "NC" for no-connect; unlisted pins are flagged no-connect.
        """
        self.use(sym)
        x, y = (round(at[0] / GRID) * GRID, round(at[1] / GRID) * GRID)
        ref = ref or self._next_ref(ref_prefix)
        self.items.append(self._instance(sym, ref, value, x, y, fields, dnp=dnp))
        for num, name, ptype, px, py, ang in sym.pins:
            net = nets.get(num, nets.get(name, "NC"))
            pin = (x + px, y - py)
            a = math.radians(ang)
            d = (-round(math.cos(a)), round(math.sin(a)))
            end = (pin[0] + d[0] * STUB, pin[1] + d[1] * STUB)
            if net == "NC":
                self.no_connect(pin)
                continue
            self._wire(pin, end)
            self.net_pins.setdefault(net, []).append(ptype)
            angle = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[d]
            if net in POWER_NETS:
                p_ang = {(-1, 0): 90, (1, 0): 270, (0, -1): 0, (0, 1): 180}[d]
                if net == "GND":
                    p_ang = {(-1, 0): 270, (1, 0): 90, (0, -1): 180, (0, 1): 0}[d]
                self._power(net, end, p_ang)
            else:
                self._label(net, end, angle)
        return ref

    def power_flags(self, at, extra_nets=()):
        """PWR_FLAG on every power net (and extra_nets) that no power-output pin drives."""
        flag = self.use(load_library_symbol("power", "PWR_FLAG"))
        x, y = (round(at[0] / GRID) * GRID, round(at[1] / GRID) * GRID)
        for net in list(POWER_NETS) + list(extra_nets):
            types = self.net_pins.get(net, [])
            if not types or "power_out" in types:
                continue
            self.pwr_count += 1
            self.items.append(self._instance(flag, f"#FLG{self.pwr_count:03d}", "PWR_FLAG", x, y, hide_ref=True))
            self._wire((x, y), (x, y + STUB))
            if net in POWER_NETS:
                self._power(net, (x, y + STUB), 180 if net == "GND" else 0)
            else:
                self._label(net, (x, y + STUB), 270)
            x += 12.7

    def save(self, path, project_lib_text=None, project_lib_name=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        libs = "\n".join(s.text if s.text.startswith("\t") else "\t" + s.text for s in self.libs.values())
        body = "\n".join(self.items)
        txt = (f'(kicad_sch (version {SCH_VERSION}) (generator "eeschema") (generator_version "9.0")\n'
               f'\t(uuid "{self.root}")\n\t(paper "{self.paper}")\n'
               f'\t(title_block (title "{self.title}") (rev "{self.rev}") (company "GNSS anti-jam CRPA")'
               f' (comment 1 "Generated by hardware/*/gen_*.py - edit the generator, not this file")'
               f' (comment 2 "Part numbers marked VERIFY are candidates: check datasheet, pinout, availability"))\n'
               f'\t(lib_symbols\n{libs}\n\t)\n{body}\n'
               f'\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n')
        path.write_text(txt, encoding="utf-8")
        pro = path.with_suffix(".kicad_pro")
        if not pro.exists():
            pro.write_text('{"meta": {"filename": "%s", "version": 1}}\n' % pro.name)
        if project_lib_text:
            lib = path.parent / f"{project_lib_name}.kicad_sym"
            lib.write_text('(kicad_symbol_lib (version 20251024) (generator "gen")\n'
                           + "\n".join(project_lib_text) + "\n)\n", encoding="utf-8")
            (path.parent / "sym-lib-table").write_text(
                '(sym_lib_table\n  (version 7)\n'
                f'  (lib (name "{project_lib_name}")(type "KiCad")(uri "${{KIPRJMOD}}/{project_lib_name}.kicad_sym")(options "")(descr ""))\n)\n')
        return path
