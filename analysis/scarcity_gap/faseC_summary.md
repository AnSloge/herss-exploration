# Fase C — løpende sammendrag

Generert 2026-08-19T13:59:56+00:00 av `faseC_summary.py`. Skrives om etter hver ferdige celle; et delvis resultat er ment å være lesbart.

**Celler:** 11 Fase C, 9 fra 2026-08-04, 5 uTAHPS-utsnitt.

## Brocelle — er sammenslåing tillatt?

syn_rho1_R4 pa 16001 punkt (90 celler/fullaststeg) (gammelcellen er merket 8001 punkt, men DP-verdien kommer fra den doblede 16001-punktskjoringen -- run_measurement.py tar max av de to) ga 0.0090 %; pa 27453 punkt (155 celler/fullaststeg) 0.0074 %. Forskyvning -0.0016 prosentpoeng mot toleranse 0.010. Sammenslaing tillatt: opplosningen flytter ikke gapet nok til a endre formen pa kurven.

### Syntetisk rutenett, sammenslått (brocellen bekreftet)

| instans | rho | R | B2 gap % | B4 gap % | overløp Mm³ | steg m/ovl | celler/fullaststeg | n_grid | konv. |
|---|---|---|---|---|---|---|---|---|---|
| `syn_rho0p5_R0p5` | 0.500 | 0.0357 | 7.449 | 3.460 | 1.76 | 15 | 389 | 8001 | +0.00309 % |
| `syn_rho1_R0p5` | 1.000 | 0.0357 | 7.384 | 1.647 | 34.54 | 94 | 312 | 8001 | +0.00214 % |
| `syn_rho0p5_R1` | 0.500 | 0.0713 | 6.877 | 1.560 | 0.05 | 5 | 197 | 8001 | +0.00278 % |
| `syn_rho0p75_R1` | 0.750 | 0.0713 | 5.014 | 1.464 | 4.32 | 28 | 172 | 8001 | +0.00301 % |
| `syn_rho1_R1` | 1.000 | 0.0713 | 4.439 | 1.795 | 22.33 | 61 | 153 | 8001 | +0.00282 % |
| `syn_rho1p25_R1` | 1.250 | 0.0713 | 3.821 | 0.575 | 44.78 | 92 | 139 | 8001 | +0.00116 % |
| `syn_rho1p75_R1` | 1.750 | 0.0713 | 1.941 | 0.055 | 95.77 | 159 | 155 | 10641 | ikke kjørt |
| `syn_rho0p782_R1p25` | 0.782 | 0.0892 | 4.118 | 0.601 | 3.02 | 28 | 155 | 8979 | ikke kjørt |
| `syn_rho1_R1p25` | 1.000 | 0.0892 | 4.086 | 1.106 | 17.84 | 60 | 155 | 9891 | ikke kjørt |
| `syn_rho1_R1p5` | 1.000 | 0.1070 | 3.428 | 0.845 | 13.42 | 58 | 155 | 11637 | +0.00152 % |
| `syn_rho0p782_R2` | 0.782 | 0.1427 | 1.775 | 0.063 | 0.20 | 13 | 155 | 13787 | ikke kjørt |
| `syn_rho1_R2` | 1.000 | 0.1427 | 2.085 | 0.161 | 5.87 | 47 | 82 | 8001 | +0.00114 % |
| `syn_rho0p782_R4` | 0.782 | 0.2854 | 1.169 | 0.014 | 0.00 | 0 | 155 | 25033 | +0.00250 % |
| `syn_rho1_R4` | 1.000 | 0.2854 | 0.524 | 0.009 | 0.18 | 14 | 45 | 8001 | +0.00158 % |
| `syn_rho1_R4 (bro)` | 1.000 | 0.2854 | 0.523 | 0.007 | 0.18 | 14 | 155 | 27453 | ikke kjørt |
| `syn_rho1p221_R4` | 1.221 | 0.2854 | 1.281 | 0.003 | 8.73 | 66 | 155 | 29875 | ikke kjørt |
| `syn_rho1p25_R4` | 1.250 | 0.2854 | 1.319 | 0.003 | 11.16 | 76 | 41 | 8001 | +0.00065 % |
| `syn_rho0p782_R8` | 0.782 | 0.5708 | 0.737 | 0.008 | 0.00 | 0 | 155 | 43305 | ikke kjørt |
| `syn_rho1_R8` | 1.000 | 0.5708 | 0.646 | 0.010 | 0.00 | 0 | 155 | 47001 | +0.00229 % |
| `syn_rho1p733_R8` | 1.733 | 0.5708 | 0.266 | 0.001 | 25.52 | 182 | 155 | 59175 | ikke kjørt |


