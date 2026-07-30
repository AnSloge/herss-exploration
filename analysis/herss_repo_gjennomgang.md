# HERSS — full gjennomgang av repositoriet, modellen og datasettene

**Formål:** vurdere om HERSS kan brukes som simulator/evalueringsmotor i en masteroppgave i
optimering / Operations Research, og gi nok grunnlag til å diskutere dette med en erfaren hydrolog.

**Versjon som er gjennomgått:** HERSS `VERSION 3.1.03`, `VERSION_DATE 20260611`
(`src/herss.h:49-50`), upstream commit `029a2d5`.

**Arbeidsmåte:** hele repoet er lest read-only. Ingen filer er endret, ingen simuleringer er kjørt i
denne gjennomgangen. Målte tall er hentet fra en tidligere kjøring dokumentert i
`analysis/herss_benchmark_report.md` (samme versjon og commit) og er merket som sådan.

**Merkelapper brukt i hele rapporten:**

| Merke | Betydning |
|---|---|
| **[kilde]** | Lest direkte i kildekode eller manual. Filsti og linjenummer oppgitt. |
| **[målt]** | Målt i tidligere kjøring, se `analysis/herss_benchmark_report.md`. Ikke målt på nytt nå. |
| **[vurdering]** | Min faglige vurdering. Kan diskuteres. |
| **[antakelse]** | Antakelse jeg gjør fordi repoet ikke svarer entydig. |
| **[usikkert]** | Repoet gir ikke svar. Må avklares. |

---

# 1. Kort oppsummering

## Hva HERSS er

HERSS (Hydraulic Economic River System Simulator) er en **deterministisk simulator** for et regulert
vassdrag med vannkraft. Du gir den:

- en **topologi** (hvilke magasin, kraftstasjoner og elvestrekninger som finnes, og hvordan de henger
  sammen),
- **tidsserier** for tilsig og kraftpris,
- en **starttilstand** (magasinfyllinger, vann under transport i elvene),
- og en **handlingsplan** (`actions`): hvor mye hver generator og hver magasinluke skal kjøre i hvert
  tidssteg.

Den simulerer vassdraget tidssteg for tidssteg og returnerer ett tall: **verdifunksjonen `V`** — sum
av inntekter minus kostnader gjennom horisonten, pluss en anslått verdi av vannet som står igjen i
magasinene ved slutten.

Formelt: HERSS er en funksjon

```
V = f(a)        der a = handlingssekvens, V ∈ ℝ
```

med alt annet (topologi, pris, tilsig, starttilstand) holdt fast. Det er nøyaktig formen et
optimeringsproblem trenger for å bruke noe som **evalueringsorakel**.

## Hva HERSS *ikke* er

- **Ikke en optimeringsmodell.** Den inneholder ingen løser, ingen søkealgoritme, ingen
  vannverdiberegning som styrer driften. Den evaluerer en gitt plan — den finner ikke en god plan.
  (Det finnes én funksjon `CalcWaterValue_atEndofStp` som numerisk deriverer verdifunksjonen mot
  tilsig, men den er begrenset til **ett** magasin og avbryter med feil ellers, `herss.cpp:597-599`
  **[kilde]**.)
- **Ikke en hydrologisk modell.** Den regner ikke avrenning fra nedbør. Tilsig er ren input.
- **Ikke en stokastisk modell.** Én prisserie, ett tilsigsforløp, ingen scenarier, ingen usikkerhet.
- **Ikke en modell med harde begrensninger.** Nesten alle «begrensninger» er implementert som
  straffekostnader eller automatisk klipping, ikke som forbud. Dette er avgjørende for
  optimeringsarbeid og behandles i kapittel 9.

## Hvorfor det kan være relevant for optimering

1. **Ren orakelform.** Handlingssekvens inn, ett skalartall ut.
2. **Deterministisk og resettbar.** Gjentatt `Simulate()` med samme input gir bit-identisk `V`, og
   A→B→A gjenskaper A eksakt **[målt]**. Uten dette ville ingenting nedstrøms være gyldig.
3. **Raskt nok.** ~16 000 evalueringer/sekund på det minste instansen, ~21/sekund på hele
   time-oppløste året, i en debug-kompilert build uten filskriving **[målt]**.
4. **Kallbar fra Python** via `cppyy` uten å skrive bindingskode.
5. **Ikke-lineariteter som faktisk biter:** fallhøydeavhengig produksjon (13–47 % variasjon over
   magasinets reguleringsområde **[målt]**), ikke-konkave turbinkurver, kvadratisk falltap,
   transportforsinkelse i elvene, og en hard diskontinuitet ved «aggressive» handlinger.

Men — og dette er poenget i kapittel 11 — at simulatoren fungerer betyr ikke automatisk at det finnes
et masterbidrag. De to spørsmålene må holdes fra hverandre.

---

# 2. Repositoriets struktur

```
herss/
├── README.md            Kort prosjektbeskrivelse. Peker på manualen.
├── LICENSE.md           MIT.
├── .gitignore           Se advarselen nedenfor.
├── doc/
│   ├── herss.pdf        Brukermanual (kompilert).
│   ├── herss.tex        LaTeX-kilden til manualen (1921 linjer). Lettest å lese/søke i.
│   ├── herss30.tex      Eldre variant.
│   └── figures/         Figurer til manualen.
├── src/                 All C++-kildekode. ~7600 linjer.
│   ├── Makefile         Bygger herss.exe og herss.so. Har også "make test".
│   ├── herss.h          Sentral header: alle klasser, konstanter, VERSION. 957 linjer.
│   ├── main.cpp         Kommandolinjeprogrammet. Viser hele kjøresekvensen på 50 linjer.
│   ├── globalconfig.cpp Leser global.txt, teller noder og tidssteg.
│   ├── topoparser.cpp   Laster topologifilen inn i minnet som linjer.
│   ├── dataset.cpp      Leser pris-, tilsigs- og handlingsfiler. Utleder Δt.
│   ├── herss.cpp        Herss-klassen: simuleringsløkken, Set*/Get*-API, vannbalanse.
│   ├── riversystem.cpp  Verdifunksjonen (CalcVF) og all aggregert output.
│   ├── node.cpp         Basisklassen Node.
│   ├── reservoir.cpp    Magasin. Største enkeltfil (1253 linjer).
│   ├── powerstation.cpp Kraftstasjon med generatorer.
│   ├── channel.cpp      Elvestrekning.
│   ├── cascadedreservoirs.cpp  Rutingmodellen (kaskade av lineære reservoar).
│   ├── arraycurve.cpp   Rask stykkevis-lineær kurveoppslag.
│   ├── qmin.cpp, line.cpp, xtime.cpp, scenario.cpp, logger.cpp  Hjelpeklasser.
│   └── routing.cpp      Ikke i Makefile — død kode.
├── src_tests/           Google Test-suite, 11 filer, ~95-100 tester. Egen README.txt.
│   └── utahps_test/     Eget lite datasett testene kjører mot.
├── py_src/
│   └── pyherss.py       Eneste Python-eksempel. Demonstrerer hele orakel-løkken.
├── data/                12 datasett. Se kapittel 7.
├── plots/               GMT-baserte bash-skript for plotting. Ikke del av modellen.
└── analysis/            (Ikke upstream — lokalt tillegg.) Tidligere målerapport.
```

## Hvordan delene henger sammen

```
   global.txt
       │
       ├─► GlobalConfig::readGlobalFile()      globalconfig.cpp:321
       │      leser filnavn og flagg
       │
       ├─► GlobalConfig::Diagnose()            globalconfig.cpp:169
       │      laster topologifil, teller noder/typer/generatorer/luker,
       │      leser kolonneoverskrifter i actions- og tilsigsfil
       │
       └─► GlobalConfig::checkNrSteps()        globalconfig.cpp:67
              teller datarader i prisfilen  ⇒  T (antall tidssteg)
                    │
                    ▼
              Dataset(gc) + readAllData()      dataset.cpp:139
                 pris → tilsig → actions → utled Δt per tidssteg
                    │
                    ▼
              Herss(gc) + prepaireSimulation(data)
                 bygger Riversystem, alloker Node-objekter,
                 les topologiparametre per node, les starttilstand,
                 sett pekere mellom noder, map action-kolonner til generatorer
                    │
                    ▼
              herss.Simulate()                 herss.cpp:640
                 for t = 0..T-1:
                     for n = 0..N-1:  nodes[n]->Simulate(t)
                    │
                    ▼
              rs->CalcVF(restprice)            riversystem.cpp:406   ⇒  V
                    │
                    ▼
              WriteRiverSystemData / WriteReservoirData / WriteStateFile
              (+ WriteNodeOutput hvis WRITE_NODEFILES 1)
```

**Nøkkelobservasjon [kilde]:** `Simulate()` skriver **ingen** filer. Filskriving er separate kall
(`herss.cpp:355`, `herss.cpp:755`, `riversystem.cpp:533`). En optimeringsløkke kan derfor kjøre helt
uten disk-I/O. Det er en forutsetning for ytelse — se kapittel 8.

## Byggesystemet

`src/Makefile` definerer to mål:

- `herss.exe` — kommandolinjeprogrammet
- `herss.so` — delt bibliotek, som er det Python laster

**Merknad om kompileringsflagg [kilde]:** `CFLAGS` settes tre ganger i Makefile. Den **siste**
tilordningen vinner, og den er `-Wall -g -pedantic -fPIC` — altså debug-build uten `-O3` og uten
`-march=native`. Linjene med `-O3` er overskrevet. Dette er sannsynligvis utilsiktet, men i praksis
betyr det at alle ytelsestall er konservative; en optimalisert build vil være vesentlig raskere.
Makefile ligger under `src/` og skal ikke endres uten avklaring.

`make test` krever gtest-kildetreet i `/usr/src/gtest` (`Makefile:28,95-99`). Det finnes ikke på denne
maskinen, så testsuiten er **ikke kjørt** **[kilde]**. Installer `libgtest-dev` for å kjøre den.

## Reproduserbarhetsfelle i `.gitignore` — viktig

`.gitignore` linje 26 er `data/*`. Likevel er **173 filer under `data/` git-sporet**, fordi de ble
lagt til før regelen kom **[kilde, verifisert med `git ls-files data/ | wc -l`]**. Konsekvensene:

1. Eksisterende datasett *er* versjonskontrollert.
2. **Ethvert nytt datasett eller generert instans som legges under `data/` blir stille usporet.**
3. Outputfilene under `data/*/output/` er sporet, så **hver eneste simuleringskjøring skitner
   arbeidstreet**. `git status` viser allerede seks endrede outputfiler.

**[vurdering]** For en masteroppgave er dette en direkte trussel mot reproduserbarhet. Alle genererte
instanser og alle eksperimentresultater bør ligge **utenfor** `data/`, i en eksplisitt konfigurert
katalog.

---

# 3. Hvordan HERSS fungerer på høyt nivå

## Sentrale begreper

| Begrep | Betydning i HERSS |
|---|---|
| **Node** | Én komponent i vassdraget. Har et heltalls-ID (`IDNR`) og én av tre typer. |
| **Reservoir** | Magasin. Lagrer vann. Eneste nodetype med lagring som teller økonomisk. |
| **Power station** | Kraftstasjon. Lagrer ikke vann — alt inn i et tidssteg går ut samme tidssteg. |
| **Channel** | Elvestrekning. Forsinker og demper vannføringen. Lagrer vann, men uten økonomisk verdi. |
| **Topologi** | Den rettede asykliske grafen av noder. Bestemmer også regnerekkefølgen. |
| **State (tilstand)** | Magasinvolum, vann i elvestrekningenes lineærreservoar. |
| **Action** | Beslutningsvariabel `a ∈ [0,1]`. Én per generator, én per aktiv magasinluke, per tidssteg. |
| **Inflow (tilsig)** | Eksogen naturlig vanntilførsel til magasin [m³/s]. |
| **Price (pris)** | Eksogen kraftpris [valuta/MWh]. Én felles serie for hele systemet. |
| **Reservoir filling** | `fr = (V − V_LRW) / (V_HRW − V_LRW)`. 0 = tomt reguleringsmagasin, 1 = fullt. |
| **Head (fallhøyde)** | Høydeforskjell mellom vannspeil og turbin. Bestemmer hvor mye energi hver m³ gir. |
| **Discharge (slukeevne)** | Vannføring `Q = a · Q_max` [m³/s]. |
| **Production** | Produsert energi i tidssteget [MWh]. |
| **Profit** | Inntekt minus kostnader i simuleringsperioden. |
| **Remaining water value** | Verdien av vann igjen i magasinene ved horisontens slutt. |
| **Value function `V`** | Profit + remaining water value. **Målfunksjonen.** |

## Simuleringsflyten, steg for steg

### 1. Konfigurasjonsfiler leses

`main.cpp:76` leser `global.txt`. Det er den eneste filen som gis på kommandolinjen. Den peker på alle
andre filer.

### 2. Topologien bygges

`GlobalConfig::Diagnose()` (`globalconfig.cpp:169`) laster topologifilen inn i minnet og teller
`NODE`-linjer per type. Det gir `nr_nodes`, `nr_reservoirs`, `nr_pstations`, `nr_channels`. Den teller
også `NR_GENERATORS` og aktive `OUTLET_HATCH` for å vite hvor mange action-kolonner som *skal* finnes.

`Riversystem`-konstruktøren (`riversystem.cpp:18`) allokerer ett objekt per nodetype og setter opp
`nodes[]`-arrayen slik at `nodes[n]` peker på riktig objekt for node-ID `n`.

`Herss::prepaireSimulation` (`herss.cpp:115`) lar deretter hver node lese sine egne parametre fra
topologifilen, og `SetPointers()` (`herss.cpp:314`) kobler nedstrømspekere.

**Kritisk detalj [kilde]:** simuleringen kjører nodene i **stigende ID-rekkefølge**
(`herss.cpp:666-676`). Manualen sier eksplisitt at HERSS **ikke** sorterer eller validerer topologisk
rekkefølge — brukeren må selv nummerere oppstrøms noder lavere enn nedstrøms noder. Gjør du det feil,
kommer bidraget ett tidssteg for sent, uten feilmelding.

### 3. Tidsserier lastes

`Dataset::readAllData()` (`dataset.cpp:139`) leser pris, tilsig og actions i den rekkefølgen, og
kaller til slutt `multi_temporal_resolution()`.

**Antall tidssteg `T` bestemmes utelukkende av antall datarader i prisfilen** (`globalconfig.cpp:67`).
Tilsigs- og handlingsfilene må ha nøyaktig samme antall rader og identiske tidsstempler; avvik gir
feil og programmet avslutter.

**Δt utledes automatisk** fra differansen mellom påfølgende tidsstempler (`dataset.cpp:82-101`). Siste
tidssteg får samme Δt som nest siste. `DT` og `DT_LAST` i `global.txt` er deprecated siden mai 2026.

### 4. Initialtilstand settes

`ReadStateFile` per node. Magasin får en fyllingsfraksjon `fr`, kraftstasjon får siste produksjon
[MWh], elvestrekning får volum i hvert lineærreservoar.

### 5. Hvert tidssteg simuleres

```
for t = 0 .. T-1:
    Δt ← getDeltaT(t)
    for n = 0 .. N-1:
        nodes[n].S->dt ← Δt
        nodes[n].Simulate(t)
```

