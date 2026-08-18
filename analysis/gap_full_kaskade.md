# Full kaskade: `utahps_daily` uten eksakt referanse

**Kjøring:** 2026-08-04 → 2026-08-06 00:51. **Repo-commit:** `a32ded6`, upstream pinnet `029a2d5`.
**HERSS:** VERSION 3.1.03 / VERSION_DATE 20260611.
**Instans:** `analysis/instances/utahps_daily`, T=365, dt=86 400 s (verifisert via
`Dataset::getDeltaT`, ikke antatt). 4 magasin, 4 kraftstasjoner, 4 kanaler,
**1460 beslutningsvariabler**.

Merking gjennomgående: **[kilde]** verifisert i C++-kilden, **[målt]** kjørt og målt,
**[vurdering]** min tolkning, **[antakelse]**, **[usikkert]**.

---

## 0. Sammendrag

1. **Spredningen mellom åtte konvergerte B4-omstarter er 27 062 EUR = 0,0722 % av beste.**
   Under 0,1 %-grensen fastsatt før måling. [vurdering] Landskapet er velformet;
   **en metode konstruert for å unnslippe lokale optima er ikke berettiget på denne
   instansen.** Åtte omstarter mot to på HJELLE og `res_casc_A`.

2. **Begge kaskade-naboskapene ga nøyaktig null.** B5 − B4 = +11 884 EUR, hvorav
   **(a) to stasjoner i samme steg = 0,00** og **(c) oppstrøms `t` + nedstrøms `t+1` = 0,00**.
   Hele gevinsten kommer fra (b), samme stasjon i to nabosteg — tidsutjevning innenfor
   én stasjon, ikke kaskadekobling — og 98 % av den fra SVOLETJONN alene.
   Gevinsten er dessuten **mindre enn halvparten av omstartsspredningen**.

3. **Premisset om forsinket kobling var feil.** Rutingforsinkelsen er 0 steg ved daglig
   oppløsning: 77–96 % av et slipp forlater kanalen i samme steg, og noder kjøres i
   topologisk rekkefølge innenfor tidssteget. (c) måler reservoarmediert kobling, ikke
   ruting. Se §2.1.

4. **B1 og B2 kjøper skrankebrudd.** De aggressive handlingene koster dem 9 800–11 300 EUR
   over 80–87 steg; B4/B5 bruker ett steg til 1,70 EUR. B2s «bare 0,51 % under» er en
   sammenlikning mot en løsning som bryter vannbalansen 80 ganger. Se §8.2.

5. **Den leverte `actions_utahps.txt` er 29,5 % under beste** og bør ikke siteres som
   baselinje. Se §5.

6. **Arbeidshypotesen «bindende overløp bryter koordinatoppstigning» overlever ikke.**
   Overløp binder i tre av fire magasin (33,5 Mm³ over 192 steg selv i B5), og spredningen
   er likevel 0,0722 %. Se §8.3.

7. **Skive-instansene lå i feil regime.** Realisert `rho` er 49 % (TOPPSY) og 76 %
   (KROKNESVATN) høyere enn skivene viste, fordi skivene bare fikk eget tilsig. Se §8.4.

**Konsekvens for oppgaven [vurdering].** Etter sju instanser er det ikke funnet rom for et
algoritmebidrag rettet mot multimodalitet eller mot kaskadekobling — de to tingene denne
kjøringen var designet for å finne. Det som *er* funnet, er at baselinjene vinner ved å
bryte skranker simulatoren ikke håndhever. Et forsvarbart problemspesifikt bidrag ligger
derfor nærmere **reparasjonsoperatorer og korrekt håndtering av straffede skranker** enn
metaheuristikk. Se §10 for hva som ikke er utelukket.

---

## 1. Hva kjøringen skulle svare på

Seks instanser var målt fra før. Alle var ett-magasin-skiver eller små systemer der eksakt
DP var mulig, og på fire av dem lå B4 (koordinatoppstigning) 0,0000–0,0069 % fra optimum.
Bare HJELLE viste et reelt gap (1,075 %), og det hvilte på én instans.

Ingen av dem hadde kaskademekanismene: vann som passerer flere stasjoner med ulik
energiekvivalent, oppstrøms beslutninger som forårsaker nedstrøms overløp, ruting mellom
kraftverk. Utsnittsmetoden hadde systematisk fjernet nettopp det som kunne gjøre problemet
hardt.

`utahps_daily` er det eneste systemet der de mekanismene finnes. Eksakt DP er utelukket
(se §9). Kjøringen måler derfor **vanskelighet uten fasit**, og hovedresultatet er
**spredningen mellom uavhengige B4-omstarter**.

---

## 2. To premisser korrigert før kjøring

### 2.1 Rutingforsinkelsen er 0 steg, ikke τ ≥ 1

**[målt]** Impulsrespons regnet direkte fra `src/cascadedreservoirs.cpp:83–117` med
dt = 86 400 s:

| kanal | idnr | N | K | ut i steg t | t+1 | t+2 |
|---|---|---|---|---|---|---|
| VANAROSEN | 2 | 3 | 4 t | **0,8424** | 0,1487 | 0,0087 |
| GRONANI | 4 | 3 | 1 t | **0,9589** | 0,0405 | 0,0006 |
| DALSANA | 8 | 3 | 6 t | **0,7703** | 0,2101 | 0,0191 |
| HYNNEKLEIV | 11 | 2 | 4 t | **0,8403** | 0,1528 | 0,0069 |

`k_res = K·3600/N` gir 1200–7200 s mot et døgnsteg, så `exp(-dt/k_res)` underflyter til
~0 og magasinene i kanalen tømmes i praksis hvert steg.

**[kilde]** `herss.cpp:669–677` kjører noder i idnr-rekkefølge **innenfor** hvert tidssteg,
og idnr-rekkefølgen er topologisk her (0→1→2→5→6→8→9→10→11 og 3→7→8; verifisert av
`params3.assert_topological_order`). Et slipp oppstrøms i `t` når derfor nedstrøms stasjon
i **samme** steg.

**[vurdering]** Oppgaveteksten rangerte naboskap (c) — oppstrøms `t` med nedstrøms `t+τ`,
`τ` = rutingforsinkelsen — som det viktigste, med den begrunnelse at koblingen i en kaskade
er forsinket. Ved daglig oppløsning er `τ = 0`, og (c) kollapser mot (a). (c) beholdes som
`t → t+1`, men den fanger da **reservoarmediert** kobling — vann som blir liggende i
nedstrøms magasin over natten — pluss 4–21 % kanalhale. Det er ikke rutingforsinkelse, og
rapporteres ikke som det. **(a), to stasjoner i samme steg, er den ekte koblingen her.**

### 2.2 Det kaskade-bevisste terminalleddet virker her

**[kilde]** Alle fire magasin har `OUTLET_TUNNEL`, så `reservoir.cpp:1063–1073` setter
`ptr_downstream_node` til kraftstasjonen. `res_casc_A`-patologien — oppstrøms vann verdt
null fordi pekeren gikk til overløpsnoden — gjentar seg **ikke**.

Kjedeekvivalenter, summen av `LOCAL_ENERGY_EQUIVALENT` over hver stasjon vannet ennå må
passere:

| magasin | kjede | e_kjede [kWh/m³] |
|---|---|---|
| HJELLE | SVOLETJONN + SVEIGSHYL_I + EASTER | 0,11+0,11+0,11 = **0,33** |
| GRESSE | SVEIGSHYL_II + EASTER | 0,39+0,11 = **0,50** |
| TOPPSY | SVEIGSHYL_I + EASTER | 0,11+0,11 = **0,22** |
| KROKNESVATN | EASTER | **0,11** |

**[målt]** Kryssjekket mot simulatorens eget tall i den leverte outputen: aktive
sluttvolum 2,2569 / 15,7394 / 126,6400 / 199,2700 Mm³ gir 58 394,977 MWh mot filens
`tot_remaining_MWh = 58 394,966` — relativ differanse 1,9·10⁻⁷.

**[vurdering]** GRESSE-vann er verdt 4,5 ganger så mye som KROKNESVATN-vann per m³, fordi
SVEIGSHYL_II har `LOCAL_ENERGY_EQUIVALENT` 0,39 mot 0,11 for de tre andre. Det er en ekte
asymmetri i objektivet og den eneste kilden til reell kaskadestruktur i terminalleddet.

---

## 3. Instans og validering

### 3.1 Instansbygging

`analysis/instances/utahps_daily` er en arbeidskopi av `data/utahps_daily`. Alle fem
inputfiler er byte-for-byte kopier med sine opprinnelige navn, inkludert
`global_utahps_daily.txt`. Eneste genererte fil er `start_state_utahps.txt`, der kanalenes
lineærmagasin settes til stasjonærtilstand `S = k_res·Q`
(`cascadedreservoirs.cpp:41,106`) for målt middelgjennomstrømning.

**[målt]** Middelgjennomstrømning under levert `actions_utahps.txt`: VANAROSEN 3,0557,
GRONANI 0,0000, DALSANA 7,8833, HYNNEKLEIV 9,9716 m³/s. GRONANI fører ingenting fordi
GRESSE aldri går i overløp under de leverte handlingene.

**[målt, avvik fra `res_casc_A`]** Kanalinitialiseringen er **ikke** verdinøytral her.
dVF = **+1983,60 EUR** (0,0075 %), fordi plassholderne 0,001/0,002/0,003 utgjør 0,006 Mm³
mot stasjonærtilstandens 0,335 Mm³. I `res_casc_A` lå alle kanaler nedstrøms eneste
stasjon og kunne ikke påvirke V; her ligger VANAROSEN, GRONANI og DALSANA **mellom**
kraftverk. Global vannbalanse lukker til 0,000000.

