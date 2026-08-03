# Gap-måling i knapphetsregimet: HJELLE og GRESSE

**Dato:** 2026-08-02
**HERSS:** VERSION 3.1.03 / VERSION_DATE 20260611
**Upstream pinnet:** `029a2d5` · **arbeidstre:** `59730f1`
**Instanser:** `analysis/instances/{hjelle_daily, gresse_daily, hjelle_daily_e163}`
**Kode:** `analysis/scarcity_gap/`
**Rådata:** `result_{hjelle, gresse, hjelle_e163}.json`,
`validation_instance.json`, `validation_replica.json`

Alle påstander er merket **[kilde]** (verifisert i C++-kilden), **[målt]** (beregnet i denne
kjøringen), **[vurdering]**, **[antakelse]** eller **[usikkert]**.

---

## Hovedresultat

| | `mini_utahps_daily` (2026-07-30) | **HJELLE** | **GRESSE** |
|---|---|---|---|
| `rho` (knapphet) | 1,82 | **0,782** | **0,563** |
| `R` (lagringsdybde) | 0,87 | **0,071** | **0,325** |
| gap, terskel + nivå (B2) | **0,285 %** | **5,121 %** | **0,407 %** |
| gap, myopisk (B3) | — | 6,305 % | 0,141 % |
| gap, koordinatoppstigning (B4) | — | **1,075 %** | **0,0000 %** |
| overløp under DP-optimum | — | 6,124 Mm³ (33 steg) | **0,000 Mm³** |
| DP-optimum ligner en terskelregel? | ja (degenerert) | **nei** (81,4 % treff) | **ja** (99,7 % treff) |

Tre funn, i rekkefølge etter hvor mye de betyr:

1. **0,285 % var et artefakt av vannoverflod.** Den samme terskelfamilien ligger **5,12 %** fra
   optimum på HJELLE — en faktor 18. Spørsmålet oppgaven stilte er besvart med ja.
2. **Hypotesen om lagringsdybde er motbevist.** GRESSE har 4,6× dypere lagring og et 12× *mindre*
   gap. Den avgjørende egenskapen er ikke lagringsdybde, men om **overløpsbegrensningen binder**
   (§9).
3. **Ingen myk begrensning er aktiv på noen av instansene.** LRW-straffen er strukturelt
   uoppnåelig i et ett-magasin-utsnitt, og start/stopp-kosten er under 0,003 % av verdien (§8).

Etter kriteriene fastsatt før tallene var kjent er gapet mot **beste** baselinje **1,075 %** på
HJELLE (uavklart 1–3 %-båndet) og **0,0000 %** på GRESSE (under 1 %).

---

## 1. Hvorfor målingen ble gjort på nytt

Gating-målingen 2026-07-30 på `mini_utahps_daily` ga et gap på **0,285 %** mellom eksakt DP og
tunet terskelpolitikk — under CLAUDE.md §10.6 sin 1 %-grense. Diagnosen var at instansen lå i et
*overflodsregime*:

```
rho = (initialt aktivt volum + tilsig) / (Q_max · dt · T) = 1,82
```

Med `rho > 1` finnes det ikke noe allokeringsvalg — eneste fornuftige politikk er å kjøre for
fullt, og optimal terskelpolitikk ble degenerert (`K=29, L=0,99` ≈ «kjør alltid»). 0,285 % var
derfor en egenskap ved instansens vannbalanse, ikke ved vannkraftplanlegging. **[vurdering]**

Denne rapporten gjentar målingen i **knapphetsregimet** (`rho < 1`) på to ett-magasin-utsnitt av
`utahps_daily`.

Skillet mellom de to screeningtallene:

- `rho` = totalt tilgjengelig vann / turbinkapasitet over horisonten. Sier om det i det hele tatt
  finnes et allokeringsvalg.
- `R` = aktivt magasinvolum / turbinkapasitet over horisonten. Sier hvor langt framover valget
  rekker — lagringsdybde.

`R` alene skiller ikke mellom å binde i *overflodsretningen* (du får ikke plass til vannet) og i
*knapphetsretningen* (du må velge hvor du bruker begrenset vann). Planleggingsvanskelighet kommer
fra knapphet, så `rho` er screeningtallet og `R` sier hvor dyp koblingen er. **[vurdering]**

---

## 2. Instansene

### 2.1 Konstruksjon

Begge utsnitt er tatt **verbatim** fra `data/utahps_daily/topology_utahps.txt`. Ingen fysisk
parameter er endret: magasinkurve, overløpskurve, turbinkurve, `HEADLOSSCOEF`,
`GENERATOR_MAX_DISCHARGE`, `POWSTAT_MASL`, `POWSTAT_STARTSTOP`, `RES_PENALTY` og
`LOCAL_ENERGY_EQUIVALENT` er kopiert bit for bit. Byggeskriptet er
`analysis/scarcity_gap/build_instances.py`.

| | HJELLE-utsnitt | GRESSE-utsnitt |
|---|---|---|
| Magasin | node 0 HJELLE | node 3 GRESSE → **0** |
| Kraftstasjon | node 1 SVOLETJONN | node 7 SVEIGSHYL_II → **1** |
| Kanal (systemutløp) | node 2 VANAROSEN | node 8 DALSANA → **2** |
| `OUTLET_TUNNEL` | 1 | 7 → **1** |
| `DOWNLINK_IDNR` | 2 | 8 → **2** |
| `OVERFLOW_CURVE`-mål | 2 | 4 (GRONANI) → **2** |

Kun tre strukturelle endringer, hver av dem påtvunget:

1. **Renummerering.** `riversystem.cpp:58,65,71` gjør `nodes[n]->idnr = n` — node-ID-en
   overskrives med nodens **posisjon** i topologifila. ID-en som står i fila er *ikke* nøkkelen.
   Alle `OUTLET_TUNNEL`/`DOWNLINK_IDNR`/`OVERFLOW_CURVE`-referanser og kolonnehodet i tilsigsfila
   må derfor følge posisjonen. `CalcVF` behandler i tillegg `nodes[nr_nodes-1]` som mest nedstrøms
   node, så kanalen må ligge sist. **[kilde]**