Hver node leser `up_inflow[t]` som oppstrømsnodene allerede har skrevet, regner sin egen utstrømning,
og legger den til nedstrømsnodens `up_inflow[t]`.

### 6. Hvordan vann flyttes mellom noder

Et magasin har inntil fire utløp, som evalueres i **fast rekkefølge** (`reservoir.cpp:427-640`):

```
        tilsig + oppstrøms
                ▼
        ┌───────────────┐
        │   MAGASIN     │
        └───────────────┘
           │  │   │   │
    1. tunnel │   │   └── 4. overløp   (alltid aktivt)
       (til   │   └────── 3. auto-Qmin (ufullstendig implementert)
    kraftstasj.)
              └────────── 2. luke (hatch)
```

Rekkefølgen er ikke likegyldig: tunnelen får «førsterett» på vannet, og magasinnivået oppdateres etter
hvert uttak. Overløpet regnes til slutt, på det som er igjen.

### 7. Kraftproduksjon og kostnader

Kraftstasjonen får vannet gjennom tunnelen, sammen med magasinets vannspeil ved **start og slutt** av
tidssteget. Se kapittel 4 for detaljene.

### 8. Output og verdifunksjon

Etter siste tidssteg akkumulerer `Simulate()` gjenværende vann nedover i grafen
(`herss.cpp:685-694`), og `CalcVF()` (`riversystem.cpp:406`) regner ut `V`.

---

# 4. Modellens komponenter

## 4.1 Reservoir (magasin)

### Tilstand

En enkelt skalar per magasin: **lagret volum `res_Mm3`**. Vannspeilet `res_masl` og fyllingsfraksjonen
`res_fr` er avledet fra den.

To måter å konvertere mellom volum og vannspeil:

| Metode | Nøkkelord | Beskrivelse |
|---|---|---|
| Målt kurve | `RESERVOIR_CURVE n` + n punkter `[masl, Mm³]` | Stykkevis lineær interpolasjon. Mer nøyaktig, tregere. |
| Parametrisk geometri | `RESERVOIR_GEOMETRY` + `WIDTH_M`, `LENGTH_M`, `THETA`, `BOTTOM_MASL` | Trapesformet basseng. `V(z) = h·(s + W)·L / 10⁶` der `s = tan((90−θ)π/180)`. Lineær og rask. |

De to er gjensidig utelukkende; begge samtidig gir feil (`reservoir.cpp:1094-1097`) **[kilde]**.

### Input

- Lokalt tilsig `S->inflow[t]` fra tilsigsfilen [m³/s]
- Oppstrøms tilsig `S->up_inflow[t]` fra oppstrømsnoder [m³/s]

### Utløp

**Tunnel (`OUTLET_TUNNEL <idnr>`)** — hovedutløpet, går til en kraftstasjon. Magasinet styrer **ikke**
vannføringen selv; den bestemmes av kraftstasjonens action. Magasinet gir kraftstasjonen to ting
(`reservoir.cpp:498-509`):

- vannspeilet, **begrenset oppad til HRW** (`reservoir.cpp:502`) — det skal aldri lønne seg å flomme
  for å få høyere trykk
- `up_res_Mm3` = tilgjengelig volum, definert som `max(0, res_Mm3 − filling_at_lrw_Mm3)`
  (`reservoir.cpp:509`) — altså **kun vann over LRW er brukbart for produksjon**

**Luke (`OUTLET_HATCH <idnr> <Qmin> <Qmax> <hatch_masl>`)** — en styrbar luke, typisk til en
elvestrekning. Dette er den **andre** typen beslutningsvariabel (`reservoir.cpp:564`):

```
Q_hatch = Qmin + a · (Qmax − Qmin)
```

Merk: ved `a = 0` slippes fortsatt `Qmin`. Luken virker bare når `res_masl > hatch_masl`, og
vannføringen klippes mot tilgjengelig volum over lukens terskelnivå.

**Auto-Qmin (`OUTLET_AUTO_QMIN`)** — sesongstyrt minstevannføring uavhengig av actions.
**Ufullstendig implementert** — se kapittel 10.

**Overløp (`OVERFLOW_CURVE` eller `SPILLWAY`)** — alltid aktivt. Tre varianter:

| Variant | Formel | Kilde |
|---|---|---|
| `OVERFLOW_CURVE` | Stykkevis lineær `masl → m³/s`. Klippes så magasinet ikke dreneres under HRW. | `reservoir.cpp:180-222` |
| `SPILLWAY C L level` | Overløpsformel `Q = C · L · H^{3/2}`, `H = res_masl − crest`. Klippes mot volum over terskel. | `reservoir.cpp:239` |
| `FAST_OVERFLOW TRUE` | Overstyrer begge: `Q_overflow = max(V − V_HRW, 0)`. Raskt og numerisk stabilt ved store Δt. | `reservoir.cpp:172-178` |

`OVERFLOW_CURVE` og `SPILLWAY` er gjensidig utelukkende.

### Kostnader

Kun **én** kostnad er faktisk aktiv i magasinnoder (`reservoir.cpp:648-653`):

```
if res_masl < LRW:
    cost_lrw = RES_PENALTY · (Δt/3600) · (LRW − res_masl)
```

Straffen er proporsjonal med både brudddybde og tidsstegets lengde. Merk at den er lineær i **meter**,
ikke i volum.

`FLOODLEVEL_PENALTY` leses fra topologifilen (`reservoir.cpp:789-790`) men **brukes aldri i
simuleringen** — variabelen `floodlevel_penalty` forekommer kun i deklarasjon, initialisering og
parsing (`herss.h:605-606`, `reservoir.cpp:75,790`), aldri i en beregning **[kilde, verifisert med
grep over hele `src/`]**. Se kapittel 10.

### Actions som påvirker magasinet

Kun luke-action. Tunnelvannføringen bestemmes av kraftstasjonen nedstrøms.

### Betydning for optimering **[vurdering]**

- Magasinvolum er den **eneste** tilstandsvariabelen som kobler tidsstegene økonomisk. Det er kjernen
  i tidskoblingen.
- Verdifunksjonen er **ikke-deriverbar ved HRW**: vann over HRW er verdt null (se kapittel 9), og
  overløpet slår inn. En knekk, ikke et hopp.
- LRW-straffen gir en myk nedre skranke med gradient — den er lettere å håndtere i søk enn
  aggressive-action-klippet.
- **Vann under LRW er dødt** for produksjon. Det gir en effektiv nedre skranke på uttak selv uten
  straff.

## 4.2 Power station (kraftstasjon)

### Hvordan den mottar vann

Utelukkende gjennom tunnelen fra ett oppstrøms magasin. Kraftstasjonen har ingen lagring:
`remaining_Mm3 = 0` alltid (`powerstation.cpp:294`), og koden sjekker at inn = ut hvert tidssteg og
avslutter ved avvik over 0,001 m³/s (`powerstation.cpp:297-305`).

### Fra action til vannføring

Per generator `g` (`powerstation.cpp:132`):

```
Q_g = a_g · GENERATOR_MAX_DISCHARGE_g
Q_total = Σ_g Q_g
```

### Fallhøyde og virkningsgrad

```
H_brutto = (masl_start + masl_slutt)/2 − POWSTAT_MASL        powerstation.cpp:167
ΔH       = HEADLOSSCOEF · Q²                                 powerstation.cpp:174 / 209
H_netto  = H_brutto − ΔH
P        = η_turbin(Q) · η_generator · ρ g · H_netto · Q      powerstation.cpp:192 / 226
           (kode: P[W] = η · 1000 · 9.80665 · H_netto · Q, deretter /10⁶ → MW,
            deretter · STATIC_GENERATOR_EFFICIENCY)
E        = P · Δt/3600   [MWh]                                powerstation.cpp:196 / 230
Inntekt  = E · pris[t]                                        powerstation.cpp:203 / 236
```

**Viktig for enhver ekstern reimplementasjon [kilde]:** `H_brutto` bruker **gjennomsnittet** av
magasinnivået ved start og slutt av tidssteget. Sluttnivået avhenger av hvor mye man tapper. Fallhøyden
er derfor **implisitt avhengig av handlingen innenfor samme tidssteg**. Rekkefølgen må være: nivå før →
uttak → nivå etter → snitt → effekt.

Virkningsgraden `η_turbin(Q)` kommer fra én av to kurvetyper (`powerstation.cpp:68-106`):

| Type | Nøkkelord | Evaluering |
|---|---|---|
| Generell | `TURBINE_CURVE n` + n punkter `[m³/s, %]` | Stykkevis lineær via `ArrayCurve`, binærsøk-lignende oppslag. |
| Uniform normalisert | `UNIFORM_NORMALIZED_CURVE 11` + 11 verdier ved `Q/Qmax = 0.0, 0.1, …, 1.0` | Direkte indeksberegning, `O(1)`. Raskere. |

Ved `Q < 10⁻⁶` returneres 0 uten kurveoppslag.

### Flere generatorer

`NR_GENERATORS n` (maks 6, `herss.h:94`). Hver generator har egen kurve, egen `GENERATOR_MAX_DISCHARGE`
og egen action-kolonne. To rørgatekonfigurasjoner (`SHARED_PENSTOCK`):

- `TRUE`: falltapet regnes av **samlet** vannføring, samme `H_netto` for alle generatorer
- `FALSE`: falltap og `H_netto` regnes per generator

### Kostnader og straffer

**Start/stopp** (`powerstation.cpp:245-257`):

```
previous_action = (t > 0) ? action[t−1] : 0.0
if (previous_action > 0.01) ≠ (current_action > 0.01):
    startstopCost += POWSTAT_STARTSTOP / 2
```

**Avvik dokumentasjon/kode [kilde]:** manualen sier at `NODE PSTATION`-verdien i starttilstandsfilen
«is used to evaluate start/stop cost transitions at the first time step of the new simulation»
(`doc/herss.tex`, §The State File). **Koden gjør ikke dette.** Ved `t = 0` er `previous_action` alltid
`0.0`, uavhengig av `init_Power`. `init_Power` brukes utelukkende i `CalcAdjustmenCosts`
(`powerstation.cpp:812`), som bare kjører når `MAX_ADJUST > 0` — og `MAX_ADJUST` er `-9999` i alle
datasett, og gir dessuten feil om den settes positiv. **Dette har direkte konsekvens for rullerende
horisont** og forklarer den lille sømfeilen som ble målt ved kjeding (se kapittel 8).

**Aggressive actions.** Her finnes det **to separate kodeveier**, ikke én:

*Vei 1 — volumsjekk i `GetTunnelFLow` (`powerstation.cpp:785-791`):*

```cpp
if (Q_Mm3 > up_res_Mm3) {
    aggressive_actions_cost = (Q_Mm3 - up_res_Mm3) * HERSS_AGGRESSIVE_ACTIONS_COST;  // = 1000
    flow = 0.0;
}
```

Straffen er proporsjonal med bruddets dybde — det er bedre enn manualen antyder. Men `flow = 0.0`
legger inn en **stegdiskontinuitet** i produksjonsleddet: rett før terskelen produserer man nesten
maksimalt, rett etter produserer man ingenting.

Manualen sier dette gir «a strong gradient signal to drive the solution away from infeasible regions».
Kildekommentaren rett over koden sier noe annet: *«I think we should give a minor penalty when we run
action to aggresively. Just so we dont get the same value in VF.»* **Straffen er designet for å bryte
platåer i verdifunksjonen, ikke for å håndheve feasibility.** **[kilde, dokumentasjonsavvik]**

*Vei 2 — inn/ut-sjekk i `Simulate` (`powerstation.cpp:145-153`):*

```cpp
if (total_Q > S->up_inflow[t] * 1.000001) {
    total_Q = 0.0;  for all g: Q_gen[g] = 0.0;
}
```

Denne gir **ingen** kostnad — den nullstiller bare produksjonen. I praksis er den konsistent med vei 1
(når vei 1 setter `flow = 0`, blir `up_inflow = 0`, og vei 2 slår inn), men den er en egen mekanisme.

**Minste vannføring** (`powerstation.cpp:160-165`): `POWSTAT_MIN_DISCHARGE` gir kun en **advarsel** i
loggen. Koden som ville nullstilt produksjonen er kommentert ut (`powerstation.cpp:198-200`,
`:232-234`). Dette er en ren myk begrensning uten kostnad.

**`AUTO_QMIN`** (`powerstation.cpp:776-779`): hvis satt positivt, heves vannføringen til minst
`AUTO_QMIN` uavhengig av action. Ikke aktiv i noe datasett (`-9999` overalt).

### Kilder til ikke-linearitet og diskontinuitet **[vurdering]**

| Mekanisme | Type | Alvorlighet |
|---|---|---|
| `H_netto · Q` (produkt av to handlingsavhengige ledd) | Bilineær | Grunnleggende |
| `ΔH = k·Q²` | Kvadratisk | Moderat |
| `η_turbin(Q)` stykkevis lineær, ikke-konkav, med topp under fullast | Ikke-konveks | Moderat–stor |
| Fallhøyde avhenger av magasinnivå | Ikke-lineær tidskobling | Stor |
| Aggressive-action-klippet (`flow = 0`) | **Diskontinuerlig** | Stor for søk |
| Start/stopp-terskelen ved `a = 0.01` | **Diskontinuerlig** | Liten i praksis (se kap. 7) |
| Overløpsknekk ved HRW | Ikke-deriverbar | Moderat |

## 4.3 Channel (elvestrekning)

### Hvorfor de finnes

For å representere at vann bruker tid på å komme fra ett punkt til et annet, og at en flombølge dempes
underveis. Uten dem ville alt vann i systemet ankomme nedstrøms momentant.

### Ruting og forsinkelse

Rutingen er en **kaskade av `N` lineære reservoar** (Nash-kaskade), med `N = N_CASCADE_LINRES` og total
tidskonstant `K_total = K_TRAVELTIME_HOURS`, fordelt likt: `K = K_total / N`
(`cascadedreservoirs.cpp:38`).

Hvert lineærreservoar oppdateres med den **eksakte** diskrete løsningen for konstant tilsig over
tidssteget (`cascadedreservoirs.cpp:104-113`):

```
S_{t+Δt} = S_t · e^{−Δt/K} + K·(1 − e^{−Δt/K})·I_t
Q_ut     = (S_t + I_t·Δt − S_{t+Δt}) / Δt
```

Utløpet fra ett reservoar er innløpet til det neste.

**[vurdering]** Dette er **lineært i tilsiget** og massebevarende ved enhver Δt. Det betyr at
kanalrutingen er den mest MILP-vennlige delen av hele modellen: den kan skrives som et lineært
tilstandsromsystem med konstante koeffisienter (gitt fast Δt), uten binærvariabler.

Effekten av `N`: `N = 1` gir maksimal demping; høyere `N` gir mindre demping og respons nærmere ren
tidsforsinkelse. Manualen anbefaler `N = 3–5` for naturlige elvestrekninger. Maks `N = 10`
(`herss.h:95`), maks `K_total = 240` timer (`herss.h:57`).

### Påvirker kanaltilstanden objektivfunksjonen?

