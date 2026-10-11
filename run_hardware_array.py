"""
Simulate the array exactly as laid out in hardware/antenna (array_plate/element_positions.json):
3x3 grid at 125 mm pitch (RHCP / linear-H / vertical monopole) + 3 LHCP modules tilted to
boresight elevation 10 deg toward the expected jammer (azimuth 0 = north = top of the plate).

Plate coordinates are KiCad (x right, y down); the model uses x = east, y = north.

Run:  python run_hardware_array.py      (writes results/hardware_array.md)
"""
import json
from pathlib import Path

import numpy as np

from crpa_model import ArrayConfig, Emitter, Port, jones_rhcp
from run_experiments import (OUT, TRACK_DB_HZ, array_user_mixed, jammers_default, make_rx,
                             run_processor, satellites_default)

import sys

REV_DIRS = {"A": "antenna", "B": "antenna_tmm"}
REV = sys.argv[1].upper() if len(sys.argv) > 1 else "A"      # python run_hardware_array.py B
ELEMENTS = Path(__file__).parent / "hardware" / REV_DIRS[REV] / "array_plate" / "element_positions.json"


def hardware_array(tilted_kind="L"):
    ports = []
    for e in json.loads(ELEMENTS.read_text()):
        pos = (e["x"] / 1000.0, -e["y"] / 1000.0)
        if e["kind"] == "L_tilted":
            ports.append(Port(tilted_kind, pos, boresight_el_deg=e["boresight_el_deg"],
                              boresight_az_deg=e["boresight_az_deg"]))
        elif e["kind"] == "H":
            ports.append(Port("H", pos, orient_deg=e.get("pol_deg", e["rot_deg"])))
        else:
            ports.append(Port(e["kind"], pos))
    ref = next(i for i, p in enumerate(ports) if p.kind == "R" and p.pos == (0.0, 0.0))
    label = "LHCP" if tilted_kind == "L" else "RHCP (jumpers swapped)"
    return ArrayConfig(f"Rev {REV} hardware, tilted = {label}", ports, ref_port=ref)


def main():
    sats = satellites_default()
    cases = {
        "6 mixed jammers (experiment 2)": jammers_default(),
        "RHCP jammer 60 dB, el 10 az 0": [Emitter(10, 0, jones_rhcp(), 60, bw_hz=8e6)],
        "RHCP jammer 80 dB, el 10 az 0": [Emitter(10, 0, jones_rhcp(), 80, bw_hz=8e6)],
        "RHCP jammer 90 dB, el 10 az 0": [Emitter(10, 0, jones_rhcp(), 90, bw_hz=8e6)],
        "2 RHCP jammers (65 dB az 0, 60 dB az 150)": [Emitter(10, 0, jones_rhcp(), 65, bw_hz=8e6),
                                                      Emitter(6, 150, jones_rhcp(), 60, bw_hz=8e6)],
    }
    arrays = [array_user_mixed(), hardware_array("L"), hardware_array("R")]
    rng = np.random.default_rng(50)
    lines = ["# Hardware array check", "",
             "Satellites tracked (of 9, C/N0 >= 28 dB-Hz) with equalized channels, 5 taps.", "",
             "| Scenario | " + " | ".join(f"{a.name} PI / MVDR" for a in arrays) + " |",
             "|---|" + "---|" * len(arrays)]
    for title, jams in cases.items():
        cells = []
        for cfg in arrays:
            rx = make_rx(cfg, n_samples=2 ** 14)
            got = []
            for algo in ("PI", "MVDR"):
                _, ev = run_processor(rx, jams, sats, algo, 5, rng)
                got.append(str(int((ev["cn0"] >= TRACK_DB_HZ).sum())))
            cells.append(" / ".join(got))
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
        print(lines[-1], flush=True)
    (OUT / f"hardware_array_rev{REV}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
