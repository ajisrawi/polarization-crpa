"""
Project symbol library ("crpa") for the CRPA front-end and DSP/GNSS carrier schematics.

These are functional symbols: pin NAMES are what matters. Pin numbers are sequential
placeholders, so every symbol here carries "VERIFY" in its Description. Assign the real
footprint and pin numbers from the chosen part's datasheet before PCB layout.
Standard parts (R, C, L, SMA, USB-C, ZED module) come from the official KiCad libraries.
"""
from sch_writer import box_symbol

LIB = "crpa"
PAS, PIN, POUT, IN, OUT, BID = "passive", "power_in", "power_out", "input", "output", "bidirectional"


def _sym(name, ref, desc, left=(), right=(), top=(), bottom=(), width=20.32):
    def number(side, start):
        return [(str(start + i), n, t) for i, (n, t) in enumerate(side)]
    n = 1
    sides = []
    for side in (left, right, top, bottom):
        sides.append(number(side, n))
        n += len(side)
    return box_symbol(LIB, name, *sides, width=width, ref=ref, description=desc)


def all_symbols():
    s = {}
    s["LIMITER"] = _sym("LIMITER", "D", "RF power limiter 0.5-2 GHz, +40 dBm survivable. Candidate: Skyworks/Macom PIN limiter. VERIFY",
                        left=[("IN", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["COUPLER"] = _sym("COUPLER", "U", "20 dB directional coupler 1.1-1.7 GHz for cal injection. VERIFY",
                        left=[("IN", PAS)], right=[("OUT", PAS)], top=[("CPL", PAS)], bottom=[("GND", PIN)])
    s["LNA"] = _sym("LNA", "U", "Multi-band GNSS LNA 1164-1615 MHz, NF<1 dB. Candidate: Infineon BGA855N6. VERIFY",
                    left=[("RFIN", PAS)], right=[("RFOUT", PAS)], top=[("VCC", PIN)], bottom=[("GND", PIN)])
    s["BPF"] = _sym("BPF", "FL", "Band-pass 1150-1620 MHz (anti-alias for 2.0 GSPS 2nd Nyquist). VERIFY",
                    left=[("IN", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["LPF"] = _sym("LPF", "FL", "Low-pass ~1.7 GHz reconstruction filter for the RF-DAC output. VERIFY",
                    left=[("IN", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["GAIN_BLOCK"] = _sym("GAIN_BLOCK", "U", "Gain block, bias through RF choke. Candidate: Mini-Circuits PGA-103+. VERIFY",
                           left=[("RFIN", PAS)], right=[("RFOUT", PAS)], bottom=[("GND", PIN)])
    s["SPLIT4"] = _sym("SPLIT4", "U", "1:4 power splitter 1.1-1.7 GHz. VERIFY",
                       left=[("IN", PAS)], right=[("OUT1", PAS), ("OUT2", PAS), ("OUT3", PAS), ("OUT4", PAS)],
                       bottom=[("GND", PIN)])
    s["BALUN"] = _sym("BALUN", "T", "1:1 balun 10-6000 MHz for RFSoC ADC/DAC. Candidate: Mini-Circuits TCM1-63AX+. VERIFY",
                      left=[("SE", PAS)], right=[("BAL_P", PAS), ("BAL_N", PAS)], bottom=[("GND", PIN)])
    s["LDO"] = _sym("LDO", "U", "Low-noise LDO. Candidate: ADI LT3045. VERIFY",
                    left=[("VIN", PIN), ("EN", IN)], right=[("VOUT", POUT)], bottom=[("GND", PIN)])
    s["DCDC"] = _sym("DCDC", "U", "Buck converter 12V->5V 3A. Candidate: TI TPS54560 or module. VERIFY",
                     left=[("VIN", PIN), ("EN", IN)], right=[("VOUT", POUT)], bottom=[("GND", PIN)])
    s["OCXO"] = _sym("OCXO", "Y", "10 MHz OCXO, LVCMOS out, <1 ppb. VERIFY",
                     left=[("VCC", PIN)], right=[("OUT", OUT)], bottom=[("GND", PIN)])
    s["CLKBUF2"] = _sym("CLKBUF2", "U", "1:2 LVCMOS clock buffer. Candidate: TI LMK1C1102. VERIFY",
                        left=[("IN", IN), ("VCC", PIN)], right=[("OUT1", OUT), ("OUT2", OUT)], bottom=[("GND", PIN)])
    s["HYBRID90"] = _sym("HYBRID90", "U", "SMD 90-degree 3 dB hybrid 1-2 GHz. Candidate: Electro-Photonics Q3XG-1500R. VERIFY port map",
                         left=[("IN", PAS), ("ISO", PAS)], right=[("THRU", PAS), ("CPL", PAS)], bottom=[("GND", PIN)])
    s["SAW_LO"] = _sym("SAW_LO", "FL", "GNSS SAW/BAW band-pass 1164-1300 MHz (L5/E5/L2/G2/E6/B3). VERIFY part",
                       left=[("IN", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["SAW_HI"] = _sym("SAW_HI", "FL", "GNSS SAW/BAW band-pass 1559-1610 MHz (B1I/L1/E1/B1C/G1). VERIFY part",
                       left=[("IN", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["WILKINSON"] = _sym("WILKINSON", "U", "2-way Wilkinson combiner 1.1-1.7 GHz, printed on RO4350B (100R isolation resistor)",
                          left=[("IN1", PAS), ("IN2", PAS)], right=[("OUT", PAS)], bottom=[("GND", PIN)])
    s["JUMPER3"] = _sym("JUMPER3", "JP", "3-pad alternate-fit 0R jumper: fit A-C or C-B",
                        left=[("A", PAS), ("B", PAS)], right=[("C", PAS)], width=12.7)
    s["PROBE"] = _sym("PROBE", "P", "Antenna feed probe / coax inner (PTH pad)",
                      right=[("FEED", PAS)], width=10.16)
    s["GNSS_LNA_WB"] = _sym("GNSS_LNA_WB", "U", "Wideband GNSS LNA 1164-1615 MHz. Candidate: Infineon BGA855N6. VERIFY",
                            left=[("RFIN", PAS)], right=[("RFOUT", PAS)], top=[("VCC", PIN)], bottom=[("GND", PIN)])
    adc = [(f"ADC{i}_{pn}", IN) for i in range(12) for pn in ("P", "N")]
    dac = [(f"DAC{i}_{pn}", OUT) for i in range(3) for pn in ("P", "N")]
    misc = [("REF_10M_IN", IN), ("PPS_IN", IN), ("GNSS_UART_TX", OUT), ("GNSS_UART_RX", IN),
            ("GNSS_RESET_N", OUT), ("GNSS_EXTINT", OUT)]
    s["RFSOC_SOM"] = _sym("RFSOC_SOM", "U",
                          "iWave iW-RainboW-G42M ZU49DR RFSoC SOM (2x 400-pin B2B). Functional view: map every pin to the SOM pinout. VERIFY",
                          left=adc, right=dac + misc, top=[("VIN_12V", PIN)], bottom=[("GND", PIN)], width=40.64)
    return s