### 3.2 Replikavalidering per steg

`replica3.py` er en full 12-node-replika. Validert i `validate3_replica.py` mot
**per-steg-sporene i CLI-ens nodefiler**, ikke bare mot VF — `CalcOverflow`-fallgruven fra
forrige kjøring var usynlig i VF alene.

**[målt]** Tre aksjonssett × 76 sporede felt over alle 12 noder:

| sett | VF `CalcVF` | VF replika | rel. avvik | felt som feiler | negative overløp | vannbalanse |
|---|---|---|---|---|---|---|
| levert `actions.txt` | 26 430 725,2210 | 26 430 725,2303 | 3,5·10⁻¹⁰ | 0 / 76 | 0 | 0,000000 |
| alle handlinger 0 | 8 430 520,5000 | 8 430 520,5000 | 0 | 0 / 76 | 0 | 0,000000 |
| tilfeldig, seed 42 | 22 741 123,4375 | 22 741 123,4357 | 8,0·10⁻¹¹ | 0 / 76 | 0 | −0,000000 |

Toleransen er ikke uniform, og det er ikke slurv: nodefilene skrives med `%.4f`, så
5·10⁻⁴ er gulvet for enhver størrelse. For **avledede** pengekolonner forplanter det seg —
`income` er `Power` ganger pris, og `Power` er bare skrevet til 1e-4, så oppnåelig samsvar
er 5·10⁻⁴ · pris, opptil 0,28 EUR ved instansens toppris 564,88. **[målt]** HERSS' egen
skrevne `income` avviker fra HERSS' egen skrevne `Power` ganger pris med opptil 0,025 EUR;
filen er altså allerede uenig med seg selv på det nivået. Toleransen er derfor
`5·10⁻⁴ · maks(pris, 1)` for `income` og `profit`, `5·10⁻⁴` ellers.

**[målt]** `resume_batch` — inkrementell evaluering fra det perturberte steget, som er det
som gjør B4 betalbart — er **bit-identisk** med full replay: 40 no-op-overstyringer, 80
enkeltvariabeltrekk og 15 tostegstrekk gir alle maks avvik 0,000e+00 (`test_resume.py`).

### 3.3 Determinisme

**[målt]** A → A → B → A i samme prosess:
26 430 725,220978 → 26 430 725,220978 → 22 741 123,437483 → 26 430 725,220978.
Både gjentakelse og A→B→A er **bit-identiske**. `Simulate()` lekker ikke tilstand.

### 3.4 Et sidefunn: `CalcVF` og outputfilen er uenige

**[målt]** CLI-ens skrevne `valuefunction_Euro` avviker fra `CalcVF`:

| aksjonssett | CLI skrevet | `CalcVF` | differanse |
|---|---|---|---|
| levert | 26 430 725,4180 | 26 430 725,2210 | **+0,1970** |
| alle 0 | 8 430 520,5000 | 8 430 520,5000 | 0,0000 |
| tilfeldig | 22 741 124,1560 | 22 741 123,4375 | **+0,7185** |

**[kilde]** `riversystem.cpp:533` `WriteRiverSystemData` regner om og **overskriver**
`valuefunction_Euro` på linje 576, 591 og 593, og dupliserer dermed logikken i `CalcVF`.
Dette er åpent verifikasjonspunkt 4 i CLAUDE.md §8, nå målt på `utahps_daily`.

**[vurdering]** Størrelsen er økonomisk ubetydelig (3·10⁻⁸ relativt), men konsekvensen er
metodisk: **hvilken verdi man leser avhenger av kallrekkefølgen.** Alle tall i denne
rapporten leses fra `CalcVF` direkte, aldri fra outputfilen.

---

## 4. Regimetall

**[målt]** Statiske tall for hele året. `R` = aktivt magasin / stasjonskapasitet,
`rho` = (initielt aktivt + tilsig) / stasjonskapasitet.

| magasin | aktiv Mm³ | init aktiv | eget tilsig | stasjon | kap. Mm³ | R | rho eget | rho full (øvre gr.) |
|---|---|---|---|---|---|---|---|---|
| HJELLE | 9,00 | 6,30 | 92,32 | SVOLETJONN | 126,14 | **0,071** | 0,782 | 0,782 |
| GRESSE | 61,44 | 49,15 | 57,29 | SVEIGSHYL_II | 189,22 | 0,325 | 0,563 | 0,563 |
| TOPPSY | 126,64 | 113,98 | 75,21 | SVEIGSHYL_I | 186,06 | 0,681 | 1,017 | ≤ 1,547 |
| KROKNESVATN | 199,27 | 131,50 | 161,27 | EASTER | 309,06 | 0,645 | 0,947 | ≤ 2,213 |

