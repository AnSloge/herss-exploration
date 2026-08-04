# Finnes det en optimeringsoppgave i HERSS?

**Status per 3. august 2026** — undersøkelse før valg av masteroppgave

---

## Kort oppsummert

HERSS simulerer regulerte vannkraftsystemer. Den kan ikke optimere — den regner ut hva en gitt
produksjonsplan er verdt. Optimeringen må ligge utenfor.

Spørsmålet jeg har undersøkt er ikke om man *kan* optimere med HERSS. Det kan man. Spørsmålet er
om det er **vanskelig nok** til å bære en masteroppgave i optimering.

Svaret så langt: **det avhenger sterkt av instansen**, og jeg har funnet ut hva forskjellen
skyldes.

---

## 1. Hva problemet er

En produksjonsplan er en tabell med tall mellom 0 og 1 — ett per kraftverk per tidssteg. 0 betyr
stopp, 1 betyr full produksjon, 0,5 betyr halv.

```
dag 1:  0.0     dag 2:  1.0     dag 3:  0.5    ...    dag 365: 0.8
```

Denne tabellen sendes til HERSS, som simulerer og gir tilbake **ett tall**: verdien i euro
(inntekt fra kraftsalg, pluss verdien av vannet som står igjen ved slutten).

Optimeringsproblemet er: **hvilke tall gir høyest verdi?**

Beslutningene henger sammen. Bruker du mye vann i dag, er magasinet tommere i morgen. Sparer du
for lenge, renner det over og vannet er tapt. Du kan ikke velge hver dag for seg.

---

## 2. Hvordan man vet hva som er best

For å måle om en optimeringsmetode er god, må man vite hva den *kunne* ha oppnådd. Uten fasit
kan man bare sammenligne metoder mot hverandre — man vet aldri om alle er dårlige.

Derfor bygget jeg en fasit: **dynamisk programmering** (DP), som regner bakover fra siste dag og
finner den beviselig beste planen.

DP virker bare når systemet er lite nok. Ett magasin: uproblematisk. Fire magasiner med kanaler
imellom: umulig — man må holde styr på rundt 15 størrelser samtidig.

For å få DP til å virke måtte fysikken gjenskapes i Python, siden HERSS bare kan simulere hele
horisonten på én gang. Den kopien er testet mot ekte HERSS på 18 forskjellige planer og treffer
med under 0,02 euro på verdier rundt 2 millioner euro.

Dette er et poeng i seg selv: **den publiserte metoden på dette feltet kan ikke verifisere om den
finner det beste svaret.** Det står eksplisitt i Matheussen, Granmo & Sharma (2019). Med DP kan
jeg det, i alle fall på små systemer.

---

## 3. Metodene som ble sammenlignet

| | Hva den gjør |
|---|---|
| **DP** | Fasiten. Beviselig best, men bare på små systemer. |
| **B1 – prisgrense** | Kjør for fullt når prisen er over en grense. Én knapp å skru på. |
| **B2 – prisgrense + nivå** | Som B1, men velg også hvor hardt du kjører. To knapper. |
| **B3 – myopisk** | Se bare på i dag. Ingen framsyn i det hele tatt. |
| **B4 – koordinatoppstigning** | Endre én dag om gangen, behold det som hjelper, gjenta. Dette er metoden fra 2019-artikkelen. |

B4 er den viktigste. Den er ikke avansert, men den er den publiserte praksisen på feltet — og den
genererer treningsdataene som de nevrale nettverkene i artikkelen lærer av.

---

## 4. Første test: ingenting å optimere

Første måling ga et gap på **0,29 %** mellom DP og den enkle terskelregelen. Altså: en regel med
to knapper fant 99,7 % av det beste mulige.

Det så ut som at det ikke fantes noe optimeringsproblem.

Men den beste terskelregelen viste seg å være «produser 29 av 30 dager på 99 % kapasitet» — altså
**kjør alltid for fullt**. Det er ingen strategi. Det er fravær av valg.