**Direkte: nei.** `income[t] = 0`, `remaining_active_Mm3 = 0` (`channel.cpp:126-127`). Terminalleddet i
`CalcVF` summerer kun over `PSTATION`-noder (`riversystem.cpp:433-436`), så vann i en kanal telles
aldri i terminalverdien.

**Indirekte: ja, og betydelig.** En kanal mellom to kraftverk i en kaskade forsinker vannet slik at det
ankommer nedstrøms magasin senere. Dette flytter når vannet kan brukes — og dermed hvilken pris det
kan realiseres til.

**[vurdering, viktig konsekvens]** I et system med **ett** magasin og én kraftstasjon der kanalen er
den nederste noden, er kanalen fullstendig irrelevant for `V`. Den kan droppes fra en DP-tilstand. I en
kaskade kan den **ikke** droppes.

### Begrensninger

`QMIN` er den eneste, og den er **deaktivert**: hvis `QMIN` settes til et positivt antall perioder,
avbryter koden umiddelbart med «WORK IN PROGRESS, BVM May 2026 — This functionality has not yet been
quality controlled» (`channel.cpp:264`) **[kilde]**. Alle datasett har `QMIN -9999`.

Kostnadsstrukturen finnes i koden (`channel.cpp:110-117`), men periodeparsingen er kommentert ut.

**Merknad om parsing [kilde]:** kanalparseren er den eneste som **avviser ukjente nøkkelord**
(`channel.cpp:271-273`). Magasin- og kraftstasjonparserne ignorerer ukjente nøkkelord stille. Det
betyr at en skrivefeil i en magasinblokk kan gå upåaktet hen — parameteren beholder bare sin
initialiseringsverdi.

---

# 5. Alle inputfiler

Alle filer er ren tekst, whitespace-separert. Linjer som starter med `#` er kommentarer.

## 5.1 `global.txt` — inngangspunktet

Eneste fil som gis på kommandolinjen: `herss.exe global.txt`.

| Nøkkelord | Betydning | Kilde |
|---|---|---|
| `SYSTEMNAME` | Navn på vassdraget. Brukes i outputfilnavn. | `globalconfig.cpp:388` |
| `INPUTDIR` | Katalog for alle inputfiler. Prefikses alle inputfilnavn. | `:427` |
| `OUTPUTDIR` | Katalog for output. Prefikses `OUTSTATEFILE` og `outputfile`. | `:421` |
| `TOPOLOGYFILE` | Topologifil. | `:363` |
| `PRICEFILE` | Prisfil. **Definerer også `T` og Δt.** | `:357` |
| `INFLOWFILE` | Tilsigsfil. | `:351` |
| `ACTIONFILE` | Handlingsfil. | `:345` |
| `STARTSTATEFILE` | Starttilstand. | `:394` |
| `OUTSTATEFILE` | Sluttilstand som skrives. | `:400` |
| `WRITE_NODEFILES` | `1` = skriv én outputfil per node, `0` = ikke. | `:421` |
| `PRINT_GLOBAL_INFO` | `TRUE`/`FALSE`. Skriv systeminfo til skjerm. | `:369` |
| `PRINT_ECONOMIC_INFO` | `TRUE`/`FALSE`. Skriv økonomisk sammendrag til skjerm. | `:375` |
| `DT`, `DT_LAST` | **Deprecated siden mai 2026.** Aksepteres, men ignoreres med melding i loggen. | `:406,415` |

**Ukjente nøkkelord gir feil og avslutter programmet** (`globalconfig.cpp:432-440`).

**Merknad for Python-bruk [kilde]:** `SetDirectoriesAndFilenames()` (`globalconfig.cpp:106`) prefikser
filnavnene med `inputdir`/`outputdir`. Kalles den to ganger, blir prefikset lagt på to ganger.
`pyherss.py` setter `gc.inputdir`/`gc.outputdir` manuelt **etter** `readGlobalFile()` og **før**
`SetDirectoriesAndFilenames()` — den rekkefølgen må holdes.

### Eksempel (`data/mini_utahps_daily/global.txt`)

```
SYSTEMNAME mini_uTAHPS_daily
INPUTDIR ./
ACTIONFILE actions.txt
INFLOWFILE inflowseries.txt
PRICEFILE pricefile.txt
TOPOLOGYFILE topology.txt
STARTSTATEFILE start_state.txt
OUTSTATEFILE outstate.txt
WRITE_NODEFILES 1
OUTPUTDIR ./output/
PRINT_GLOBAL_INFO FALSE
PRINT_ECONOMIC_INFO FALSE
```

## 5.2 `topology.txt` — vassdragets struktur

Filen er en sekvens av nodeblokker:

```
NODE  <NODETYPE>  <IDNR>  <NAME>  [<DOWNSTREAM_IDNR>  — kun for CHANNEL]
  <nøkkelord>  <verdi>
  ...
ENDNODE
```

### Node-ID og rekkefølge

- ID-er starter på 0 og øker.
- **Oppstrøms noder må ha lavere ID enn nedstrøms noder.** HERSS validerer ikke dette.
- Maks 30 noder (`MAX_NR_NODES`, `herss.h:53`).
- Siste node er typisk systemets utløp (kanal med nedstrøms-ID `-9`).

### Forbindelser

| Nodetype | Hvordan nedstrøms angis |
|---|---|
| `RESERVOIR` | Implisitt i utløpsnøkkelordene: `OUTLET_TUNNEL`, `OUTLET_HATCH`, `OVERFLOW_CURVE`/`SPILLWAY`, `OUTLET_AUTO_QMIN` — hver bærer sin egen nedstrøms-ID. |
| `PSTATION` | `DOWNLINK_IDNR <idnr>` |
| `CHANNEL` | Siste felt på selve `NODE`-linjen. `-9` = ingen nedstrøms (utløp). |

### Parametre — RESERVOIR

| Nøkkelord | Enhet | Rolle | Constraint? |
|---|---|---|---|
| `HRW` | masl | Høyeste regulerte vannstand | Definerer aktivt volum + tak for verdsatt vann. **Ikke** en hard skranke — flom er tillatt. |
| `LRW` | masl | Laveste regulerte vannstand | Nedre grense for aktivt volum. Brudd straffes. |
| `RES_PENALTY` | valuta/(m·time) | Straff per meter under LRW per time | **Myk constraint.** |
| `FLOODLEVEL_PENALTY` | — | Leses, **brukes aldri** | **Ingen effekt.** |
| `RESERVOIR_CURVE n` | masl, Mm³ | n punkter, volum–nivåkurve | Modellparameter |
| `RESERVOIR_GEOMETRY` + `WIDTH_M`/`LENGTH_M`/`THETA`/`BOTTOM_MASL` | m, m, grader, masl | Alternativ parametrisk geometri | Modellparameter |
| `OVERFLOW_CURVE n <ds_idnr>` | masl, m³/s | Overløpskurve + nedstrømsnode | Automatisk mekanisme |
| `SPILLWAY <ds_idnr> C L <masl>` | –, m, masl | Overløpsformel `Q = C·L·H^{3/2}` | Automatisk mekanisme |
| `FAST_OVERFLOW` | `TRUE`/`FALSE` | Forenklet overløp: alt over HRW | Modellvalg |
| `OUTLET_TUNNEL <ds_idnr>` | — | Produksjonsutløp til kraftstasjon. `-9999` = ikke i bruk. | Topologi |
| `OUTLET_HATCH <ds_idnr> <Qmin> <Qmax> <masl>` | –, m³/s, m³/s, masl | Styrbar luke. **Genererer en action-kolonne.** `-9999` = ikke i bruk. | Kapasitetsskranke via Qmax |
| `OUTLET_AUTO_QMIN <n_perioder> <ds_idnr>` | — | Sesongstyrt slipp. **Avbryter med feil hvis aktivert.** | Ikke brukbar |

### Parametre — PSTATION

| Nøkkelord | Enhet | Rolle |
|---|---|---|
| `DOWNLINK_IDNR` | — | Nedstrømsnode |
| `NR_GENERATORS n` | — | Antall generatorer, maks 6. **Genererer n action-kolonner.** |
| `GENERATOR g` | — | Starter en generatorblokk (må komme i rekkefølge 0, 1, …) |
| `TURBINE_CURVE n` | m³/s, % | Virkningsgradskurve, n punkter |
| `UNIFORM_NORMALIZED_CURVE 11` | –, % | Alternativ: 11 verdier ved `Q/Qmax = 0.0…1.0`. Må ha nøyaktig 11. |
| `GENERATOR_MAX_DISCHARGE` | m³/s | **Kapasitetsskranke.** `Q = a·Qmax`. Må komme rett etter kurven. |
| `STATIC_GENERATOR_EFFICIENCY` | – | Konstant generatorvirkningsgrad (0.96 i alle datasett) |
| `HEADLOSSCOEF` | s²/m⁵ | `ΔH = k·Q²` |
| `SHARED_PENSTOCK` | `TRUE`/`FALSE` | Felles eller separate rørgater |
| `POWSTAT_MASL` | masl | Turbinens senterhøyde |
| `POWSTAT_MIN_DISCHARGE` | m³/s | **Kun advarsel.** Ingen kostnad, ingen håndheving. |
| `POWSTAT_STARTSTOP` | valuta | Kostnad per start/stopp-transisjon (deles i to) |
| `LOCAL_ENERGY_EQUIVALENT` | kWh/m³ | **Kun brukt i terminalverdien.** Konstant. |
| `AUTO_QMIN` | m³/s | Minstevannføring gjennom turbinen uavhengig av action. `-9999` = av. |
| `MAX_ADJUST` | – | **Avbryter med feil hvis > −1.** Ikke kvalitetssikret. |
| `POWSTAT_MAX_DISCHARGE` | m³/s | **Finnes i `utahps_daily`-topologien, men parses ikke.** Se kapittel 10. |

### Parametre — CHANNEL

| Nøkkelord | Enhet | Rolle |
|---|---|---|
| `N_CASCADE_LINRES n` | – | Antall lineærreservoar i kaskaden, 1–10 |
| `K_TRAVELTIME_HOURS` | timer | Total tidskonstant, 0–240 |
| `QMIN n` | – | Antall minstevannføringsperioder. **Avbryter med feil hvis > 0.** |
| `TRAVELTIME`, `DECAY` | – | **Fjernet.** Gir eksplisitt feilmelding om nytt format. |

### Eksempel — den lille uTAHPS-topologien

```
NODE RESERVOIR 0 HJELLE
HRW 757.0
LRW 748.0
RES_PENALTY 300
FLOODLEVEL_PENALTY 300
RESERVOIR_CURVE 7
747	0.0
748	1.0
749	2.37
750	3.24
757	10.0
758	15.0
760	500
OVERFLOW_CURVE 3 2
757	0.0
758	10.0
760	200.0
FAST_OVERFLOW FALSE
OUTLET_HATCH -9999
OUTLET_TUNNEL 1
OUTLET_AUTO_QMIN -9999
ENDNODE

NODE PSTATION 1 SVOLETJONN
DOWNLINK_IDNR 2
NR_GENERATORS 1
GENERATOR 0
TURBINE_CURVE 10
0.00	0
1.00	50
...
4.00	88
GENERATOR_MAX_DISCHARGE 4.0
STATIC_GENERATOR_EFFICIENCY	0.96
HEADLOSSCOEF	0.3
SHARED_PENSTOCK	TRUE
POWSTAT_MASL 690.0
POWSTAT_MIN_DISCHARGE	1.0
POWSTAT_STARTSTOP	2.0
LOCAL_ENERGY_EQUIVALENT	0.11
AUTO_QMIN -9999
MAX_ADJUST -9999
ENDNODE

NODE CHANNEL 2 VANAROSEN -9
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 4
QMIN -9999
ENDNODE
```

Herav: aktivt volum = `V(757) − V(748)` = 10,0 − 1,0 = **9,0 Mm³**. Bruttofallhøyde ved LRW = 748 − 690
= 58 m, ved HRW = 757 − 690 = 67 m — altså **13,4 % variasjon**.

## 5.3 `pricefile.txt`

```
RESTPRICE	33
Date	Price
2022090100	24.88
2022090200	25.85
...
```

| Element | Beskrivelse | Kilde |
|---|---|---|
| Linje 1 | `RESTPRICE <verdi>` — vannverdien ved horisontens slutt [valuta/MWh]. **Obligatorisk første ikke-kommentarlinje.** | `dataset.cpp:346-350` |
| Linje 2 | `Date Price` — fast kolonneoverskrift | `dataset.cpp:355-361` |
| Kolonne 1 | Tidsstempel. Fire formater aksepteres: `yyyymmddhh`, `yyyymmdd`, `yyyy-mm-dd`, `yyyy-mm-dd-hh` (`xtime.cpp:103-170`). | |
| Kolonne 2 | Spotpris [valuta/MWh]. Én serie for hele systemet — HERSS antar ett prisområde. | |

**Tidsoppløsningen bestemmes her.** `Δt(t) = epoch(t+1) − epoch(t)`, og siste tidssteg arver nest
sistes Δt (`dataset.cpp:82-101`). Blandet oppløsning i samme fil er tillatt — det er
`utahps_multires` bygget på.

**Antall tidssteg `T` = antall datarader** (`globalconfig.cpp:96-102`).

**Slik inngår prisen i objektivet:** `income[t] = Power[t] · price[t]` per kraftstasjon
(`powerstation.cpp:203`), og `RESTPRICE` ganges med gjenværende energi i terminalleddet
(`riversystem.cpp:474`).

## 5.4 `inflowseries.txt`

```
Date_NodeID	0	3	5	9
20220901	1.50	0.80	2.10	3.4
...
```

| Element | Beskrivelse | Kilde |
|---|---|---|
| `Date_NodeID` | Obligatorisk første token i header | `dataset.cpp:245-249` |
| Header-tokens etter | Node-ID-ene som mottar tilsig | `dataset.cpp:265-272` |
| Kolonne 1 | Tidsstempel. **Må matche prisfilen eksakt** — avvik gir feil. | `dataset.cpp:313-321` |
| Øvrige kolonner | Tilsig [m³/s] til noden med tilsvarende ID | |

**Kun magasinnoder kan motta tilsig.** Koden sjekker at hver ID i headeren peker på en `RESERVOIR`
(`dataset.cpp:277-285`), og at antall kolonner er lik `nr_reservoirs` (`globalconfig.cpp:283-296`).
Alle andre noder får null lokalt tilsig.

**Rolle i optimeringsproblemet:** ren eksogen input. Den bestemmer hvor mye vann som er tilgjengelig og
når. Sammen med magasinkapasiteten avgjør den om lagringsskranken faktisk binder — se kapittel 7.

## 5.5 `actions.txt` — beslutningsvariablene

Dette er den viktigste filen for optimering.

```
Date_NodeID 0 4_0 4_1
20220901 0.7 0.8 0.75
20220902 0.8 0.8 0.0
...
```

| Kolonnenavn | Betyr |
|---|---|
| `<idnr>_<gen>` | Generator `gen` i kraftstasjonen med node-ID `idnr`. Nullbasert generatorindeks. |
| `<idnr>` (uten understrek) | **Magasinluke** i magasinet med node-ID `idnr`. |

Eksempelet over er `res_casc_A`: kolonne `0` er luken i magasin `RES_A`, kolonnene `4_0` og `4_1` er de
to generatorene i kraftstasjon `PSTAT_B`.

