# Fase C: `rho` og `R` skilt fra hverandre — syntetisk rutenett

**SYNTETISK KAPITTEL.** Alt i kapittel 1–9 er målt på konstruerte instanser som *ikke* er uTAHPS.
De hører hjemme her og skal aldri inngå i en konklusjon om det virkelige systemet. uTAHPS-tallene
står isolert i §10, kun som posisjonsangivelse.

Kjørt 2026-08-18 18:46Z → 2026-08-19 09:47Z. Driver: `analysis/scarcity_gap/run_fase_c.sh`.
HERSS `VERSION` 3.1.03 / `VERSION_DATE` 20260611, oppstrøms pinnet `029a2d5`, arbeidstre `7e65a49`.
Seeds (1, 2) for B4. Alle celleresultater ligger som `result_syn_*.json`; løpende tabell i
`faseC_summary.md`.

---

## 0. Sammendrag

1. **[målt] Gapet krever både lav `R` og `rho` nær 1.** Det er ikke `R` alene, slik de ni cellene
   fra 2026-08-04 antydet. Langs `rho`-kanten ved lav `R` topper gapet seg ved `rho` ≈ 1 (1,795 %)
   og kollapser til 0,055 % ved `rho` = 1,75. Det er utfall nummer tre av de fire som ble
   forhåndsregistrert i `prompts/prompt-phase-c.md`.
2. **[målt] 1 %-krysningen er lokalisert, og den flytter seg med `rho`:** `R*` ≈ 0,096 ved
   `rho` = 1,00 og `R*` ≈ 0,074 ved `rho` = 0,782. Tidligere var den kun klemt til en faktor to
   (0,071–0,143).
3. **[målt] Arbeidshypotesen «overløp driver gapet» er motbevist i den formen.** Langs
   `rho`-kanten stiger overløpet monotont til 95,77 Mm³ mens gapet faller til 0,055 %. Volum alene
   forklarer ingenting.
4. **[vurdering] Det som ser ut til å gjelde er om overløpet er *unngåelig ved planlegging*.**
   Ved `rho` = 1,75 er søl strukturelt uunngåelig og ingen politikk kan handle det bort; ved
   `rho` ≈ 1 er det marginalt og omstridt, og det er der DP slår B4.
5. **[målt] HJELLE ligger på skulderen av hjørnet, ikke på et platå og ikke på toppen.** Toppen
   langs `rho`-kanten ligger ved `rho` = 1,00; HJELLE ligger ved 0,782 med 1,075 %.
6. **[målt] Brocellen frikjenner sammenslåing** av 2026-08-04-cellene og Fase C-cellene:
   forskyvning −0,0016 prosentpoeng, mot toleranse 0,010.

---

## 1. Hva kjøringen skulle svare på

`rho` og `R` varierer sammen i alle uTAHPS-instansene som er målt, så mekanismen bak gapet er ikke
identifisert. Kjøringen varierer dem uavhengig over et rutenett og måler gapet i hver celle:

1. Er det `rho`, `R` eller samspillet som skaper gapet?
2. Hvor i parameterrommet krysser gapet 1 %?
3. Er HJELLE representativ eller et avvik?

## 2. Forensikk før noe ble bygget — og hvilken vei beslutningsregelen endte på

`prompts/prompt-phase-c.md` forutsetter at generator-ideen hviler på **ett** datapunkt. Det stemte
ikke. **[kilde]** Et syntetisk rutenett på ni celler kjørte allerede 2026-08-04 og ligger commitet i
`analysis/scarcity_gap/result_syn_*.json` (commit `a32ded6`). Kapittel 7 i `gap_multiinstans.md` sto
som `*(fylles inn)*` — rapporten ble skrevet 05:41, resultatene landet 00:38–02:03 samme natt.

Før noe ble skrevet opp eller slått sammen ble `R` og `rho` regnet **tilbake fra magasinkurvene på
disk**, ikke fra hva de var ment å være:

| Sjekk | Funn |
|---|---|
| Konvensjon | `V'(m) = s_R · V(m)` på **alle** kurvepunkt, også under LRW. LRW/HRW fast 748/757. Forholdstallet er konstant over alle sju punkt i alle ni instanser. |
| Negativt volum | Ingen. `min V = 0,00` overalt. |
| `rho` konstant etter volumskalering? | **Ja.** Ved `rho` = 1,0 er tilsigssummene 122,99 / 119,84 / 113,54 / 100,94 Mm³ for `s_R` = 0,5/1/2/4 — nøyaktig kompenserende. Tilbakeregnet `rho` treffer 0,5000/0,7500/1,0000/1,2500; `R` treffer 0,0357/0,0713/0,1427/0,2854. |
| Konvergenssjekk | Kjørt på **alle ni**. Diskretiseringsdelta/gap ≤ 0,007 for hver celle med gap > 0,1 %. |

**Vei: den billige.** Samme konvensjon, konvergens dokumentert, aksene rimelig dekket. De ni skrives
opp som prior-run og Fase C kjørte bare det nye — betinget av brocellen i §5.

**[usikkert] Ett forbehold som ikke vaskes bort:** 2026-08-04-kjøringen holdt `n_grid` fast på 8001,
så oppløsningen falt fra 389 til 41 celler per fullastdøgn når `R` vokste — og de groveste cellene er
nettopp dem som rapporterer nær-null gap. Et grovere rutenett gjør DP *dårligere*, som gjør gapet
*mindre*. `R` betyr det samme i begge rutenett, men DP-kvaliteten gjør det ikke. Derfor brocellen, og
derfor står oppløsningskolonnen i hver tabell.

**Et hull i den gamle kjøringen [kilde]:** de ni cellene ble **aldri replika-validert**.
`validate_replica.py` skrev én delt rapport som ble overskrevet hver kjøring, og bare
`toppsy`/`kroknesvatn` overlevde i den. Rettet her med et `--out`-flagg; alle ti nye instanser er
validert (§4).

## 3. Konstruksjon og konvensjoner

Basis: `analysis/instances/hjelle_daily`, T = 365, dt = 86400, prisserie fra `utahps_daily`
(`RESTPRICE 101`), kopiert uendret i alle celler.

- **`R`-akse:** `V'(m) = s_R · V(m)`, hele kurven, LRW/HRW fast i masl. Fallhøyde som funksjon av
  *nivå* er uendret; det som endres er volum per meter.
- **`rho` holdes eksakt** ved tilsigsreskalering, `params.synthetic_inflow_scale`:
  `k = (rho_mål · kapasitet − init_fr · s_R · aktiv_0) / tilsig_0`. Uten den ville skalering av
  kurven dratt `rho` med seg gjennom initiallageret — nettopp den sammenblandingen rutenettet
  finnes for å fjerne. Faktisk `rho` er rapportert per celle fra den bygde instansen.
- **Tilstandsrutenett:** ~155 celler per fullaststeg, øvre grense = maks volum under «alle av» ×
  1,15. Nytt i Fase C; `n_grid` går fra 8 979 til 59 175 avhengig av `s_R`.
- **Baselines:** B2 (terskel + nivå) og B4 (koordinatoppstigning, 2 omstarter, grov→fin,
  `epsilon` 0,01). B1/B3 er kjørt fordi de koster ~0,1–5 s, men rapporteres ikke på denne aksen.
- **Gap regnet på HERSS-VF**, ikke replika-VF. DP-politikken og B4-vinneren er kryssvalidert mot
  ekte HERSS i isolert subprosess for hver celle.

**Metodemerknad.** `prompt-phase-c.md` foreslår en annen `R`-akse,
`V'(m) = V(LRW) + s_R · (V(m) − V(LRW))`, som holder dødvolumet fast. Den er uten tvil den mer
fysiske lesningen av «dypere magasin», men er **ikke** brukt, av to grunner: den ville forket
datasettet bort fra de ni validerte cellene, og slik den er skrevet gir den negativt volum under LRW
(ved 747 masl: `1 + 8·(0−1) = −7` Mm³). Forskjellen er notert her, ikke behandlet som et veivalg.

**Merknad om rekkevidde.** Aksen isolerer `R` **ved konstant fallhøydespenn**. Et virkelig magasin
med åtte ganger volumet ville ikke hatt de samme 9 m reguleringshøyde. Dette er en smalere påstand
enn å isolere `R`, og konstruksjonen er ikke fysisk realiserbar.

## 4. Validering før måling

Alle ti nye instanser, før noe gap ble regnet:

- **[målt]** CLI-kjøring uten ERROR/WARN; `Diagnose()`, `checkNrSteps()` og
  `DiagnoseRiversystemConfiguration()` rene. 30/30 PASS.