2. **Kanalen blir systemutløp** (`-9`), som i `data/mini_utahps_daily`.
3. **GRESSEs overløp omdirigeres** fra kanal 4 (GRONANI, ikke med i utsnittet) til utløpskanalen.
   Verdinøytralt: overløpsvann forlater systemet uansett, gir null inntekt, og teller ikke i
   terminalleddet — `CalcVF` summerer `local_energy_equivalent` kun over PSTATION-noder
   (`riversystem.cpp:429-440`). **[kilde]** + **[vurdering]**

Prisfil kopiert uendret (`RESTPRICE 101`, T=365, døgnoppløsning). Tilsig: kolonne `0` hhv. `3`
fra `inflowseries_utahps.txt`. Startfylling `0.7` / `0.8` fra `start_state_utahps.txt`.

### 2.2 Kanalens startlagring

`0.001 0.002 0.003` i de leverte datasettene er en plassholder som gir en oppfyllingstransient de
første døgnene, og som er ulik mellom instansene fordi VANAROSEN har `K=4 h` og DALSANA `K=6 h`.
Begge instanser er derfor initiert i **stasjonær tilstand** for horisontens middeltilsig.

`cascadedreservoirs.cpp:106` gir den eksakte lineærmagasin-oppdateringen
`S_{t+Δt} = S_t·e^{−Δt/K} + K(1−e^{−Δt/K})·I_t`, med
`k_res = K_TRAVELTIME_HOURS·3600 / N_CASCADE_LINRES` (`:41`). Stasjonærtilstanden under konstant
gjennomstrømning `Q` er `S = k_res · Q` i hvert lineærmagasin. **[kilde]**

| Kanal | K [h] | N | k_res [s] | middel-Q [m³/s] | S per linres [Mm³] | totalt [Mm³] |
|---|---|---|---|---|---|---|
| VANAROSEN (HJELLE) | 4 | 3 | 4800 | 2,9275 | 0,014052 | **0,042156** |
| DALSANA (GRESSE) | 6 | 3 | 7200 | 1,8165 | 0,013079 | **0,039237** |

**[målt]**

### 2.3 Validering av instansene

CLI-kjøring (`src/herss.exe global.txt`) på begge: laster uten feil, ingen `ERROR`- eller
`WARN`-linjer i logfila, `Diagnose()` / `checkNrSteps()` /
`DiagnoseRiversystemConfiguration()` rene. **[målt]**

Global vannbalanse fra `output/riversystem_*_output.txt` (konstant handling 0,5):

| | start vann [Mm³] | herav kanal | tilsig [Mm³] | utløp [Mm³] | slutt vann [Mm³] | herav kanal | **balanse** |
|---|---|---|---|---|---|---|---|
| HJELLE | 7,342156 | 0,042156 | 92,320992 | 95,502268 | 4,160880 | 0,0288 | **0,000000** |
| GRESSE | 155,791237 | 0,039237 | 57,286656 | 94,582437 | 118,495456 | 0,0648 | **−0,000000** |

**[målt]** Kanallagringen er samme størrelsesorden ved start og slutt (0,042 → 0,029 Mm³ og
0,039 → 0,065 Mm³), mot 92,3 hhv. 57,3 Mm³ totalt tilsig — restransienten er under 0,05 % av
vannomsetningen.

### 2.4 Regimetall — rapportert før gapet

| Magasin | aktiv Mm³ | init aktiv Mm³ | eget tilsig Mm³ | turbinkapasitet Mm³ | **R** | **rho** |
|---|---|---|---|---|---|---|
| HJELLE | 9,00 | 6,300 | 92,321 | 126,144 | **0,0713** | **0,7818** |
| GRESSE | 61,44 | 49,152 | 57,287 | 189,216 | **0,3247** | **0,5625** |

**[målt]** — reproduserer oppgavetekstens tall. `rho < 1` for begge, så utsnittene gjorde det de
skulle. Ingen stopp.

**Forbehold som må stå.** GRESSE ligger nedstrøms i den virkelige kaskaden og mottar der også
slipp ovenfra (via VANAROSEN → TOPPSY → GRONANI-grenen). Utsnittet med kun eget tilsig gjør
GRESSE **knappere** enn den er i uTAHPS; reelt `rho` for GRESSE i full kaskade er høyere enn
0,5625. Det er akseptabelt — vi tester en instans, ikke gjenskaper systemet — men det betyr at
resultatet ikke uten videre kan overføres til GRESSE-noden i full uTAHPS. **[vurdering]**

---

## 3. Seks funn i kildekoden som styrer målingen

### 3.1 Node-ID-er overskrives med posisjonsindeks
`riversystem.cpp:58,65,71`. Se §2.1. Konsekvens utover denne oppgaven: en topologifil med
«feil» ID-nummerering blir **stille akseptert** og gir en annen kobling enn forfatteren skrev.
Oppstrøms topologivalidering fanger det ikke. **[kilde]**

### 3.2 LRW-straffen er strukturelt uoppnåelig i et ett-magasin-utsnitt
`reservoir.cpp:509`: `up_res_Mm3 = max(0, res_Mm3 − filling_at_lrw_Mm3)`, og
`powerstation.cpp:785-791` nuller flow når `Q_Mm3 > up_res_Mm3`. Med `OUTLET_HATCH -9999` og
overløp som kun fjerner vann over HRW kan magasinet **aldri** gå under LRW-volumet. **[kilde]**

Den bindende harde nedre grensen er altså aggressive-action-klippet, ikke `RES_PENALTY`.
Dette er bekreftet **[målt]**: i alle 18 valideringssekvenser — inkludert den som er konstruert
for å drive magasinet ned mot LRW og holde det der — er LRW-straffen nøyaktig 0,00 i både
replika og ekte HERSS.

### 3.3 `POWSTAT_MIN_DISCHARGE` er en myk begrensning
`powerstation.cpp:160-165` logger kun en advarsel; produksjonsnullingen er utkommentert
(`:198`, `:232`). Kommentaren i kilden sier det rett ut: «For now we use it as a soft
constrain.» **[kilde]** → replikaen trenger ingen min-discharge-gren.

