# Gap-måling over flere instanser: koblede beslutningsvariabler og `rho`/`R`-aksen

**Kjøring:** 2026-08-03 (natt). **Repo-commit:** `f56237f`, upstream pinnet `029a2d5`.
**HERSS:** VERSION 3.1.03 / VERSION_DATE 20260611.
**Seeds:** 1 og 2 (registrert i hver `result_*.json`).

Merking gjennomgående: **[kilde]** verifisert i C++-kilden, **[målt]** kjørt og målt,
**[vurdering]** min tolkning, **[antakelse]**, **[usikkert]**.

---

## 0. Sammendrag

*(fylles inn til slutt)*

---

## 1. Hva kjøringen skulle svare på

Tre instanser var målt fra før — `mini_utahps_daily`, HJELLE og GRESSE — alle med **ett
magasin, én generator og ingen luke**. To spørsmål sto igjen:

1. **Svikter koordinatoppstigning når beslutningsvariablene er koblet?** B4 endrer én
   variabel om gangen og kan per konstruksjon ikke finne forbedringer som krever at to
   variabler endres samtidig. Ingen målt instans hadde mer enn én variabel per tidssteg.
2. **Er `rho ≈ 1` med lav `R` vanskelighetsregimet?** Arbeidshypotesen hvilte på to
   punkter.

`res_casc_A` (to magasin, luke, to generatorer) svarer på det første. TOPPSY og
KROKNESVATN legger to punkter til `rho`/`R`-aksen. Et syntetisk rutenett skiller `rho`
fra `R`.

---

## 2. Et funn som endret oppgave A: RES_A sitt vann er verdiløst i objektivet

**[kilde]** `herss.cpp:657–693` akkumulerer `upstream_remaining_active_Mm3` **kun** langs
`ptr_downstream_node` — én peker per node. `reservoir.cpp:1062–1073` setter den pekeren til
**overløpsnoden** når magasinet ikke har tunnel; luken teller ikke med. RES_A har ingen
`OUTLET_TUNNEL` og `OVERFLOW_CURVE … 2`, så kjeden blir 0 → 2 (CHAN2) → 5 (utløp) og når
aldri PSTAT_B.

**[målt]** Bekreftet i den leverte outputen
`data/res_casc_A/output/riversystem_ResCascA_output.txt`:

```
tot_active_remaining_Mm3 = 18.000     (9,0 fra RES_A + 9,0 fra RES_B)
tot_remaining_MWh        =  990.000   = 0,11 × 9,0 × 1000   →  kun RES_B
```

**Konsekvens:** vann lagret i RES_A ved horisontslutt har verdi **null**. Den eneste måten
A-vann får verdi på er å bli flyttet gjennom luken til RES_B og turbinert innenfor
horisonten, og luken er ratebegrenset til 6,0 m³/s = 0,5184 Mm³/døgn.

**[vurdering]** Dette er både et modelleringsartefakt som må rapporteres, og grunnen til at
instansen faktisk *har* ekte kobling: lukebeslutningen er koblet til produksjonsbeslutningen
gjennom en ratebegrenset overføring. Artefaktet isoleres i kapittel 6 med en syntetisk
variant der terminalleddet også verdsetter RES_A.

---

## 3. Verifisert transisjonsstruktur for kaskaden [kilde]

- Noder simuleres i idnr-rekkefølge (`herss.cpp:660–677`), så RES_A sin lukeflyt lander i
  RES_B sin `up_inflow[t]` i **samme** tidssteg (`reservoir.cpp:573`).
- Luken har **ingen** aggressive-action-straff. Flyten klippes mot
  `current_filling − filling_at_hatchlevel` (`reservoir.cpp:565–571`). `hatch_masl` = 848,0
  = LRW, så luken kan tømme RES_A helt ned til LRW.
- Lukeklippingen går gjennom en **kurve-tur/retur**: `ac_res_masl_2_Mm3.x2y(res_masl)` der
  `res_masl` selv kom fra `ac_res_Mm3_2_masl.x2y(res_Mm3)`. Fordi ArrayCurve er et
  1000-bøtters oppslag er dette ikke identitet. Overløpsklippingen bruker derimot rå
  `res_Mm3` (`reservoir.cpp:261`). Begge er portet som skrevet.