`rho full` er en **øvre grense**, ikke realisert tilsig: hvor mye som faktisk kommer
nedstrøms er en funksjon av politikken. De realiserte tallene står i §8.

**[vurdering]** To regimer i samme system. HJELLE har `R = 0,071` — 26 døgns lagring mot
et helt års stasjonskapasitet, altså nesten elvekraftverk. TOPPSY og KROKNESVATN har
`rho > 1` når oppstrøms avløp regnes med, altså mer vann enn stasjonene kan kjøre.
Sammenlikningen mot skive-tallene står i §8.

---

## 5. Baselinjer B0–B3

**[målt]** Alle verdier fra `CalcVF` på ekte HERSS. `|d|` er avviket mot replikaen.

| | metode | VF [EUR] | mot B2 | `|d|` HERSS−replika | fulle eval. | stegceller | s |
|---|---|---|---|---|---|---|---|
| B0 | levert `actions_utahps.txt` | 26 430 725,22 | **−29,14 %** | 0,0094 | 1 | 365 | 0,2 |
| B1 | prisgrense per stasjon | 37 249 971,45 | −0,14 % | 0,0219 | 45 260 | 16,5 M | 12 |
| B2 | prisgrense + nivå per stasjon | **37 300 419,78** | — | 0,0224 | 452 600 | 165 M | 33 |
| B3 | myopisk, kjedeekvivalent vannverdi | 36 940 103,66 | −0,97 % | 0,0287 | 5 344 000 | 5,3 M | 21 |

**[målt] B0 ligger 29 % under en enkel tunet prisgrense.** Den leverte handlingsfilen er
ikke en baselinje i noen meningsfull forstand — den kjører SVOLETJONN på fast 0,80 store
deler av året og lar TOPPSY og KROKNESVATN ende **over HRW**, der vannet er verdt null.
**[antakelse]** Filen er en demonstrasjonsfil for simulatoren, ikke et forsøk på god drift.
Dette bør avklares med Bernt før den siteres som referansepunkt noe sted.

**[målt]** B1s tunede parametre: stasjonene er på i 355 / 340 / 115 / 355 av 365 døgn, alle
på fullt nivå. B2 flytter bare SVOLETJONN til nivå 0,95 og vinner 0,14 %.

**[vurdering]** At optimal terskel ligger på «kjør nesten alltid» for tre av fire stasjoner
sier at systemet er **kapasitetsbegrenset, ikke prisbegrenset**: det er ikke nok vann til å
fylle stasjonene, så spørsmålet er ikke *om* man skal produsere, men *når* de siste
prosentene skal tas. Det er samme strukturelle situasjon som gjorde skive-instansene lette.

---

## 6. B4 — spredning mellom omstarter (hovedresultatet)

**[målt]** Åtte uavhengige omstarter, seeds 1–8, én prosess hver, kjørt parallelt på 16
kjerner med `OMP_NUM_THREADS=1`. **Ingen tidsgrense** — **alle åtte konvergerte**
(`all_converged = true`, ingen feilede omstarter) ved epsilon = 0,01 EUR på både grovraster
(21 nivå) og finpuss (201 nivå). Veggklokketid for hele settet: **16,51 t**, lik den
tregeste enkeltomstarten, som er hva parallellkjøring skal gi.

Pilotmålingen som lå til grunn for beslutningen: én omstart alene brukte 91,1 min på
grovfasen (1580 iterasjoner, konvergert) og traff et 180-minutters tak i finpussen, med
toppminne 93 MB. Ekstrapolert til åtte parallelle ga det 740 MB, altså langt under
tilgjengelig RAM, og minne var derfor aldri den bindende ressursen. Under åtte samtidige
prosesser økte tiden per omstart til 12,3–16,5 t på grunn av delt minnebåndbredde.

| seed | VF HERSS [EUR] | konvergert | grov it. | fin it. | finpuss [EUR] | veggklokke [t] |
|---|---|---|---|---|---|---|
| 2 | 37 479 891,60 | ja | 1586 | 311 | 5 680,47 | 15,39 |
| 1 | 37 474 011,46 | ja | 1580 | 354 | 4 339,09 | 15,93 |
| 4 | 37 467 576,82 | ja | 1542 | 223 | 3 923,40 | 13,09 |
| 5 | 37 464 592,51 | ja | 1651 | 267 | 4 336,22 | 14,82 |
| 7 | 37 461 977,02 | ja | 1614 | 415 | 13 641,66 | 16,51 |
| 6 | 37 458 695,10 | ja | 1438 | 280 | 4 990,77 | 14,32 |
| 8 | 37 457 356,45 | ja | 1720 | 180 | 4 057,35 | 12,31 |
| 3 | 37 452 829,79 | ja | 1519 | 330 | 9 773,91 | 15,57 |

