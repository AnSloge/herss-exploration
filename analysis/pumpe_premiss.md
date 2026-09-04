# Pumpepremiss-sjekk: skaper pumping et hardt optimeringsproblem?

**Kjørt:** 2026-08-19T13:46:23+02:00  
**Primærdata:** `data/utahps_daily/pricefile_utahps.txt` og `data/utahps_hourly/pricefile_utahps.txt`, NO2, 1. september 2022–31. august 2023.  
**Metode/kode:** `analysis/pumpe_premiss.py`.

Alle beregnede tall nedenfor er **[målt]**. Tersklene 1,20, 1,33 og 1,50 følger rundtursvirkningsgrader 0,83, 0,75 og 0,67 **[antakelse]**.

## Datavalidering

- **[målt]** Døgnserien har 365 observasjoner, timeserien har 8 760 observasjoner, og begge dekker samme år.
- **[målt]** Døgnprisene samsvarer med timeseriens døgnsnitt; største absolutte differanse er 0.005 EUR/MWh.
- **[målt]** Alle primærpriser er strengt positive. Ratioene er derfor veldefinerte.
- **[målt]** HJELLE-tilsiget er valgt etter den eksplisitt validerte headeren `0` i `inflowseries_utahps.txt`, ikke etter kolonneposisjon.

## 1. Prisstrukturanalyse

### 1.1 Grunnleggende statistikk

| Oppløsning | n | Min | Maks | Median | Snitt | Std.avvik (n−1) | <20 | >200 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Døgn | 365 | 0.04 | 564.88 | 108.75 | 137.88 | 98.90 | 7 | 58 |
| Time | 8760 | 0.01 | 702.83 | 108.62 | 137.88 | 104.64 | 413 | 1411 |

Figur: [prisfordeling (SVG)](pumpe_premiss/prisfordeling.svg).

### 1.2 Ratioer mellom fremoverpar

For hvert vindu er alle ordnede par `(t, t+k)` med `1 ≤ k ≤ vindu` brukt. «Alle fremoverpar» beholder også prisfall og måler hvor ofte en vilkårlig tidsflytting er lønnsom. «Kun stigende par» betinger på at sluttprisen er høyere enn startprisen og måler størrelsen på de faktiske oppgangene.

| Vindu | Populasjon | Antall par | >1,20 | >1,33 | >1,50 | Median ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 6t | Alle fremoverpar | 52,539 | 16.3 % | 11.0 % | 7.5 % | 0.996 |
| 6t | Kun stigende par | 24,548 | 34.8 % | 23.6 % | 16.1 % | 1.111 |
| 12t | Alle fremoverpar | 105,042 | 19.8 % | 13.8 % | 9.7 % | 0.998 |
| 12t | Kun stigende par | 50,530 | 41.1 % | 28.7 % | 20.2 % | 1.142 |
| 24t | Alle fremoverpar | 209,940 | 21.6 % | 15.2 % | 10.8 % | 1.000 |
| 24t | Kun stigende par | 103,746 | 43.8 % | 30.8 % | 21.9 % | 1.159 |
| 48t | Alle fremoverpar | 419,304 | 23.9 % | 17.2 % | 12.5 % | 1.000 |
| 48t | Kun stigende par | 208,537 | 48.1 % | 34.6 % | 25.2 % | 1.187 |
| 7d | Alle fremoverpar | 2,527 | 23.9 % | 16.1 % | 10.7 % | 0.981 |
| 7d | Kun stigende par | 1,184 | 50.9 % | 34.3 % | 22.9 % | 1.206 |

Figur: [ratiofordelinger (SVG)](pumpe_premiss/ratiofordelinger.svg).

### 1.3 Sesongmønster

- **[målt]** Dag/natt-ratioen (gjennomsnitt 08–19 delt på gjennomsnitt 00–05) er **1.21**.
- **[målt]** Sommer/vinter-ratioen (jun–aug delt på des–feb) er **0.46**.
- **[vurdering]** En ratio klart over én indikerer høyere pris i førstnevnte periode, men er ikke i seg selv en operativ pumpepolicy.

Figur: [måneds- og timeprofil (SVG)](pumpe_premiss/sesongmonster.svg).

## 2. Pumpehorisont og magasinstørrelse

Aktiv lagring er 9,0 Mm³ for HJELLE og 61,4 Mm³ for GRESSE. Tabellen bruker `ΔV = Q_pump × Δt`; «ja» betyr at pumpevolumet alene er mindre enn eller lik aktiv lagring.

| Q_pump [m³/s] | Horisont | Krav [Mm³] | HJELLE | GRESSE |
| --- | --- | --- | --- | --- |
| 1 | 6t | 0.0216 | ja | ja |
| 1 | 12t | 0.0432 | ja | ja |
| 1 | 24t | 0.0864 | ja | ja |
| 1 | 7d | 0.6048 | ja | ja |
| 2 | 6t | 0.0432 | ja | ja |
| 2 | 12t | 0.0864 | ja | ja |
| 2 | 24t | 0.1728 | ja | ja |
| 2 | 7d | 1.2096 | ja | ja |
| 5 | 6t | 0.1080 | ja | ja |
| 5 | 12t | 0.2160 | ja | ja |
| 5 | 24t | 0.4320 | ja | ja |
| 5 | 7d | 3.0240 | ja | ja |