Årsaken var i vannregnskapet:

- Turbinen klarte å slippe gjennom **10,4 Mm³** på 30 dager
- Det var **18,9 Mm³** vann tilgjengelig

**Nesten dobbelt så mye vann som anlegget kunne bruke.** Da finnes det ingen beslutning å ta —
alt annet enn å kjøre for fullt gir bare mer overløp.

Dette ga et enkelt screeningtall:

```
rho = tilgjengelig vann / hva turbinen kan slippe gjennom
```

Er `rho` over 1, finnes det ikke noe allokeringsvalg. Instansen hadde 1,82.

**Vi målte på feil instans.**

---

## 5. Andre test: to nye instanser

Jeg klippet ut to enkeltmagasiner fra det store systemet, begge med `rho` under 1 — altså for lite
vann til å kjøre for fullt, så man *må* velge.

| Instans | `rho` | `R` (lagringsdybde) | Gap mot terskelregel |
|---|---|---|---|
| Første instans | 1,82 | 0,87 | **0,29 %** |
| **HJELLE** | 0,78 | 0,07 | **5,12 %** |
| **GRESSE** | 0,56 | 0,32 | **0,41 %** |

**Faktor 18 på HJELLE.** Samme metode, samme kode, helt annet resultat.

Det avklarte hovedspørsmålet: 0,29 % var en egenskap ved den første instansen, ikke ved
vannkraftplanlegging.

---

## 6. Overraskelsen

Jeg forventet at GRESSE ville være det vanskelige tilfellet. Den har 4,6 ganger dypere magasin,
altså mer å planlegge med over tid.

**Det motsatte skjedde.** Dypere lagring ga et 12 ganger *mindre* gap.

Forklaringen ligger i om noe faktisk begrenser deg:

**GRESSE** har rikelig magasinplass. Ingenting renner over, ingenting går tomt. Da er den beste
planen bokstavelig talt en prisregel — en enkel grense treffer 364 av 365 beslutninger riktig.
Til og med en metode helt uten framsyn kommer innenfor 0,14 %.

**HJELLE** har nesten ingen buffer: magasinet rommer 9 Mm³, mens 92 Mm³ renner gjennom i løpet av
året. Magasinet renner over i 33 av 365 dager. Da må man produsere selv når prisen er lav — ellers
går vannet tapt — og man må treffe magasinkapasiteten presist. Den beste planen bruker **71
forskjellige produksjonsnivåer**, og ingen prisgrense klassifiserer mer enn 81 % av
på/av-beslutningene riktig.

> **Funnet: det er ikke dyp lagring som skaper et optimeringsproblem. Det er knapphet på
> lagringsplass i forhold til vannmengden — altså at overløpsbegrensningen faktisk binder.**

Dypere magasin gjør problemet *lettere*, ikke vanskeligere.

---

## 7. Hvor mye rom er det egentlig?

Dette er det avgjørende for om det finnes en oppgave.

Gap mot DP på HJELLE, den vanskeligste instansen:

| Metode | Gap |
|---|---|
| Prisgrense (B1) | 8,02 % |
| Myopisk (B3) | 6,31 % |
| Prisgrense + nivå (B2) | 5,12 % |
| **Koordinatoppstigning (B4)** | **1,08 %** |

En ny metode må måles mot det **beste** eksisterende alternativet, ikke det svakeste. Rommet er
altså **ett prosentpoeng**, ikke fem.

Det er trangt. Men to ting gjør det mer interessant enn tallet alene:

**B4 er upålitelig.** To kjøringer med ulikt startpunkt, begge kjørt til de ikke kunne forbedres
mer, landet **9 778 euro fra hverandre** — 0,49 % av verdien. Nesten halve gapet er *tilfeldighet*,
ikke systematisk avstand. En metode som pålitelig lander på 0,2 % ville være en klar forbedring
over en som treffer et 0,5 %-bånd.