### 3.4 `SHARED_PENSTOCK` er irrelevant med én generator
`powerstation.cpp:173` (shared) og `:205` (separate) er identiske når `generators.size() == 1`.
**[kilde]** → SVEIGSHYL_II, som mangler `SHARED_PENSTOCK`-linja, bruker samme formel som
SVOLETJONN.

### 3.5 `LOCAL_ENERGY_EQUIVALENT` er inkonsistent hos HJELLE, men ikke hos GRESSE

CLAUDE.md §7 forutsier at terminalleddet og i-horisont-produksjonen bruker inkonsistente
omregninger, fordi `local_energy_equivalent` er en konstant fra topologifila mens produksjonen
er fallhøydeavhengig. Størrelsen på avviket er svært ulik: **[målt]**

| Stasjon | `e` i topologi | fullhøyde-ekvivalent (≈) | forhold | terminal EUR/Mm³ | prisekvivalent EUR/MWh |
|---|---|---|---|---|---|
| SVOLETJONN (HJELLE) | 0,110 | 0,163 | **0,68** | 11 110 | **68,2** |
| SVEIGSHYL_II (GRESSE) | 0,390 | 0,409 | 0,96 | 39 390 | **96,4** |

Vann lagret ved horisontslutt er altså underpriset ~32 % hos HJELLE og ~4 % hos GRESSE.
`RESTPRICE 101` er åpenbart ment å bety «vann er verdt 101 EUR/MWh ved horisontslutt»; det
stemmer for GRESSE (96,4) og ikke for HJELLE (68,2).

To konsekvenser:

1. HJELLE har et systematisk insentiv til å tømme magasinet som ikke er fysisk begrunnet.
2. **Sammenligningen HJELLE-vs-GRESSE er konfundert:** de skiller seg både i lagringsdybde
   (`R` 0,07 vs 0,32) og i vannverdi. Derfor er det kjørt en egen sensitivitetskjøring på HJELLE
   med `e = 0,163` (§7).

Merk at begge prisekvivalenter ligger *inne i* prisfordelingen (median 108,75, snitt 137,88) —
i motsetning til `mini_utahps_daily`. Det er premisset for at det finnes et allokeringsvalg i
det hele tatt. **[vurdering]**

### 3.6 Start/stopp-kostnaden er økonomisk ubetydelig ved døgnoppløsning
`POWSTAT_STARTSTOP 2.0` gir `powstat_startstop/2 = 1,0` EUR per overgang
(`powerstation.cpp:256`), maks 365 EUR over horisonten, mot en verdifunksjon i størrelsesorden
2–7 MEUR. Det er under 0,02 %. **[målt]** Den viktigste kilden til diskret struktur i
formuleringen — commitment-binærvariablene — bærer altså nesten ingen økonomisk vekt her.

---

## 4. Replikaen

### 4.1 Hvorfor den finnes
HERSS eksponerer kun `Simulate()` over hele horisonten. Eksakt DP trenger en enkeltstegs
transisjonsfunksjon. `analysis/scarcity_gap/replica.py` er den funksjonen, med hver formel
sitert mot C++-kilden.

Koden er en **parametrisert** kopi av `analysis/mini_utahps_daily_dp/replica.py`: instansens
konstanter er flyttet inn i `params.InstanceParams`. Originalene er urørt.
`test_regression.py` beviser at ingen formel er endret ved å reprodusere
`mini_utahps_daily`-resultatene innenfor relativ toleranse 1e-6:

```
DP-optimal VF     : 93826.70808000  (ref 93826.70808000, rel 0.000e+00)
tunet terskel VF  : 93559.03201804  (ref 93559.03201804, rel 0.000e+00)
terskel argmax    : K=29, L=0.99    (ref K=29, L=0.99)
```

**[målt]** — eksakt reproduksjon, ikke bare innenfor toleransen.

### 4.2 To rettelser gjort underveis

**(a) LRW-straffen manglet i replikaens verdifunksjon.** Den opprinnelige
`mini_utahps_daily/replica.py` la `res_cost_lrw` utenfor `profit`, mens dens egen `dp.py` la den
inn. `CalcVF` (`riversystem.cpp:466-470`) summerer `S->cost[t]` over **alle** noder, altså også
magasinets egen LRW-straff, så `dp.py` hadde rett. Avviket var latent fordi LRW-grenen aldri
fyrte. Rettet her, slik at et LRW-brudd faktisk ville slå ut i V i stedet for å være gratis.
**[kilde]**

**(b) `ArrayCurve` er ikke `np.interp`.** Dette er den viktigste tekniske rettelsen.
`src/arraycurve.cpp` normaliserer begge akser til [0,1], forhåndsberegner en tabell med
`POINTS_IN_ARRAY = 1000` bøtter som hver peker på ett kurvesegment (`:69-84`), og slår opp med
`idx = int(frac·1000)` (`:183`). Inne i et segment er dette eksakt — men innenfor én bøttebredde
av et bruddpunkt kan bøtta fortsatt peke på *forrige* segment, og oppslaget **ekstrapolerer** da
forrige segments linje forbi bruddpunktet. **[kilde]**

Med `np.interp` i stedet ble restfeilen på HJELLE over 365 steg:

| | med `np.interp` | med portert `ArrayCurve` | forbedring |
|---|---|---|---|
| maks \|ΔVF\| | 0,745 EUR | 0,011 EUR | 68× |
| maks \|ΔPower\| per steg | 4,42e−3 MWh | 1,72e−7 MWh | 26 000× |
| maks \|ΔIncome\| per steg | 5,77e−1 EUR | 6,50e−4 EUR | 890× |

**[målt]** `analysis/scarcity_gap/arraycurve.py` er en eksakt port. Poenget er ikke at 0,745 EUR
av 1,5 MEUR er mye — det er det ikke — men at det var et *systematisk modellavvik*, ikke
flyttallsstøy. Med porten er replikaen eksakt til flyttallspresisjon, og enhver senere
«replika mot HERSS»-differanse kan leses av i stedet for å diskuteres.