### uTAHPS-utsnitt (ekte, ikke syntetiske — aldri i samme konklusjon som cellene over)

| instans | rho | R | B2 gap % | B4 gap % | overløp Mm³ | steg m/ovl | celler/fullaststeg | n_grid | konv. |
|---|---|---|---|---|---|---|---|---|---|
| `hjelle_daily` | 0.782 | 0.0713 | 5.121 | 1.075 | 6.12 | 33 | 169 | 8001 | +0.00193 % |
| `hjelle_daily_e163` | 0.782 | 0.0713 | 7.001 | 1.077 | 6.13 | 35 | 169 | 8001 | +0.00188 % |
| `gresse_daily` | 0.563 | 0.3247 | 0.407 | 0.000 | 0.00 | 0 | 170 | 26001 | +0.00000 % |
| `kroknesvatn_daily` | 0.947 | 0.6448 | 1.271 | 0.002 | 0.00 | 0 | 25 | 8001 | +0.00032 % |
| `toppsy_daily` | 1.017 | 0.6806 | 1.611 | 0.001 | 0.00 | 0 | 25 | 8001 | +0.00035 % |


### Budsjett

| instans | veggklokke s | fulle horisontevalueringer | DP-stegceller |
|---|---|---|---|
| `syn_rho0p5_R0p5` | 2128 | 25,935,518 | 587,723,730 |
| `syn_rho1_R0p5` | 1877 | 15,611,634 | 587,723,730 |
| `syn_rho0p5_R1` | 3434 | 70,949,362 | 587,723,730 |
| `syn_rho0p75_R1` | 2112 | 18,679,950 | 587,723,730 |
| `syn_rho1_R1` | 2109 | 18,547,352 | 587,723,730 |
| `syn_rho1p25_R1` | 2026 | 21,248,838 | 587,723,730 |
| `syn_rho1_R2` | 2066 | 27,463,148 | 587,723,730 |
| `syn_rho1_R4` | 2595 | 45,948,206 | 587,723,730 |
| `syn_rho1p25_R4` | 1725 | 25,392,430 | 587,723,730 |
| `syn_rho1p75_R1` | 30623 | 22,250,868 | 781,407,330 |
| `syn_rho0p782_R1p25` | 30565 | 21,247,820 | 659,474,700 |
| `syn_rho1_R1p25` | 1297 | 18,639,344 | 726,383,580 |
| `syn_rho1_R1p5` | 2443 | 18,991,980 | 854,478,870 |
| `syn_rho0p782_R2` | 35288 | 38,677,366 | 1,012,213,620 |
| `syn_rho0p782_R4` | 3386 | 36,152,018 | 1,837,276,410 |
| `syn_rho1_R4 (bro)` | 1913 | 45,948,206 | 2,014,819,710 |
| `syn_rho1p221_R4` | 2004 | 28,511,054 | 2,192,509,740 |
| `syn_rho0p782_R8` | 2159 | 36,661,148 | 3,177,801,690 |
| `syn_rho1_R8` | 8297 | 39,433,724 | 3,448,958,730 |
| `syn_rho1p733_R8` | 1765 | 13,290,274 | 4,342,104,240 |
| `hjelle_daily` | 2505 | 34,338,650 | 587,723,730 |
| `hjelle_daily_e163` | 1835 | 33,692,610 | 587,723,730 |
| `gresse_daily` | 3087 | 22,822,404 | 1,908,293,730 |
| `kroknesvatn_daily` | 2194 | 30,986,872 | 587,723,730 |
| `toppsy_daily` | 2026 | 23,771,730 | 587,723,730 |

> Kun veggklokketid er sammenlignbar på tvers av metodene. En «full horisontevaluering» i B2/B4 og en DP-stegcelle er ikke samme arbeidsmengde: DP-stegcellen er én tilstand-handling-transisjon, vektorisert, mens en B2/B4-evaluering er en hel T-stegs framoverkjøring. Kolonnene står ved siden av hverandre for å vise hva som faktisk ble brukt, ikke for å settes mot hverandre.


> Konvergenssjekk ikke kjørt på: `syn_rho0p782_R1p25`, `syn_rho0p782_R2`, `syn_rho0p782_R8`, `syn_rho1_R1p25`, `syn_rho1_R4 (bro)`, `syn_rho1p221_R4`, `syn_rho1p733_R8`, `syn_rho1p75_R1`. Etter planen kjøres den på tre representative celler; gapene for de øvrige hviler på at diskretiseringsfeilen der oppfører seg som på de tre.