- `SHARED_PENSTOCK TRUE`: ett falltap på summert flyt, men virkningsgrad slås opp per
  generator (`powerstation.cpp:173–199`). Start/stopp telles per generator (`:240–258`),
  1,0 EUR per overgang.
- Aggressive-action-straffen ligger i `GetTunnelFLow` (`powerstation.cpp:783–791`) på
  **summen** av generatorflyt mot RES_B sitt `up_res_Mm3`, og nuller da flyten for begge.

### 3.1 En fallgruve i overløpsberegningen [kilde]

`CalcOverflow` (`reservoir.cpp:206–274`) har HRW-klippingen **inni** vakten
`res_masl > masl_start_overflow`; under det nivået returnerer den 0,0 uten å røre klippingen.
Løfter man klippingen ut av vakten, blir «overløpet» `res_Mm3 − filling_at_hrw` — et
**negativt** tall når magasinet ligger under HRW — som trekkes fra og dermed *fyller*
magasinet til nøyaktig HRW for alltid.

Dette ble faktisk observert i første versjon av replikaen: RES_B lå fastspikret på 10,00000
Mm³ gjennom hele horisonten mens HERSS tømte det. Rapportert her fordi det er en ikke-åpenbar
strukturell detalj enhver reimplementasjon må få riktig, og fordi den bare avsløres av en
per-steg-sammenlikning — VF alene ville sett «bare litt for høy» ut.

---

## 4. Validering før måling

### 4.1 Byggeoppsett

**[målt]** `make` i `src/`: intakt, ingenting å bygge (arbeidstreet er rent mot `f56237f`).
**`make test` kunne ikke kjøres:** gtest-headerne mangler på denne maskinen
(`fatal error: gtest/gtest.h: No such file or directory`). Dette er en begrensning ved
kjøremiljøet, ikke ved koden — `src/` er uendret fra den pinnede tilstanden. **[usikkert]**
om testsuiten hadde passert; det kan ikke siteres i metodekapittelet uten å installere gtest.

### 4.2 Instanser

Alle nye instanser ligger under `analysis/instances/`; ingenting under `src/` eller `data/`
er endret. `res_casc_A` er en **verbatim kopi** av `data/res_casc_A` (topologi, priser,
tilsig, handlinger byte for byte), med to endringer: egen `output/`-katalog, og kanalenes
lineærmagasin initiert i stasjonær tilstand `S = k_res · Q`
(`cascadedreservoirs.cpp:41,106`) mot den flyten hver kanal faktisk fører.

**[målt]** Kanalinitieringen er **verdinøytral**: VF med leverte plassholderverdier og VF med
stasjonær tilstand er `88996,5020` i begge tilfeller, ΔVF = **0,0000 eksakt**. Det bekrefter
argumentet om at kanalene ikke kan påvirke V (ingen inntekt, QMIN av, alle nedstrøms
PSTAT_B), så replikaen modellerer dem ikke.

| kontroll | res_casc_A | toppsy_daily | kroknesvatn_daily |
|---|---|---|---|
| CLI-kjøring, 0 ERROR/WARN | ✔ | ✔ | ✔ |
| `Diagnose` / `checkNrSteps` / `DiagnoseRiversystemConfiguration` | ✔ | ✔ | ✔ |
| global vannbalanse | 0,000000 | 0,000000 | 0,000000 |
| `dt` verifisert fra `Dataset::getDeltaT` | 86400 × 30 | 86400 × 365 | 86400 × 365 |

### 4.3 Regimetall — rapportert før gapet

**[målt]**, regnet fra instansenes egne filer.

| instans | T | aktivt Mm³ | tilsig Mm³ | turbinkapasitet Mm³ | `R` | `rho` |
|---|---|---|---|---|---|---|
| `mini_utahps_daily` | 30 | 9,00 | — | — | 0,87 | 1,82 |
| HJELLE | 365 | 9,00 | 92,32 | 126,14 | **0,0713** | **0,7818** |
| GRESSE | 365 | 61,44 | 57,29 | 189,22 | **0,3247** | **0,5625** |
| TOPPSY | 365 | 126,64 | 75,21 | 186,06 | **0,6806** | **1,0168** |
| KROKNESVATN | 365 | 199,27 | 161,27 | 309,05 | **0,6448** | **0,9474** |
| `res_casc_A` (system) | 30 | 18,00 | 16,67 | 20,74 | **0,8681** | **1,5199** |