**B4 har en kjent strukturell svakhet.** Den endrer én variabel om gangen. Den kan derfor per
definisjon aldri finne forbedringer som krever at *to* variabler endres samtidig. Det er ikke
testet ennå, fordi ingen målt instans har hatt mer enn én beslutningsvariabel per tidssteg.

---

## 8. Andre funn underveis

**Testdataene er ikke laget for å være krevende.** Straffene i HERSS er der for å skille
løsninger fra hverandre, ikke for å håndheve driftsbegrensninger. I ett-magasinsystemer kan
magasinet fysisk aldri gå under nedre grense, så den straffen kan aldri utløses.
Start/stopp-kostnaden er under 0,003 % av verdien. Skal begrensninger være en del av oppgaven,
må de legges til bevisst.

**Fallhøydeavhengigheten betyr mindre enn ventet.** Å frata optimereren evnen til å kjøre på
dellast koster 2,78 %. Å frata den fallhøydeavhengigheten koster 0,42 %. Det er relevant fordi
fallhøyde er den mekanismen som er vanskeligst å modellere med standard lineære metoder — og den
viser seg altså å bety lite her.

**En verdikonstant er feilkalibrert.** Vann som står igjen ved horisontslutt prises 32 % for lavt
i det ene systemet, fordi konstanten som brukes ikke stemmer med den faktiske fysikken. Å rette
det gjorde gapet *større*, ikke mindre.

---

## 9. Hva som gjenstår

Alle instanser målt så langt har **ett magasin og ingen luke** — den enkleste strukturen i hele
datasettet.

**Neste test: `res_casc_A`.** To magasiner, en luke mellom dem, ett kraftverk. Samme oppbygning
som det virkelige anlegget i 2019-artikkelen. Der er det **to koblede beslutningsvariabler per
tidssteg** — hvor mye slippes fra øvre magasin, og hvor mye produseres.

Det er den første ekte testen av B4s svakhet. Sammen med den kjøres en variant som *kan* endre to
variabler samtidig. Hvis den slår B4 vesentlig, er svakheten målt og ikke bare påstått — og da er
en metode som håndterer koblede beslutninger velbegrunnet.

---

## 10. Vurdering

**Det finnes et optimeringsproblem, men det er trangt på de enkleste instansene.**

Argumenter for at det holder:

- Vanskelighet er identifisert og forklart, ikke bare observert
- Publisert metode ligger 1,08 % fra optimum og varierer med 0,49 % mellom kjøringer
- En strukturell svakhet er identifisert og er umiddelbart testbar
- Kaskadesystemet er utestet, og der faller fasiten bort — som er nettopp begrunnelsen for
  heuristikker

Argumenter mot:

- Ett prosentpoeng er lite å jobbe i
- Testdataene mangler bindende begrensninger
- Kun tre instanser målt, alle med ett magasin
- Fallhøydeavhengigheten, som skulle motivere avanserte metoder, er verdt under en halv prosent

**Det som gjør dette til en robust oppgave uansett:** hovedresultatet er en *måling*, ikke en
seier. Spørsmålet «når trengs avanserte metoder, og når holder en enkel regel?» gir et svar
uansett hvordan tallene faller. Sammenlign med «jeg sammenlignet fem metaheuristikker og X vant»
— der står man igjen med ingenting hvis tallene ikke samarbeider.

---

## Åpne spørsmål

- Hvilket vannregime befinner ekte norske anlegg seg i? Hvis `rho > 1` er typisk, er funnene mine
  en observasjon om bransjen, ikke om testdataene.
- Binder overløpsbegrensningen i praksis? Hele mekanismen hviler på det.
- Er `res_casc_A` en forenklet versjon av Kvinesdal fra 2019-artikkelen?
- Hva koster en start/stopp i virkeligheten? Verdien i datasettene gir ingen effekt.