- **[målt]** Vannbalansen lukker (|balanse| < 1e-6) i alle ti.
- **[målt]** `rho` og `R` rapportert før gapet, tilbakeregnet fra instansen. Alle treffer målet
  eksakt (0,7820 / 1,0000 / 1,2210 / 1,7330 / 1,7500).
- **[målt]** Replikaen revalidert mot HERSS på hver ny `s_R`, ni handlingssekvenser per instans.
  Alle PASS. Verste |ΔVF| = 0,029 EUR (`syn_rho0p782_R4`), mot toleranse 0,05; øvrige ≤ 0,019.
- **[målt]** `test_regression.py` passerer uendret (rel. avvik 0,000e+00 på alle fire referanser),
  som viser at utvidelsen av `params.py` ikke rørte en formel.

## 5. Brocellen — er sammenslåing tillatt?

`syn_rho1_R4` nøyaktig som den ligger på disk, målt om på det avledede rutenettet. Instansen er
uendret, så enhver endring i gapet er **ren oppløsning**.

| | punkt | celler/fullaststeg | B4-gap |
|---|---|---|---|
| 2026-08-04 | 16 001 (*effektivt*) | 90 | 0,0090 % |
| Fase C | 27 453 | 155 | 0,0074 % |

Forskyvning **−0,0016 prosentpoeng** mot toleranse 0,010 ⇒ **sammenslåing tillatt.**

**[kilde]** Merk at gammelcellen er *merket* 8001 punkt, men DP-verdien kommer fra den doblede
16001-kjøringen: `run_measurement.py` tar `max(grunnrutenett, doblet rutenett)` når
konvergenssjekken kjøres. Å sammenlikne mot 8001 ville påstått at brocellen spenner et
oppløsningssprang på 3,4× når det i virkeligheten er 1,7×.

**[usikkert]** Forskyvningen er *negativ* — finere rutenett ga marginalt mindre gap, der en bedre DP
skulle gitt større. Ved 0,0074 % (≈ 160 EUR av 2,1 M) er cellen på gulvet der DP-avrunding, ikke
optimering, dominerer. Den støtter sammenslåingen; den er ikke bevis for at oppløsning aldri betyr
noe, og oppløsningskolonnen blir stående i hver tabell.

## 6. Resultater — hele det syntetiske rutenettet

B4-gap er mot DP, på HERSS-VF. «c/steg» er rutenettceller per fullaststeg.

| rho | R | B2 gap % | B4 gap % | overløp Mm³ | steg | c/steg | konv. | celle |
|---|---|---|---|---|---|---|---|---|
| 0,500 | 0,0357 | 7,449 | **3,460** | 1,76 | 15 | 389 | +0,00309 % | `syn_rho0p5_R0p5` |
| 0,500 | 0,0713 | 6,877 | 1,560 | 0,05 | 5 | 197 | +0,00278 % | `syn_rho0p5_R1` |
| 0,750 | 0,0713 | 5,014 | 1,464 | 4,32 | 28 | 172 | +0,00301 % | `syn_rho0p75_R1` |
| 0,782 | 0,0892 | 4,118 | 0,601 | 3,02 | 28 | 155 | ikke kjørt | `syn_rho0p782_R1p25` |
| 0,782 | 0,1427 | 1,775 | 0,063 | 0,20 | 13 | 155 | ikke kjørt | `syn_rho0p782_R2` |
| 0,782 | 0,2854 | 1,169 | 0,014 | 0,00 | 0 | 155 | +0,00250 % | `syn_rho0p782_R4` |
| 0,782 | 0,5708 | 0,737 | 0,008 | 0,00 | 0 | 155 | ikke kjørt | `syn_rho0p782_R8` |
| 1,000 | 0,0357 | 7,384 | 1,647 | 34,54 | 94 | 312 | +0,00214 % | `syn_rho1_R0p5` |
| 1,000 | 0,0713 | 4,439 | **1,795** | 22,33 | 61 | 153 | +0,00282 % | `syn_rho1_R1` |
| 1,000 | 0,0892 | 4,086 | 1,106 | 17,84 | 60 | 155 | ikke kjørt | `syn_rho1_R1p25` |
| 1,000 | 0,1070 | 3,428 | 0,845 | 13,42 | 58 | 155 | +0,00152 % | `syn_rho1_R1p5` |
| 1,000 | 0,1427 | 2,085 | 0,161 | 5,87 | 47 | 82 | +0,00114 % | `syn_rho1_R2` |
| 1,000 | 0,2854 | 0,524 | 0,009 | 0,18 | 14 | 45 | +0,00158 % | `syn_rho1_R4` |
| 1,000 | 0,2854 | 0,523 | 0,007 | 0,18 | 14 | 155 | ikke kjørt | `syn_rho1_R4` (bro) |
| 1,000 | 0,5708 | 0,646 | 0,010 | 0,00 | 0 | 155 | +0,00229 % | `syn_rho1_R8` |
| 1,221 | 0,2854 | 1,281 | 0,003 | 8,73 | 66 | 155 | ikke kjørt | `syn_rho1p221_R4` |
| 1,250 | 0,0713 | 3,821 | 0,575 | 44,78 | 92 | 139 | +0,00116 % | `syn_rho1p25_R1` |
| 1,250 | 0,2854 | 1,319 | 0,003 | 11,16 | 76 | 41 | +0,00065 % | `syn_rho1p25_R4` |
| 1,733 | 0,5708 | 0,266 | 0,001 | 25,52 | 182 | 155 | ikke kjørt | `syn_rho1p733_R8` |
| 1,750 | 0,0713 | 1,941 | 0,055 | 95,77 | 159 | 155 | ikke kjørt | `syn_rho1p75_R1` |