TOPPSY og KROKNESVATN traff de forventede tallene (0,68/1,02 og 0,64/0,95).

**`res_casc_A` er et unntak fra `rho`-måltallet.** `rho_system` = 1,52 ser ut som
overflodsregimet, men det gamle måltallet ser ikke overføringsflaskehalsen: RES_A har
7,74 + 12,22 = **19,96 Mm³** tilgjengelig mot en lukekapasitet på **15,55 Mm³** over
horisonten. Forholdet er **1,284**, altså kan luken ikke passere 28 % av vannet i RES_A, og
overløp fra RES_A er **strukturelt uunngåelig**. Prediksjonen, notert før måling: under
arbeidshypotesen («vanskelig når overløpsbegrensningen binder») skulle dette vært en
vanskelig instans.

### 4.4 Replikaer — revalidert per instans, ikke gjenbrukt

**res_casc_A** (`analysis/cascade/validate2_replica.py`): 16 handlingssekvenser valgt for å
treffe hver gren — lukeklipping, lukevakt, aggressive handlinger, overløp i begge magasin,
start/stopp i hver generator, 0,01-terskelen, asymmetrisk generatorlast (som bare betyr noe
fordi rørgaten er delt).

**[målt]** Verste `|ΔVF|` = **0,000422 EUR** (grense 0,05). Per-steg-spor sammenliknet for
fire sekvenser over 11 felter: `res_Mm3` begge magasin, `hatchflow_m3s`, `tunnelflow_m3s`,
overløp begge magasin, `power_MWh`, `profit`, aggressive-kostnad, start/stopp, `Hnetto` —
alle innenfor ~2·10⁻⁸ (flyttallsstøy), unntatt `profit` på 2,5·10⁻⁴ av en størrelse på ~10⁴.

**TOPPSY og KROKNESVATN** (`validate_replica.py`, egen kjøring per instans): alle sekvenser
PASS, verste `|ΔVF|` = **0,0196 EUR**.

**Regresjonsvakt:** `test_regression.py` passerer uendret etter utvidelsen av `params.py`
— DP-VF og terskel-VF for `mini_utahps_daily` reproduseres til relativ 0,0.

### 4.5 2D-DP-en mot replikaen

**[målt]** `dp2.check_against_replica`: verste avvik **1,8·10⁻¹²** over 16 handlingskombinasjoner
× 6 tilfeldige tilstander.

---

## 5. Resultater

### 5.1 `res_casc_A` — den koblede instansen

DP-optimum **134 653,73 EUR** (161×161 tilstandsrutenett, 21×21 handlingsrutenett).
DP-politikken kjørt gjennom **ekte HERSS** gir samme verdi til `|Δ|` = **4,4·10⁻⁵ EUR**.
Det er også den blokkerende verifiseringen av ommerkingsargumentet for de to identiske
generatorene: hadde symmetrireduksjonen vært feil, ville politikken ikke reprodusert seg i
simulatoren. Alle gap er regnet på **HERSS-VF**.

| metode | VF (HERSS) | gap mot DP | veggklokke | fulle horisontevalueringer | steg-celler |
|---|---:|---:|---:|---:|---:|
| **DP** | **134 653,73** | — | 21,5 min | — | 3,77·10⁹ |
| B0 levert `actions.txt` | 88 996,50 | **33,907 %** | <0,1 s | 1 | 30 |
| B2 terskel + nivå + lukenivå | 134 064,68 | **0,4375 %** | 0,44 s | 32 550 | 9,77·10⁵ |
| B3 myopisk (primær, `w_A = w_B`) | 118 690,76 | **11,855 %** | 0,01 s | 50 431 | 5,05·10⁴ |
| B3 myopisk (sekundær, `w_A = 0`) | 120 134,99 | **10,782 %** | 0,01 s | 50 431 | 5,05·10⁴ |
| **B4** koordinatoppstigning | **134 644,47** | **0,0069 %** | 25,9 s | 3 893 021 | 6,04·10⁷ |
| **B5** + parvise trekk | **134 623,43** | **0,0225 %** | 82,3 s | 20 001 176 | 3,17·10⁸ |

