Du skal opptre som en grundig, kritisk og presis researcher med ansvar for å undersøke hele HERSS-repositoriet.

Målet er å gi meg en enkel, men samtidig grundig og oversiktlig introduksjon til:

1. repositoriet,
2. HERSS-modellen,
3. datastrukturen,
4. hvordan simuleringen fungerer,
5. hvilke beslutningsvariabler som finnes,
6. hvilke outputs og objective values modellen gir,
7. og hvordan prosjektet potensielt kan brukes som grunnlag for en masteroppgave i optimering.

Kontekst:
Jeg vurderer å bruke HERSS som simulator eller evalueringsmotor i en masteroppgave innen optimering / Operations Research. Jeg skal snart ha en samtale med en erfaren hydrolog på jobb for å diskutere om dette kan bli en god optimeringsoppgave.

Det er derfor svært viktig at jeg forstår hele repoet og modellen godt nok til å kunne forklare:

- hva HERSS faktisk gjør,
- hvilke data modellen trenger,
- hvordan systemet simuleres,
- hvilke handlinger som kan optimeres,
- hvilke begrensninger og kostnader som finnes,
- og hvilke deler av modellen som er stabile, uferdige eller risikable.

Viktig faglig avgrensning:
Dette skal først og fremst vurderes som et mulig OPTIMERINGSPROBLEM.

Ikke gjør rapporten til en detaljert hydrologisk lærebok. Forklar hydrologiske, hydrauliske og krafttekniske begreper bare så langt det er nødvendig for å forstå:

- beslutningsproblemet,
- tilstandsutviklingen,
- objective function,
- constraints,
- simulatorens oppførsel,
- og hvilke konsekvenser dette har for optimeringsalgoritmer.

Arbeidsmåte

Start med å undersøke repositoriet uten å endre noen filer.

Du skal:

- lese hele mappestrukturen,
- lese README-filer,
- lese Makefile,
- lese sentrale C++-header- og kildefiler,
- lese Python-grensesnittet og eksempelprogrammene,
- undersøke testene,
- lese dokumentasjonen under `doc/` nøye,
- og undersøke alle datasett under `data/`.

Dokumentasjonen under `doc/` er spesielt viktig. Ikke bare skum gjennom den. Sammenlign dokumentasjonen med kildekoden der det er relevant, fordi dokumentasjonen kan være ufullstendig eller avvike fra implementasjonen.

Ikke gjør noen av følgende uten at jeg eksplisitt ber om det:

- ikke rediger filer,
- ikke refaktorer kode,
- ikke opprett nye filer,
- ikke installer pakker,
- ikke kjør destruktive kommandoer,
- ikke commit eller push,
- ikke endre Makefile,
- ikke endre datasett,
- ikke «fikse» oppdagede problemer.

Du kan lese filer og kjøre ufarlige inspeksjonskommandoer. Dersom du ønsker å kjøre simuleringer eller tester, forklar først nøyaktig hva du vil kjøre og hvorfor.

Krav til presisjon

Skill tydelig mellom:

- fakta lest direkte fra dokumentasjon eller kode,
- resultater fra faktisk kjøring,
- faglige vurderinger,
- antakelser,
- og usikkerhet.

Ikke gjett dersom repoet ikke gir et klart svar.

Når du beskriver en viktig funksjon, oppgi filsti og relevante linjer eller funksjonsnavn, for eksempel:

- `src/herss.cpp`
- `src/powerstation.cpp`
- `src/reservoir.cpp`
- `src/riversystem.cpp`
- `src/globalconfig.cpp`
- `py_src/pyherss.py`

Dersom dokumentasjon og kode motsier hverandre, skal dette fremheves eksplisitt.

Rapporten skal skrives på norsk.

Ønsket struktur på rapporten

# 1. Kort oppsummering

Gi først en kort og forståelig forklaring på:

- hva HERSS er,
- hva det ikke er,
- hva modellen simulerer,
- og hvorfor den kan være relevant for en optimeringsoppgave.

Forklar dette slik at en person med teknisk bakgrunn, men begrenset erfaring med hydropower-modellering, kan forstå det.

