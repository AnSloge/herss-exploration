# Fase C: separer `rho` fra `R` — syntetisk rutenett

## Hvorfor denne kjøringen

Seks instanser er målt. B4 (koordinatoppstigning) traff optimum på fem av dem; bare HJELLE viste et
reelt gap (1,075 %). HJELLE er også den eneste med lav `R` (0,071) og bindende overløp.

**Men `rho` og `R` varierer sammen i alle seks instansene.** De er ikke separat identifisert. Vi vet
at HJELLE-kombinasjonen ga et gap, men ikke om det er `rho`, `R`, samspillet, eller noe tredje ved
HJELLE spesielt. Hele ideen om en instansgenerator som treffer et «hardt» regime hviler foreløpig på
**ett datapunkt**.

Denne kjøringen varierer de to uavhengig over et rutenett og måler gapet i hver celle. Den svarer på:

1. Er det `rho`, `R`, eller samspillet som skaper gapet?
2. Hvor i parameterrommet krysser gapet 1 %?
3. Er HJELLE representativ eller et avvik?

Dette er syntetiske instanser. De holdes strengt adskilt fra uTAHPS-resultatene og brukes aldri i
konklusjoner om det virkelige systemet.

## Instansene

Basis: `analysis/instances/hjelle_daily` (`rho ≈ 0,78`, `R ≈ 0,071`, T=365, dt=86400).

Bygg syntetiske varianter som **egne instanser på disk** via `build_instances.py` — ikke
Python-side-overstyring. (Lærdom fra e163: overstyrer man bare replikaen, optimerer simulatoren et
annet objektiv, og hver kryssjekk sammenligner to ulike verdifunksjoner.)

**`rho`-akse** — skaler tilsigsserien:
```
tilsig' = s_rho · tilsig,   s_rho ∈ {0,64 · 1,0 · 1,6 · 2,3}
```
som gir `rho ≈ {0,5 · 0,78 · 1,25 · 1,8}` med basis-`R`. Verifiser de faktiske `rho`-verdiene fra de
bygde instansene før måling.

**`R`-akse** — skaler magasinets volumkurve:
```
V'(m) = V(LRW) + s_R · (V(m) − V(LRW))   for alle kurvepunkt,   s_R ∈ {1 · 2 · 4 · 8}
```
som gir `R ≈ {0,071 · 0,14 · 0,28 · 0,57}`. **LRW og HRW i masl holdes fast (748/757)**, så
fallhøyde-som-funksjon-av-nivå er uendret; det er kun volum per meter som skaleres. Det er den fysiske
betydningen av «dypere magasin». Init-fyllingsgrad holdes på 0,7.

Prisserien er `utahps_daily`-prisen (`RESTPRICE 101`), kopiert uendret i alle celler. Alle andre
fysiske parametre fra `hjelle_daily`, uendret.

## Rutenett og prioritering

4×4 = 16 celler er for mye for én natt, og volumskalering gjør de høye-`R`-cellene dyre (større
DP-tilstandsrutenett ved samme oppløsning). Prioriter:

1. **Diagonalen** (4 celler): `(s_rho, s_R)` = (0,64;1), (1;2), (1,6;4), (2,3;8). Replikerer at de to
   varierer sammen, som i de observerte instansene.
2. **`rho`-kanten ved fast lav `R`** (3 nye celler): `s_R = 1`, `s_rho ∈ {0,64 · 1,6 · 2,3}`. Isolerer
   `rho` ved HJELLEs egen lave `R`. Basiscellen (1;1) er HJELLE selv — allerede målt, ikke kjør på nytt.
2. **`R`-kanten ved fast `rho ≈ 0,78`** (3 nye celler): `s_rho = 1`, `s_R ∈ {2 · 4 · 8}`. Isolerer `R`.

Det er 4 + 3 + 3 = 10 celler. Rapporter eksplisitt hvilke som faktisk ble kjørt.

## Per celle