*Kun veggklokketid er sammenliknbar på tvers av metodefamilier. «Fulle
horisontevalueringer» teller kandidattrajektorier; B4/B5 evaluerer dem i vektoriserte
batchsveip til langt lavere kostnad per stykk enn B2s løkke, og DP-en teller ikke i samme
enhet i det hele tatt (den evaluerer transisjonsceller, ikke trajektorier). Dette retter
opp den misvisende ensøylerapporteringen i forrige rapport.*

**Omstartsspredning** (selvstendig resultat): B4 **73,13 EUR = 0,054 % av VF**, B5
**58,30 EUR = 0,043 %**. Finpussen på 201 nivå la til 124–285 EUR (B4) og 60–113 EUR (B5)
— ikke kosmetisk.

### 5.2 Hovedspørsmålet: B5 mot B4

**[målt]** `B5 − B4 = −21,04 EUR = −0,0156 % av VF`. Negativt, og en størrelsesorden under
både B4s egen omstartsspredning (0,054 %) og signifikansterskelen som ble fastsatt før
måling (0,49 %).

**Utfallet er altså «B4 ≈ B5, begge nær DP».** Men konklusjonen må formuleres presist, for
diagnosen forklarer *hvorfor*, og forklaringen begrenser hvor langt resultatet rekker:

| diagnose, DP-optimum | verdi |
|---|---|
| lukens utnyttelsesgrad | **0,9998** |
| steg der luken ligger på taket | **29 av 30** |
| steg der luken er null | 0 |
| steg der stasjonen er på | **30 av 30** (terskeltilpasning degenerert) |
| overløp RES_A | **0,000 Mm³ (0 steg)** |
| overløp RES_B | 0,093 Mm³ (4 steg) |
| aggressive handlinger | 0,00 EUR (0 steg) |
| LRW-straff | 0,00 EUR (0 steg) |
| start/stopp | 4,00 EUR (4 overganger) |
| strandet aktivt vann i RES_A ved T | **4,414 Mm³** |
| fallhøydespenn `Hnetto` | 49,05 → 61,31 m (23,7 %) |
| distinkte totale Q-nivå | 14 |

**Lukebeslutningen er en hjørneløsning.** Luken ligger på taket i 29 av 30 steg og
stasjonen er på i alle 30. Da finnes det ingen koblet forbedring å finne: den ene variabelen
sitter på sin grense uavhengig av den andre, så B5s parvise trekk har ingenting å bidra med.

**[vurdering]** Dette er *ikke* bevis for at koordinatoppstigning takler koblede variabler.
Det er et bevis for at **denne instansen ikke stiller spørsmålet**, og grunnen er
artefaktet i kapittel 2: siden vann i RES_A er verdt null, er «slipp så fort som mulig»
ubetinget optimalt, og luken har ingen avveining. Den korrigerte varianten i kapittel 6 er
derfor den egentlige testen av spørsmål 1.

### 5.3 En prediksjon som ble motbevist

I §4.3 ble det notert, før måling, at overløp fra RES_A skulle være **strukturelt
uunngåelig** fordi luken bare kan passere 15,55 Mm³ av de 19,96 Mm³ som er tilgjengelig.

**Det var feil.** Overløp fra RES_A under DP-optimum er **0,000 Mm³ i 0 steg**. Feilslutningen
var å sette likhetstegn mellom «luken kan ikke passere alt vannet» og «magasinet må gå over
HRW». Luken (0,5184 Mm³/døgn) er raskere enn middeltilsiget (0,4074 Mm³/døgn), så nivået
faller jevnt fra start og når aldri HRW. De 4,41 Mm³ som ikke rekker gjennom blir ikke sølt —
de blir **strandet**, og verdsatt til null. Bindingen er terminalverdien av strandet vann,
ikke HRW-begrensningen.

