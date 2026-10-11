"""
RFSoC carrier schematic: 12 ADC inputs, beamformed RF out to the u-blox ZED-X20P,
calibration output, 10 MHz reference, power.

Signal path:
  front-end CHn -> SMA -> balun -> AC coupling -> RFSoC RF-ADC n (2.0 GSPS, 2nd Nyquist 1.0-2.0 GHz)
  STAP beamformer in the PL (crpa_dsp.py algorithms, power inversion / MVDR)
  RF-DAC0 (~6.4 GSPS, direct L-band synthesis 1164-1610 MHz) -> balun -> LPF -> 10 dB pad
      -> DC block -> ZED-X20P RF_IN      (clean all-band GNSS signal)
  RF-DAC2 -> same chain -> SMA "AJ RF OUT" for an external GNSS receiver
  RF-DAC1 -> balun -> SMA "CAL OUT" -> front-end calibration injection

The ZED-X20P uses KiCad's reviewed ZED-F9P symbol and footprint (u-blox states X20 is
pin-to-pin compatible with F9). VERIFY the pin table against the ZED-X20P datasheet.

Run:  python hardware/dsp_gnss/gen_dsp_sch.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
from sch_writer import Schematic, load_library_symbol  # noqa: E402
from crpa_symbols import all_symbols  # noqa: E402


def rf_dac_chain(sch, lib, C, R, x, y, dac, net_out, title):
    """RF-DAC -> balun -> LPF -> 10 dB pi pad -> net_out."""
    sch.text(title, (x - 10, y - 14), 2)
    sch.place(C, "C", "100n", (x - 6, y), {"1": f"DAC{dac}_P", "2": f"D{dac}P"})
    sch.place(C, "C", "100n", (x + 6, y), {"1": f"DAC{dac}_N", "2": f"D{dac}N"})
    sch.place(lib("BALUN"), "T", "TCM1-63AX+", (x + 35, y),
              {"SE": f"D{dac}SE", "BAL_P": f"D{dac}P", "BAL_N": f"D{dac}N", "GND": "GND"})
    sch.place(lib("LPF"), "FL", "LPF 1.7 GHz", (x + 75, y), {"IN": f"D{dac}SE", "OUT": f"D{dac}F", "GND": "GND"})
    # 10 dB pi attenuator: 96.2R shunt, 71.2R series, 96.2R shunt
    sch.place(R, "R", "96.2R", (x + 105, y + 12), {"1": f"D{dac}F", "2": "GND"})
    sch.place(R, "R", "71.2R", (x + 115, y), {"1": f"D{dac}F", "2": net_out})
    sch.place(R, "R", "96.2R", (x + 125, y + 12), {"1": net_out, "2": "GND"})


def main():
    sym = all_symbols()
    lib = lambda k: sym[k][0]
    R = load_library_symbol("Device", "R")
    C = load_library_symbol("Device", "C")
    SMA = load_library_symbol("Connector", "Conn_Coaxial")
    ZED = load_library_symbol("RF_GPS", "ZED-F9P")
    USB = load_library_symbol("Connector", "USB_C_Receptacle_USB2.0_16P")
    JACK = load_library_symbol("Connector", "Barrel_Jack")
    H2 = load_library_symbol("Connector_Generic", "Conn_01x02")
    H6 = load_library_symbol("Connector_Generic", "Conn_01x06")
    TP = load_library_symbol("Connector", "TestPoint")
    sch = Schematic("dsp_gnss", "CRPA RFSoC carrier + u-blox ZED-X20P", paper="A0")

    sch.text("RFSoC carrier: 12 RF-ADC inputs, STAP beamformer in PL, RF-DAC regenerates clean L-band RF for the ZED-X20P.", (20, 25), 3)

    # ---- SOM -------------------------------------------------------------------------------
    som_nets = {f"ADC{i}_{p}": f"ADC{i}_{p}" for i in range(12) for p in "PN"}
    som_nets.update({f"DAC{i}_{p}": f"DAC{i}_{p}" for i in range(3) for p in "PN"})
    som_nets.update({"REF_10M_IN": "REF_SOM", "PPS_IN": "PPS", "GNSS_UART_TX": "GNSS_RXD",
                     "GNSS_UART_RX": "GNSS_TXD", "GNSS_RESET_N": "GNSS_RESET_N",
                     "GNSS_EXTINT": "GNSS_EXTINT", "VIN_12V": "+12V", "GND": "GND"})
    sch.place(lib("RFSOC_SOM"), "U", "iW-RainboW-G42M (ZU49DR)", (330, 150), som_nets, ref="U1")

    # ---- 12 ADC inputs ---------------------------------------------------------------------
    for i in range(12):
        y = 60 + i * 22.86
        sch.place(SMA, "J", f"ADC{i} in (from front-end CH{i + 1})", (40, y), {"1": f"AIN{i}", "2": "GND"})
        sch.place(lib("BALUN"), "T", "TCM1-63AX+", (85, y),
                  {"SE": f"AIN{i}", "BAL_P": f"AB{i}P", "BAL_N": f"AB{i}N", "GND": "GND"})
        sch.place(C, "C", "100n", (130, y - 4), {"1": f"AB{i}P", "2": f"ADC{i}_P"})
        sch.place(C, "C", "100n", (155, y + 4), {"1": f"AB{i}N", "2": f"ADC{i}_N"})

    # ---- RF-DAC outputs ---------------------------------------------------------------------
    rf_dac_chain(sch, lib, C, R, 450, 60, 0, "GNSS_RF", "RF-DAC0 -> clean GNSS RF -> ZED-X20P")
    rf_dac_chain(sch, lib, C, R, 450, 110, 2, "AJ_OUT", "RF-DAC2 -> AJ RF OUT (external receiver)")
    sch.place(SMA, "J", "AJ RF OUT (SMA)", (600, 110), {"1": "AJ_OUT", "2": "GND"})
    sch.text("RF-DAC1 -> CAL OUT (to front-end J_CAL)", (440, 146), 2)
    sch.place(C, "C", "100n", (444, 160), {"1": "DAC1_P", "2": "D1P"})
    sch.place(C, "C", "100n", (456, 160), {"1": "DAC1_N", "2": "D1N"})
    sch.place(lib("BALUN"), "T", "TCM1-63AX+", (485, 160), {"SE": "CAL_OUT", "BAL_P": "D1P", "BAL_N": "D1N", "GND": "GND"})
    sch.place(SMA, "J", "CAL OUT (SMA)", (530, 160), {"1": "CAL_OUT", "2": "GND"})

    # ---- u-blox ZED-X20P ------------------------------------------------------------------
    zx, zy = 470, 300
    sch.text("u-blox ZED-X20P all-band GNSS (KiCad ZED-F9P symbol/footprint, pin-compatible: VERIFY)", (zx - 60, zy - 85), 2.2)
    sch.place(C, "C", "47p DC block", (zx - 70, zy - 40), {"1": "GNSS_RF", "2": "ZED_RF"})
    zed_nets = {
        "RF_IN": "ZED_RF", "VCC": "+3V3", "V_BCKP": "+3V3", "V_USB": "VBUS",
        "USB_DM": "USB_DM", "USB_DP": "USB_DP",
        "TXD/SPI_MISO": "GNSS_TXD", "RXD/SPI_MOSI": "GNSS_RXD",
        "TXD2": "GNSS_TXD2", "RXD2": "GNSS_RXD2", "SDA/~{SPI_CS}": "GNSS_SDA", "SCL/SPI_CLK": "GNSS_SCL",
        "TIMEPULSE": "PPS", "EXTINT": "GNSS_EXTINT", "~{RESET}": "GNSS_RESET_N",
        "~{SAFEBOOT}": "GNSS_SAFEBOOT_N", "GND": "GND",
    }
    sch.place(ZED, "U", "ZED-X20P", (zx, zy), zed_nets, ref="U2",
              fields={"Footprint": "RF_GPS:ublox_ZED"})
    sch.place(C, "C", "100n", (zx + 55, zy - 50), {"1": "+3V3", "2": "GND"})
    sch.place(C, "C", "10u", (zx + 70, zy - 50), {"1": "+3V3", "2": "GND"})
    sch.place(TP, "TP", "SAFEBOOT_N", (zx + 60, zy + 60), {"1": "GNSS_SAFEBOOT_N"})
    sch.place(H6, "J", "UART2/I2C (RTCM, config)", (zx + 100, zy),
              {"1": "+3V3", "2": "GNSS_TXD2", "3": "GNSS_RXD2", "4": "GNSS_SDA", "5": "GNSS_SCL", "6": "GND"})
    sch.place(R, "R", "2.2k", (zx + 100, zy - 40), {"1": "+3V3", "2": "GNSS_SDA"})
    sch.place(R, "R", "2.2k", (zx + 115, zy - 40), {"1": "+3V3", "2": "GNSS_SCL"})
    sch.place(SMA, "J", "PPS OUT (SMA)", (zx + 100, zy + 45), {"1": "PPS", "2": "GND"})

    usb_nets = {"VBUS": "VBUS", "D+": "USB_DP", "D-": "USB_DM", "CC1": "CC1", "CC2": "CC2",
                "GND": "GND", "SHIELD": "GND", "SBU1": "NC", "SBU2": "NC"}
    sch.place(USB, "J", "USB-C (u-blox config, u-center)", (zx - 120, zy + 40), usb_nets)
    sch.place(R, "R", "5.1k", (zx - 80, zy + 75), {"1": "CC1", "2": "GND"})
    sch.place(R, "R", "5.1k", (zx - 65, zy + 75), {"1": "CC2", "2": "GND"})

    # ---- 10 MHz reference -----------------------------------------------------------------
    sch.text("10 MHz reference (common to all RF-ADC/DAC tiles through the SOM clocking)", (40, 360), 2.2)
    sch.place(lib("OCXO"), "Y", "OCXO 10 MHz", (60, 380), {"VCC": "+3V3", "OUT": "REF_OCXO", "GND": "GND"})
    sch.place(lib("CLKBUF2"), "U", "LMK1C1102", (110, 380),
              {"IN": "REF_OCXO", "VCC": "+3V3", "OUT1": "REF_SOM", "OUT2": "REF_OUT", "GND": "GND"})
    sch.place(SMA, "J", "10 MHz REF OUT (SMA)", (160, 380), {"1": "REF_OUT", "2": "GND"})
    sch.place(C, "C", "100n", (60, 405), {"1": "+3V3", "2": "GND"})

    # ---- power ----------------------------------------------------------------------------
    sch.text("Power: 12 V in -> SOM; buck 12->5 V (front-end + LDO); LDO 3.3 V (GNSS, clock)", (40, 430), 2.2)
    sch.place(JACK, "J", "12V DC in", (50, 455), {"1": "+12V", "2": "GND"})
    sch.place(C, "C", "100u", (80, 465), {"1": "+12V", "2": "GND"})
    sch.place(lib("DCDC"), "U", "TPS54560 12V->5V", (115, 455), {"VIN": "+12V", "EN": "+12V", "VOUT": "+5V", "GND": "GND"})
    sch.place(C, "C", "47u", (150, 465), {"1": "+5V", "2": "GND"})
    sch.place(lib("LDO"), "U", "LT3045 3.3V", (185, 455), {"VIN": "+5V", "EN": "+5V", "VOUT": "+3V3", "GND": "GND"})
    sch.place(C, "C", "10u", (220, 465), {"1": "+3V3", "2": "GND"})
    sch.place(H2, "J", "+5V to front-end", (250, 455), {"1": "+5V", "2": "GND"})
    sch.power_flags((40, 490), extra_nets=["VBUS"])

    path = sch.save(HERE / "dsp_gnss.kicad_sch", [v[1] for v in sym.values()], "crpa")
    print("wrote", path)


if __name__ == "__main__":
    main()