# 2. Repositoriets struktur

Gå gjennom alle viktige mapper og filer.

Forklar kort formålet med:

- `src/`
- `src_tests/`
- `py_src/`
- `doc/`
- `data/`
- `README.md`
- `Makefile`
- andre relevante filer eller mapper

Ikke bare list filene. Forklar hvordan delene henger sammen.

Lag gjerne en enkel tekstbasert oversikt over arkitekturen.

# 3. Hvordan HERSS fungerer på høyt nivå

Forklar hele simuleringsflyten fra start til slutt:

1. hvilke konfigurasjonsfiler som leses,
2. hvordan topologien bygges,
3. hvordan tidsserier lastes,
4. hvordan initial state settes,
5. hvordan hvert tidssteg simuleres,
6. hvordan vann flyttes mellom noder,
7. hvordan kraftproduksjon og kostnader beregnes,
8. hvordan output og value function beregnes.

Hold forklaringen enkel, men ikke overflatisk.

Forklar sentrale begreper som:

- node,
- reservoir,
- power station,
- channel,
- topology,
- state,
- action,
- inflow,
- price,
- reservoir filling,
- head,
- discharge,
- production,
- profit,
- remaining water value,
- value function.

Forklar kun den hydrologiske eller fysiske betydningen som er nødvendig for å forstå modellen.

# 4. Modellens komponenter

Forklar hver nodetype separat:

## Reservoir

Forklar:

- hvilken state magasinet har,
- hvilken input det mottar,
- hvilke outlets som finnes,
- hvordan tunnel, hatch og overflow fungerer,
- hvilke begrensninger eller straffekostnader som finnes,
- hvilke actions som kan påvirke magasinet,
- og hvilken betydning dette har for optimering.

## Power station

Forklar:

- hvordan en kraftstasjon mottar vann,
- hvordan action oversettes til vannføring,
- hvordan head og virkningsgrad påvirker produksjonen,
- hvordan flere generatorer håndteres,
- hvilke kostnader og penalties som finnes,
- hvordan start/stopp håndteres,
- og hvilke deler som kan gi ikke-linearitet eller diskontinuitet.

## Channel

Forklar:

- hvorfor channel-noder finnes,
- hvordan routing og delay fungerer,
- om channel state påvirker objective function direkte eller indirekte,
- hvilke constraints som finnes,
- og hvilke features som ikke er ferdige.

# 5. Alle inputfiler

Dette er svært viktig.

Finn og forklar alle typer inputfiler som HERSS bruker.

For hver filtype skal du beskrive:

- formålet,
- formatet,
- hver kolonne eller parameter,
- hvilke objekter i modellen som bruker dataene,
- og hvordan filen påvirker simuleringen eller optimeringsproblemet.

Forklar minst:

## `global.txt`

Forklar hver setting og filreferanse.

## `topology.txt`

Forklar:

- nodeblokkene,
- node-ID,
- rekkefølgen på noder,
- forbindelser mellom noder,
- alle viktige parametere for reservoir, power station og channel,
- og hvilke parametere som potensielt fungerer som constraints eller modellparametere.

## `pricefile.txt`

Forklar:

- tidsstempler,
- priser,
- `RESTPRICE`,
- hvordan tidsoppløsningen bestemmes,
- og hvordan prisene inngår i objective function.

## `inflowseries.txt`

Forklar:

- hvilke noder som mottar tilsig,
- kolonnene,
- enhetene,
- tidskoblingen,
- og hvilken rolle tilsiget har i optimeringsproblemet.

## `actions.txt`

Forklar svært nøye:

- hvilke kolonner som representerer hvilke beslutninger,
- forskjellen mellom kraftstasjons-actions og hatch-actions,
- hvordan generatorindekser angis,
- intervallet `[0,1]`,
- og hvordan en action påvirker faktisk vannføring eller produksjon.

## `start_state.txt`

Forklar:

- state for reservoir,
- state for power station,
- state for channel,
- hvordan state brukes ved oppstart,
- og hvordan state chaining eller rolling horizon kan gjennomføres.