Strandet vann tilsvarer **16 021 EUR**, altså **11,9 % av VF**, som objektivets topologi
kaster bort. Det er størrelsen på artefaktet fra kapittel 2, målt.

**[vurdering]** For arbeidshypotesen er dette et *støttende* datapunkt fra en helt annen
struktur: `res_casc_A` har praktisk talt ikke overløp (0,000 + 0,093 Mm³), og instansen er
**lett** — B2 er 0,44 % fra optimum og B4 er 0,007 %. Ingen overløp ⇒ lite gap, som
hypotesen forutsier.

### 5.4 TOPPSY og KROKNESVATN

Begge DP-er konvergerte godt: ved doblet tilstandsrutenett **og** doblede handlingsrutenett
flyttet verdien seg **+0,000347 %** (TOPPSY) og **+0,000325 %** (KROKNESVATN) — tre til fire
størrelsesordener under de målte gapene. DP-politikken reproduseres i ekte HERSS til
0,0017 og 0,0079 EUR.

| | TOPPSY | KROKNESVATN |
|---|---:|---:|
| DP (HERSS) | 3 555 557,24 | 15 593 840,97 |
| B1 ren terskel | 2,158 % | 1,271 % |
| B2 terskel + nivå | **1,611 %** | **1,271 %** |
| B3 myopisk | 1,185 % | 3,665 % |
| B4 koordinatoppstigning | **0,0013 %** | **0,0017 %** |
| overløp under DP-optimum | **0,000 Mm³ (0 steg)** | **0,000 Mm³ (0 steg)** |
| aggressive handlinger / LRW | 0 / 0 | 0 / 0 |
| start/stopp | 57,00 EUR (57 overganger) | 29,00 EUR (29 overganger) |
| terskelregelens treffsikkerhet | 90,7 % (34 feil) | 95,3 % (17 feil) |
| magasinnivå brukt | 26,1 % av [LRW,HRW] | 49,3 % |
| `Hnetto` gjennomløpt | 12,8 % (av 43,5 % tilgjengelig) | 29,2 % (av 46,5 %) |
| distinkte produksjonsnivå i DP-optimum | 52 | 25 |

### 5.5 Formen på gapet over fem instanser

| instans | `rho` | `R` | B2 | B3 | B4 | overløp (DP) | terskeltreff |
|---|---:|---:|---:|---:|---:|---:|---:|
| GRESSE | 0,563 | 0,325 | 0,407 % | 0,141 % | 0,0000 % | 0,000 Mm³ | 99,7 % |
| HJELLE | 0,782 | 0,071 | **5,121 %** | 6,305 % | **1,075 %** | **6,124 Mm³ (33 steg)** | 81,4 % |
| KROKNESVATN | 0,947 | 0,645 | 1,271 % | 3,665 % | 0,0017 % | 0,000 Mm³ | 95,3 % |
| TOPPSY | 1,017 | 0,681 | 1,611 % | 1,185 % | 0,0013 % | 0,000 Mm³ | 90,7 % |
| `mini_utahps_daily` | 1,820 | 0,868 | 0,285 % | — | — | — | — |
| `res_casc_A` | 1,520 | 0,868 | 0,438 % | 11,855 % | 0,0069 % | 0,093 Mm³ (4 steg) | degenerert |

**Formen, ikke bare tallene:**

1. **Gapet er ikke monotont i `rho`.** Langs 0,56 → 0,78 → 0,95 → 1,02 → 1,52 → 1,82 går B2
   0,41 → 5,12 → 1,27 → 1,61 → 0,44 → 0,29 %. Det er en pukkel med toppen ved HJELLE, ikke
   en terskel. B2 krysser 1 % et sted mellom GRESSE og KROKNESVATN og igjen mellom TOPPSY og
   `mini`, men `rho` alene forutsier ikke hvor.

2. **Gapet er heller ikke monotont i `R`.** 0,071 → 0,325 → 0,645 → 0,681 → 0,868 gir
   5,12 → 0,41 → 1,27 → 1,61 → 0,29/0,44 %. Samme pukkel, motsatt vei.