Konvergenssjekken er etter planen kjørt på tre Fase C-celler. Diskretiseringsdelta mot gap:
`syn_rho1_R1p5` 0,0018 (gap 0,845 %) — kravet om at en nær-1 %-avlesning ikke er et
avrundingsartefakt er innfridd med god margin. For `syn_rho1_R8` (0,23) og `syn_rho0p782_R4` (0,18)
er forholdet mye høyere, men der er gapet på gulvet (0,010 % / 0,014 %) og deltaet er positivt, så
en finere DP kunne bare gjort de gapene *litt større* — de forblir nær null uansett.

## 7. Formen, ikke bare tallene

### 7.1 `R`-kanten ved fast `rho` — monoton, og krysningen er lokalisert

Ved `rho` = 1,00: 1,647 → **1,795** → 1,106 → 0,845 → 0,161 → 0,009 → 0,010 for
`R` = 0,036 → 0,571. Fallende og monotont fra toppen ved `R` ≈ 0,071, og flatt på ~0,01 % fra
`R` ≈ 0,29 og oppover.

Ved `rho` = 0,782: 1,075† → 0,601 → 0,063 → 0,014 → 0,008. Samme form, forskjøvet ned.

> † **Forbehold om blanding.** Punktet ved `R` = 0,0713 på denne kanten *er* `hjelle_daily`, altså
> et virkelig uTAHPS-utsnitt, ikke en syntetisk celle. Den syntetiske cellen (0,782; `s_R` = 1) ble
> ikke bygget, fordi den ville vært HJELLE med tilsiget skalert med `k` = 1,00026 — numerisk samme
> instans. Bruken er derfor forsvarlig, men den er en blanding, og den står markert her og i §7.2
> heller enn å gli inn ubemerket. Krysningen ved `rho` = 0,782 hviler på dette punktet; uten det er
> den kanten uten forankring under `R` = 0,089.

**[målt] 1 %-krysningen**, lineært interpolert mellom nabocellene:

| `rho` | krysser 1 % ved | mellom |
|---|---|---|
| 1,000 | `R*` ≈ 0,096 | 0,0892 (1,106 %) og 0,1070 (0,845 %) |
| 0,782 | `R*` ≈ 0,074 | 0,0713 (1,075 %) og 0,0892 (0,601 %) |

Krysningen er altså ikke en konstant `R`, den flytter seg med `rho`.

### 7.2 `rho`-kanten ved lav `R` — ikke monoton, med topp ved `rho` ≈ 1

| rho | B4 gap % | overløp Mm³ | steg med overløp |
|---|---|---|---|
| 0,500 | 1,560 | 0,05 | 5 |
| 0,750 | 1,464 | 4,32 | 28 |
| 0,782† | 1,075 | 6,12 | 33 |
| 1,000 | **1,795** | 22,33 | 61 |
| 1,250 | 0,575 | 44,78 | 92 |
| 1,750 | 0,055 | 95,77 | 159 |

