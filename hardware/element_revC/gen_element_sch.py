"""
Rev C ACTIVE element electronics (one per patch module, on the feed board) + monopole base.

Per band:  probe pair -> 90deg hybrid -> RHCP/LHCP jumper -> limiter -> LNA -> band SAW
Both bands -> Wilkinson combiner -> bias-tee -> SMA (5 V DC arrives on the coax)
Circular modules (R and tilted): all parts fitted. Linear modules: hybrids DNP, the single
probe of each band is bridged straight to the limiter with the 0R option (R_LIN_LO / R_LIN_HI).
Monopole base board: limiter -> wideband LNA -> 1150-1620 MHz band-pass -> bias-tee -> SMA.

EM-verified antenna-side values (hardware/em, air4_c9): upper probes need C_HI = 1.5 pF series.

Run:  python hardware/element_revC/gen_element_sch.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
from sch_writer import Schematic, load_library_symbol  # noqa: E402
from crpa_symbols import all_symbols  # noqa: E402


def band_chain(sch, lib, R, C, x, y, band, saw):
    """Probe pair -> hybrid -> jumper/terminations -> limiter -> LNA -> SAW. Returns output net."""
    b = band
    sch.text(f"{'LOWER band 1164-1300 MHz (patch A, disk-fed probes)' if b == 'LO' else 'UPPER band 1559-1610 MHz (patch C, coax-fed probes)'}",
             (x - 10, y - 30), 2.2)
    sch.place(lib("PROBE"), "P", f"probe X {b}", (x, y - 10), {"FEED": f"PX_{b}"})
    sch.place(lib("PROBE"), "P", f"probe Y {b}", (x, y + 10), {"FEED": f"PY_{b}"})
    if b == "HI":   # EM-tuned series capacitors on the upper probes
        sch.place(C, "C", "1.5p C0G 0402", (x + 22, y - 10), {"1": f"PX_{b}", "2": f"PXC_{b}"},
                  fields={"Description": "EM-tuned (air4_c9); +-0.05 pF"})
        sch.place(C, "C", "1.5p C0G 0402", (x + 34, y + 10), {"1": f"PY_{b}", "2": f"PYC_{b}"},
                  fields={"Description": "EM-tuned (air4_c9); +-0.05 pF"})
        px, py = f"PXC_{b}", f"PYC_{b}"
    else:
        sch.place(C, "C", "0R (disk feed)", (x + 22, y - 10), {"1": f"PX_{b}", "2": f"PXC_{b}"})
        sch.place(C, "C", "0R (disk feed)", (x + 34, y + 10), {"1": f"PY_{b}", "2": f"PYC_{b}"})
        px, py = f"PXC_{b}", f"PYC_{b}"
    sch.place(lib("HYBRID90"), "U", "Q3XG-1500R (DNP on linear)", (x + 70, y),
              {"THRU": px, "CPL": py, "IN": f"H1_{b}", "ISO": f"H4_{b}", "GND": "GND"})
    sch.place(R, "R", "49.9R if RHCP (term ISO port)", (x + 50, y + 30), {"1": f"H4_{b}", "2": "GND"})
    sch.place(R, "R", "49.9R if LHCP (term IN port)", (x + 62, y + 30), {"1": f"H1_{b}", "2": "GND"})
    sch.place(lib("JUMPER3"), "JP", "0R on A-C = RHCP / C-B = LHCP", (x + 110, y),
              {"A": f"H1_{b}", "B": f"H4_{b}", "C": f"POL_{b}"})
    sch.place(R, "R", "0R linear only (else DNP)", (x + 110, y + 30), {"1": px, "2": f"POL_{b}"})
    sch.place(lib("LIMITER"), "D", "PIN limiter", (x + 145, y), {"IN": f"POL_{b}", "OUT": f"LIM_{b}", "GND": "GND"})
    sch.place(lib("GNSS_LNA_WB"), "U", "BGA855N6", (x + 180, y),
              {"RFIN": f"LIM_{b}", "RFOUT": f"LNA_{b}", "VCC": "+3V3", "GND": "GND"})
    sch.place(C, "C", "100n", (x + 180, y - 25), {"1": "+3V3", "2": "GND"})
    sch.place(lib(saw), "FL", saw.replace("_", " "), (x + 215, y), {"IN": f"LNA_{b}", "OUT": f"BAND_{b}", "GND": "GND"})
    return f"BAND_{b}"


def main():
    sym = all_symbols()
    lib = lambda k: sym[k][0]
    R = load_library_symbol("Device", "R")
    C = load_library_symbol("Device", "C")
    L = load_library_symbol("Device", "L")
    SMA = load_library_symbol("Connector", "Conn_Coaxial")
    sch = Schematic("element_revC", "CRPA rev C active element (feed board) + monopole base", paper="A2")
    sch.text("Rev C active element: dual-band stacked patch, per-band hybrid + LNA + SAW, Wilkinson combine, DC over coax",
             (15, 15), 3)

    lo = band_chain(sch, lib, R, C, 30, 60, "LO", "SAW_LO")
    hi = band_chain(sch, lib, R, C, 30, 140, "HI", "SAW_HI")
    sch.place(lib("WILKINSON"), "U", "printed 2-way Wilkinson", (300, 100), {"IN1": lo, "IN2": hi, "OUT": "COMB", "GND": "GND"})
    sch.place(R, "R", "100R isolation (in Wilkinson)", (300, 125), {"1": lo, "2": hi})
    # bias-tee: DC from the coax -> LDO; RF -> SMA
    sch.place(C, "C", "100p DC block", (335, 100), {"1": "COMB", "2": "RF_OUT"})
    sch.place(L, "L", "82n RF choke", (355, 115), {"1": "RF_OUT", "2": "VCOAX"})
    sch.place(C, "C", "10n", (370, 130), {"1": "VCOAX", "2": "GND"})
    sch.place(SMA, "J", "SMA to front-end (RF + 5 V)", (390, 100), {"1": "RF_OUT", "2": "GND"})
    sch.place(lib("LDO"), "U", "TPS7A2033 3.3 V", (390, 150), {"VIN": "VCOAX", "EN": "VCOAX", "VOUT": "+3V3", "GND": "GND"})
    sch.place(C, "C", "1u", (420, 160), {"1": "+3V3", "2": "GND"})
    sch.place(C, "C", "1u", (365, 160), {"1": "VCOAX", "2": "GND"})

    # monopole active base (separate small board, same supply scheme)
    my = 230
    sch.text("MONOPOLE active base board (V elements): limiter -> wideband LNA -> BPF 1150-1620 MHz -> bias-tee -> SMA",
             (15, my - 20), 2.2)
    sch.place(lib("PROBE"), "P", "monopole rod (SMA bulkhead)", (30, my), {"FEED": "MONO"})
    sch.place(lib("LIMITER"), "D", "PIN limiter", (70, my), {"IN": "MONO", "OUT": "MLIM", "GND": "GND"})
    sch.place(lib("GNSS_LNA_WB"), "U", "BGA855N6", (110, my), {"RFIN": "MLIM", "RFOUT": "MLNA", "VCC": "+3V3M", "GND": "GND"})
    sch.place(lib("BPF"), "FL", "BPF 1150-1620", (150, my), {"IN": "MLNA", "OUT": "MBPF", "GND": "GND"})
    sch.place(C, "C", "100p DC block", (185, my), {"1": "MBPF", "2": "M_RF_OUT"})
    sch.place(L, "L", "82n RF choke", (205, my + 15), {"1": "M_RF_OUT", "2": "MVCOAX"})
    sch.place(SMA, "J", "SMA to front-end (RF + 5 V)", (235, my), {"1": "M_RF_OUT", "2": "GND"})
    sch.place(lib("LDO"), "U", "TPS7A2033 3.3 V", (235, my + 40), {"VIN": "MVCOAX", "EN": "MVCOAX", "VOUT": "+3V3M", "GND": "GND"})
    sch.place(C, "C", "1u", (265, my + 50), {"1": "+3V3M", "2": "GND"})
    sch.place(C, "C", "100n", (110, my - 25), {"1": "+3V3M", "2": "GND"})
    sch.place(C, "C", "10n", (220, my + 30), {"1": "MVCOAX", "2": "GND"})
    sch.power_flags((300, my + 40), extra_nets=["VCOAX", "MVCOAX"])

    path = sch.save(HERE / "element_revC.kicad_sch", [v[1] for v in sym.values()], "crpa")
    print("wrote", path)


if __name__ == "__main__":
    main()