### Hvordan en action påvirker systemet

| Kolonnetype | Effekt | Kilde |
|---|---|---|
| Generator | `Q_g = a · GENERATOR_MAX_DISCHARGE_g` | `powerstation.cpp:132` |
| Luke | `Q_hatch = Qmin_hatch + a · (Qmax_hatch − Qmin_hatch)` | `reservoir.cpp:564` |

**Merk asymmetrien:** for en generator gir `a = 0` null vannføring. For en luke gir `a = 0` fortsatt
`Qmin_hatch`. Det er ikke samme parametrisering.

### Intervallet `[0,1]`

Håndheves med toleranse `±10⁻⁶`. Verdier utenfor gir feil og **avslutter programmet**
(`powerstation.cpp:135-138` for generatorer, `reservoir.cpp:548-552` for luker) **[kilde]**. Dette er
ikke en myk skranke — det er en prosessdrap. Se kapittel 8 og 10.

### Kolonnetelling

`GlobalConfig::Diagnose()` teller forventet antall action-kolonner fra topologifilen: sum av
`NR_GENERATORS` over alle kraftstasjoner, pluss én per aktiv `OUTLET_HATCH`
(`globalconfig.cpp:196-231`). `Dataset::readActionsFile` sjekker at handlingsfilen har akkurat så mange
kolonner (`dataset.cpp:176-184`).

**Merknad om kobling [kilde]:** kolonnene bindes til generatorer ved **navnematching** i
`prepaireSimulation` (`herss.cpp:273-292`) — kolonnenavnet `"4_1"` konstrueres fra node-ID og
generatorindeks og slås opp i headeren. Rekkefølgen på kolonnene i filen spiller derfor ingen rolle;
navnene gjør. Det samme gjelder luker (`herss.cpp:236-251`).

## 5.6 `start_state.txt`

```
# STATEFILE MINI UTAHPS
NODE RESERVOIR 0 HJELLE 0.67
NODE PSTATION 1 SVOLETJONN 0.0
NODE CHANNEL 2 VANAROSEN 0.001 0.002 0.003
```

| Nodetype | Verdi(er) | Betydning | Kilde |
|---|---|---|---|
| `RESERVOIR` | 1 verdi: `fr` | Fyllingsfraksjon. `V_start = V_LRW + fr·(V_HRW − V_LRW)`. Verdier utenfor `[0,1]` aksepteres (advarsel over 1.5). | `reservoir.cpp:1140-1145`, `:322` |
| `PSTATION` | 1 verdi: MWh | Produksjon i forrige periodes siste tidssteg. **Brukes ikke til start/stopp — se kapittel 10.** | `powerstation.cpp:609` |
| `CHANNEL` | `N` verdier: Mm³ | Volum i hvert lineærreservoar. Antall må matche `N_CASCADE_LINRES` nøyaktig. | `channel.cpp:344-349` |

Både magasin- og kraftstasjonlinjene må ha **nøyaktig 5 kolonner**, ellers feil
(`reservoir.cpp:1128-1131`, `powerstation.cpp:595-601`).

### Tilstandskjeding og rullerende horisont

Outputfilen `outstate.txt` har **identisk format** med `start_state.txt`. Kjeding er derfor trivielt:

```
kjør periode 1  →  output/outstate.txt
                        │
                        └─► kopier til start_state.txt for periode 2
kjør periode 2  →  ...
```

**[målt]** En delt kjøring av `mini_utahps_daily` ved `t = 15` gjenskapte lagring, produksjon og
terminalverdi **eksakt**. Eneste avvik var 1 EUR i start/stopp-kostnad i skjøten — relativ feil
1,4·10⁻⁵ — som er nøyaktig det man forventer gitt at `init_Power` ikke brukes i start/stopp-logikken.
Rullerende horisont er altså en gyldig dekomponering **så lenge start/stopp-kostnadene er
neglisjerbare**. Blåses de opp for å skape diskret struktur, vokser sømfeilen og må håndteres
eksplisitt. **[vurdering]**

---

# 6. Alle outputfiler

Alle skrives til `OUTPUTDIR`. HERSS **oppretter ikke katalogen** — den må finnes.

| Fil | Skrives av | Innhold |
|---|---|---|
| `node<idnr>_<NAVN>.txt` | `Herss::WriteNodeOutput` (`herss.cpp:755`), kun hvis `WRITE_NODEFILES 1` | Full tidsserie per node. Kolonner avhenger av nodetype. |
| `reservoirs_<SYSTEMNAME>_out.txt` | `Riversystem::WriteReservoirData` (`riversystem.cpp:157`) | Fyllingsfraksjon per magasin per tidssteg. |
| `riversystem_<SYSTEMNAME>_output.txt` | `Riversystem::WriteRiverSystemData` (`riversystem.cpp:533`) | Aggregert sammendrag: nodeinventar, vannbalanse, all økonomi. |
| `<OUTSTATEFILE>` | `Herss::WriteStateFile` (`herss.cpp:355`) | Sluttilstand i samme format som starttilstandsfilen. |
| `herss_<VERSION>_<DATE>.log` | Logger, skrives i **arbeidskatalogen** (ikke `OUTPUTDIR`) | Alle `LOG_MSG`/`LOG_WARN`/`LOG_ERR` med tidsstempel, fil, linje, funksjon. |

## 6.1 Nodeoutput — magasin

```
RESERVOIR node 0 HJELLE
reservoir_init_fr= 0.67000  masl=757.575
Filling at HRW [Mm3] = 10.00000
Filling at LRW [Mm3] = 1.00000
Active reservoir capacity [Mm3] = 9.00000
yyyy mm dd hh Inflow Price Action Up_Inflow Res_Mm3 Res_masl Res_fr lrw_cost tunnelflow hatchflow overflow auto_qmin tot_outflow
2022 9 1 0 1.5000 24.8800 0.0000 0.0000 6.8140 753.7009 0.6460 0.0000 4.0000 0.0000 0.0000 0.0000 4.0000
```

**Merknad [kilde]:** `masl=757.575` i header nr. 2 er **ikke** initialnivået — det er `res_masl` slik
den står ved skrivetidspunktet, altså etter siste tidssteg. Den er trykket ved siden av
`reservoir_init_fr` og er lett å mistolke (`reservoir.cpp:1183`). I dette eksempelet er sluttnivået
over HRW = 757.

## 6.2 Nodeoutput — kraftstasjon

```
POWERSTATION node 1 SVOLETJONN
init_Power = 0.00000
penstock_config = SHARED
headloss_coef = 0.300000
yyyy mm dd hh Up_Inflow Price Action_g0 tot_outflow auto_qmin Hnetto Hbrutto Power est_eekv income tot_cost startstopCost adjust_cost cost_aggressive_actions profit
2022 9 1 0 4.0000 24.8800 1.0000 4.0000 0.0000 59.0127 63.8127 46.9344 0.1358  1167.7283 1.0000 1.0000 0.0000 0.0000 1166.7283
```

Én `Action_g<g>`-kolonne per generator. Dette er **den viktigste filen for feasibility-kontroll**:
`cost_aggressive_actions` og `startstopCost` per tidssteg.

## 6.3 Nodeoutput — kanal

```
CHANNEL node 2 VANAROSEN
N_CASCADE_LINRES 3
K_TRAVELTIME_HOURS 4.00
yyyy mm dd hh Up_Inflow Storage_Mm3 tot_outflow Qmin_Cost
2022 9 1 0 4.0000 0.05467839 3.4366 0.0000
```

## 6.4 `riversystem_*_output.txt` — hovedsammendraget

```
Riversystem mini_uTAHPS_daily
Node Idnr Nodename          Nodetype int Nodetypename Remaining_Mm3
Node  0 HJELLE               Nodetype 0  RESERVOIR             12.8727
Node  1 SVOLETJONN           Nodetype 1  PSTATION              0.0000
Node  2 VANAROSEN            Nodetype 2  CHANNEL               0.1455
-------------------------------------------
GLOBAL WATERBALANCE
start_water_Mm3   = 7.036000
inflow_volume_Mm3 = 12.877920
outflow_Mm3       = 6.895679
end_water_Mm3     = 13.018241
waterbalance      = 0.000000
-------------------------------------------
Average_price_Euro           = 44.774
RestPrice_Euro               = 33.000
tot_remaining_Mm3            = 13.018
tot_active_remaining_Mm3     = 9.000
tot_remaining_MWh            = 990.000
tot_remaining_Euro           = 32670.000
Sum_Production_MWh           = 797.636
tot_income_Euro              = 36470.224
Avg_achieved_price_E_MWh     = 45.723
sum_qmin_cost_Euro           = 0.000
sum_lrw_cost_Euro            = 0.000
sum_startstopcost_Euro       = 5.000
sum_max_adjustment_cost      = 0.000
sum_aggressive_actions_cost  = 0.000
tot_cost_Euro                = 5.000
tot_profit_Euro              = 36465.224
valuefunction_Euro           = 69135.224
```

Merk at **hver kostnadstype er separat rapportert**. Det er akkurat det man trenger for en
feasibility-tabell.

**Vannbalansen** skal lukke til null. `Herss::GlobalWaterBalance` (`herss.cpp:706`) sjekker at
`start + tilsig − slutt − utstrømning = 0` og avslutter programmet ved avvik over 10⁻⁴ Mm³.

## 6.5 Advarsel: duplisert verdifunksjonsberegning

`WriteRiverSystemData` (`riversystem.cpp:533`) **regner om og overskriver** medlemsvariabelen
`valuefunction_Euro` (`riversystem.cpp:567,576,593`), med logikk som dupliserer `CalcVF`. To
konsekvenser **[kilde]**:

1. Å skrive output har en **sideeffekt** på objektets tilstand.
2. `tot_remaining_Mm3` defineres **forskjellig** i de to: `CalcVF` bruker kun
   `upstream_remaining_Mm3` (`:418`), mens `WriteRiverSystemData` legger til `remaining_Mm3` i
   bunnnoden (`:567`). Ingen av dem inngår i `V`, så tallet er ikke feil i seg selv — men det er en
   vedlikeholdsfelle.

**[målt]** For lik `restprice` er de to numerisk identiske bit for bit på testede datasett. Men
**[vurdering]** en harness bør likevel alltid lese returverdien fra `CalcVF()` direkte, aldri
medlemsvariabelen etter en skriveoperasjon.

## 6.6 Hvilke outputs er mest relevante?

| Formål | Bruk |
|---|---|
| **Evaluering av kandidatløsning** | Returverdien fra `CalcVF()` i minnet. Ingen filskriving. |
| **Feasibility-kontroll** | `sum_aggressive_actions_cost`, `sum_lrw_cost_Euro`, `sum_qmin_cost_Euro`, `sum_startstopcost_Euro` fra `riversystem_*_output.txt`; eller `cost_aggressive_actions` per tidssteg fra nodefilen. |
| **Debugging** | `node*_*.txt` + loggfilen. Loggen inneholder linjenummer og funksjonsnavn. |
| **Sammenligning av algoritmer** | `valuefunction_Euro` + separat feasibility-tabell + antall simulatorkall. |
| **Spill-diagnose** | `overflow`-kolonnen i magasinnodefilen. |
| **Rullerende horisont** | `outstate.txt`. |

---

# 7. Gjennomgang av alle datasett under `data/`

12 datasett. Alle bygger på samme fiktive system, «Upper Tovdalen Artificial Hydro Power System»
(uTAHPS), i ulike utsnitt og oppløsninger.

## 7.1 Oversiktstabell

| Datasett | T | Δt | Res | Kraftst. | Kanal | Gen. | Action-kol. | Beslutn.dim. | Testet feature | Økon. objektiv? | Benchmark? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `mini_utahps_daily` | 30 | 86400 | 1 | 1 | 1 | 1 | 1 | 30 | Baseline, daglig | Ja | **Ja — DP-referanse** |
| `mini_utahps_hourly` | 48 | 3600 | 1 | 1 | 1 | 1 | 1 | 48 | Baseline, timeoppl. | Ja | Nei — frakoblet |
| `mini_utahps_new_inputformat` | 48 | 3600 | 1 | 1 | 1 | 1 | 1 | 48 | `RESERVOIR_GEOMETRY` | Ja | Nei — frakoblet |
| `mini_utahps_spillway` | 48 | 3600 | 1 | 1 | 1 | 1 | 1 | 48 | `SPILLWAY` + `UNIFORM_NORMALIZED_CURVE` | Ja | Nei — frakoblet |
| `res_casc_A` | 30 | 86400 | 2 | 1 | 3 | 2 | 3 | 90 | Kaskade + luke + multigen. | Ja | **Ja — liten kaskade** |
| `res_casc_B` | 12 | 3600 | 2 | **0** | 2 | 0 | 1 | 12 | To magasin, kun luke | **Nei — `V = 0`** | **Nei — ubrukelig** |
| `res_casc_C` | 48 | 3600 | 1 | 1 | 1 | 1 | 1 | 48 | `RESERVOIR_GEOMETRY` | Ja | Nei — frakoblet |
| `res_casc_D` | 12 | 3600 | 2 | **0** | 2 | 0 | 2 | 24 | To luker i serie | **Nei — `V = 0`** | **Nei — ubrukelig** |
| `utahps_daily` | 365 | 86400 | 4 | 4 | 4 | 4 | 4 | 1460 | Full kaskade, daglig | Ja | **Ja — middels** |
| `utahps_daily_new_format` | 365 | 86400 | 4 | 4 | 4 | **5** | 5 | 1825 | `SPILLWAY` + multigen. på n10 | Ja | Ja — multigen.-variant |
| `utahps_hourly` | 8760 | 3600 | 4 | 4 | 4 | 4 | 4 | 35040 | Full kaskade, ett år timevis | Ja | **Ja — stor** |
| `utahps_multires` | 1560 | variabel | 4 | 4 | 4 | 4 | 4 | 6240 | Blandet oppløsning | Ja | Ja — men mangler `output/` |

Beslutningsdimensjon = antall action-kolonner × `T`.

## 7.2 Systemet som ligger under

De store datasettene (`utahps_*`) har 12 noder:

```
   HJELLE (0)              GRESSE (3)
   748–757 masl            740–749 masl
   aktiv 9.0 Mm³           aktiv 61.4 Mm³
        │ tunnel                │ tunnel
        ▼                       ▼
  SVOLETJONN (1)         SVEIGSHYL_II (7)
  Qmax 4.0, e=0.11       Qmax 6.0, e=0.39
  turbin@690 masl        turbin@581 masl
        │                       │
        ▼                       │
   VANAROSEN (2) ──┐            │
                   │            │
   GRONANI (4) ────┤            │
     (fra GRESSE   │            │
      overløp)     ▼            │
              TOPPSY (5)        │
              620–650 masl      │
              aktiv 126.6 Mm³   │
                   │ tunnel     │
                   ▼            │
            SVEIGSHYL_I (6)     │
            Qmax 5.9, e=0.11    │
            turbin@581 masl     │
                   │            │
                   └────┬───────┘
                        ▼
                   DALSANA (8)
                        ▼
               KROKNESVATN (9)
               333–433 masl
               aktiv 199.3 Mm³
                        │ tunnel
                        ▼
                   EASTER (10)
                   Qmax 9.8, e=0.11
                   turbin@218 masl
                        ▼
                 HYNNEKLEIV (11) → hav
```