### 4.3 Valideringsresultat

Ni sekvenser per instans, hver kjørt gjennom ekte HERSS i isolert subprosess med timeout.
Full tabell i `validation_replica.json`. Sammendrag: **18/18 PASS.**

| Instans | maks \|ΔVF\| [EUR] | VF-nivå [EUR] | maks \|ΔPower\| [MWh] | maks \|ΔIncome\| [EUR] |
|---|---|---|---|---|
| HJELLE | 0,0113 | 0,10–1,79 M | 1,72e−7 | 6,50e−4 |
| GRESSE | 0,0202 | 2,42–7,36 M | 2,61e−8 | 2,83e−3 |

**[målt]** Relativt avvik ≈ 3e−9. Sekvensene dekker: konstant 0,5; alle av; alle på (utløser
aggressive-action); tilfeldig uniform (seed 42); av i 200 steg så maks (utløser overløp);
bang-bang på de 149 dyreste stegene; nesten tom start (`init_fr=0,02`) + alle på; og «tapp mot
LRW og hold».

I tillegg er `_forward_batch` og `_forward_batch_levels` (de vektoriserte kandidatsveipene B4
bruker) verifisert mot den skalare replikaen med **maks avvik 0,0** — batchingen er en ren
implementasjonsdetalj, ikke en annen algoritme. **[målt]**

---

---

## 5. Måling: HJELLE

### 5.1 DP og konvergens

| | verdi [EUR] |
|---|---|
| DP, rutenett 8 001 × 201/2 001 | 1 997 821,09 |
| DP, doblet rutenett 16 001 × 401/4 001 | **1 997 859,75** |
| endring ved dobling | **+38,65 EUR = +0,00194 %** |
| DP-politikken evaluert i **ekte HERSS** | **1 997 859,7485** |
| replika − ekte HERSS | −0,00165 EUR |

**[målt]** Lagringsrutenettet spenner `[1,0 , 17,34]` Mm³ (nedre grense = LRW-volumet, jf. §3.2;
øvre = maks volum under «alle av»-politikken, 15,21 Mm³, med 15 % margin). 588 mill.
transisjonsevalueringer i grunnkjøringen.

Konvergensendringen er **0,0019 %**, altså tre størrelsesordener mindre enn gapet under. DP-en
er konvergert.

### 5.2 De fire baselinjene

Alle tall er verdifunksjonen i **ekte HERSS**, ikke replikaen.

| | politikk | tunede parametre | VF [EUR] | **gap mot DP** | evalueringer |
|---|---|---|---|---|---|
| **DP** | eksakt | — | 1 997 859,75 | — | 5,9e8 transisjoner |
| **B4** | koordinatoppstigning | seeds 1,2; ε=0,01 | 1 976 390,74 | **1,075 %** | 34 302 050 |
| **B2** | prisgrense + tunet nivå | K=350, L=0,92 | 1 895 553,22 | **5,121 %** | 36 600 |
| **B3** | myopisk, ingen framsyn | w=11 110 EUR/Mm³ | 1 871 905,15 | **6,305 %** | 730 365 |
| **B1** | prisgrense, full produksjon | τ=27,69 | 1 837 570,72 | **8,023 %** | 363 |

**[målt]** Replika−HERSS-differansen er under 0,002 EUR for alle fem løsningene.

**B4-detaljer.** Begge omstarter nådde konvergens (ingen enkeltvariabelendring forbedret V med
mer enn ε=0,01 EUR):

| seed | grovt rutenett (21 nivå) | finpuss (201 nivå) |
|---|---|---|
| 1 | 1 973 859,64 (407 iterasjoner, konvergert) | **1 976 390,73** (211 iterasjoner, konvergert) |
| 2 | 1 962 777,01 (381 iterasjoner, konvergert) | 1 966 612,59 (172 iterasjoner, konvergert) |

Finpussen var nødvendig og ikke kosmetisk: den la til 2 531 EUR (seed 1) og 3 836 EUR (seed 2).
Uten den ville gapet mot B4 vært rapportert som ~1,20 % i stedet for 1,07 %, og differansen ville
vært ren diskretisering. **[målt]**

Spredningen mellom de to omstartene er 9 778 EUR = **0,49 % av DP** — betydelig, og et konkret
mål på hvor mye startpunktet betyr for metoden.

### 5.3 Tolkning av HJELLE-gapet

Etter kriteriene fastsatt før tallet var kjent:

- **Mot beste baselinje (B4): 1,075 % → «UAVKLART»-båndet (1–3 %).** Skal ikke rundes mot noe
  ønsket svar.
- **Mot terskelfamilien (B2), som er direkte sammenlignbar med målingen 2026-07-30: 5,121 %.**

Dette er hovedresultatet. Den *samme* politikkfamilien som lå 0,285 % fra optimum i
overflodsregimet ligger **5,12 %** fra optimum i knapphetsregimet — en faktor 18. **[målt]**
0,285 % var altså et artefakt av vannoverfloden på `mini_utahps_daily`, ikke en egenskap ved
ett-magasinproblemet. **[vurdering]**

At B3 (helt uten framsyn) ligger 6,3 % under DP er den viktigste diagnostiske observasjonen:
framsyn *er* verdt noe her, i motsetning til på `mini_utahps_daily`.

Samtidig: en godt implementert, konvergert koordinatoppstigning kommer innenfor 1,07 %. Rommet
mellom en seriøs generisk optimerer og eksakt DP er altså ett prosentpoeng, ikke fem. Begge tall
må stå. **[vurdering]**

### 5.4 Diagnose — hva politikken faktisk gjør