- DP med dokumentert diskretisering. **Tilstandsrutenettet må skaleres med `s_R`** — øvre grense =
  maks volum under «alle av»-politikken × 1,15, som vokser med magasinstørrelsen. Behold samme
  oppløsning relativt til maks døgnutslipp (~155 celler per fullastdøgn, som i HJELLE/GRESSE).
- B2 (terskel + nivå) og B4 (koordinatoppstigning, ≥2 omstarter til konvergens, med finpuss).
  **Ikke B3 eller B5** — de tilfører ikke noe på denne aksen.
- Gap regnet på **HERSS-VF**, ikke replika-VF. Kryssvalider DP-politikken og B4-vinneren mot ekte HERSS.

**Konvergenssjekk kun på tre representative celler** (én diagonal, én per kant), ikke alle ti. Doble
rutenettet der og bekreft at verdien flytter seg størrelsesordener mindre enn gapet. Hvis en av de tre
ikke konvergerer, kjør sjekken på flere. Dette halverer omtrent kjøretiden.

## Validering før måling

For hver bygd instans: HERSS laster uten feil, `Diagnose()` / `checkNrSteps()` /
`DiagnoseRiversystemConfiguration()` rene, vannbalanse lukker, `rho` og `R` rapporteres **før** gapet.
Revalider replikaen på minst diagonalcellene (`|ΔVF| < 0,05 EUR`) — volumskalering endrer
magasinkurven, så replikaens kurveoppslag må treffe den nye kurven. `test_regression.py` må fortsatt
passere uendret.

## Rapportering

- Gap-tabell som funksjon av (`rho`, `R`), med B2 og B4 hver for seg.
- **Formen, ikke bare tallene:** krysser gapet 1 % langs `rho`-kanten? Langs `R`-kanten? Er
  effekten monoton? Er HJELLE (1;1) på en topp, en skråning, eller et platå?
- Overløp per celle — nøkkeltallet for arbeidshypotesen. Sammenhold gap mot overløp direkte.
- Budsjett i tre kolonner (veggklokketid, fulle horisontevalueringer, stegceller), fotnote om at kun
  veggklokketid er sammenlignbar.
- Merking: [kilde] / [målt] / [vurdering] / [antakelse] / [usikkert].
- **Eget kapittel, merket syntetisk.** Aldri blandet inn i uTAHPS-konklusjoner.
- Rapport på norsk: `analysis/gap_fase_c.md`.

## Rammer

- Ingenting under `src/` eller `data/` endres. Alt under `analysis/`.
- Simulatoren i isolert subprosess med timeout (`std::exit` og cppyy-segfaulten er åpne).
- Faste seeds (1, 2), registrert. Stemple hver kjøring med commit-hash og `VERSION` / `VERSION_DATE`.
- **Skriv resultat per celle til disk straks cellen er ferdig** (`result_faseC_<rho>_<R>.json`), ikke
  samlet til slutt. Et delvis resultat skal være brukbart hvis jobben stopper.

## Tolkning — fastsett før tallene er kjent

- **Gap følger `R` (lav `R` → stort gap), uavhengig av `rho`** ⇒ lagringsstramhet er driveren, og en
  generator kan treffe hardt regime ved å velge lav `R`. Sterkeste utfall for generator-ideen.
- **Gap følger `rho`, ikke `R`** ⇒ det er knapphet, ikke lagringsstramhet, og generatoren må styre
  `rho` i stedet.
- **Gap krever begge lav `R` og `rho ≈ 1`** ⇒ mekanismen er samspillet, generatoren må treffe et
  hjørne, og HJELLE var det hjørnet.
- **Gap er lite i hele rutenettet, HJELLE var et avvik** ⇒ generator-ideen hviler ikke på en robust
  mekanisme, og retningen må revurderes. Dette er utfallet som er dyrest å oppdage sent, og billigst å
  oppdage nå.

Hvis et premiss svikter — en instans lander i uventet regime, replikaen validerer ikke etter
volumskalering, DP konvergerer ikke — si det rett ut og stopp den cellen. Et motbevist premiss er mer
verdt enn en fullført kjøring.