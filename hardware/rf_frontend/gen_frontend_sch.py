"""
12-channel RF front-end schematic (antenna element -> RFSoC carrier).

Per channel: SMA in -> limiter -> 20 dB cal coupler -> LNA -> band-pass -> gain block -> SMA out.
A calibration tone/noise from RFSoC DAC1 is split 1:12 and injected through the couplers,
so the DSP can measure and equalize every RF chain (see crpa_model.Receiver.equalize).

Run:  python hardware/rf_frontend/gen_frontend_sch.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
from sch_writer import Schematic, load_library_symbol  # noqa: E402
from crpa_symbols import all_symbols  # noqa: E402

N_CH = 12
ELEMENTS = ["RHCP", "RHCP", "RHCP", "H", "H", "H", "V", "V", "V", "LHCP-tilted", "LHCP-tilted", "LHCP-tilted"]


def main():
    sym = all_symbols()
    R = load_library_symbol("Device", "R")
    C = load_library_symbol("Device", "C")
    L = load_library_symbol("Device", "L")
    SMA = load_library_symbol("Connector", "Conn_Coaxial")
    sch = Schematic("rf_frontend", "CRPA 12-channel RF front-end", paper="A0")
    lib = lambda k: sym[k][0]

    x0, y0, dx, dy = 30.0, 60.0, 50.8, 33.02
    sch.text("CRPA 12-channel RF front-end - one row per antenna element. Rev C: active elements (LNA at the antenna); this board: bias-tee, cal coupler, BPF, gain block.", (20, 25), 3)
    sch.text("Cal injection: DAC1 tone/noise -> J_CAL -> 1:12 split -> 20 dB couplers (after the element LNAs; element part characterised at the factory).", (20, 33), 2)
    for ch in range(N_CH):
        y = y0 + ch * dy
        n = ch + 1
        x = x0
        sch.text(f"CH{n:02d}  element: {ELEMENTS[ch]}", (x - 10, y - 12), 2)
        # rev C: the element is ACTIVE (limiter + per-band LNA + SAW at the antenna); this board
        # feeds it 5 V over the coax and keeps the cal coupler, filter and gain block.
        sch.place(SMA, "J", f"ANT{n} (RF in, 5 V out)", (x, y), {"1": f"ANT{n}", "2": "GND"})
        sch.place(L, "L", "82n RF choke", (x + 18, y - 15), {"1": f"ANT{n}", "2": f"VANT{n}"})
        sch.place(R, "R", "10R (current limit / sense)", (x + 33, y - 15), {"1": "+5V", "2": f"VANT{n}"})
        sch.place(C, "C", "10n", (x + 46, y - 15), {"1": f"VANT{n}", "2": "GND"})
        x += dx
        sch.place(C, "C", "100p DC block", (x, y), {"1": f"ANT{n}", "2": f"RFI{n}"})
        x += dx * 0.75
        sch.place(lib("COUPLER"), "U", "COUPLER 20dB", (x, y),
                  {"IN": f"RFI{n}", "OUT": f"CPO{n}", "CPL": f"CAL{n}", "GND": "GND"})
        x += dx
        sch.place(lib("BPF"), "FL", "BPF 1150-1620", (x, y), {"IN": f"CPO{n}", "OUT": f"BPF{n}", "GND": "GND"})
        x += dx
        sch.place(C, "C", "100p DC block", (x, y), {"1": f"BPF{n}", "2": f"AMI{n}"})
        x += dx * 0.75
        sch.place(lib("GAIN_BLOCK"), "U", "PGA-103+", (x, y), {"RFIN": f"AMI{n}", "RFOUT": f"AMO{n}", "GND": "GND"})
        x += dx
        sch.place(L, "L", "82n RF choke", (x, y - 15), {"1": f"BIAS{n}", "2": f"AMO{n}"})
        sch.place(R, "R", "10R", (x + 15, y - 15), {"1": "+5V", "2": f"BIAS{n}"})
        sch.place(C, "C", "10n", (x + 28, y - 15), {"1": f"BIAS{n}", "2": "GND"})
        x += dx * 0.75
        sch.place(C, "C", "100p DC block", (x, y), {"1": f"AMO{n}", "2": f"OUT{n}"})
        x += dx
        sch.place(SMA, "J", f"CH{n} out to RFSoC ADC{ch}", (x, y), {"1": f"OUT{n}", "2": "GND"})

    # calibration distribution: 1 -> 4 -> 12 (+ spare outputs terminated)
    cx, cy = x0 + 11 * dx + 40, y0
    sch.text("Calibration distribution", (cx - 10, cy - 15), 2.5)
    sch.place(SMA, "J", "J_CAL in from DAC1", (cx, cy), {"1": "CAL_IN", "2": "GND"})
    sch.place(lib("SPLIT4"), "U", "SPLIT4 (stage 1)", (cx + 45, cy),
              {"IN": "CAL_IN", "OUT1": "CALA", "OUT2": "CALB", "OUT3": "CALC", "OUT4": "CAL_SPARE", "GND": "GND"})
    sch.place(R, "R", "49.9R term", (cx + 80, cy + 20), {"1": "CAL_SPARE", "2": "GND"})
    for k, src in enumerate(("CALA", "CALB", "CALC")):
        outs = {f"OUT{j + 1}": f"CAL{k * 4 + j + 1}" for j in range(4)}
        sch.place(lib("SPLIT4"), "U", f"SPLIT4 (stage 2{'abc'[k]})", (cx + 45, cy + 45 + k * 40),
                  {"IN": src, **outs, "GND": "GND"})

    # power: +5V in, LDO to +3V3
    py = y0 + 7 * dy
    sch.text("Power", (cx - 10, py - 15), 2.5)
    pwr = load_library_symbol("Connector", "Conn_Coaxial")  # placeholder-free: use a 2-pin header below
    hdr = load_library_symbol("Connector_Generic", "Conn_01x02")
    sch.place(hdr, "J", "+5V in (from carrier)", (cx, py), {"1": "+5V", "2": "GND"})
    sch.place(C, "C", "22u", (cx + 25, py + 10), {"1": "+5V", "2": "GND"})
    sch.place(lib("LDO"), "U", "LT3045 3.3V", (cx + 55, py), {"VIN": "+5V", "EN": "+5V", "VOUT": "+3V3", "GND": "GND"})
    sch.place(C, "C", "10u", (cx + 85, py + 10), {"1": "+3V3", "2": "GND"})
    sch.power_flags((cx, py + 40))
    del pwr

    path = sch.save(HERE / "rf_frontend.kicad_sch", [v[1] for v in sym.values()], "crpa")
    print("wrote", path)


if __name__ == "__main__":
    main()