Merk: SVEIGSHYL_II har `LOCAL_ENERGY_EQUIVALENT = 0.39` mot 0.11 for de tre andre — en faktor 3,5. Det
gjør at vann i GRESSE er langt mer verdifullt i terminalleddet enn vann i de andre magasinene.

## 7.3 Fallhøydevariasjon per kraftstasjon **[målt]**

| Stasjon | Turbinhøyde | H ved LRW | H ved HRW | Relativ variasjon | `HEADLOSSCOEF` |
|---|---|---|---|---|---|
| SVOLETJONN | 690 | 58 | 67 | **13,4 %** | 0,3 |
| SVEIGSHYL_I | 581 | 39 | 69 | **43,5 %** | 0,2 |
| SVEIGSHYL_II | 581 | 159 | 168 | 5,4 % | 0,145 |
| EASTER | 218 | 115 | 215 | **46,5 %** | 0,145 |

Dette er den enkeltmålingen som avgjør om «hva koster linearisering»-spørsmålet i det hele tatt er
interessant. En variasjon på 1–2 % ville drept det. 13–47 % gjør det ikke.

## 7.4 Lagringsstramhet **[målt]**

Definer `R = aktivt volum / (Q_max · Δt · T)` — hvor stor del av horisonten man kan kjøre på full
kapasitet fra fullt magasin. `R ≫ 1` betyr at lagringen aldri binder.

| Magasin (datasett) | Aktiv Mm³ | Maks uttak over horisonten | **R** | Regime |
|---|---|---|---|---|
| HJELLE (`mini_utahps_daily`, T=30) | 9,0 | 10,37 | **0,87** | **Binder** |
| HJELLE (alle time-mini, T=48) | 9,0 | 0,69 | **13,0** | **Frakoblet — for lett** |
| HJELLE (`utahps_daily`, T=365) | 9,0 | 126,1 | 0,07 | Binder hardt, spill sannsynlig |
| GRESSE (uTAHPS) | 61,4 | 189,2 | 0,33 | Binder |
| TOPPSY (uTAHPS) | 126,6 | 186,1 | 0,68 | Binder |
| KROKNESVATN (uTAHPS) | 199,3 | 309,1 | 0,65 | Binder |

**[vurdering]** De timebaserte mini-datasettene er nesten degenererte: du kan i praksis kjøre hva du
vil uten å gå tom for vann. De er testdatasett for tekniske features, ikke optimeringsinstanser. De må
ikke brukes som hovedbenchmark.

## 7.5 Turbinkurver — hvorfor produksjonen ikke er bang-bang **[målt]**

| Kurve | Toppvirkningsgrad | Ved full last | Relativt tap ved full last |
|---|---|---|---|
| SVOLETJONN / RES_B | 93 % ved Q ≈ 2,8–3,5 | 88 % ved Q = 4,0 | 5,4 % |
| `UNIFORM_NORMALIZED` (spillway-settet + new_format) | 92 % ved 0,5·Qmax | 82 % ved Qmax | **10,9 %** |
| SVEIGSHYL_I | 93 % ved ~0,7·Qmax | 90 % | 3,2 % |
| SVEIGSHYL_II | 91 % ved Q ≈ 2,4 | 89 % ved Q = 6,0 | Flat topp, bred |
| EASTER | 93 % | 90 % | 3,2 % |

Beste driftspunkt ligger **under** full last for alle kurvene. Delvis last er derfor et reelt valg,
ikke bare et kompromiss. Kombinert med at kurvene evalueres stykkevis lineært, blir objektivet
ikke-konvekst i `Q`.

## 7.6 Pris og restprice **[målt]**

| Datasett | T | min | median | maks | std | `restprice` | Persentil |
|---|---|---|---|---|---|---|---|
| `mini_utahps_daily` | 30 | 10,0 | 38,2 | 99,1 | 28,2 | 33 | 50. |
| time-mini (alle) | 48 | 8,0 | 18,7 | 99,1 | 25,0 | 33 | 69. |
| `res_casc_B`/`D` | 12 | 10,0 | 26,2 | 52,9 | 12,4 | 33 | 67. |
| `utahps_daily` (+new_format) | 365 | 0,04 | 108,8 | 564,9 | 98,8 | 101 | 43. |
| `utahps_hourly` | 8760 | 0,01 | 108,6 | 702,8 | 104,6 | 101 | 42. |
| `utahps_multires` | 1560 | 0,07 | 202,8 | 673,7 | 142,7 | 101 | 19. |

`restprice` ligger midt i prisfordelingen overalt. Det betyr at en terskelpolitikk faktisk må velge —
den kan ikke bare produsere alltid eller aldri. **Datasettene er ikke degenererte i denne dimensjonen.**

## 7.7 Diskret struktur — den svake siden **[målt]**

`POWSTAT_STARTSTOP = 2.0` for **hver** kraftstasjon i **hvert** datasett. Målte totalsummer over hele
horisonten:

| Datasett | Sum start/stopp-kostnad | Verdifunksjon |
|---|---|---|
| `mini_utahps_daily` | 5 EUR | 69 135 |
| `mini_utahps_hourly` | 6 EUR | 24 891 |
| `utahps_daily` | 22 EUR | 26 428 742 |
| `utahps_daily_new_format` | 42 EUR | ~31 mill. |

**[vurdering]** Enhetsforpliktelse (unit commitment) har praktisk talt ingenting å bite på her.
Start/stopp utgjør 0,0001–0,01 % av verdifunksjonen. En oppgave som bygger på binære driftsvariabler
som hoveddriver må enten blåse opp `POWSTAT_STARTSTOP` kraftig (og da må realismen begrunnes med
hydrologen) eller finne den diskrete strukturen et annet sted — som i aggressive-action-klippet.

## 7.8 Datasett verdt eksplisitt kritikk

**`res_casc_B` og `res_casc_D` — ingen kraftstasjon.** Begge har `NODE RESERVOIR 0 YVATN` → kanal →
`NODE RESERVOIR 2 HJELLE` → kanal → hav. Ingen `NR_GENERATORS` i det hele tatt. Terminalleddet i
`CalcVF` løper kun over `PSTATION`-noder — derfor er `tot_remaining_MWh = 0` og `tot_income_Euro = 0`,
og **`V ≡ 0` uansett hva du gjør** **[kilde, bekreftet målt]**. De er rene mekanismetester for
lukelogikk og kaskaderuting. De kan ikke brukes som orakel.

**De timebaserte mini-settene (`mini_utahps_hourly`, `_new_inputformat`, `_spillway`, `res_casc_C`).**
`R = 13` — lagringen binder ikke over 48 timer. De skiller seg fra hverandre bare i én teknisk feature:

| Datasett | Forskjell fra `mini_utahps_hourly` |
|---|---|
| `mini_utahps_new_inputformat` | `RESERVOIR_GEOMETRY` i stedet for `RESERVOIR_CURVE` |
| `res_casc_C` | Identisk med `new_inputformat` (`RESERVOIR_CURVE` utkommentert). Duplikat. |
| `mini_utahps_spillway` | `RESERVOIR_GEOMETRY` + `SPILLWAY 2 2.1 50.0 757.0` + `UNIFORM_NORMALIZED_CURVE` |

**[vurdering]** `res_casc_C` og `mini_utahps_new_inputformat` er praktisk talt samme datasett. At de
begge finnes, med forskjellige `SYSTEMNAME`-verdier som til overmål er identiske (`mini_uTAHPS_hourly`
i begge, og også i `mini_utahps_spillway`), tyder på ufullført opprydding. Tre datasett skriver output
med samme filnavn — kjører du dem fra samme katalog, overskriver de hverandre.

**`utahps_multires` — mangler `output/`-katalog.** Datasettet simulerer, men kan ikke skrive output
fordi katalogen ikke finnes og HERSS ikke oppretter den (`riversystem.cpp:539-543`) **[målt]**. Én
`mkdir` løser det, men det er en pakkefeil i det eneste datasettet som tester variabel tidsoppløsning.
Prisfilen viser mønsteret: timevis i sep–okt 2022, deretter daglig, deretter ukentlig fra jan 2023
(`data/utahps_multires/aggregate_data.py`).

**Navnekonvensjonen `new_format` / `new_inputformat`.** `utahps_daily_new_format` bruker `SPILLWAY` på
node 0 og 3, og har to generatorer på EASTER. `mini_utahps_new_inputformat` bruker
`RESERVOIR_GEOMETRY`. Det er altså **ikke** ett «nytt format» — det er ulike features med samme
navnesuffiks. **[usikkert]** Hvilket inputformat som er kanonisk framover må avklares med
utvikleren før man bygger verktøy mot ett av dem.

## 7.9 Anbefalt benchmarksett **[vurdering]**

| Rolle | Datasett | Begrunnelse |
|---|---|---|
| **Eksakt DP-referanse** | `mini_utahps_daily` | 1-dimensjonal tilstand (kanalen kan droppes), lagringen binder (`R = 0,87`), 13,4 % fallhøydevariasjon, 30 tidssteg. |
| **Liten kaskade** | `res_casc_A` | 2 magasin, luke-action, 2 generatorer, kanalforsinkelse. |
| **Middels** | `utahps_daily` | 4×4-system, 365 steg, sterk fallhøydevariasjon på EASTER og SVEIGSHYL_I. |
| **Stor / stresstest** | `utahps_hourly` | 35 040 beslutningsvariabler. |
| **Variabel oppløsning** | `utahps_multires` | Etter `mkdir output`. |
| **Unngå** | time-mini-settene, `res_casc_B`, `res_casc_D` | Frakoblet lagring / ingen objektiv. |

---

# 8. Python-grensesnittet

## 8.1 Hvordan det virker

```python
import cppyy
cppyy.load_library("../src/herss.so")
cppyy.include("../src/herss.h")
```

To linjer. `cppyy` kjører en C++-tolk som leser headeren og eksponerer alle klasser i `herss.h` som
Python-objekter under `cppyy.gbl`. Ingen bindingskode skrives eller kompileres.

**Loggeren må initialiseres manuelt**, fordi `main()` aldri kjøres:

```python
version      = cppyy.gbl.VERSION
version_date = cppyy.gbl.VERSION_DATE
logfilename  = f"herss_{version}_{version_date}.log"
cppyy.gbl.Logger.instance().init(logfilename)
```

**[vurdering]** Disse to variablene bør stemples inn i hver eneste eksperimentlogg. De er den eneste
maskinlesbare versjonsidentifikatoren HERSS eksponerer.

## 8.2 Oppsettsekvensen

Nøyaktig samme rekkefølge som `main.cpp`:

```python
gc = cppyy.gbl.GlobalConfig()
gc.globalfile = inputdir + "global.txt"
gc.readGlobalFile()
gc.inputdir  = inputdir            # må settes ETTER readGlobalFile
gc.outputdir = inputdir + "output/"
gc.SetDirectoriesAndFilenames()    # og kun ÉN gang
gc.Diagnose()
gc.checkNrSteps()

data = cppyy.gbl.Dataset(gc)
data.readAllData()

herss = cppyy.gbl.Herss(gc)
herss.prepaireSimulation(data)
herss.rs.DiagnoseRiversystemConfiguration()   # valideringssjekk — bruk den
```

## 8.3 Orakel-løkken

```python
herss.Simulate()
vf = herss.rs.CalcVF(data.restprice)
```

Setterne og getterne (`herss.cpp:370-556`):

| Metode | Signatur | Merknad |
|---|---|---|
| `SetAction` | `(node_idnr, gen_idnr, t, value)` | For `PSTATION`: setter `generators[gen].action[t]`. For `RESERVOIR`: setter lukeaction; feiler hvis noden ikke har luke. |
| `GetAction` | `(node_idnr, gen_idnr, t)` | Samme logikk. |
| `SetPrice` | `(t, price, restprice)` | Setter pris i **alle** noder for tidssteg `t`, og `restprice` globalt. |
| `SetInflowInNode` | `(t, node, q)` | m³/s. |
| `GetInflowInNode` | `(t, node)` | |
| `SetReservoir_Init_fr` | `(node_idnr, fr)` | Advarer hvis utenfor `[0, 1.1]`, men aksepterer. |
| `GetReservoir_Init_fr` | `(res_idnr)` | **Merk: tar reservoarindeks, ikke node-ID.** Asymmetrisk med setteren. |
| `GetReservoirLevel_fr` | `(node_idnr, t)` | Fyllingsfraksjon ved slutten av tidssteg `t`. |
| `GetPrice` | `(t)` | |

**Advarsel om asymmetri [kilde]:** `SetReservoir_Init_fr` tar **node-ID** og slår opp
`reservoir_idnr` internt (`herss.cpp:436,459-461`), mens `GetReservoir_Init_fr` tar
**reservoarindeks** direkte (`herss.cpp:565`). I `mini_utahps_daily` er begge 0, så feilen er usynlig
der. I `utahps_daily` er magasinene node 0, 3, 5, 9 men reservoarindeks 0, 1, 2, 3. En harness må
kapsle dette inn.

## 8.4 Slik ser en optimeringsløkke ut

```python
# 1. Initialiser simulatoren ÉN gang
gc, data, herss = setup(dataset_dir)

def evaluate(action_matrix):
    # 2-3. Sett actions programmatisk
    for (node, gen, t), a in action_matrix.items():
        herss.SetAction(node, gen, t, a)
    # 4. Simuler
    herss.Simulate()
    # 5. Hent objektivverdi
    return herss.rs.CalcVF(data.restprice)

# 6-7. Evaluer nye løsninger, gjenta
best = max(evaluate(a) for a in candidates)
```

## 8.5 Resettes tilstanden mellom kjøringer?

**Ja — verifisert både i kode og ved måling.**

`Herss::Simulate()` (`herss.cpp:640-652`) starter med:

```cpp
for r: rs->reservoirs[r].InitReservoir();     // gjenoppretter startvolum, nullstiller up_inflow
for c: rs->channels[c].SetStartState();       // gjenoppretter lineærreservoarene, nullstiller up_inflow
for n: nullstill remaining_Mm3, upstream_remaining_Mm3,
                 remaining_active_Mm3, upstream_remaining_active_Mm3
```

**[målt]** Gjentatt `Simulate()` med identiske actions gir **bit-identisk** `V` på alle testede
datasett. A→B→A-testen (`mini_utahps_daily`, node 1 / gen 0 / t=5, `a: 0.61 → 0.123 → 0.61`) ga
`V(A) = 69135.22354412361`, `V(B) = 68787.42447794124`, `V(A igjen) = 69135.22354412361` — siste bit
identisk. **Orakelet er deterministisk og eksakt resettbart in-process.**

## 8.6 Er fil-I/O nødvendig?

**Nei — og det er avgjørende for ytelsen.**

`Simulate()` skriver ingenting. **[målt]**, per `Simulate() + CalcVF()`, debug-build:

| Datasett | T | Kun beregning | Ev./s | Med filskriving | Ev./s med skriving |
|---|---|---|---|---|---|
| `res_casc_B` | 12 | 0,024 ms | 41 930 | 0,730 ms | 1 369 |
| `mini_utahps_daily` | 30 | 0,063 ms | **15 995** | 1,003 ms | 997 |
| `mini_utahps_hourly` | 48 | 0,132 ms | 7 568 | 1,251 ms | 800 |
| `utahps_hourly` | 8760 | 46,8 ms | **21** | 307 ms | 3 |