(† = `hjelle_daily`, ikke en syntetisk celle. Se noten i §7.1.)

Dette er hovedfunnet. **Gapet er ikke monotont i `rho`** — det topper seg ved `rho` ≈ 1 og kollapser
med en faktor 33 fram til `rho` = 1,75.

**[usikkert]** Punktet ved `rho` = 0,782 (1,075 %) ligger under begge naboene 0,750 (1,464 %) og
1,000 (1,795 %). Gapflaten er ikke glatt, og det bør den heller ikke forventes å være: gapet er
DP − B4, og B4 er et lokalsøk med faste seeds. Slike krusninger måler B4s hell i den enkelte
instansen, ikke en egenskap ved regimet. Formen — topp nær `rho` ≈ 1, kollaps over 1,25 — er robust
over flere celler; enkeltavvik på ±0,4 prosentpoeng er det ikke.

### 7.3 Diagonalen — ut av hjørnet med én gang

Når `rho` og `R` stiger sammen, slik de gjør i alle de virkelige instansene:

| rho | R | B4 gap % |
|---|---|---|
| 0,500 | 0,0713 | 1,560 |
| 0,782 | 0,1427 | 0,063 |
| 1,221 | 0,2854 | 0,003 |
| 1,733 | 0,5708 | 0,001 |

Kollapsen er nesten umiddelbar. Å bevege begge parametrene sammen fører rett ut av det harde
regimet i stedet for langs det.

## 8. Overløp mot gap — arbeidshypotesen, motbevist i den formen den hadde

Hypotesen som gikk inn i kjøringen var at bindende overløp bryter B4 og dermed skaper gapet.

**[målt] Langs `R`-kanten stemmer den:** ved `rho` = 1 faller overløpet 22,33 → 0,00 Mm³ i takt med
at gapet faller 1,795 → 0,010 %.

**[målt] Langs `rho`-kanten er den motbevist:** overløpet stiger monotont 0,05 → 95,77 Mm³ mens
gapet faller 1,560 → 0,055 %. Ved den høyeste overløpsmengden i hele rutenettet er gapet nest
lavest på den kanten. **Overløpsvolum alene forklarer ingenting.**

**[vurdering] Den lesningen som er forenlig med begge kantene** er at det avgjørende ikke er om det
spilles vann, men om spillet er *unngåelig ved planlegging*:

- Ved `rho` = 1,75 kommer det 95,77 Mm³ overløp fordelt på 159 av 365 døgn. Tilsiget overgår
  turbinkapasiteten så grovt at ingen handlingssekvens kan lagre seg unna. Søl er en konstant, ikke
  en beslutning, og en terskelregel er da nesten optimal.
- Ved `rho` ≈ 1 er søl marginalt og omstridt: 22,33 Mm³ over 61 døgn, i et magasin som kan holde
  9 Mm³ aktivt. Om man søler avhenger av timing, og det er der DP henter 1,795 % over B4.
- Ved `rho` = 0,5 er det nesten ikke overløp (0,05 Mm³) og gapet er likevel 1,560 %. Der kommer
  vanskeligheten fra noe annet — knapphet og hodeavhengighet, ikke søl.

Dette er en **[vurdering]**, ikke et måleresultat. Den er konsistent med alle 19 cellene, men er
ikke testet direkte. En direkte test ville vært å måle hvor mye av overløpet som er *unngåelig*
under den optimale politikken og korrelere det mot gapet i stedet for totalvolumet.

## 9. Budsjett

| celle | veggklokke s | fulle horisontevalueringer | DP-stegceller |
|---|---|---|---|
| `syn_rho1_R1p25` | 1 297 | 18 639 344 | 726 383 580 |
| `syn_rho1_R1p5` | 2 443 | 18 991 980 | 854 478 870 |
| `syn_rho1_R8` | 8 297 | 39 433 724 | 3 448 958 730 |
| `syn_rho0p782_R4` | 3 386 | 36 152 018 | 1 837 276 410 |
| `syn_rho0p782_R8` | 2 159 | 36 661 148 | 3 177 801 690 |
| `syn_rho1p221_R4` | 2 004 | 28 511 054 | 2 192 509 740 |
| `syn_rho1p733_R8` | 1 765 | 13 290 274 | 4 342 104 240 |
| `syn_rho1_R4` (bro) | 1 913 | 45 948 206 | 2 014 819 710 |
| `syn_rho0p782_R1p25` | (30 565)¹ | 21 247 820 | 659 474 700 |
| `syn_rho0p782_R2` | (35 288)¹ | 38 677 366 | 1 012 213 620 |
| `syn_rho1p75_R1` | (30 623)¹ | 22 250 868 | 781 407 330 |