| statistikk | verdi |
|---|---|
| min | 37 452 829,79 |
| median | 37 463 284,76 |
| gjennomsnitt | 37 464 616,34 |
| maks | 37 479 891,60 |
| standardavvik | 8 976,34 |
| **spredning (maks−min)** | **27 061,81 EUR** |
| **spredning i % av beste** | **0,0722 %** |

### Tolkning mot kriteriet fastsatt før måling

Kriteriet var: under ~0,1 % ⇒ velformet landskap; over ~1 % ⇒ lokale optima som betyr noe
økonomisk; mellom ⇒ uavklart.

**Spredningen er 0,0722 %, altså under 0,1 %-grensen.** [vurdering] Landskapet er
velformet: åtte uavhengige koordinatoppstigninger fra tilfeldige startpunkter lander
innenfor 27 kEUR av hverandre på en verdifunksjon på 37,5 MEUR. **En metode som er
konstruert for å unnslippe lokale optima er ikke berettiget på denne instansen.**

Referansepunkter: HJELLE 0,49 % (2 omstarter), `res_casc_A` 0,054 % (2 omstarter). Med
åtte omstarter i stedet for to er dette tallet vesentlig bedre understøttet enn begge.

**[vurdering] Merk hva som *ikke* følger.** Spredningen måler om lokalsøk konvergerer
til omtrent samme punkt, ikke hvor langt det punktet ligger fra optimum. Uten fasit kan
ingen av delene avgjøres her. Det som er utelukket er én bestemt type bidrag — å håndtere
multimodalitet — ikke algoritmebidrag generelt.

**[usikkert]** Finpussgevinsten varierer kraftig mellom omstarter (3 923–13 642 EUR, altså
en faktor 3,5) og korrelerer ikke med sluttverdien: seed 7 har den nest største finpussen
og havner likevel som nummer fem. Det er et selvstendig argument for at grovrasteret ikke
kunne vært brukt alene — uten finpuss ville en del av det som her måles som
landskapsstruktur i stedet vært rasterstøy.

---

## 7. B5 — parvise trekk

**[målt]** B5 startet fra B4s beste omstart (seed 2) og la til de parvise naboskapene.
**Konvergert** etter 57 iterasjoner, 1,48 t, parraster 11 nivå.

**Metodisk avvik fra `res_casc_A`, med begrunnelse.** Der kjørte B5 sine egne omstarter med
et ekte supersett av B4s trekk, og kom ut 21 EUR *dårligere* — ikke fordi parvise trekk
skader, men fordi et større trekksett tar en annen bane gjennom landskapet og kan lande i
et annet lokalt optimum. Det forvirrer nøyaktig det spørsmålet B5 finnes for å svare på.
Ved å starte B5 i B4s konvergerte punkt blir B5 ≥ B4 sant per konstruksjon, og differansen
er attribuerbar til naboskapene alene.

B5 − B4 = **+11 884,45 EUR** (+0,0317 % av B4).

| naboskap | gevinst [EUR] |
|---|---|
| **(a) to stasjoner i samme steg** | **0,00** |
| (b) samme stasjon i to nabosteg | 11 759,10 |
| **(c) oppstrøms `t` + nedstrøms `t+1`** | **0,00** |
| enkelttrekk låst opp av parvise trekk | 125,35 |

Per trekktype:

| trekk | gevinst [EUR] |
|---|---|
| `b_adj:g1` (SVOLETJONN) | 11 641,27 |
| `b_adj:g6` (SVEIGSHYL_I) | 102,71 |
| `single:g1` | 64,15 |
| `single:g6` | 59,81 |
| `b_adj:g7` (SVEIGSHYL_II) | 15,13 |
| `single:g7` | 1,38 |

### Dette er kjøringens skarpeste negative funn

**[målt] Begge kaskade-naboskapene ga nøyaktig null.** Ikke «lite», ikke «under
støygulvet» — null forbedring ble funnet i noen iterasjon, verken for to stasjoner i samme
steg (a) eller for oppstrøms/nedstrøms med ett stegs forsinkelse (c). Alle fire ekte
kaskadepar var med i kandidatsettet (`g1→g6`, `g1→g10`, `g6→g10`, `g7→g10`; `g1+g7` og
`g6+g7` er korrekt utelatt fordi SVEIGSHYL_II mates av GRESSE og går utenom TOPPSY).

Hele gevinsten kommer fra (b) — **samme stasjon i to nabosteg**, som ikke er en
kaskadekobling i det hele tatt, men tidsutjevning innenfor én stasjon. 98 % av den kommer
fra SVOLETJONN alene, stasjonen på HJELLE med `R = 0,071`, altså det minste magasinet med
26 døgns lagring. **[vurdering]** Det er nettopp der ett døgns beslutning binder det neste
hardest, og det er en enkeltnodeeffekt, ikke en systemeffekt.