Filskriving koster 6,5× på den store instansen og 10–40× på de små. **En søkeløkke må holde orakelet
in-process og aldri skrive nodefiler.**

**Budsjettregnestykke [vurdering]:** ~16 000 ev/s på DP-instansen gir ~1,4 milliarder evalueringer per
døgn. På `utahps_hourly` gir 21 ev/s ~1,8 millioner per døgn — mot 35 040 beslutningsvariabler. Det er
rikelig for en matheuristikk **forutsatt at beslutningsrommet reduseres**. Direkte søk i 35 040
dimensjoner er utelukket.

## 8.7 Begrensninger i Python-grensesnittet

| Begrensning | Konsekvens |
|---|---|
| **`LOG_ERR` kaller `std::exit(EXIT_FAILURE)`** (`logger.cpp:41`, `logger.h:78`) | **Den alvorligste.** Ingen exception, ingen returkode — hele Python-prosessen dør. Se under. |
| Alt oppsett går via tekstfiler | Man kan ikke bygge et `Herss`-objekt fra Python uten en katalog med input. Manualen nevner dette som ønsket framtidig arbeid. |
| Ingen `GetValueFunction()`-getter | `CalcVF(restprice)` returnerer verdien, men man må selv holde styr på `restprice`. |
| `GetRestPrice()` er ikke implementert | Den kaller `LOG_ERR("WORK IN PROGRESS")` og dreper prosessen (`herss.cpp:487`). **Ikke kall den.** |
| Ingen kopi- eller serialiseringsmekanisme | Parallellisering må skje ved å bygge flere `Herss`-objekter fra bunnen, eller ved separate prosesser. |
| `CalcWaterValue_atEndofStp` | Kun ett magasin. Avslutter ellers (`herss.cpp:597-599`). |

### Hvorfor `std::exit` er en førsteordens risiko **[vurdering]**

`LOG_ERR` brukes i koden både for reelle feil og for ting som burde vært advarsler. Eksempler som en
optimeringsalgoritme lett vil utløse:

- action utenfor `[0,1]` med mer enn 10⁻⁶ (`powerstation.cpp:136-138`, `reservoir.cpp:550-552`)
- magasinnivå over toppen av reservoarkurven — «Numerical instability, there is too much water in your
  system» (`reservoir.cpp:418-424`)
- vannbalanse som ikke lukker (`herss.cpp:743-751`)

Når noen av disse slår inn, dør Python-prosessen med all akkumulert søketilstand. Det finnes ingen
måte å fange det på fra Python. **Praktisk konsekvens:** en harness må enten (a) validere og klippe
actions **før** de settes — altså ha en repair-operator uansett — eller (b) kjøre evalueringene i en
underprosess og sjekkpunkte tilstanden. Alternativ (a) er billigere og faller uansett sammen med det
et fornuftig søk bør gjøre.

---

# 9. Objektivfunksjon og constraints

## 9.1 Beslutningsvariabler

| Variabel | Domene | Antall | Effekt |
|---|---|---|---|
| `a_{n,g,t}` — generator-action | `[0, 1]` | Σ_kraftstasjoner NR_GENERATORS × T | `Q = a · Q_max` |
| `a_{n,t}` — luke-action | `[0, 1]` | (antall aktive luker) × T | `Q = Qmin + a·(Qmax − Qmin)` |

Kontinuerlige variabler. Ingen eksplisitte binærvariabler — men start/stopp-kostnaden induserer
implisitt en binær driftstilstand via terskelen `a > 0.01`.

## 9.2 Tilstandsvariabler

| Tilstand | Per node | Kommentar |
|---|---|---|
| `res_Mm3` — magasinvolum | Per magasin | **Eneste tilstand med økonomisk verdi.** |
| `S_i` — volum i lineærreservoar `i` | `N` per kanal | Ingen direkte verdi, men flytter vann i tid. |
| Driftstilstand (av/på) | Implisitt per generator | Kun via `a_{t-1} > 0.01`. **Ikke bevart over horisontgrenser.** |

Kraftstasjoner er tilstandsløse: `remaining_Mm3 = 0` alltid.

## 9.3 Eksogene input

Pris `p_t`, tilsig `q_{n,t}`, topologi (alle fysiske parametre), starttilstand, `restprice`.

## 9.4 Objektivfunksjonen — eksakt

Fra `Riversystem::CalcVF` (`riversystem.cpp:406-497`):

$$
V \;=\; \underbrace{\sum_{n}\sum_{t}\bigl(\text{income}_{n,t} - \text{cost}_{n,t}\bigr)}_{\text{tot\_profit\_Euro}}
\;+\;
\underbrace{p_{\text{rest}} \cdot \sum_{n \in \text{PSTATION}} e_n \cdot U_n \cdot 1000}_{\text{tot\_remaining\_Euro}}
$$

der:

- `income_{n,t} = Power_{n,t} · p_t` for kraftstasjoner, 0 ellers (`powerstation.cpp:203`)
- `cost_{n,t}` = start/stopp + aggressive actions (kraftstasjon), LRW-straff (magasin), qmin-kostnad
  (kanal, alltid 0)
- `e_n` = `LOCAL_ENERGY_EQUIVALENT` [kWh/m³], **konstant fra topologifilen**
- `U_n` = `upstream_remaining_active_Mm3` — aktivt volum oppstrøms for kraftstasjon `n` [Mm³]
- Faktoren 1000 kommer av `Mm³ → m³` (×10⁶) og `kWh → MWh` (÷10³) (`riversystem.cpp:436`)

### Tre egenskaper ved terminalleddet som må forstås

**1. Det er kaskadebevisst — bevisst.** Summen løper over kraftstasjoner, ikke over magasin. Vann som
ligger oppstrøms for tre kraftstasjoner telles tre ganger, én gang per stasjon det kan passere. Det er
**riktig** — samme vannmengde produserer energi ved hvert kraftverk på veien ned.

Akkumuleringen skjer etter siste tidssteg (`herss.cpp:685-694`):

```cpp
nodes[n]->ptr_downstream_node->upstream_remaining_active_Mm3
    += (nodes[n]->remaining_active_Mm3 + nodes[n]->upstream_remaining_active_Mm3);
```

**[usikkert]** Om denne akkumuleringen er korrekt ved forgreninger — der en node har flere nedstrøms
noder (tunnel til ett sted, overløp til et annet) — bør verifiseres numerisk. Løkken bruker kun
`ptr_downstream_node`, som settes til tunnelnoden hvis den finnes, ellers overløpsnoden
(`reservoir.cpp:1073-1081`). Vann som fysisk kan gå to veier telles derfor bare langs én. Dette er
et åpent punkt.

**2. Kun aktivt volum teller, og det er tak-klippet ved HRW** (`reservoir.cpp:663-676`):

```cpp
fract_filling = (res_Mm3 − V_LRW) / (V_HRW − V_LRW);
remaining_active_Mm3 = fract_filling · (V_HRW − V_LRW);
if (fract_filling > 1.0)  remaining_active_Mm3 = (V_HRW − V_LRW);   // tak ved HRW
if (fract_filling < 0.0)  remaining_active_Mm3 = 0.0;               // gulv ved LRW
```

Vann over HRW er verdt **null**. Det er et riktig insentiv (ikke la det flomme), men gjør objektivet
**ikke-deriverbart ved HRW**.

**3. Marginalverdien av vann er konstant.** Terminalleddet er lineært i terminallagringen mellom LRW og
HRW. Dette er den viktigste enkeltegenskapen for optimeringsvurderingen — se kapittel 11.

### Inkonsistens som må stå eksplisitt i en oppgave **[vurdering]**

Produksjonen **i** horisonten bruker fallhøydeavhengig fysikk: `P ∝ η(Q) · H_netto(nivå, Q) · Q`.
Terminalverdien bruker en **konstant** `e_n` fra topologifilen, som ikke avledes fra faktisk fallhøyde.

De to konverteringene er derfor inkonsistente. Fortegnet på biasen avhenger av om sluttnivået ligger
over eller under det nivået `e_n` er kalibrert for. For SVOLETJONN: `e = 0,11 kWh/m³`. Med
`η ≈ 0,90 · 0,96` og `H` mellom 58 og 67 m gir fysikken
`0,90 · 0,96 · 9,80665 · H / 3600 ≈ 0,137–0,158 kWh/m³` — altså **20–40 % høyere enn `e_n`**. Vann i
magasinet undervurderes systematisk i terminalleddet på denne instansen.

**[vurdering]** Dette er en reell modellbegrensning som må oppgis eksplisitt i en masteroppgave. Den
er også et opplagt angrepspunkt hvis den ikke nevnes.

## 9.5 Constraints — klassifisert

| Mekanisme | Type | Håndhevelse | Kilde |
|---|---|---|---|
| `a ∈ [0,1]` | **Hard — men på verste måte** | Brudd > 10⁻⁶ ⇒ `LOG_ERR` ⇒ **prosessen avsluttes** | `powerstation.cpp:136`, `reservoir.cpp:550` |
| `Q ≤ GENERATOR_MAX_DISCHARGE` | **Hard, strukturelt** | Følger av `Q = a·Qmax` og `a ≤ 1`. Kan ikke brytes. | `powerstation.cpp:132` |
| Aggressive actions (`Q_Mm3 > up_res_Mm3`) | **Straff + hard nullstilling** | Kostnad `(Q − tilgjengelig)·1000` **og** `flow = 0` | `powerstation.cpp:785-791` |
| `total_Q > up_inflow` | **Hard nullstilling, ingen kostnad** | All `Q` settes til 0 | `powerstation.cpp:145-153` |
| LRW-brudd | **Myk (straff)** | `RES_PENALTY · (Δt/3600) · (LRW − nivå)` | `reservoir.cpp:652` |
| HRW / flom | **Ingen skranke** | Nivået kan gå over HRW. Overløp regnes automatisk. Vann over HRW verdsettes til 0. | `reservoir.cpp:625`, `:672` |
| Magasinkapasitet (topp av kurve) | **Hard — prosessen avsluttes** | «Numerical instability, too much water» | `reservoir.cpp:418-424` |
| `POWSTAT_MIN_DISCHARGE` | **Kun advarsel** | Ingen kostnad, ingen effekt på produksjon | `powerstation.cpp:160-165` |
| Lukekapasitet `Qmax_hatch` | **Hard, strukturelt** | Følger av parametriseringen | `reservoir.cpp:564` |
| Lukens terskel `hatch_masl` | **Automatisk klipping** | Ingen slipp når nivået er under terskelen | `reservoir.cpp:562` |
| Start/stopp | **Myk (kostnad)** | `POWSTAT_STARTSTOP/2` per transisjon | `powerstation.cpp:256` |
| Kanal-`QMIN` | **Under utvikling — deaktivert** | Aktivering avslutter programmet | `channel.cpp:264` |
| `FLOODLEVEL_PENALTY` | **Ingen effekt** | Leses, brukes aldri | `reservoir.cpp:790` |
| `MAX_ADJUST` | **Under utvikling — deaktivert** | Positiv verdi avslutter programmet | `powerstation.cpp:420-424` |
| `OUTLET_AUTO_QMIN` | **Under utvikling — deaktivert** | Aktivering avslutter programmet | `reservoir.cpp:948-952` |
| Global vannbalanse | **Intern sanitetssjekk** | Avvik > 10⁻⁴ Mm³ ⇒ prosessen avsluttes | `herss.cpp:743-751` |
| Terminalverdi | **Ikke en skranke** | Lineært ledd i objektivet | `riversystem.cpp:474` |

### Den viktigste observasjonen **[vurdering]**

Det finnes **ingen** myk-men-lønnsom vei rundt de virkelig bindende skrankene: `a`-intervallet og
kapasitetene er strukturelt håndhevet, aggressive actions nullstiller produksjonen. Derimot finnes det
**to** typer straff som en søkealgoritme kan «kjøpe seg fri fra»:

1. **LRW-straffen.** `RES_PENALTY = 300` per meter per time. Ved høye priser kan det lønne seg å
   tappe under LRW. **Dette bør regnes ut for hvert datasett.**
2. **Start/stopp-kostnaden.** 2 EUR. Praktisk talt gratis.

Aggressive-action-straffen på 1000 EUR/Mm³ er derimot ikke «kjøpbar» i vanlig forstand, siden `flow`
også settes til null — man betaler og får ingenting.

**Derfor: enhver rapportering av resultater må ha en separat feasibility-tabell** ved siden av
objektivverdien. Å rapportere `V` alene ville være en metodisk feil, siden en metode kan vinne ved å
kjøpe brudd billig.

---

# 10. Kjente problemer og uferdige features

