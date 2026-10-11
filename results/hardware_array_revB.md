# Hardware array check

Satellites tracked (of 9, C/N0 >= 28 dB-Hz) with equalized channels, 5 taps.

| Scenario | B: 3R+3L+3H+3V (your design) PI / MVDR | Rev B hardware, tilted = LHCP PI / MVDR | Rev B hardware, tilted = RHCP (jumpers swapped) PI / MVDR |
|---|---|---|---|
| 6 mixed jammers (experiment 2) | 3 / 9 | 5 / 9 | 6 / 8 |
| RHCP jammer 60 dB, el 10 az 0 | 9 / 9 | 9 / 9 | 8 / 9 |
| RHCP jammer 80 dB, el 10 az 0 | 9 / 9 | 5 / 9 | 9 / 9 |
| RHCP jammer 90 dB, el 10 az 0 | 9 / 8 | 2 / 5 | 9 / 9 |
| 2 RHCP jammers (65 dB az 0, 60 dB az 150) | 8 / 9 | 9 / 9 | 8 / 9 |