**[vurdering]** Dette ble også observert på et 30-stegs utsnitt før hovedkjøringen, med
samme mønster (a = 0, c = 0, b > 0). To uavhengige kjøringer med samme resultat.

**[vurdering, viktig]** B5 − B4 = 11 884 EUR er **mindre enn halvparten av spredningen
mellom B4-omstartene** (27 062 EUR). Den parvise gevinsten er altså mindre enn variasjonen
man får ved å bytte startpunkt. Å rapportere den som en metodeforbedring uten å si dette
ville vært misvisende.

---

## 8. Diagnose

### 8.1 Metodesammenlikning og budsjett

| | metode | VF HERSS [EUR] | mot beste | fulle eval. | stegceller | veggklokke [s] |
|---|---|---|---|---|---|---|
| B0 | levert `actions_utahps.txt` | 26 430 725,22 | −29,5026 % | 1 | 365 | 0 |
| B1 | prisgrense per stasjon | 37 249 971,45 | −0,6450 % | 1 185 | 432 525 | 4 |
| B2 | prisgrense + nivå per stasjon | 37 300 419,78 | −0,5104 % | 29 601 | 10 804 365 | 12 |
| B3 | myopisk, kjedeekvivalent vannverdi | 36 940 103,66 | −1,4714 % | 5 343 966 | 5 344 330 | 4 |
| B4 | koordinatoppstigning, 8 omstarter | 37 479 891,60 | −0,0317 % | 1 083 022 586 | 198 201 352 460 | 424 560 |
| B5 | B4 + parvise trekk | **37 491 776,05** | 0,0000 % | 52 826 574 | 9 677 512 976 | 5 331 |

**Kun veggklokketid er sammenlignbar på tvers av metodefamilier** — en batchet sveip og en
skalar løkke koster svært ulikt per «evaluering». B4s veggklokketid er **summen over åtte
omstarter**; per omstart står i §6 (12,31–16,51 t), og de åtte kjørte parallelt.

Avviket mellom HERSS og replikaen er ≤ 0,029 EUR for samtlige metoder.

**[vurdering]** Prisen for de siste 0,51 % over B2 er fire størrelsesordener flere
evalueringer og fem størrelsesordener mer veggklokketid. Det er en reell avveining som må
stå i en oppgave, ikke skjules bak «B4 vinner».

### 8.2 Feasibility — og en fallgruve i baselinjene

**[målt]** Nesten alle skranker i HERSS er straffet, ikke håndhevet, så en metode kan vinne
ved å kjøpe brudd billig (CLAUDE.md §11).

| metode | aggressive [EUR / steg] | LRW-straff [EUR / steg] | start/stopp [EUR] | steg over HRW |
|---|---|---|---|---|
| B0 | 0,0 / 0 | 0,0 / 0 | 22,0 | 656 |
| B1 | **11 274,3 / 87** | 0,0 / 0 | 95,0 | 214 |
| B2 | **9 801,2 / 80** | 0,0 / 0 | 89,0 | 212 |
| B3 | 0,0 / 0 | 0,0 / 0 | 195,0 | 408 |
| B4 | 1,7 / 1 | 0,0 / 0 | 150,0 | 193 |
| B5 | 1,7 / 1 | 0,0 / 0 | 148,0 | 192 |

**[målt] B1 og B2 kjøper aggressive handlinger i 80–87 av 365 steg**, til 9 800–11 300 EUR.
B4 og B5 gjør det i **ett** steg til 1,70 EUR. Terskelbaselinjene ber altså rutinemessig om
mer vann enn magasinet har, og betaler straffen fordi den er billigere enn å la være.

**[vurdering]** Dette endrer hvordan B2-tallet skal leses. B2 ligger 0,51 % under B5, men
gjør det med 80 skrankebrudd. Straffen på 1000 EUR/Mm³ overtrukket er åpenbart ikke stor
nok til å avskrekke — den er, som kildekommentaren i `powerstation.cpp:786` sier, ment å
bryte platåer i verdifunksjonen, ikke å håndheve. **En reparasjonsoperator som klipper
handlinger til tilgjengelig volum ville gjort B1/B2 til ærlige baselinjer**, og det er et
konkret, forsvarbart problemspesifikt bidrag. Uten det er «B2 er nesten like god» en
sammenlikning mellom en gyldig og en ugyldig løsning.

**LRW-straffen er null overalt.** Det bekrefter på et fullt kaskadesystem det som ble
funnet på ett-magasin-skivene: LRW-grensen er strukturelt uoppnåelig, fordi
`up_res_Mm3 = maks(0, res − filling_at_LRW)` gjør at produksjon aldri kan trekke magasinet
under LRW i utgangspunktet.

### 8.3 Overløp

**[målt]** Overløpsvolum [Mm³] / antall steg med overløp:

| magasin | B0 | B1 | B2 | B3 | B4 | B5 |
|---|---|---|---|---|---|---|
| HJELLE | 31,3 / 138 | 5,8 / 30 | 6,5 / 32 | 26,2 / 88 | 6,0 / 35 | 6,0 / 35 |
| GRESSE | 0,0 / 0 | 0,0 / 0 | 0,0 / 0 | 0,0 / 0 | 0,0 / 0 | 0,0 / 0 |
| TOPPSY | 68,8 / 245 | 0,8 / 33 | 0,6 / 29 | 31,5 / 168 | 3,0 / 31 | 3,0 / 30 |
| KROKNESVATN | 166,5 / 273 | 28,0 / 151 | 27,9 / 151 | 32,5 / 152 | 24,5 / 127 | 24,5 / 127 |
| **sum** | **266,5 / 656** | **34,6 / 214** | **35,0 / 212** | **90,1 / 408** | **33,5 / 193** | **33,5 / 192** |

**[målt] Overløpet binder, men lar seg ikke fjerne.** Selv B5 søler 33,5 Mm³ over 192 steg,
og 73 % av det er KROKNESVATN. **[vurdering]** Det er det magasinet med `rho_realisert =
1,668` — det mottar 222,8 Mm³ fra oppstrøms i tillegg til sitt eget tilsig på 161,3, og
EASTER kan ikke kjøre alt. Overløpet der er ikke en beslutningsfeil, det er en
kapasitetsgrense. GRESSE går aldri i overløp under noen metode.

**[vurdering]** Arbeidshypotesen var at bindende overløp er det som gjør problemet hardt —
det var forklaringen på HJELLEs 1,075 % B4-gap. Her binder overløpet i tre av fire magasin,
og spredningen er likevel 0,0722 %. **Hypotesen «overløp bryter koordinatoppstigning»
overlever ikke denne instansen** i den formen. Det som skiller HJELLE-skiven er ikke at
overløp forekommer, men [antakelse] at overløpet der var *styrbart* — en beslutning kunne
unngå det — mens KROKNESVATNs overløp er uunngåelig gitt tilsiget.

### 8.4 Regimetall med fullt tilsig

**[målt]** Realisert under B4, mot de statiske skive-tallene:

| magasin | R | rho eget | rho realisert | oppstrøms mottatt [Mm³] | differanse |
|---|---|---|---|---|---|
| HJELLE | 0,071 | 0,782 | 0,782 | 0,0 | 0,0 % |
| GRESSE | 0,325 | 0,563 | 0,563 | 0,0 | 0,0 % |
| TOPPSY | 0,681 | 1,017 | **1,516** | 92,9 | **+49,1 %** |
| KROKNESVATN | 0,645 | 0,947 | **1,668** | 222,8 | **+76,1 %** |

**[målt]** Forbeholdet i `gap_multiinstans` §9.1 — at skivene bare fikk eget tilsig og at
`rho` derfor var en nedre grense — er nå kvantifisert: **skivene undervurderte `rho` med 49
og 76 % for TOPPSY og KROKNESVATN.** De to skive-instansene lå altså i et helt annet regime
enn de samme nodene gjør i systemet. HJELLE og GRESSE er upåvirket, siden de ligger øverst.

### 8.5 Drift og kobling

**[målt]** Antall distinkte handlingsnivåer / antall produserende steg:

| stasjon | B2 | B4 | B5 |
|---|---|---|---|
| SVOLETJONN | 2 / 280 | 100 / 289 | 91 / 288 |
| SVEIGSHYL_I | 2 / 340 | 40 / 330 | 42 / 330 |
| SVEIGSHYL_II | 2 / 115 | 23 / 142 | 25 / 142 |
| EASTER | 2 / 355 | 9 / 357 | 9 / 357 |

**[vurdering]** Optimum er **ikke** en terskelregel. B4 bruker 100 distinkte nivåer på
SVOLETJONN mot B2s to, og bare 9 på EASTER. Graderingen konsentreres altså der magasinet er
minst (`R = 0,071`) og forsvinner der det er stort. Det er den samme
enkeltnode-mekanismen som forklarer hele B5-gevinsten i §7, sett fra en annen vinkel.

**[målt]** Korrelasjon mellom stasjonenes produksjonsserier:

| stasjonspar | B0 | B2 | B4 | B5 |
|---|---|---|---|---|
| SVOLETJONN ~ SVEIGSHYL_I | 0,668 | 0,137 | 0,509 | 0,508 |
| SVOLETJONN ~ SVEIGSHYL_II | 0,670 | 0,260 | 0,421 | 0,427 |
| SVOLETJONN ~ EASTER | 0,662 | 0,079 | 0,200 | 0,198 |
| SVEIGSHYL_I ~ SVEIGSHYL_II | 0,999 | 0,206 | 0,356 | 0,357 |
| SVEIGSHYL_I ~ EASTER | 0,999 | 0,606 | 0,444 | 0,444 |
| SVEIGSHYL_II ~ EASTER | 0,997 | −0,005 | −0,005 | −0,005 |