| Feature | Status | Kilde | Risiko | Konsekvens for optimeringsarbeid |
|---|---|---|---|---|
| **`LOG_ERR` ⇒ `std::exit`** | Design, men udokumentert | `logger.cpp:41`, `logger.h:78` | **Høy** | Enhver intern sjekk som slår ut dreper Python-prosessen med all søketilstand. Krever repair-operator eller prosessisolasjon. **Ikke nevnt i manualen.** |
| **PSTATION-starttilstand brukes ikke til start/stopp** | Dokumentasjonsavvik | Manual §State File vs. `powerstation.cpp:245-247` | **Middels** | Rullerende horisont får en liten, systematisk sømfeil (målt til 1 EUR / rel. 1,4·10⁻⁵). Vokser hvis start/stopp blåses opp. |
| **Kanal-`QMIN`** | Ufullstendig. Aktivering avslutter | `channel.cpp:264` | **Middels** | Minstevannføring i elv kan ikke brukes som skranke i det hele tatt. Fjerner en realistisk miljøbegrensning fra problemet. |
| **`OUTLET_AUTO_QMIN`** | Ufullstendig. Aktivering avslutter | `reservoir.cpp:948-952` | Lav | Automatisk miljøslipp fra magasin utilgjengelig. |
| **`MAX_ADJUST`** | Implementert, ikke kvalitetssikret. Positiv verdi avslutter | `powerstation.cpp:420-424` | Lav | Reguleringsstraff utilgjengelig. `CalcAdjustmenCosts` antar dessuten fast timesteg (`powerstation.cpp:806-808`). |
| **`FLOODLEVEL_PENALTY`** | Leses, brukes aldri | `reservoir.cpp:790`; ingen bruk i `src/` | **Middels** | Står i alle mini-datasett med verdien 300 og **ser bindende ut**. Flomstraff finnes ikke. Bare HRW-taket på verdsatt vann motvirker flom. |
| **Multigenerator start/slutt-tilstand** | Ikke implementert | Manual kap. 5 | **Middels** | Alle generatorer tvinges til samme tilstand ved horisontgrenser. Rammer rullerende horisont med flere generatorer. |
| **Variabelt tidssteg + start/stopp/adjust** | Delvis | Manual kap. 5; `powerstation.cpp:806-808` | **Middels** | **Fjerner «ulike temporale oppløsninger» som eksperimentakse så snart start/stopp er med i modellen.** |
| **`GENERATOR_MAX_DISCHARGE` vs. `POWSTAT_MAX_DISCHARGE`** | To nesten like navn | Manual kap. 5; `utahps_daily/topology_utahps.txt` | Lav–middels | `POWSTAT_MAX_DISCHARGE` står i uTAHPS-topologien, men **parses ikke** av `Powerstation::ReadNodeData`. Den er død tekst. Lett å tro at den binder. |
| **Duplisert VF-beregning** | Vedlikeholdsfelle | `riversystem.cpp:533,567,576,593` | Lav | Å skrive output har sideeffekt på objekttilstand. Les alltid returverdien fra `CalcVF()`. |
| **Aggressive actions: to kodeveier** | Uklar arkitektur | `powerstation.cpp:145-153` og `:785-791` | Lav–middels | Vei 2 gir ingen kostnad. Diagnosevariabelen `auto_qmin_m3s[t]` blir stående foreldet når vei 1 slår inn. |
| **Testnavn vs. terskel** | Kosmetisk, men kvalitetssignal | `test_runtime.cpp:16` («Under350ms») vs. `:22,71` (`0.75`) | Lav | Ytelsestesten håndhever 0,75 s, ikke 350 ms. |
| **`make test` krever `/usr/src/gtest`** | Miljøavhengighet | `Makefile:28,95-99` | Lav | Testsuiten kan ikke kjøres uten `libgtest-dev`. **Ikke kjørt i denne gjennomgangen.** |
| **`utahps_multires` mangler `output/`** | Pakkefeil | Målt | Lav | Det eneste datasettet for variabel oppløsning kan ikke skrive output. Én `mkdir` løser det. |
| **Ingen topologivalidering** | Kjent, dokumentert | Manual §Node Topology | **Middels** | Feil nummerering gir stille feil ruting — bidraget kommer ett tidssteg for sent. Ingen feilmelding. Bruk `gc.Diagnose()` og `DiagnoseRiversystemConfiguration()`. |
| **Ukjente nøkkelord ignoreres stille** | Inkonsistens | `channel.cpp:271-273` avviser; magasin/kraftstasjon gjør ikke | **Middels** | Skrivefeil i en magasin- eller kraftstasjonblokk oppdages ikke; parameteren beholder initialverdien. |
| **`ArrayCurve::x2y` returnerer `−10⁹` utenfor område** | Stille feilverdi | `arraycurve.cpp:170,199` | Lav–middels | Returnerer et stort negativt tall i stedet for å avbryte. Kan forplante seg. I praksis fanges de fleste tilfeller av `ValidateReservoirLevelMm3` først. |
| **Parallellisering** | Ikke implementert | Manual §Future Work | Lav | `Herss`-objekter er uavhengige, så parallellisering på scenarionivå bør være rett fram — men det er ikke gjort, og ikke testet. |
| **`GetRestPrice()`** | Stubb som avslutter | `herss.cpp:487` | Lav | Ikke kall den fra Python. |
| **`Riversystem::WriteSelectedOutputMatrix`** | Stubb som avslutter | `riversystem.cpp:97-102` | Lav | Ikke kall den. |
| **`src/routing.cpp`** | Ikke i Makefile | `Makefile:14-16` | Lav | Død kode. Erstattet av `cascadedreservoirs.cpp`. Kan forvirre. |
| **Y2038** | Kjent begrensning | `herss.h:232-233` | Ingen | `time_t` brukes til epoch. Ikke relevant for datasettene. |

## Hva som *ikke* er et problem

Verdt å si eksplisitt, siden det var rimelige bekymringer:

- **Determinisme og reset:** bit-identisk, verifisert **[målt]**.
- **Vannbalanse:** lukker til null på alle testede datasett **[målt]**.
- **`CalcVF` vs. `WriteRiverSystemData`:** numerisk enige bit for bit **[målt]**.
- **`restprice` utenfor prisområdet:** nei, ligger midt i fordelingen overalt **[målt]**.
- **Ytelse:** ikke en flaskehals, forutsatt in-process og uten filskriving **[målt]**.
- **Rullerende horisont:** kjeder til relativ feil 10⁻⁵ **[målt]**.

---

# 11. Relevans for en masteroppgave i optimering

## 11.1 Fire spørsmål som må holdes fra hverandre

Dette er den viktigste distinksjonen i hele rapporten.

| # | Spørsmål | Svar | Status |
|---|---|---|---|
| 1 | Kan repoet bygges og kjøres? | Ja. `make` gir `herss.exe` og `herss.so`; CLI og Python-orakel verifisert. | **Avklart** |
| 2 | Er simulatoren et brukbart evalueringsorakel? | Ja. Deterministisk, eksakt resettbar, rask, kallbar fra Python. | **Avklart** |
| 3 | Inneholder datasettene et ikke-trivielt optimeringsproblem? | Delvis. Avhenger kritisk av instansvalg. | **Delvis avklart — se 11.3** |
| 4 | Finnes det et tydelig, originalt og gjennomførbart masterbidrag? | **Ikke avklart.** Se 11.4. | **Åpent** |

At 1 og 2 er positive sier **ingenting** om 3 og 4. En oppgave som stopper ved «jeg fikk simulatoren til
å kjøre og skrev en genetisk algoritme» har ikke et bidrag.

## 11.2 Hva er egentlig optimeringsproblemet?

$$
\max_{a \in [0,1]^{G \times T}} \; V(a)
$$

der `G` = antall generatorer + antall aktive luker. Bokseskranker, kontinuerlige variabler, ingen
eksplisitte lineære skranker — all fysikk og alle skranker er begravd i simulatoren.

Formelt er dette **boks-begrenset svart-boks-optimering**. Det er en dårlig ramme å angripe det i, av
to grunner: (a) dimensjonen er for høy (30 til 35 040), og (b) man kaster bort all kjent struktur.

## 11.3 Hvor kommer vanskeligheten fra — og hvor kommer den ikke fra?

### Tidskobling

**Kilde: magasinvolumet.** Det er den eneste tilstanden som bærer økonomisk verdi over tid. Vann brukt
i time `t` er ikke tilgjengelig i time `t+1`.

**Sekundær kilde: kanalforsinkelsen.** Vann som slippes ved `t` ankommer nedstrøms magasin fordelt over
flere senere tidssteg. Det gjør kaskadekoblingen ikke-triviell.

**Ikke-kilde: driftstilstand.** Start/stopp-kostnaden er så lav (2 EUR, totalt 5–42 EUR per horisont) at
den knapt kobler tidsstegene i praksis.

### Ikke-linearitet

| Kilde | Størrelsesorden |
|---|---|
| Fallhøydeavhengig produksjon | **13,4 % (DP-instans) til 46,5 % (EASTER)** |
| Ikke-konkave turbinkurver | 5,4–10,9 % virkningsgradsspenn |
| Kvadratisk falltap `k·Q²` | Ved SVOLETJONN: `0,3·16 = 4,8 m` av 58–67 m ≈ **7–8 %** ved full last |
| Bilinearitet `H_netto · Q` | Grunnleggende |
| Kanalruting | **Lineær** — den eneste delen som ikke bidrar |

### Diskontinuitet

**Hovedkilden er aggressive-action-klippet**, ikke enhetsforpliktelsen. Ved `Q_Mm3 > up_res_Mm3`
faller produksjonen fra tilnærmet maksimal til null i ett sprang. Det er en ekte diskontinuitet i
objektivet, og det gjør gradientbaserte metoder og naiv lokalsøk problematiske i nærheten av tomme
magasin.

**[målt]** Under de leverte `actions.txt` er `sum_aggressive_actions_cost = 0.000` på **alle 11
kjørbare datasett**. Klippet er altså **latent**: referansepolitikkene rører det aldri, men enhver
søkealgoritme som øker vannføringen vil treffe det.

**[vurdering]** Dette er den mest opplagte plassen for et **problemspesifikt algoritmisk bidrag**: en
repair-operator som klipper actions mot tilgjengelig volum før evaluering dominerer det å stole på
straffen. Den er billig, den er velbegrunnet, og den er nødvendig uansett for å unngå
`std::exit`-problemet.

### Er problemet for enkelt på noen datasett?

**Ja, og det må sies rett ut.**

- `res_casc_B`, `res_casc_D`: `V ≡ 0`. Ikke et optimeringsproblem i det hele tatt.
- Alle time-baserte mini-sett: `R = 13`. Lagringen binder ikke. Kjør på når prisen er høy, av når den
  er lav — det er hele løsningen.
- `mini_utahps_daily`: `R = 0,87`. Lagringen binder. Dette er den minste instansen som faktisk
  inneholder et problem.

## 11.4 Den sentrale trusselen mot oppgaven **[vurdering]**

**Marginalverdien av vann er konstant.** Terminalleddet er lineært i terminallagringen (mellom LRW og
HRW). Kombinert med:

- én deterministisk prisserie,
- perfekt framsyn,
- ingen usikkerhet,

følger det at optimum ligger **strukturelt nær en terskelregel**: produser når `p_t · e_n` overstiger
alternativkostnaden for vann, lagre ellers.

Alt som gjør dette til et *vanskelig* optimeringsproblem er en **perturbasjon** av den regelen:

| Perturbasjon | Målt størrelse |
|---|---|
| Fallhøydeavhengighet | 13,4–46,5 % |
| Turbinkurvens beste driftspunkt (partiell last lønner seg) | 5,4–10,9 % |
| Kvadratisk falltap | ~7–8 % ved full last |
| Spillunngåelse (HRW-knekk) | Binder når `R < 1` |
| Kaskadeforsinkelse | Timer til dager |
| Aggressive-action-klippet | Diskontinuerlig |
| Start/stopp | **~0,001–0,01 % — neglisjerbar** |

**Den avgjørende målingen som ennå ikke er gjort:** løs `mini_utahps_daily` eksakt med dynamisk
programmering over diskretisert lagring og handling, og sammenlign mot en tunet terskelpolitikk.

- **Gap under ~1 %:** formuleringen er ennå ikke en masteroppgave. Bindende struktur må legges til
  (terminallagringsskranke, rampebegrensninger, flere generatorer med reell forpliktelse) før man
  binder seg.
- **Gap over ~3 %:** det finnes et problem verdt å løse.

**[vurdering]** Uten denne målingen er hele oppgaven bygget på en antakelse. Den bør gjøres først, og
den er billig: ~500 lagringsnivåer × ~50 handlinger × 30 tidssteg ≈ 750 000 enkelttrinns overganger.
Men merk: HERSS eksponerer kun `Simulate()` over **hele** horisonten — det finnes ingen
enkelttrinns-API. En DP må derfor bruke en **ekstern replika** av overgangsfunksjonen (~9 funksjoner
fra `reservoir.cpp`, `powerstation.cpp`, `riversystem.cpp`), og den replikaen må valideres mot HERSS.
Det er i seg selv en jobb, og en risiko.

## 11.5 Er eksakte metoder mulig på små instanser?

**Ja, på `mini_utahps_daily`.** Tilstanden er endimensjonal: magasinvolum. Kanalen er terminal og
uvurdert, altså droppbar. Driftstilstanden betyr nesten ingenting fordi start/stopp er neglisjerbar.

Fallgruven som må håndteres **[kilde]**: fallhøyden bruker **gjennomsnittet** av nivået ved start og
slutt av tidssteget, og sluttnivået avhenger av handlingen. Overgangen må regnes i riktig rekkefølge:
nivå før → uttak → nivå etter → snitt → effekt. Gjør man det feil, avviker replikaen systematisk fra
HERSS.

På `utahps_daily` (4 magasin) er eksakt DP utelukket — tilstandsrommet er 4-dimensjonalt pluss
kanaltilstander.

## 11.6 Er heuristikker eller metaheuristikker faglig begrunnet?

**Spørsmålet må stilles i riktig rekkefølge.** Før man foreslår en metaheuristikk, må man svare:

| Metode | Kan den løse dette adekvat? |
|---|---|
| **Terskelregel** | Trolig svært nær optimum, gitt konstant marginalverdi. **Må måles.** Dette er baseline nr. 1. |
| **LP/MILP på en linearisert modell** | Kanalrutingen er allerede lineær. Fallhøydeavhengighet krever suksessiv linearisering eller stykkevis-lineær approksimasjon. Start/stopp gir binærvariabler (men biter knapt). Realistisk. |
| **Eksakt DP** | Ja, på énmagasininstansen. Gir en referanse ingen heuristikk kan overgå. |
| **Grådig / lokalsøk i redusert rom** | Trolig sterk, gitt problemets nesten-terskelstruktur. |
| **Generisk GA / SA / PSO** | **Ikke begrunnet uten videre.** 30–35 040 dimensjoner, ingen utnyttelse av kjent struktur, ingen konvergensgaranti. |

**[vurdering]** «Sammenlign flere hyllevare-metaheuristikker» er et svakt bidrag. Det svarer på et
spørsmål ingen har stilt, og resultatet avhenger mer av parametertuning enn av problemet. Hvis en
metaheuristikk skal inn, må den ha **problemspesifikke komponenter**: en repair-operator for
aggressive actions, suksessiv linearisering over fallhøyde, fix-and-optimize på driftsvariabler.

**Dekomponeringsargument [vurdering]:** siden orakelet gir ~16 000 ev/s på små instanser, men bare 21
ev/s på den store, er **reduksjon av beslutningsrommet en forutsetning, ikke en senere forbedring**.
Mot 35 040 variabler er 1,8 millioner evalueringer per døgn ingenting. Mot en redusert
parametrisering på 50–500 parametre er det rikelig.

## 11.7 Risiko for scope-drift

| Drift-retning | Risiko | Hvorfor den truer |
|---|---|---|
| **Hydrologisk modellering** | Middels | Fristelsen til å «forbedre» rutingen eller kalibrere tilsig. Er ikke optimering. |
| **Simulatorutvikling** | **Høy** | Mange uferdige features (`QMIN`, `MAX_ADJUST`, `FLOODLEVEL_PENALTY`, `AUTO_QMIN`) inviterer til å «bare fikse det». Hver fiks gjør resultatene uforenlige med den pinnede upstream-tilstanden. |
| **Datavask** | Middels | 12 datasett, delvis duplikater, ett med manglende katalog, uklart hvilket inputformat som er kanonisk. Kan sluke uker. |
| **Debugging** | **Høy** | `std::exit`-oppførselen tvinger fram defensiv koding. Uten disiplin blir dette hovedaktiviteten. |
| **Software engineering** | Middels | Å bygge et «rammeverk» rundt HERSS i stedet for å svare på et forskningsspørsmål. |

**Motmiddel [vurdering]:** hold `src/` pinnet og urørt (som `CLAUDE.md` allerede krever), legg all
oppgavekode i et separat tre som kun *kaller* simulatoren, og logg upstream-commit + `VERSION` i hver
eneste kjøring.

## 11.8 Er den foreslåtte strukturen realistisk?

Den foreslåtte strukturen var:

1. etablere enkle og sterke baselines
2. lage en eksakt eller nær-eksakt referanse for små instanser
3. utvikle en problemspesifikk heuristikk eller matheuristikk
4. evaluere under samme tids- eller evalueringsbudsjett
5. analysere kvalitet, robusthet og skalerbarhet

**[vurdering] Ja, med to forbehold:**

**Forbehold 1 — rekkefølgen må snus i starten.** Steg 2 (eksakt referanse på `mini_utahps_daily`) og
en tunet terskelpolitikk fra steg 1 må gjøres **før** man binder seg til tema. Gapet mellom dem er
go/no-go-målingen. Å utvikle en matheuristikk før man vet at det finnes et gap å lukke, er å bygge på
sand.