| | DP | B4 (beste baselinje) |
|---|---|---|
| magasinnivå gjennomløpt [masl] | 748,00 – 757,46 | 748,00 – 757,46 |
| andel av [LRW, HRW] | 105,1 % | 105,1 % |
| netto fallhøyde gjennomløpt [m] | 53,23 – 64,60 | 53,21 – 64,59 |
| `(H_max − H_min)/H_max` **gjennomløpt** | **17,6 %** | 17,6 % |
| samme, *tilgjengelig* fra [LRW,HRW] | 13,4 % | 13,4 % |
| produksjon [MWh] | 12 278,5 | 12 205,1 |
| terminalverdi [EUR] | 53 369 | 52 305 |

**[målt]** To ting er verdt å merke seg:

1. Nivået går **over** HRW (757,46 > 757,0) fordi overløpskurven først gir 10 m³/s ved 758 masl;
   magasinet kan derfor stå midlertidig over HRW. Vann over HRW er verdiløst i terminalleddet.
2. **Gjennomløpt fallhøydespenn (17,6 %) er større enn tilgjengelig magasinspenn (13,4 %).**
   Dette er motsatt av `mini_utahps_daily`, der gjennomløpt (8,4 %) var mindre enn tilgjengelig
   (13,4 %). Forklaringen er falltapet `HEADLOSSCOEF·Q² = 0,3·Q²`, som ved `Q = 4,0 m³/s` er
   4,8 m — sammenlignbart med magasinets eget 9 m spenn. Ikke-lineariteten i fallhøyde kommer
   her like mye fra *driftspunktet* som fra magasinfyllingen. **[vurdering]**

**Feasibility-tabell**

| | DP | B4 |
|---|---|---|
| aggressive-action-kost | 0,02 EUR (1 steg) | 0,96 EUR (2 steg) |
| **LRW-straff** | **0,00 EUR (0 steg)** | **0,00 EUR (0 steg)** |
| start/stopp-kost | 45,00 EUR (45 overganger) | 45,00 EUR (45 overganger) |
| totalt overløp | 6,124 Mm³ (33 steg) | 5,935 Mm³ (33 steg) |
| steg med magasinet på LRW | 0 | 0 |

**[målt]** Ingen løsning kjøper seg fordeler gjennom brudd: samlet straffekost er under 46 EUR av
en verdifunksjon på 2 MEUR. Den eneste virkelig aktive begrensningen er **overløp** — 6,1 Mm³
spilt vann, altså 6,6 % av årstilsiget, i 33 av 365 steg.

### 5.5 Politikkens form — den ligner *ikke* en terskelregel

| | DP | B4 |
|---|---|---|
| steg på / av | 285 / 80 | 289 / 76 |
| full last / dellast | 42 / 243 | 62 / 227 |
| antall distinkte nivåer når på | **71** | 65 |
| beste terskelregels treffsikkerhet på/av | **81,4 %** (68 feilklassifiserte steg) | 82,5 % |
| laveste pris med produksjon | **27,40** | 27,40 |
| høyeste pris uten produksjon | **122,13** | 126,04 |

**[målt]** Tre observasjoner, i økende viktighet:

1. **243 av 285 produserende steg er på dellast**, fordelt på 71 distinkte nivåer. En
   terskelregel med ett nivå kan ikke uttrykke dette.
2. **Ingen prisgrense klassifiserer mer enn 81,4 % av på/av-beslutningene riktig.** Optimum
   produserer ved priser helt ned til 27,40 EUR/MWh og står stille ved priser opp til 122,13 —
   et overlappsbånd på 94,7 EUR/MWh. Beslutningen er tilstandsavhengig, ikke prisavhengig.
3. Dellasten skyldes **ikke** jakt på turbinens beste driftspunkt: bare 12,3 % av de
   produserende stegene ligger innenfor 5 % av 2,79 m³/s (93 % virkningsgrad), og
   gjennomsnittshandlingen er 0,892 (≈ 3,57 m³/s). Korrelasjonen mellom produksjonsnivå og
   magasinfylling er bare 0,117, så det er heller ikke primært en fallhøydeeffekt. **[målt]**

**[vurdering] Hva driver den da?** Med `R = 0,07` buffrer magasinet bare ~26 døgn ved full
kjøring, mens `rho = 0,78` betyr at nesten alt vann *må* brukes. Den bindende avveiningen er
derfor overløpsunngåelse innenfor et kort vindu: i tilsigsrike perioder må man produsere selv om
prisen er lav, ellers spilles vannet — og man må modulere nivået for å treffe magasinkapasiteten
presist. Det forklarer både produksjonen ved 27,40 EUR/MWh og de 71 nivåene. Dette er en
struktur en terskelregel ikke kan uttrykke, og det er den mest presise beskrivelsen av hvorfor
gapet er 5,1 % mot B2. **[usikkert]** — forklaringen er konsistent med tallene, men ikke bevist;
en direkte test ville vært å variere overløpskurven, noe som ville brutt «ingen fysiske
endringer»-regelen.

### 5.6 Dekomponering av gapet

Gapet mot beste baselinje overstiger 1 %, så dekomponeringen er kjørt. Tre **separate**
begrensede DP-kjøringer — de summerer ikke til totalen, og rekkefølgen betyr noe:

| begrensning | VF [EUR] | under full DP |
|---|---|---|
| (a) **timing alene** — handlinger kun `{0,1}`, full framsyn, full fysikk | 1 942 254,78 | **2,783 %** |
| (b) **nivåmodulering** — fullt handlingsrutenett, fallhøyde fryst på 752,5 masl | 1 989 548,58 | **0,416 %** |
| (c) **full modell** | 1 997 859,75 | 0 |

**[målt]** Frysenivået 752,5 masl er midtpunktet mellom LRW (748) og HRW (757) — **eksogent
valgt**, ikke lest av DP-optimum, nettopp for å unngå å bruke svaret til å definere mellomsteget.

Lesningen: å frata optimereren evnen til å kjøre dellast koster **2,78 %**; å frata den
fallhøydeavhengigheten koster **0,42 %**. Nivåmodulering er altså den klart viktigste
enkeltkapabiliteten, og fallhøyde-ikke-lineariteten — som er den mekanismen CLAUDE.md §2
framhever som det som «motstår lineærisering» — er verdt under en halv prosent på denne
instansen. **[vurdering]**

---