> Kun veggklokketid er sammenlignbar på tvers av metodene. En «full horisontevaluering» i B2/B4 og
> en DP-stegcelle er ikke samme arbeidsmengde: stegcellen er én tilstand-handling-transisjon,
> vektorisert, mens en B2/B4-evaluering er en hel T-stegs framoverkjøring. Kolonnene står ved siden
> av hverandre for å vise hva som faktisk ble brukt, ikke for å settes mot hverandre.

> ¹ **[kilde] Disse tre veggklokketallene er ugyldige** og må ikke brukes. De tre cellene kjørte i
> samme bølge natt til 2026-08-19, og verten (WSL2) sov mesteparten av natten. DP-en i de samme
> prosessene tok 149/213/170 s — helt normalt — mens B2 og B4 rapporterte 9 400–25 700 s mot
> 466–1 019 s i sammenliknbare celler. Skjevfordelingen mellom stegene utelukker CPU-kappestrid:
> DP-en rakk å bli ferdig før verten sovnet, og `time.time()` i B2/B4 absorberte deretter
> ~8 timer dvale, mens VM-ens egen klokke sto stille (`ps` rapporterte 27 min forløpt for en
> prosess loggen mente var 9,75 t gammel). Måletallene — gap, overløp, konvergens — er upåvirket;
> kun disse tre tidene er det.

**[vurdering]** Realistisk budsjett per celle uten dvale: ~1 300–3 400 s ved `s_R` ≤ 4 uten
konvergenssjekk, ~8 300 s med konvergenssjekk ved `s_R` = 8. DP-tiden vokser klart superlineært i
`n_grid` — `syn_rho1_R8` brukte 5 152 s på 47 001 punkt mot ~150 s på ~9 000 punkt, altså ~5,9×
rutenett men ~34× tid. Sannsynligvis hurtigbuffer- og båndbreddeeffekter når tilstandsrekkene
slutter å få plass i cache. Verdt å vite før noen planlegger et rutenett med `s_R` = 16.

## 10. Posisjonering mot uTAHPS — kun for å plassere, ikke for å konkludere

**Disse er ikke syntetiske og hører ikke til i kapitlene over.** De står her bare for å vise hvor de
virkelige utsnittene ligger i (`rho`, `R`)-planet.

| instans | rho | R | B2 gap % | B4 gap % | overløp Mm³ | c/steg |
|---|---|---|---|---|---|---|
| `gresse_daily` | 0,563 | 0,3247 | 0,407 | 0,000 | 0,00 | 170 |
| `hjelle_daily` | 0,782 | 0,0713 | 5,121 | 1,075 | 6,12 | 169 |
| `hjelle_daily_e163` | 0,782 | 0,0713 | 7,001 | 1,077 | 6,13 | 169 |
| `kroknesvatn_daily` | 0,947 | 0,6448 | 1,271 | 0,002 | 0,00 | 25 |
| `toppsy_daily` | 1,017 | 0,6806 | 1,611 | 0,001 | 0,00 | 25 |

**[vurdering]** HJELLE er det eneste utsnittet som ligger i nærheten av hjørnet, og det forklarer
hvorfor det var det eneste med et reelt gap. GRESSE, KROKNESVATN og TOPPSY ligger alle ved
`R` ≥ 0,32, godt inne i det flate området der det syntetiske rutenettet også gir ~0,01 %.

**[usikkert] Et forbehold som gjelder uTAHPS-tallene, ikke bare de syntetiske:** `toppsy_daily` og
`kroknesvatn_daily` ble målt med bare 25 rutenettceller per fullaststeg — seks ganger grovere enn
Fase C-standarden. Deres nær-null gap bærer nøyaktig samme oppløsningsforbehold som de gamle
høy-`R`-cellene. Brocellen tyder på at effekten er liten på dette gap-nivået, men de to er ikke
selv kontrollert, og det bør stå i konklusjonene om det virkelige systemet.

## 11. Tolkning, mot de fire forhåndsregistrerte utfallene

