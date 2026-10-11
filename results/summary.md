# CRPA simulation results

## Experiment 1 - jammer tilt sweep (jammer el 10 / az 0, satellite el 12 / az 3)

Power inversion, 5 taps. Values: output J/N [dB] / satellite C/N0 [dB-Hz].

| Tilt [deg] | Fixed H antenna, no DSP | 1 dual-pol patch, adaptive pol only | A: 12x RHCP (space only) | B: 3R+3L+3H+3V (your design) | C: 6x dual-pol R+L (space + pol) |
|---|---|---|---|---|---|
| 0 | 23.9 / 6.9 | -0.5 / 29.5 | -3.2 / 10.1 | -2.4 / 26.1 | -3.5 / 28.5 |
| 0.5 | 24.8 / 6.0 | -0.5 / 29.5 | -3.3 / 11.1 | -2.5 / 25.4 | -3.3 / 28.5 |
| 1 | 25.7 / 5.2 | -0.4 / 29.5 | -3.2 / 11.7 | -2.6 / 25.3 | -3.6 / 29.1 |
| 2 | 27.3 / 3.5 | -0.5 / 29.5 | -3.3 / 12.3 | -2.7 / 25.7 | -3.3 / 28.1 |
| 5 | 31.2 / -0.4 | -0.5 / 29.5 | -3.5 / 12.8 | -2.6 / 25.6 | -3.3 / 28.8 |
| 10 | 35.5 / -4.7 | -0.5 / 29.7 | -3.4 / 10.9 | -2.7 / 26.6 | -3.3 / 28.3 |
| 20 | 40.5 / -9.6 | -0.8 / 30.1 | -3.7 / 9.7 | -3.1 / 26.7 | -3.5 / 29.1 |
| 30 | 43.5 / -12.6 | -1.3 / 30.7 | -4.2 / 8.0 | -3.6 / 27.8 | -3.7 / 29.0 |
| 45 | 46.2 / -15.4 | -2.4 / 32.1 | -5.4 / 11.5 | -5.0 / 29.6 | -4.2 / 29.6 |
| 60 | 47.9 / -17.0 | -3.9 / 33.9 | -6.8 / 15.5 | -6.6 / 33.1 | -4.9 / 31.7 |
| 90 | 48.9 / -18.1 | -6.8 / 36.8 | -8.7 / 19.4 | -8.7 / 34.6 | -7.4 / 34.6 |

## Experiment 2 - 9 satellites, 6 jammers

| Jammer | el / az | Polarization | J/N [dB] |
|---|---|---|---|
| J1 linear wideband | 5 / 30 | (1.00+0.00j, 0.09+0.00j) | 65 |
| J2 linear, next to G06 | 12 / 122 | (0.94+0.00j, 0.34+0.00j) | 60 |
| J3 near-horizontal, next to G08 | 8 / 200 | (0.34+0.00j, 0.94+0.00j) | 60 |
| J4 RHCP smart jammer | 20 / 280 | (0.71+0.00j, -0.00-0.71j) | 55 |
| J5 CW | 3 / 330 | (1.00+0.00j, 0.00+0.00j) | 70 |
| J6 elliptical | 30 / 75 | (0.79+0.15j, 0.55-0.21j) | 55 |

Unprotected single RHCP patch: in-band J/N = 69.2 dB, satellites tracked = 0 / 9

| Array | Processing | Worst output J/N [dB] | Satellites tracked | C/N0 per satellite [dB-Hz] |
|---|---|---|---|---|
| A: 12x RHCP (space only) | PI, 1 taps | 4.8 | 5 / 9 | 43, 41, 31, 29, 25, -3, 27, 8, 34 |
| A: 12x RHCP (space only) | PI, 5 taps | 2.2 | 7 / 9 | 44, 44, 35, 34, 30, 7, 31, 12, 35 |
| A: 12x RHCP (space only) | MVDR, 5 taps | 8.9 | 7 / 9 | 50, 49, 43, 44, 37, 20, 39, 14, 45 |
| A: 12x RHCP (space only) | MVDR, 5 taps, **no channel equalization** | 12.1 | 7 / 9 | 47, 43, 31, 37, 35, 21, 35, 12, 42 |
| B: 3R+3L+3H+3V (your design) | PI, 1 taps | 5.3 | 6 / 9 | 39, 25, 32, 33, 29, 29, 25, 29, 28 |
| B: 3R+3L+3H+3V (your design) | PI, 5 taps | 4.3 | 6 / 9 | 40, 35, 28, 33, 28, 28, 27, 26, 36 |
| B: 3R+3L+3H+3V (your design) | MVDR, 5 taps | 7.3 | 9 / 9 | 44, 40, 38, 41, 37, 32, 36, 35, 43 |
| B: 3R+3L+3H+3V (your design) | MVDR, 5 taps, **no channel equalization** | 4.1 | 9 / 9 | 42, 42, 41, 41, 36, 29, 34, 34, 42 |
| C: 6x dual-pol R+L (space + pol) | PI, 1 taps | 4.4 | 7 / 9 | 39, 36, 20, 35, 32, 29, 23, 30, 33 |
| C: 6x dual-pol R+L (space + pol) | PI, 5 taps | 4.1 | 6 / 9 | 42, 40, 18, 35, 31, 28, 19, 29, 35 |
| C: 6x dual-pol R+L (space + pol) | MVDR, 5 taps | 9.1 | 9 / 9 | 45, 44, 32, 41, 37, 34, 29, 36, 40 |
| C: 6x dual-pol R+L (space + pol) | MVDR, 5 taps, **no channel equalization** | 5.5 | 8 / 9 | 45, 45, 32, 42, 32, 17, 29, 29, 37 |

## Experiment 3 - number of jammers (median satellites tracked of 9, MVDR 5 taps)

Each cell: equalized channels / raw channels.

| Jammers | A: 12x RHCP (space only) | B: 3R+3L+3H+3V (your design) | C: 6x dual-pol R+L (space + pol) |
|---|---|---|---|
| 1 | 9 / 9 | 9 / 9 | 9 / 9 |
| 2 | 9 / 9 | 9 / 9 | 9 / 9 |
| 3 | 9 / 9 | 9 / 9 | 9 / 9 |
| 4 | 9 / 9 | 9 / 9 | 9 / 9 |
| 5 | 8 / 8 | 9 / 9 | 9 / 8 |
| 6 | 8 / 7 | 9 / 7 | 8 / 6 |
| 7 | 7 / 5 | 8 / 0 | 7 / 4 |
| 8 | 6 / 3 | 7 / 0 | 6 / 1 |
| 9 | 5 / 2 | 4 / 0 | 4 / 1 |
| 10 | 3 / 0 | 3 / 0 | 3 / 0 |
| 11 | 3 / 0 | 1 / 0 | 2 / 0 |
| 12 | 1 / 0 | 0 / 0 | 0 / 0 |
| 13 | 1 / 0 | 0 / 0 | 0 / 0 |
| 14 | 0 / 0 | 0 / 0 | 0 / 0 |