## 6. Måling: GRESSE

### 6.1 DP og konvergens

| | verdi [EUR] |
|---|---|
| DP, rutenett 26 001 × 201/2 001 | 7 404 414,6596 |
| DP, doblet rutenett 52 001 × 401/4 001 | 7 404 414,6607 |
| endring ved dobling | **+0,0011 EUR = +0,0000 %** |
| DP-politikken i **ekte HERSS** | **7 404 414,6670** |
| replika − ekte HERSS | −0,00631 EUR |

**[målt]** Lagringsrutenettet spenner `[106,60 , 186,07]` Mm³ med samme oppløsning relativt til
maks døgnutslipp som HJELLE (~155 rutenettceller per fullastdøgn). 1,91 mrd.
transisjonsevalueringer. Konvergensen er praktisk talt perfekt.

### 6.2 De fire baselinjene

| | politikk | tunede parametre | VF [EUR] | **gap mot DP** | evalueringer |
|---|---|---|---|---|---|
| **DP** | eksakt | — | 7 404 414,667 | — | 1,9e9 transisjoner |
| **B4** | koordinatoppstigning | seeds 1,2 | 7 404 414,377 | **0,0000 %** | 22 785 804 |
| **B3** | myopisk, ingen framsyn | w=39 390 EUR/Mm³ | 7 393 953,75 | **0,141 %** | 730 365 |
| **B2** | prisgrense + tunet nivå | K=171, **L=1,0** | 7 374 289,82 | **0,407 %** | 36 600 |
| **B1** | prisgrense, full produksjon | τ=111,72 | 7 374 289,82 | **0,407 %** | 363 |

**[målt]** Fire ting:

1. **B4 finner DP-optimum.** Begge omstarter konvergerte til nøyaktig samme verdi
   (7 404 414,3708), 0,29 EUR under DP — det er 4e−8 relativt. Landskapet er, så vidt to
   omstarter kan vise, unimodalt. **[vurdering]**
2. **B1 og B2 gir identisk resultat.** B2s tuning velger `L = 1,0`, altså full produksjon, og
   kollapser dermed til B1. Den ekstra parameteren kjøper ingenting — nøyaktig den degenerasjonen
   som gjorde forrige måling verdiløs, men her med et lite gap (0,41 %) i stedet for et
   degenerert regime.
3. **B3 uten framsyn er 0,141 % fra optimum.** Etter kriteriet i oppgaven er dette sterkt bevis
   for at GRESSE-instansen mangler meningsfull intertemporal struktur.
4. Gapet mot beste baselinje er **0,0000 %** → **under 1 %-kriteriet.**

### 6.3 Diagnose — GRESSE *er* en terskelregel

| | GRESSE DP | HJELLE DP (til sammenligning) |
|---|---|---|
| magasinnivå gjennomløpt [masl] | 740,43 – 747,20 | 748,00 – 757,46 |
| andel av [LRW, HRW] | 75,3 % | 105,1 % |
| netto fallhøyde gjennomløpt | 154,68 – 163,86 m | 53,23 – 64,60 m |
| `(H_max−H_min)/H_max` gjennomløpt | **5,6 %** (tilgj. 5,4 %) | 17,6 % (tilgj. 13,4 %) |
| **totalt overløp** | **0,000 Mm³ (0 steg)** | 6,124 Mm³ (33 steg) |
| aggressive-action-kost | 0,00 EUR (0 steg) | 0,02 EUR (1 steg) |
| **LRW-straff** | **0,00 EUR (0 steg)** | **0,00 EUR (0 steg)** |
| start/stopp-kost | 52,00 EUR | 45,00 EUR |
| beste terskelregels treffsikkerhet | **99,7 %** (1 feilklassifisert steg) | 81,4 % (68) |
| beste terskel τ | **105,12 EUR/MWh** | 80,53 |
| laveste pris med produksjon | 105,66 | 27,40 |
| høyeste pris uten produksjon | 110,51 | 122,13 |
| **prisoverlapp** | **4,85 EUR/MWh** | **94,73 EUR/MWh** |

**[målt]** Dette er rapportens skarpeste kontrast. På GRESSE er på/av-beslutningen en prisgrense
ved 105,12 EUR/MWh som treffer 364 av 365 steg — og terskelen ligger nesten nøyaktig på vannets
prisekvivalent fra §3.5 (96,4 EUR/MWh). Overlappsbåndet er 4,85 EUR/MWh mot HJELLEs 94,73.

Dette er akkurat den strukturen CLAUDE.md §7 forutsier: med **konstant** marginalverdi av vann,
én deterministisk prisserie og perfekt framsyn ligger optimum strukturelt nær en terskelregel.
GRESSE oppfyller premisset. HJELLE gjør det ikke — og grunnen er §9.

---

## 7. Sensitivitet: HJELLE med fysisk konsistent vannverdi

`analysis/instances/hjelle_daily_e163/` er identisk med `hjelle_daily` bortsett fra
`LOCAL_ENERGY_EQUIVALENT 0.163` i topologifila. Dette er en **egen instans på disk**, ikke en
overstyring på Python-siden: overstyrer man bare replikaen, optimerer den ekte simulatoren en
annen målfunksjon, og enhver kryssjekk sammenligner to ulike verdifunksjoner. Det ble faktisk
observert underveis — en Python-side-overstyring ga replika−HERSS = **+47 847 EUR**, mot
−0,0012 EUR med den riktige instansen. **[målt]**

| | HJELLE `e=0,11` (primær) | HJELLE `e=0,163` (sensitivitet) |
|---|---|---|
| DP (ekte HERSS) | 1 997 859,75 | 2 039 109,90 |
| konvergensendring ved dobling | +0,0019 % | +0,0019 % |
| **B4** gap | **1,075 %** | **1,077 %** |
| **B2** gap | **5,121 %** | **7,001 %** |
| **B3** gap | **6,305 %** | **12,980 %** |
| **B1** gap | **8,023 %** | **9,829 %** |
| overløp | 6,124 Mm³ (33 steg) | 6,126 Mm³ (35 steg) |
| terskeltreffsikkerhet | 81,4 % | 79,2 % |
| dekomponering (a) timing | 2,783 % | 2,643 % |
| dekomponering (b) frozen head | 0,416 % | 0,272 % |