3. **Overløpshypotesen er ikke tilstrekkelig — dette er nattens viktigste korreksjon.**
   TOPPSY og KROKNESVATN har **null overløp** og likevel B2-gap på 1,61 % og 1,27 %, altså
   over 1 %-grensen. Overløp forklarte HJELLEs 5,12 %, men er **ikke nødvendig** for et gap
   over 1 %. Formuleringen fra forrige rapport må derfor svekkes.

4. **To mekanismer, ikke én.** [vurdering] Tallene skiller seg pent når B2 og B4 leses hver
   for seg:

   - **B2-gapet** følger hvor langt optimum ligger fra en ren terskelregel
     (treffsikkerhet 81,4 → 90,7 → 95,3 → 99,7 % gir gap 5,12 → 1,61 → 1,27 → 0,41 %, perfekt
     ordnet). Optimum forlater terskelstrukturen både når overløp binder (HJELLE) **og** når
     `rho ≈ 1` gjør *mengden* vann som må produseres nesten låst (TOPPSY, KROKNESVATN) — da
     tvinges produksjon fram ved uattraktive priser uten at noe søles.
   - **B4-gapet** er derimot forsvinnende overalt bortsett fra ett sted: 0,0000 / 0,0013 /
     0,0017 / 0,0069 % mot **1,075 % på HJELLE**. Den ene instansen der koordinatoppstigning
     svikter, er nøyaktig den der overløpet binder.

   **[vurdering, viktig for oppgaven]** En publisert, enkel metode ligger altså innenfor
   0,007 % av eksakt optimum på fire av fem instanser. Rommet for en ny algoritme er ikke
   stort på instansklassen som helhet — det finnes i det overløpsbindende regimet, og det er
   det regimet en eventuell algoritmisk kontribusjon må rette seg mot og rettferdiggjøres av.
   Merk at terskeltilpasningen er beskrivende, ikke forklarende: B2 *er* en terskelfamilie,
   så at B2-gapet følger terskelavviket er nesten en tautologi. Det som har forklaringskraft
   er hvorfor optimum forlater terskelstrukturen, og der peker tallene på to ulike årsaker.

5. **Forbehold [usikkert].** Fem punkter, fire av dem utsnitt med kun eget tilsig (§9.1), og
   HJELLE er både gap-toppen og det eneste punktet med bindende overløp. «Overløp bryter B4»
   hviler dermed på **én** instans. Det syntetiske rutenettet i kapittel 7 er der nettopp for
   å teste om det er `rho`, `R` eller overløp som gjør arbeidet.

---

## 6. Syntetisk korrigert variant av `res_casc_A`

*(fylles inn)*

---

## 7. Syntetisk `rho`/`R`-rutenett

*(fylles inn)*

---

## 8. Om Matheussen, Granmo & Sharma (2019)

**[målt via websøk]** Artikkelen er *Hydropower Optimization Using Deep Learning*,
Matheussen, Granmo & Sharma, IEA/AIE 2019 (Springer LNCS), og bruker et **reelt
to-magasin-system i Sør-Norge**.

**[usikkert]** Fullteksten lot seg ikke hente i denne kjøringen, så §3s parametere kunne
ikke sammenliknes mot `res_casc_A`. Det eneste som kan sies er at **strukturen** stemmer
(to magasin, luke mellom dem, ett kraftverk). Påstanden om at `res_casc_A` er en stilisert
Kvinesdal er derfor **ikke verifisert** her og må sjekkes mot papirutgaven før den brukes.

---

## 9. Forbehold

1. **Utsnitt med kun eget tilsig.** HJELLE, GRESSE, TOPPSY og KROKNESVATN er skiver av
   `utahps_daily` som bare får sitt eget lokale tilsig. I det fulle systemet mottar TOPPSY og
   KROKNESVATN også oppstrøms avløp, så `rho` her er en **nedre grense** og skivene er
   knappere enn nodene faktisk er.
2. **`make test` ikke kjørt** (gtest mangler, §4.1).
3. **Syntetiske instanser** (kapittel 6 og 7) er ikke uTAHPS og må ikke inngå i konklusjoner
   om systemet.
4. **Fase C isolerer `R` ved konstant fallhøydespenn**, ikke `R` i sin alminnelighet — se
   kapittel 7.