Utfallene ble låst i `prompts/prompt-phase-c.md` før tallene var kjent.

| Forhåndsregistrert utfall | Dom |
|---|---|
| Gap følger `R`, uavhengig av `rho` | **Forkastet.** Gapet varierer med en faktor 33 langs `rho` ved fast `R` = 0,0713. |
| Gap følger `rho`, ikke `R` | **Forkastet.** Gapet varierer med en faktor 180 langs `R` ved fast `rho` = 1. |
| **Gap krever både lav `R` og `rho` ≈ 1** | **Støttet.** Dette er utfallet. |
| Gap er lite i hele rutenettet, HJELLE var et avvik | **Forkastet.** 3,460 % ved (0,500; 0,0357), 1,795 % ved (1,000; 0,0713). |

**Konsekvens for generator-ideen [vurdering].** En instansgenerator kan treffe det harde regimet,
men den må treffe et **hjørne**, ikke en akse: `R` ≤ ~0,09 *og* `rho` i båndet ~0,5–1,0. Det er en
strammere spesifikasjon enn «velg lav `R`», som var den billigste lesningen av de ni cellene fra
2026-08-04. Innenfor hjørnet er gapet stort og stabilt — alle **seks** syntetiske celler med gap
> 1 % ligger der, fra 1,106 % til 3,460 % — så regimet er ikke et knivsegg, men veien inn i det må
styres på begge parametre.

**[usikkert] Den øvre `rho`-grensen er ikke målt presist.** Ved `rho` = 1,00 og `R` = 0,0713 er
gapet 1,795 %; ved `rho` = 1,25 samme `R` er det 0,575 %. Overgangen ligger et sted mellom, og
ingen celle er målt der. «~1,0» er derfor en nedre kant på et intervall, ikke en målt terskel.
Tilsvarende er den nedre `rho`-grensen uprøvd: laveste målte `rho` er 0,500, og den cellen har
fortsatt 1,560 % (3,460 % ved `R` = 0,0357), så hjørnet kan strekke seg lenger ned enn rutenettet
viser.

**Hva HJELLE er [vurdering].** Ikke et avvik, og ikke en topp. HJELLE ligger på skulderen: `rho`
0,782 mot toppen ved 1,000, og `R` 0,0713 rett under krysningen `R*` ≈ 0,074 for sin egen `rho`.
Det forklarer både hvorfor HJELLE ga et gap i det hele tatt og hvorfor det var beskjedent (1,075 %)
sammenliknet med hva rutenettet kan produsere (3,460 %).

## 12. Forbehold

1. **Syntetiske instanser.** Kapittel 1–9 er ikke uTAHPS og skal aldri inngå i en konklusjon om det
   virkelige systemet.
2. **`R` isoleres ved konstant fallhøydespenn**, ikke `R` i sin alminnelighet. Konstruksjonen er
   ikke fysisk realiserbar (§3).
3. **Gapflaten er ikke glatt** fordi B4 er et lokalsøk. Enkeltcelle-avvik på noen tideler av et
   prosentpoeng måler B4s hell, ikke regimet (§7.2).
4. **Konvergenssjekk kjørt på tre av ti Fase C-celler.** Gapene for de sju øvrige hviler på at
   diskretiseringsfeilen der oppfører seg som på de tre. Antakelsen er godt understøttet — deltaet
   er 0,001–0,003 % i alle 12 cellene der den er målt — men den er en antakelse.
5. **Tre veggklokketall er ugyldige** på grunn av vertsdvale (§9, fotnote 1).
6. **`make test` ikke kjørt** (gtest mangler) — uendret fra tidligere kjøringer.
7. **Terminalleddets inkonsistens** (`LOCAL_ENERGY_EQUIVALENT` konstant mot hodeavhengig produksjon
   i horisonten) gjelder alle celler likt og er ikke undersøkt her.

---

## Reproduksjon

```bash
bash analysis/scarcity_gap/run_fase_c.sh          # hele kjøringen, ~4 t uten dvale
../../.venv/bin/python faseC_summary.py           # bygger tabellene på nytt fra result_*.json
```

Artefakter: `result_syn_*.json` (én per celle), `faseC_summary.{md,json}`,
`validation_instance_faseC.json`, `validation_replica_faseC.json`, `faseC_replica_*.log`,
`faseC_manifest.txt`, `analysis/fasec_run.log`.