**[målt] Konklusjon på konfunderen: den forklarer ingenting.** Å rette vannverdien til den
fysisk konsistente verdien gjør HJELLEs gap **større**, ikke mindre — B2 fra 5,12 % til 7,00 %,
B3 fra 6,31 % til 12,98 %. Forskjellen mellom HJELLE og GRESSE kan derfor ikke tilskrives at
HJELLEs terminalverdi er feilkalibrert. **[vurdering]**

Bemerk at B4-gapet er uendret (1,075 % → 1,077 %) mens terskel- og myopisk-gapene endres mye.
Koordinatoppstigningens avstand til optimum ser ut til å være en egenskap ved søkemetoden, ikke
ved vannverdien. **[usikkert]** — to instanser er et tynt grunnlag for den slutningen.

---

## 8. Eget resultat: ett-magasin-utsnitt av uTAHPS har ingen aktive myke begrensninger

Dette avsnittet står uavhengig av hva gapet ble.

`RES_PENALTY 300` var den eneste myke begrensningen med størrelse nok til å binde
(`300·dt/3600 = 7 200` EUR per meter under LRW per døgn). §3.2 viser at den er **strukturelt
uoppnåelig** i et ett-magasin-utsnitt. Feasibility-tabellen kollapser dermed til:

- **eneste nedre grense:** aggressive-action-klippet — hardt (`flow = 0`), ikke en straff man kan
  kjøpe seg forbi;
- **eneste øvre grense:** overløp over HRW — hardt, verditap uten straffledd;

og **ingen myk begrensning er aktiv i det hele tatt**, i noen av de tre kjøringene.

| Mekanisme | Tiltenkt rolle | Faktisk bidrag | Kilde |
|---|---|---|---|
| `RES_PENALTY 300` (LRW) | eneste bindende myke begrensning | **kan ikke fyre**; 0,00 EUR i 0 av 365 steg i alle kjøringer og alle 18 valideringssekvenser | **[kilde]** §3.2 + **[målt]** |
| `POWSTAT_STARTSTOP 2.0` | hovedkilden til diskret struktur | 45–52 EUR av 2–7 MEUR = **< 0,003 %** | **[målt]** |
| `POWSTAT_MIN_DISCHARGE` | minste driftspunkt | logges kun, håndheves ikke | **[kilde]** §3.3 |
| `FLOODLEVEL_PENALTY` | straff over HRW | leses fra fil, aldri anvendt | CLAUDE.md §9 |
| `LOCAL_ENERGY_EQUIVALENT` | konsistent vannverdi ved slutt | 32 % underpriset hos HJELLE | **[målt]** §3.5 |
| `MAX_ADJUST`, `QMIN`, `OUTLET_AUTO_QMIN` | — | deaktivert (`-9999`) i begge utsnitt | **[kilde]** |

**[vurdering] Konklusjon som skal sies rett ut:** de leverte instansene er ikke konstruert for å
være optimeringsmessig krevende. Straffeleddene i HERSS er der for å bryte platåer i
verdifunksjonen — kildekommentaren ved `powerstation.cpp:784` sier det eksplisitt: «a minor
penalty ... just so we dont get the same value in VF» — ikke for å håndheve driftsbegrensninger.
Et arbeid som vil bruke feasibility som en akse (harde vs. myke begrensninger, reparasjonsoperatorer,
straffekalibrering) må **legge til** bindende struktur selv; den finnes ikke i datasettene.

Praktisk konsekvens for CLAUDE.md §11: kravet om en separat feasibility-tabell er fortsatt riktig,
men på disse instansene vil den være tom. Det er i seg selv et resultat verdt å rapportere, ikke
en formalitet å hoppe over.

---

## 9. HJELLE mot GRESSE — hypotesen ble motbevist

Oppgaven formulerte forventningen slik: *«Hvis GRESSE gir et større gap enn HJELLE, har du
identifisert lagringsdybde som den avgjørende systemegenskapen.»*

**Det motsatte skjedde.** GRESSE har 4,6× dypere lagring og et 12× *mindre* gap:

| | HJELLE | GRESSE |
|---|---|---|
| `rho` (knapphet) | 0,782 | 0,563 |
| `R` (lagringsdybde) | **0,071** | **0,325** |
| lagring i døgn ved full kjøring | ~26 | ~119 |
| **overløp under DP-optimum** | **6,124 Mm³ (33 steg)** | **0,000 Mm³ (0 steg)** |
| gap B2 (terskel + nivå) | **5,121 %** | **0,407 %** |
| gap B3 (myopisk) | **6,305 %** | **0,141 %** |
| gap B4 (koordinatoppstigning) | **1,075 %** | **0,0000 %** |
| terskelregelens treffsikkerhet | 81,4 % | 99,7 % |
| prisoverlapp [EUR/MWh] | 94,73 | 4,85 |

**[målt]**

**[vurdering] Den avgjørende systemegenskapen er ikke lagringsdybde, men om
overløpsbegrensningen binder.**

Mekanismen: GRESSE (`R = 0,325`, `rho = 0,563`) har rikelig plass. Magasinet spiller aldri over,
aggressive-action-grenen fyrer aldri, LRW nås aldri. Ingen kapasitetsbegrensning er aktiv, og da
er problemet nøyaktig det CLAUDE.md §7 advarer om: konstant marginalverdi av vann + perfekt
framsyn ⇒ optimum *er* en terskelregel, og både en myopisk regel og en tunet terskel kommer
innenfor en halv prosent.

HJELLE (`R = 0,071`, `rho = 0,782`) har nesten ingen buffer og må håndtere nesten hele årstilsiget
gjennom turbinen. Overløpsbegrensningen binder i 33 av 365 steg. Da må politikken produsere ved
priser ned til 27,40 EUR/MWh for å unngå spill, og modulere nivået for å treffe magasinkapasiteten
— struktur en terskelregel ikke kan uttrykke, og som en myopisk regel ikke kan se.

