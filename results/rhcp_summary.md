# RHCP jammer study

Jammer: RHCP, 8 MHz wideband, at elevation 10 deg, azimuth 0 deg.

## 1. What one element receives (RHCP waves; gain relative to an RHCP patch at zenith)

| Element | RHCP jammer (el 10) | satellite at zenith | satellite at el 45 | jammer minus zenith sat |
|---|---|---|---|---|
| RHCP, facing zenith | -7.8 dB | 0.0 dB | -1.9 dB | -7.8 dB |
| LHCP, facing zenith | -16.3 dB | -25.0 dB | -29.8 dB | +8.7 dB |
| LHCP, facing the jammer | -25.0 dB | -16.3 dB | -20.3 dB | -8.7 dB |
| RHCP, facing the jammer | 0.0 dB | -7.8 dB | -15.8 dB | +7.8 dB |
| Linear H patch, facing zenith | -8.0 dB | -3.4 dB | -4.8 dB | -4.6 dB |
| Vertical monopole | -3.5 dB | -180.0 dB | -6.4 dB | +176.5 dB |

## 2. Jammer power sweep - satellites tracked (worst output J/N in brackets)

| Array | Processing | 40 dB | 50 dB | 60 dB | 70 dB | 80 dB | 90 dB |
|---|---|---|---|---|---|---|---|
| A: 12x RHCP (space only) | PI | 9 sats (-21) | 9 sats (-11) | 8 sats (-3) | 9 sats (+1) | 9 sats (-1) | 9 sats (-7) |
| A: 12x RHCP (space only) | MVDR | 9 sats (-19) | 9 sats (-10) | 9 sats (-2) | 9 sats (+3) | 9 sats (+5) | 9 sats (+7) |
| B: 3R+3L+3H+3V (your design) | PI | 9 sats (-20) | 9 sats (-11) | 9 sats (-2) | 8 sats (+2) | 9 sats (+1) | 9 sats (-2) |
| B: 3R+3L+3H+3V (your design) | MVDR | 9 sats (-17) | 9 sats (-8) | 9 sats (-1) | 9 sats (+3) | 9 sats (+4) | 8 sats (+8) |
| B1: your proposal (LHCP face jammer) | PI | 9 sats (-21) | 9 sats (-11) | 9 sats (-2) | 7 sats (+3) | 8 sats (+4) | 6 sats (+2) |
| B1: your proposal (LHCP face jammer) | MVDR | 9 sats (-17) | 9 sats (-8) | 9 sats (-1) | 9 sats (+3) | 9 sats (+6) | 6 sats (+6) |
| B2: RHCP ref. antennas face jammer | PI | 9 sats (-20) | 9 sats (-11) | 9 sats (-3) | 9 sats (+1) | 9 sats (-2) | 9 sats (-6) |
| B2: RHCP ref. antennas face jammer | MVDR | 9 sats (-15) | 9 sats (-6) | 9 sats (-1) | 9 sats (+4) | 9 sats (+6) | 9 sats (+6) |
| C: 6x dual-pol R+L (space + pol) | PI | 8 sats (-19) | 8 sats (-10) | 8 sats (-1) | 6 sats (+2) | 4 sats (+4) | 3 sats (+5) |
| C: 6x dual-pol R+L (space + pol) | MVDR | 9 sats (-19) | 9 sats (-9) | 9 sats (-2) | 9 sats (+3) | 9 sats (+5) | 8 sats (+4) |

## 3. Two RHCP jammers (65 dB at az 0, 60 dB at az 150)

| Array | Processing | Worst output J/N [dB] | Satellites tracked | C/N0 per satellite [dB-Hz] |
|---|---|---|---|---|
| A: 12x RHCP (space only) | PI | 2.2 | 8 / 9 | 44, 36, 37, 27, 34, 32, 39, 33, 41 |
| A: 12x RHCP (space only) | MVDR | 3.0 | 9 / 9 | 51, 47, 48, 41, 47, 44, 45, 42, 50 |
| B: 3R+3L+3H+3V (your design) | PI | 1.9 | 8 / 9 | 44, 33, 33, 23, 34, 36, 34, 35, 40 |
| B: 3R+3L+3H+3V (your design) | MVDR | 2.7 | 9 / 9 | 47, 44, 44, 39, 42, 43, 41, 42, 47 |
| B1: your proposal (LHCP face jammer) | PI | 2.4 | 8 / 9 | 44, 34, 32, 23, 34, 35, 34, 34, 41 |
| B1: your proposal (LHCP face jammer) | MVDR | 3.2 | 9 / 9 | 47, 43, 45, 38, 43, 42, 40, 41, 47 |
| B2: RHCP ref. antennas face jammer | PI | 2.5 | 8 / 9 | 42, 34, 35, 27, 36, 35, 35, 34, 40 |
| B2: RHCP ref. antennas face jammer | MVDR | 3.3 | 9 / 9 | 48, 44, 45, 42, 44, 42, 42, 42, 47 |
| C: 6x dual-pol R+L (space + pol) | PI | 2.4 | 7 / 9 | 42, 37, 40, 26, 37, 27, 35, 28, 34 |
| C: 6x dual-pol R+L (space + pol) | MVDR | 2.7 | 9 / 9 | 47, 44, 46, 38, 43, 40, 42, 39, 43 |