**[vurdering]** Dette er en nødvendig volumtest, ikke en full hydraulisk feasibility-test: den forutsetter ledig aktiv lagring, tilgjengelig nedre magasin og tilstrekkelig turbin-/pumpekapasitet.

## 3. Er pumpebeslutningen triviell?

Klassifiseringen under bruker `maks(fremtidig pris innen vinduet) / nåpris` **[antakelse: perfekt framsyn innen vinduet]**. For hvert gyldige starttidspunkt er ratio `<1,20` «pump aldri lønnsomt», `>1,33` «pump alltid lønnsomt» og ellers «betinget lønnsomt».

| Vindu | Starttidspunkter | Aldri | Betinget | Alltid | Median maksratio | Tolkning |
| --- | --- | --- | --- | --- | --- | --- |
| 6t | 8759 | 70.1 % | 9.0 % | 20.9 % | 1.059 | sannsynligvis triviell (<20 % betinget) |
| 12t | 8759 | 57.8 % | 12.3 % | 29.9 % | 1.140 | sannsynligvis triviell (<20 % betinget) |
| 24t | 8759 | 47.2 % | 13.8 % | 39.0 % | 1.225 | sannsynligvis triviell (<20 % betinget) |
| 48t | 8759 | 38.3 % | 13.2 % | 48.5 % | 1.312 | sannsynligvis triviell (<20 % betinget) |
| 7d | 364 | 54.4 % | 15.7 % | 29.9 % | 1.170 | sannsynligvis triviell (<20 % betinget) |

**[antakelse: perfekt framsyn innen vinduet]** Dette er en optimistisk øvre grense: en reell pumpebeslutning kan ikke observere fremtidige priser, og den faktiske andelen «alltid lønnsomt» vil være lavere.

## 4. Pris og tilsig

- **[målt]** Pearsons korrelasjon mellom daglig NO2-pris og HJELLEs lokale tilsig (node 0) er **-0.225** (`n=365`).
- **[vurdering]** Negativ korrelasjon gir konflikt mellom høy tilrenning og lav pris.

## 5. Sekundær sammenligning: Forbrukerrådet

- **[målt]** `spotpriser.xlsx` inneholder NO2 per time fra 01.09.2023 til 31.08.2024, totalt 8,784 timer; 2023/24 inneholder 29. februar.
- **[antakelse]** Råverdiene er behandlet som kr/kWh og multiplisert med 100 til EUR/MWh ved 10 NOK/EUR. [Forbrukerrådet](https://www.forbrukerradet.no/strompris/spotpriser) oppgir den historiske Excel-serien i kr/kWh og inkludert mva for NO2.
- **[målt]** Sekundær NO2 etter konvertering: min -70.73, median 78.20, snitt 80.03, maks 379.48 EUR/MWh.

Serien er et annet år og brukes bare som sammenligning; ingen av primærtallene over er blandet med den.

## 6. Konklusjon

1. **Er prisspreaden stor nok til ikke-triviell pumping?** **[vurdering]** **Nei**, ikke etter det forhåndsdefinerte 20 %-kriteriet: den høyeste betingede andelen er 15.7 % i 7d, altså **sannsynligvis triviell (<20 % betinget)**. Prisspreaden må likevel ikke vurderes med maksimumratio alene; ratio-tabellen viser også hvor ofte muligheten oppstår.
2. **Hvilken horisont passer magasinene?** **[vurdering]** **Ukehorisonten (7d) er den beste av de testede horisontene**, fordi den har høyest betinget andel. Alle angitte kombinasjoner opptil 7 døgn får fysisk plass i begge magasiner i denne rene volumtesten. Dag/natt-ratioen er 1.21, mens sommer/vinter-ratioen er 0.46; sesongpumping er ikke dimensjonert i denne 7-døgnstesten og kan derfor ikke anbefales på dette grunnlaget.
3. **Ekte optimeringsproblem eller triviell beslutning?** **[vurdering]** **Sannsynligvis triviell i den prisbaserte screeningen**: selv horisonten med mest betinget struktur, 7d, har bare 15.7 %. Pumping med eksisterende magasiner og disse prisene har dermed ikke vist et hardt optimeringsproblem. Magasinnivå, tilsig og hydrauliske grenser kan testes separat dersom man vil utfordre denne konservative konklusjonen.
4. **Minimal størrelse og kapasitet innen den testede ruten.** **[vurdering]** Ingen av de testede horisontene havnet i 20–60 %-båndet; testen kan derfor ikke identifisere en minimal ikke-triviell kombinasjon innen det angitte rutenettet.

Deterministiske historiske priser med perfekt framsyn er en gunstig analysebetingelse. Prisprognosefeil vil gjøre den reelle pumpebeslutningen vanskeligere enn denne screeningen viser.