Dette er et mer presist resultat enn hypotesen ville gitt: det er **knapphet på lagringsplass
relativt til gjennomstrømning**, ikke lagringsdybde i seg selv, som skaper et
optimeringsproblem. `R` er derfor ikke bare «hvor langt valget rekker» — lav `R` kombinert med
høy `rho` er selve vanskelighetsdriveren, og høy `R` gjør problemet *lettere*.

**Forbehold.** To instanser. `rho` og `R` varierer samtidig, så de er ikke separat identifisert av
dette designet. Utsagnet «overløp er mekanismen» er støttet av at overløpet er 6,1 Mm³ mot 0,0 og
av prisoverlappen, men ikke bevist — en ren test ville krevd å variere overløpskurven eller HRW,
altså et brudd på «ingen fysiske endringer». **[usikkert]**

Legg dessuten til forbeholdet fra §2.4: GRESSE er i utsnittet gjort *knappere* enn den er i full
uTAHPS. Den virkelige GRESSE-noden, med tilsig ovenfra, har høyere `rho` og ville altså — hvis
mekanismen over stemmer — ligge nærmere HJELLEs regime enn dette utsnittet antyder. **[usikkert]**

---

## 10. Konklusjon

**Etter kriteriene fastsatt før tallene var kjent:**

| Instans | gap mot beste baselinje | kategori |
|---|---|---|
| HJELLE (`e=0,11`, primær) | **1,075 %** (B4) | **UAVKLART** (1–3 %-båndet) |
| HJELLE (`e=0,163`, sensitivitet) | **1,077 %** (B4) | **UAVKLART** |
| GRESSE | **0,0000 %** (B4) | **under 1 %** |

Dette er de tallene kriteriene ber om, og de skal ikke rundes mot noe ønsket svar.

**Men det viktigste tallet er et annet.** Den *samme* terskelfamilien (B2) som lå **0,285 %** fra
optimum på `mini_utahps_daily` ligger **5,121 %** fra optimum på HJELLE — en faktor 18.
Spørsmålet oppgaven stilte var om 0,285 % var et artefakt av vannoverflod. **Svaret er ja, for
HJELLE.** **[målt]**

**Hva som er avklart:**

1. 0,285 % var en egenskap ved `mini_utahps_daily`s vannbalanse (`rho = 1,82`), ikke ved
   ett-magasinproblemet. På HJELLE er terskelgapet 5,1 % og det myopiske gapet 6,3 %.
2. Ett-magasinproblemet er **ikke** universelt lett i knapphetsregimet. Det avhenger av om
   overløpsbegrensningen binder.
3. Lagringsdybde gjør problemet **lettere**, ikke vanskeligere. Hypotesen er motbevist.
4. `LOCAL_ENERGY_EQUIVALENT`-inkonsistensen forklarer ikke forskjellen; å rette den forstørrer
   gapet.
5. Ingen myk begrensning er aktiv på noen av instansene (§8).
6. En godt implementert, konvergert koordinatoppstigning — den deterministiske optimereren fra
   Matheussen, Granmo & Sharma (2019) — ligger **1,08 %** fra optimum på HJELLE og treffer
   optimum på GRESSE. Artikkelen sier eksplisitt at den ikke kan verifisere om metoden finner
   optimum. Denne målingen kan: på HJELLE gjør den det ikke, og spredningen mellom to
   konvergerte omstarter er 0,49 % av verdifunksjonen. **[målt]**

**Hva som ikke er avklart:**

- Om gapet på 1,08 % mot B4 er stort nok til å bære et arbeid. 1–3 %-båndet er uavklart etter
  kriteriene, og det er kun én instans.
- Om `rho` eller `R` er den kausale variabelen — de varierer sammen i dette designet.
- Om resultatet holder i full kaskade. Det er ikke testet her.

**Neste steg som følger av dette, ikke av ønsketenkning:** vanskeligheten kommer fra en aktiv
kapasitetsbegrensning, ikke fra vannverdiavveiningen. Skal problemet bli hardt nok, må
bindende struktur legges til bevisst — terminalvolumkrav, rampegrenser, flere aggregater — slik
CLAUDE.md §10.6 allerede krever. GRESSE viser hvor lett det blir når ingen begrensning binder.

---

## Reproduksjon

```bash
cd analysis/scarcity_gap
../../.venv/bin/python build_instances.py          # bygger begge instanser
../../.venv/bin/python test_regression.py          # mini_utahps_daily, rel tol 1e-6
../../.venv/bin/python validate_instance.py        # Diagnose + vannbalanse + rho/R
../../.venv/bin/python validate_replica.py         # 9 sekvenser x 2 instanser mot ekte HERSS
../../.venv/bin/python run_measurement.py hjelle
../../.venv/bin/python run_measurement.py gresse
../../.venv/bin/python run_measurement.py hjelle_e163
```

Faste seeds: B4 bruker seeds 1 og 2; valideringssekvensene bruker seed 42 (tilfeldig politikk),
seed 7 (`_forward_batch`-sjekk) og seed 0 (`dp.check_against_replica`). Alle registrert i
`result_*.json`.

Kjøretid på 16 kjerner: HJELLE ~40 min, GRESSE ~55 min, sensitivitet ~35 min, dominert av
DP-konvergenssjekken (doblet lagrings- og handlingsrutenett) og B2s 36 600 fullhorisont-
evalueringer.

**Versjonskontroll.** Alt ligger under `analysis/`, ikke `data/`, så `.gitignore` linje 26
(`data/*`) rammer det ikke — jf. CLAUDE.md §5. To ting er likevel *ikke* sporet:
`run_*.log` (fanges av `.gitignore`-regelen `*.log`) og `analysis/scarcity_gap/__pycache__/`.
Konsollogene er reproduserbare fra `result_*.json`, som er sporet. Instansenes `output/`-kataloger
*er* sporet og skitnes til av hver kjøring — vurder å legge dem til `.gitignore` bevisst før
noe committes. **[vurdering]**