Bruk korte eksempler fra faktiske filer i repoet.

# 6. Alle outputfiler

Forklar alle outputtyper og hva de inneholder.

Forklar minst:

- node output files,
- reservoir filling output,
- river system summary,
- `outstate.txt`,
- loggfiler,
- value function,
- total income,
- total cost,
- total profit,
- remaining water value,
- water balance,
- penalties,
- overflow,
- produksjon og vannføring.

Forklar hvilke outputs som er mest relevante for:

- evaluering av en kandidat-løsning,
- debugging,
- feasibility-kontroll,
- og sammenligning av optimeringsalgoritmer.

# 7. Gjennomgang av alle datasett under `data/`

Gå gjennom alle mapper under `data/`.

For hvert datasett skal du lage en kort, standardisert oversikt med:

- navn,
- antall tidssteg,
- tidsoppløsning,
- antall reservoir-noder,
- antall kraftstasjoner,
- antall channel-noder,
- antall generatorer,
- antall action-kolonner,
- hvilke spesielle features datasettet tester,
- om det har et økonomisk objektiv,
- om det virker relevant som optimeringsbenchmark,
- og eventuelle svakheter.

Forklar blant annet forskjellene mellom:

- mini-datasett,
- daglige datasett,
- timebaserte datasett,
- multiresolution-datasett,
- cascade-datasett,
- spillway-eksempler,
- multi-generator-eksempler,
- og full uTAHPS.

For hver datafil i hvert datasett:

- forklar hva filen inneholder,
- hvilke kolonner som finnes,
- og hvordan den skiller seg fra tilsvarende fil i andre datasett.

Du trenger ikke skrive ut alle rader. Forklar strukturen, innholdet og de viktigste forskjellene.

Vær spesielt kritisk til datasett som:

- mangler kraftstasjon,
- har null eller trivielt objective,
- har svært få tidssteg,
- har constraints som ikke binder,
- eller bare er laget for å teste én teknisk feature.

# 8. Python-grensesnittet

Forklar hvordan HERSS kan brukes fra Python.

Gå nøye gjennom:

- `cppyy`,
- lasting av `herss.so`,
- initialisering av logger,
- `GlobalConfig`,
- `Dataset`,
- `Herss`,
- `prepaireSimulation`,
- `Simulate`,
- `CalcVF`,
- setters og getters,
- og eksempelskript under `py_src/`.

Forklar hvordan en optimeringsalgoritme i Python i prinsippet kan:

1. initialisere simulatoren én gang,
2. foreslå actions,
3. sette actions programmatisk,
4. kjøre simuleringen,
5. hente objective value,
6. evaluere en ny løsning,
7. og gjenta dette mange ganger.

Undersøk også:

- om simulatoren resetter state mellom kjøringer,
- om file I/O er nødvendig,
- om value function kan leses direkte,
- og om Python-grensesnittet har begrensninger.

# 9. Objective function og constraints

Beskriv HERSS som et optimeringsproblem.

Definer tydelig:

## Beslutningsvariabler

For eksempel:

- action per generator per tidssteg,
- hatch action per tidssteg.

## Tilstandsvariabler

For eksempel:

- magasininnhold,
- vann under transport i channels,
- eventuell generatorstatus.

## Eksogene input

For eksempel:

- pris,
- tilsig,
- topologi,
- initial state.

## Objective function

Forklar nøyaktig hvordan value function beregnes.

Vis gjerne en enkel matematisk formulering, men bruk HERSS-koden som fasit.

## Constraints

Skill mellom:

- harde constraints,
- myke constraints,
- penalties,
- warnings,
- automatisk clipping,
- simulatorfeil,
- og features som er under utvikling.

Forklar særlig:

- LRW/HRW,
- magasinkapasitet,
- generator capacity,
- minimum discharge,
- start/stopp,
- aggressive actions,
- overflow,
- minimum flow,
- og terminalverdi.

# 10. Kjente problemer og uferdige features

Gå gjennom dokumentasjon, kode, tester og kommentarer for å finne:

- kjente bugs,
- uferdige features,
- inkonsistenser,
- dokumentasjonsavvik,
- manglende validering,
- og funksjonalitet som ikke bør brukes som grunnlag for en masteroppgave før den er testet.

Lag en tabell med:

- feature,
- status,
- kilde,
- risiko,
- og konsekvens for optimeringsarbeidet.

Vær særlig nøye med:

- QMIN,
- multi-generator state,
- start/stopp,
- variable timesteps,
- penalties,
- flood-level penalty,
- water value,
- Python-grensesnitt,
- outputfiler,
- og parallelisering.

# 11. Relevans for en masteroppgave i optimering

Vurder kritisk om HERSS kan være grunnlag for en master i optimering.

Ikke gi et optimistisk svar uten begrunnelse.

Diskuter:

- hva som faktisk er optimeringsproblemet,
- hvorfor problemet kan være vanskelig,
- hvilke deler som skaper tidskobling,
- hvilke deler som gir ikke-linearitet,
- hvilke deler som gir diskontinuitet,
- om problemet kan være for enkelt på noen datasett,
- om eksakte metoder kan være mulige på små instanser,
- og om heuristikker eller metaheuristikker er faglig begrunnet.

Forklar også risikoen for at prosjektet glir over i:

- hydrologisk modellering,
- simulatorutvikling,
- datavask,
- debugging,
- eller generell software engineering.

Vurder om følgende masterstruktur virker realistisk:

1. etablere enkle og sterke baselines,
2. lage en eksakt eller nær-eksakt referanse for små instanser,
3. utvikle en problemspesifikk heuristikk eller metaheuristikk,
4. evaluere løsninger under samme tids- eller evalueringsbudsjett,
5. analysere kvalitet, robusthet og skalerbarhet.

Ikke anta at generiske algoritmer som GA, SA eller PSO automatisk er gode valg.

# 12. Spørsmål jeg bør stille hydrologen

Avslutt med en konkret liste over spørsmål jeg bør stille den erfarne hydrologen.

Spørsmålene bør dekke:

- fysisk og operasjonell realisme,
- datasett og parametere,
- objective function,
- terminalverdi av vann,
- realistiske constraints,
- hvilke features som faktisk er viktige i drift,
- hvilke deler av HERSS som er mest pålitelige,
- hvilke testinstanser som er representative,
- og hva som vil gjøre optimeringsresultatene relevante for Å Energi.

Skill mellom:

- spørsmål som må avklares før valg av mastertema,
- spørsmål som kan avklares senere,
- og spørsmål som ikke er nødvendige dersom oppgaven skal holdes algoritmisk.

# 13. Kort møteforberedelse

Lag til slutt en kort oppsummering jeg kan bruke før møtet:

- HERSS forklart på 5–10 setninger,
- de viktigste inputene,
- de viktigste actions,
- objective function,
- de største tekniske risikoene,
- de viktigste optimeringsmulighetene,
- og 5–10 spørsmål jeg absolutt bør stille.

Presentasjonskrav

Rapporten skal være:

- skrevet på norsk,
- grundig, men lett å lese,
- strukturert med tydelige overskrifter,
- forklart med enkelt språk,
- presis i tekniske detaljer,
- og kritisk der informasjonen er usikker.

Unngå unødvendig hydrologisk detaljnivå.

Ikke bruk kompliserte fagbegreper uten å forklare dem.

Bruk tabeller der dette gjør datasett, filer, features eller risikoer lettere å sammenligne.

Ikke skjul usikkerhet.

Ikke konkluder med at HERSS er en god masteroppgave bare fordi simulatoren fungerer. Skill mellom:

1. at repoet kan kjøres,
2. at simulatoren er et brukbart evalueringsorakel,
3. at datasettet inneholder et ikke-trivielt optimeringsproblem,
4. og at det finnes et tydelig, originalt og gjennomførbart masterbidrag.

Start nå med å undersøke repoet i read-only-modus. Før du skriver sluttrapporten, lag en kort plan over hvilke mapper, dokumenter og kodefiler du vil undersøke.