**Forbehold 2 — «samme tidsbudsjett» er ikke godt nok.** Sammenligninger må bruke **likt antall
simulatorevalueringer**, ikke bare lik veggklokketid. Ellers måler man kompilatorflagg (husk:
Makefile bygger i debug-modus), ikke algoritmer. Antall evalueringer må rapporteres sammen med hvert
resultat.

**Tillegg som ville styrke oppgaven vesentlig [vurdering]:**

- **Steg 0:** kvantifiser hva som faktisk gjør problemet vanskelig — separer bidraget fra
  fallhøydeavhengighet, turbinkurve, spill og kaskadeforsinkelse. Det er et resultat i seg selv, og det
  er sant uansett hvor godt noen algoritme presterer.
- **En separat feasibility-tabell** ved siden av hvert objektivtall.
- **Eksplisitt angivelse** av hvilke skranker som behandles som harde (håndhevet ved repair i
  søkeoperatorene) og hvilke som er myke.

## 11.9 Samlet vurdering

**HERSS er et brukbart evalueringsorakel.** Det er verifisert, ikke antatt.

**Datasettene inneholder et ikke-trivielt optimeringsproblem — men bare noen av dem.** Fem av tolv er
enten degenererte eller for lette. Instansvalget er ikke en detalj; det avgjør om oppgaven har noe å
jobbe med.

**Om det finnes et masterbidrag avhenger av én måling som ennå ikke er gjort:** gapet mellom eksakt DP
og en tunet terskelpolitikk på `mini_utahps_daily`. Under ~1 % må formuleringen styrkes før man binder
seg. Over ~3 % er det et problem verdt å løse.

**Den mest lovende innrammingen [vurdering]:** ikke «optimer denne instansen», men «hvor mye
økonomisk verdi går tapt når en linearisert modell evalueres i en ikke-lineær simulator, og kan en
matheuristikk med simulatoren i løkken hente det inn?» Lineariseringsgapet er en **målbar størrelse** —
det er et resultat uavhengig av hvor godt noen algoritme presterer. Det er forskjellen mellom et
prosjekt og et bidrag.

**Metodisk forbehold som må formuleres presist:** MILP-optimum begrenser den **lineariserte** modellen,
ikke det sanne optimum. Enhver simulator-feasible løsning er en nedre skranke på det sanne optimum. Å
klemme det sanne optimum mellom dem krever å begrense lineariseringsfeilen, hvilket ikke kan gjøres
strengt generelt — kun måles empirisk med DP på små instanser. Upresishet på dette punktet er det
opplagte angrepspunktet.

---

# 12. Spørsmål du bør stille hydrologen

## A. Må avklares FØR valg av mastertema

Disse endrer hva oppgaven kan handle om.

1. **Er en konstant marginalverdi av vann (`restprice` × konstant `LOCAL_ENERGY_EQUIVALENT`) noe
   Å Energi faktisk bruker, eller er det en forenkling i HERSS?** Hvis dere i praksis bruker en
   nivåavhengig vannverdikurve, blir problemet vesentlig rikere — og oppgaven mer relevant. Hvis
   ikke, må jeg forholde meg til at optimum ligger nær en terskelregel.
2. **Hvilke driftsbegrensninger er faktisk bindende i daglig drift?** HERSS har i praksis bare
   LRW-straff, kapasiteter og et aggressive-action-klipp. Reelle begrensninger jeg mistenker mangler:
   minstevannføring, rampebegrensninger, manøvreringsreglement, terminale magasinkrav. Hvilke av dem
   binder mest?
3. **`POWSTAT_STARTSTOP = 2.0` EUR i alle datasett gir 5–42 EUR over en hel horisont, mot
   verdifunksjoner på 25 000 til 31 millioner. Er dette realistisk, eller er det en plassholder?** Hvis
   den reelle start/stopp-kostnaden er størrelsesordener høyere, endrer det problemets diskrete
   struktur fullstendig.
4. **Hvilket datasett er mest representativt for en reell driftsbeslutning?** Jeg vurderer
   `mini_utahps_daily` som eksakt referanse og `utahps_daily`/`utahps_hourly` som benchmark. Er det
   riktig prioritering? Finnes det data for et virkelig vassdrag jeg kan bruke?
5. **Er `LOCAL_ENERGY_EQUIVALENT` kalibrert mot et bestemt magasinnivå?** Jeg regner ut at fysikken gir
   0,137–0,158 kWh/m³ for SVOLETJONN, mens topologifilen sier 0,11. Er avviket tilsiktet, og hvordan
   settes verdien i praksis?
6. **Hvilke deler av HERSS er dere mest trygge på?** Manualen lister `QMIN`, `MAX_ADJUST`,
   `FLOODLEVEL_PENALTY`, `OUTLET_AUTO_QMIN` og multigenerator-tilstand som ufullstendige. Er det
   noe *annet* dere ikke ville stolt på?
7. **Hva ville gjøre optimeringsresultater faktisk nyttige for Å Energi?** Bedre planer for et gitt
   vassdrag? Kvantifisering av hva dagens lineære planleggingsmodeller taper? En metode dere kan
   gjenbruke? Svaret bør styre innrammingen.

## B. Kan avklares senere

8. `RES_PENALTY = 300` per meter per time — er dette en realistisk kostnad, eller et rent
   numerisk knep? (Jeg må regne ut om det lønner seg å bryte LRW ved høye priser.)
9. `HERSS_AGGRESSIVE_ACTIONS_COST = 1000` EUR/Mm³ — er tallet begrunnet? Kildekommentaren tyder på at
   det bare er ment å bryte platåer i verdifunksjonen.
10. Hvilket inputformat er kanonisk framover — `RESERVOIR_CURVE` eller `RESERVOIR_GEOMETRY`,
    `OVERFLOW_CURVE` eller `SPILLWAY`? Datasettnavnene `new_format` og `new_inputformat` tyder på en
    pågående migrasjon.
11. Er `K_TRAVELTIME_HOURS` og `N_CASCADE_LINRES` i uTAHPS kalibrerte, eller plausible gjetninger?
    Dette avgjør om kaskadeforsinkelsen er en realistisk eller en kunstig del av problemet.
12. Er én felles prisserie for hele vassdraget en akseptabel forenkling?
13. Hvor mye endrer tilsigsprognosefeilen seg over 1 døgn / 1 uke? (Relevant hvis jeg gjør rullerende
    horisont med prognosefeil.)
14. Finnes det en realistisk terminalverdikrav på magasinene ved horisontens slutt? Det ville legge
    til bindende struktur som problemet i dag mangler.

## C. Ikke nødvendig hvis oppgaven holdes algoritmisk

15. Kalibrering av tilsigsserier og magasinkurver mot faktiske målinger.
16. Hydraulisk realisme i falltapskoeffisienten `HEADLOSSCOEF`.
17. Nøyaktigheten i turbinvirkningsgradskurvene mot fabrikantdata.
18. Om spillway-koeffisientene (`C`, `L`) er fysisk riktige.
19. Om Nash-kaskaden er riktig rutingmodell for disse elvestrekningene.

**[vurdering]** Punktene i C er hydrologi, ikke optimering. Å gå inn i dem er den raskeste veien til
scope-drift. Bruk dem som bakgrunn, ikke som arbeidsoppgaver.

---

# 13. Kort møteforberedelse

## HERSS på 8 setninger

HERSS er en deterministisk simulator for et regulert vassdrag med vannkraft, skrevet i C++ og
MIT-lisensiert, eid av Å Energi. Du gir den en topologi av magasin, kraftstasjoner og elvestrekninger,
tidsserier for tilsig og kraftpris, en starttilstand, og en plan for hvor mye hver generator skal kjøre
i hvert tidssteg. Den simulerer vassdraget tidssteg for tidssteg og gir tilbake ett tall:
verdifunksjonen — inntekter minus kostnader, pluss verdien av vannet som står igjen. Den optimerer
ikke; den evaluerer. Den kan kalles fra Python via cppyy, den er deterministisk og resetter seg selv
mellom kjøringer, og den evaluerer 16 000 planer i sekundet på den minste instansen. Det gjør den til
et brukbart evalueringsorakel for en optimeringsalgoritme. De interessante ikke-linearitetene er
fallhøydeavhengig produksjon, ikke-konkave turbinkurver, kvadratisk falltap og transportforsinkelse i
elvene. Flere features i modellen er ufullstendige og må ikke brukes.

## De viktigste inputene

| Fil | Hva den bestemmer |
|---|---|
| `topology.txt` | Hele systemets fysikk: magasinkurver, LRW/HRW, turbinkurver, kapasiteter, forsinkelser |
| `pricefile.txt` | Prisserie + `RESTPRICE` (vannverdi ved horisontslutt) + **antall tidssteg og Δt** |
| `inflowseries.txt` | Tilsig per magasin [m³/s] |
| `actions.txt` | **Beslutningsvariablene** |
| `start_state.txt` | Magasinfyllinger, vann i elvene, forrige produksjon |

## De viktigste actions

- **Én per generator per tidssteg**, `a ∈ [0,1]`, gir `Q = a · Q_max`
- **Én per aktiv magasinluke per tidssteg**, `a ∈ [0,1]`, gir `Q = Qmin + a·(Qmax − Qmin)`

Kolonnenavn i `actions.txt`: `1_0` = node 1, generator 0. `0` (uten understrek) = luke i node 0.

## Objektivfunksjonen

```
V = (sum inntekter − sum kostnader)  +  restprice · Σ_kraftstasjoner (e_n · aktivt vann oppstrøms · 1000)
```

- Terminalleddet er **kaskadebevisst** — vann oppstrøms for flere kraftverk telles per kraftverk
- Kun vann mellom LRW og HRW verdsettes; vann over HRW er verdt null
- `e_n` er en **konstant** fra topologifilen, mens produksjonen i horisonten er **fallhøydeavhengig** —
  en systematisk inkonsistens
- **Marginalverdien av vann er konstant** — dette er det viktigste å diskutere med hydrologen

## De største tekniske risikoene

1. **`LOG_ERR` avslutter hele prosessen** — ingen exception. En action utenfor `[0,1]` eller et
   magasin over kurvens topp dreper Python-økten. Krever repair-operator uansett.
2. **Flere features er ufullstendige og avbryter ved bruk:** kanal-`QMIN`, `MAX_ADJUST`,
   `OUTLET_AUTO_QMIN`. `FLOODLEVEL_PENALTY` leses men brukes aldri.
3. **Start/stopp-kostnaden er neglisjerbar** (5–42 EUR mot 25k–31M). Enhetsforpliktelse har nesten
   ingenting å bite på.
4. **Fem av tolv datasett er degenererte eller for lette.** `res_casc_B`/`D` har ingen kraftstasjon →
   `V ≡ 0`.
5. **Ingen topologivalidering.** Feil nodenummerering gir stille feil ruting.
6. **`.gitignore` linje 26 er `data/*`** — nye datasett under `data/` blir usporet, og hver kjøring
   skitner arbeidstreet.
7. **Manualen avviker fra koden** på minst to punkter som betyr noe: PSTATION-starttilstand brukes
   ikke til start/stopp, og aggressive actions gir ikke det «sterke gradientsignalet» manualen lover.

## De viktigste optimeringsmulighetene

1. **Måle lineariseringsgapet** — hvor mye tapes når en linearisert MILP-plan evalueres i den
   ikke-lineære simulatoren? Dette er et resultat uavhengig av algoritmeytelse.
2. **Eksakt DP på `mini_utahps_daily`** som referanse ingen heuristikk kan overgå.
3. **Repair-operator for aggressive actions** — et velbegrunnet, problemspesifikt algoritmisk bidrag
   som også løser `std::exit`-problemet.
4. **Suksessiv linearisering over fallhøyde** i en matheuristikk med simulatoren i løkken.
5. **Reduksjon av beslutningsrommet** — nødvendig, ikke valgfritt, gitt 35 040 variabler på den store
   instansen.

## De 8 spørsmålene du absolutt bør stille

1. Er konstant marginalverdi av vann noe dere faktisk bruker, eller en forenkling i HERSS?
2. Hvilke driftsbegrensninger binder faktisk i daglig drift — og hvilke mangler i HERSS?
3. Er `POWSTAT_STARTSTOP = 2 EUR` realistisk, eller en plassholder?
4. Hvilket datasett er mest representativt for en reell driftsbeslutning?
5. Hvordan settes `LOCAL_ENERGY_EQUIVALENT` i praksis — og er den kalibrert mot et bestemt nivå?
6. Hvilke deler av HERSS ville dere selv ikke stolt på?
7. Finnes det realistiske terminalkrav på magasinfylling ved planhorisontens slutt?
8. Hva ville gjøre optimeringsresultater faktisk nyttige for Å Energi?

## Én setning å avslutte møtet med

> «Simulatoren fungerer og er brukbar som orakel — det har jeg verifisert. Det jeg trenger hjelp til å
> avgjøre, er om problemet den definerer er hardt nok til å bære en masteroppgave, eller om optimum
> ligger så nær en enkel terskelregel at bidraget må komme fra noe annet.»

---

## Vedlegg: proveniens og reproduserbarhet

**Gjennomgått versjon:** HERSS `VERSION 3.1.03`, `VERSION_DATE 20260611` (`src/herss.h:49-50`),
upstream commit `029a2d5`.

**Metode:** hele repoet lest read-only. Ingen filer endret, ingen simuleringer kjørt i denne
gjennomgangen. Alle `fil:linje`-referanser er verifisert mot kilden.

**Målte tall** er hentet fra `analysis/herss_benchmark_report.md`, som dokumenterer kjøringer med samme
versjon og commit, via repoets `.venv` (Python 3.13.11, cppyy 3.5.0) mot `src/herss.so`, og
`src/herss.exe` mot de leverte datasettene.

**Byggemerknad:** `src/Makefile` setter `CFLAGS` tre ganger; den siste (`-Wall -g -pedantic -fPIC`)
vinner. Alle ytelsestall er derfor fra en debug-build og er konservative.

**Ikke gjennomført:** gtest-suiten (`make test`) — krever `libgtest-dev` i `/usr/src/gtest`, som ikke
finnes på denne maskinen. Suiten består av 11 filer og ~95–100 tester.

**Åpne punkter som bør verifiseres numerisk:**

1. Akkumulerer `upstream_remaining_active_Mm3` korrekt gjennom DAG-en ved forgreninger — ingen
   dobbelttelling, ingen utelatte sideelver? (`herss.cpp:685-694`)
2. Overstiger `HERSS_AGGRESSIVE_ACTIONS_COST = 1000` EUR/Mm³ faktisk inntekten man kunne fått ved å
   bryte ved høye priser?
3. Lønner det seg å bryte LRW ved `RES_PENALTY = 300` per meter per time, gitt de faktiske prisene?
4. Stemmer en ekstern enkelttrinns-replika av overgangsfunksjonen med HERSS bit for bit? (Nødvendig for
   eksakt DP.)
5. Hvor nær kommer de leverte `actions.txt` til aggressive-action-terskelen? (Fordelingen av
   `Q_Mm3 / up_res_Mm3` er ikke beregnet.)