**[vurdering]** Stasjonene er moderat koblet i praksis under B4 (0,20–0,51), altså mer enn
under en ren terskelregel (B2: 0,08–0,61, men ustrukturert) og langt mindre enn under B0,
der lockstep-kjøringen gir 0,997–0,999. Paret SVEIGSHYL_II ~ EASTER er **ukorrelert**
(−0,005) i alle optimerte løsninger, til tross for at de er et ekte oppstrøms/nedstrøms-par.
Det er konsistent med at (c) ga null i §7.

---

## 9. Ingen DP, ingen MILP-grense

**Ingen DP.** Tilstandsrommet er 4 magasinvolum + 11 kanalinterne lineærmagasin (3+3+3+2)
+ 4 commitment-tilstander ≈ **19 dimensjoner**. Eksakt DP er ikke dyrt, det er umulig.
Ikke forsøkt.

**Ingen MILP-grense.** `.venv` har kun `cppyy` og `numpy`; en LP/MILP-grense krever ny
avhengighet, og oppgaveteksten rangerer den sist. **Konsekvens: alle gap i denne rapporten
er differanser mellom metoder. Ingenting er oppgitt som «% fra optimum».**

---

## 10. Forbehold

1. **Ingen fasit.** Uten DP eller en gyldig MILP-grense er *ingen* tall her et gap fra
   optimum. Alle prosenter er differanser mellom metoder. At åtte omstarter lander innenfor
   0,0722 % av hverandre sier at de finner **samme** punkt, ikke at punktet er optimalt —
   systematisk skjevhet felles for alle åtte er ikke målbar her.

2. **Én instans, ett tilsigs- og prisår.** Alt hviler på `utahps_daily` med prisserien fra
   1. september 2022 og ett års tilsig. Konklusjonene om landskapsstruktur er ikke testet
   mot et annet vindu, en annen prisserie eller et annet startnivå.

3. **B5s null-resultat gjelder det kandidatsettet som ble søkt.** Parrasteret er 11 nivå
   (121 par per steg og par), og (c) ble kjørt kun som `t → t+1`. Et grovere raster kan
   overse en forbedring som krever to presise verdier samtidig. **[usikkert]** At (a) og (c)
   ga *nøyaktig* null, ikke bare lite, er sterkt, men det utelukker ikke en kobling som
   krever tre variabler eller et større tidsvindu.

4. **`epsilon` = 0,01 EUR er absolutt, ikke relativ.** Samme verdi som på HJELLE, der VF var
   ~1,5 MEUR mot 37,5 MEUR her. Relativt er terskelen dermed 25 × strammere på denne
   instansen. Beholdt for sammenliknbarhet, men det betyr at finpussen her jaget mindre
   økonomisk meningsfulle forbedringer enn på skivene.

5. **Kanalene er verdinøytrale i objektivet, men ikke i vannbalansen.** `channel.cpp:127`
   setter kanalenes `remaining_active_Mm3` til null, så vann som står i en kanal ved
   horisontslutt er verdt null uansett hvor mange stasjoner det har igjen. Det er en
   modellskjevhet i HERSS, ikke i denne kjøringen, men den favoriserer politikker som tømmer
   kanalene mot slutten. Effekten er ikke kvantifisert.

6. **Terminalleddet og produksjonen bruker inkonsistente omregninger.**
   `LOCAL_ENERGY_EQUIVALENT` er en konstant fra topologifilen, mens produksjonen i horisonten
   er fallhøydeavhengig (CLAUDE.md §7). Terminalverdien er 19,2 % av VF i B4/B5, så
   skjevheten er ikke marginal. Uendret fra tidligere kjøringer, og fortsatt ikke
   kvantifisert.

7. **`make test` er ikke kjørt** (gtest mangler på maskinen), som i forrige kjøring.
   Replikaen er i stedet validert direkte mot simulatoren per steg, §3.2.

8. **`CalcVF` og outputfilen er uenige** (§3.4). Alle tall her er lest fra `CalcVF`. Enhver
   sammenlikning mot tall lest fra `riversystem_*_output.txt` — inkludert eldre notater i
   dette repoet — må sjekke hvilken av de to som ble brukt.

9. **Hva som *ikke* er utelukket [vurdering].** Kjøringen utelukker multimodalitetsbidrag og
   parvis kaskadekobling på denne instansklassen. Den sier ingenting om: rullende horisont
   med prognosefeil, stokastisk tilsig, flere generatorer per stasjon (ikke implementert
   oppstrøms, CLAUDE.md §9), timesoppløsning der `τ ≥ 1` faktisk gjelder, eller
   reparasjonsbaserte bidrag rettet mot de straffede skrankene i §8.2. Det siste er det
   eneste av dem som er direkte støttet av tall fra denne kjøringen.
