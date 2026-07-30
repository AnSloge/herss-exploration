# Den avgjørende målingen: eksakt DP mot tunet terskelpolitikk på `mini_utahps_daily`

**Dato:** 2026-07-30
**Utført av:** Claude (Sonnet 5), på oppdrag fra repo-eier, jf. `CLAUDE.md` §10 punkt 6 og
`analysis/herss_repo_gjennomgang.md` §11.4.
**HERSS-versjon:** `VERSION 3.1.03`, `VERSION_DATE 20260611` (`src/herss.h:49-50`),
upstream commit `029a2d5`.
**Datasett:** `data/mini_utahps_daily` (T=30 dager, ett magasin (HJELLE), én kraftstasjon
med én generator (SVOLETJONN), én kanal (terminal, uten verdi i V)).
**Kode:** `analysis/mini_utahps_daily_dp/` (`oracle.py`, `replica.py`, `dp.py`,
`threshold.py`, `validate.py`, `final_measurement.py`, `result.json`).

Merkelapper som i `herss_repo_gjennomgang.md`: **[kilde]**, **[målt]**, **[vurdering]**, **[antakelse]**, **[usikkert]**.

---

## 1. Hva som ble gjort

Dette er go/no-go-målingen som både `CLAUDE.md` §10.6 og rapportens §11.4 sier må gjøres
**før** man binder seg til en endelig problemformulering: løs `mini_utahps_daily` eksakt med
dynamisk programmering over diskretisert magasinvolum og handling, sammenlign mot en tunet
pris-terskelpolitikk, og se om gapet er under ~1 % (formuleringen er ikke en masteroppgave ennå)
eller over ~3 % (det finnes et problem verdt å løse).

Fire steg, i rekkefølge:

1. **Python-replika av ett-tidssteg-overgangen** (`replica.py`), fordi HERSS kun eksponerer
   hel-horisont `Simulate()` og ingen enkelttrinns-API — nøyaktig som forutsett i §11.4.
2. **Validering av replikaen mot den ekte simulatoren** (`validate.py`, via `oracle.py`/cppyy).
3. **Eksakt DP** (`dp.py`): bakover-induksjon over diskretisert magasinvolum, pluss én
   binær på/av-dimensjon for start/stopp-kostnaden, med handlingen diskretisert over [0,1].
4. **Tunet terskelpolitikk** (`threshold.py`) og **kryssvalidering av begge løsningene mot ekte
   HERSS** (`final_measurement.py`), ikke bare mot replikaen.

## 2. Fysikk-replikaen

`replica.py` implementerer, formel for formel, sitert til linjenummer:

- Magasinets vannbalanse, tunnel-uttak, `up_res_Mm3 = max(0, res_Mm3 − filling_at_lrw_Mm3)`
  og aggressive-action-klippet (`reservoir.cpp:465-537`, `powerstation.cpp:781-793`).
- Overløp via `OVERFLOW_CURVE` (`reservoir.cpp:188-231`), LRW-straff (`reservoir.cpp:649-653`).
- **[kilde, viktig detalj]** `start_of_stp_masl` for kraftstasjonens fallhøydeberegning bruker
  magasinnivået **fra slutten av forrige dag**, ikke et nivå gjenberegnet etter dagens tilsig
  (`reservoir.cpp:499`). Dette er replikert eksakt — det er ikke en implementasjonsdetalj man
  kan velge bort.
- Fallhøyde, hodetap, turbinkurve, produksjon og inntekt (`powerstation.cpp:167-236`).
- Start/stopp-kostnad, inkludert at `t=0` alltid bruker `previous_action=0.0` uavhengig av
  starttilstandsfilen — et dokumentert kode/manual-avvik (`powerstation.cpp:246`,
  jf. rapportens §4.2).
- Terminalverdi: `e_n · remaining_active_Mm3 · 1000 · restprice` (`riversystem.cpp:436,474-476`).

Kanalnoden (id 2) er utelatt: `channel.cpp:126-127` og `riversystem.cpp:433-436` bekrefter at
kanalens inntekt og `remaining_active_Mm3` alltid er 0, og den er systemets mest nedstrøms node,
så den kan ikke påvirke V i dette ett-magasin-systemet. Tilstanden reduseres dermed eksakt til
**én skalar**: `res_Mm3` (pluss på/av-biten for start/stopp).

### Validering **[målt]**

`validate.py` sammenligner replikaen mot ekte HERSS (via cppyy) på 8 handlingssekvenser,
inkludert de leverte `actions.txt`, konstante nivåer, tilfeldige handlinger, en sekvens
designet for å utløse overløp, og en sekvens designet for å utløse aggressive-action-straffen
(nesten tomt magasin + full slukeevne). Alle 8 besto:

| Test | ΔVF (replika − ekte) |
|---|---|
| Leverte `actions.txt` | +0.00005 |
| Alle av | 0.00000 |
| Alle på (maks) | −0.00027 |
| Konstant 0.5 | −0.00002 |
| Tilfeldig, seed=42 | −0.00008 |
| Av så maks (overløp-test) | −0.00024 |
| Bang-bang topp-15-prisdager | −0.00006 |
| Nesten tomt + alle maks (aggressive-action-test) | −0.00039 |

Maksimalt avvik ~0,0004 EUR på verdier i størrelsesorden 30 000–92 000 EUR. Avviket kommer fra
at HERSS' `ArrayCurve` kvantiserer kurveoppslag til 1000 punkter (`arraycurve.h:36`), mens
replikaen bruker eksakt stykkevis-lineær interpolasjon — neglisjerbart for formålet.
Aggressive-action-testen ga `aggressive_cost ≈ 860,83` i begge (differanse 0,02 EUR), som
bekrefter at straffe-grenen er replikert korrekt, ikke bare den vanlige grenen.

**[teknisk notat, ikke HERSS-relatert]** Under arbeidet ble det funnet at cppyy segfaulter ved
lesing av mer enn ett rått `double*`-array-felt fra HERSS' `Scenario`-objekter i samme
Python-prosess (uavhengig av hvilket felt eller om man cacher referanser). Løst med
prosess-isolasjon (ett felt per subprosess). Dokumentert i minnesystemet
(`cppyy-lowlevelview-bug`) og i `oracle.py`s docstring, siden det vil ramme enhver framtidig
Python-tooling mot HERSS via cppyy.

## 3. DP

**Tilstand:** magasinvolum `res_Mm3` diskretisert over `[0, 25]` Mm³ med 4001 punkter (dekker
dødvolum under LRW og flomvolum opp til ca. masl 758, med god margin — verifisert at ingen
politikk i denne horisonten når grensen, `dp.py` sin `max res_Mm3 under all-off policy = 14.74`).
Pluss én binær på/av-dimensjon for forrige dags handling (start/stopp-kostnad).

**Handling:** diskretisert i 201 punkter i bakover-induksjonen, og i 2001 punkter i den
fremover-rettede politikk-ekstraksjonen (kontinuerlig tilstand, gjenoptimert hver dag mot den
diskretiserte verdifunksjonen fra neste dag).

**Metode:** bakover-induksjon (Bellman), vektorisert med numpy over volum-rutenettet;
kontinuasjonsverdi interpolert lineært mot nabo-rutenettpunkter. ~72 000
overgangsevalueringer totalt (`T × 2 × 201` i bakover-induksjonen + `T × 2001` i
fremover-rulleringen).

**Robusthetssjekk mot diskretisering [målt]:** å doble oppløsningen (8001 volumpunkter, 401
handlingspunkter) endret verdien fra 93826,71 til 93826,92 — en endring på 0,0002 %, altså to
størrelsesordener under gapet som rapporteres i §5. DP-verdien er konvergert nok til at
gap-tallet ikke er et diskretiseringsartefakt.

## 4. Tunet terskelpolitikk

Familie: `a_t = L` hvis dag `t` er blant de `K` høyeste-prisdagene, ellers `0`. Dette er
nøyaktig en prisgrense (τ = den K-te høyeste prisen) med ett produksjonsnivå `L`. Både `K`
(0..30) og `L` (0,01 til 1,00 i steg på 0,01) ble søkt uttømmende (3100 evalueringer) og
evaluert gjennom den validerte replikaen — ingen "repair"-operator; hvis en kandidat ber om
mer vann enn tilgjengelig, slår aggressive-action-straffen inn nøyaktig som i HERSS.

**Beste terskelpolitikk:** `K=29` (produser 29 av 30 dager), `L=0,99`.

## 5. Resultat — kryssvalidert mot ekte HERSS **[målt]**

| | Handlinger | VF (ekte HERSS) | VF (replika) | Replika−ekte |
|---|---|---|---|---|
| **DP (eksakt)** | fremover-rullert politikk | **93 826,7081** | 93 826,7081 | −0,00002 |
| **Terskel (tunet)** | K=29, L=0,99 | **93 559,0323** | 93 559,0320 | −0,00026 |
| Leverte `actions.txt` (referanse) | — | 69 135,2234 | — | — |

```
gap = 93 826,7081 − 93 559,0323 = 267,68 EUR
gap% = 267,68 / 93 826,7081 = 0,2853 %
```

### Feasibility-tabell **[målt]**

Begge løsningene er fullt gjennomførbare — ingen soft constraint er i praksis bindende:

| | aggressive-action-kost | LRW-straff | start/stopp-kost | sum overløp | magasinnivå-spenn |
|---|---|---|---|---|---|
| DP | 0,00 | 0,00 | 1,00 EUR | 0,00 Mm³ | [751,37; 757,00] masl |
| Terskel | 0,00 | 0,00 | 3,00 EUR | 0,00 Mm³ | [751,36; 756,99] masl |

Begge holder seg innenfor `[LRW, HRW]` = `[748, 757]` gjennom hele horisonten og rører aldri
aggressive-action-grensen. Dette bekrefter rapportens observasjon (§7.3, §11.3): selv den
sanne optimale politikken finner det ikke lønnsomt å bryte volumgrensen mot 1000 EUR/Mm³-straffen.

## 6. Konklusjon og go/no-go **[vurdering]**

**Gapet er 0,29 %, godt under 1 %-grensen.** Per kriteriene i `CLAUDE.md` §10.6 og rapportens
§11.4/§11.9: **formuleringen er, på dette datasettet, ikke ennå en masteroppgave.** Bindende
struktur må legges til før man binder seg til denne som hovedbidrag — for eksempel en
terminal-lagringsskranke, rampebegrensninger, eller flere generatorer med reell forpliktelse
(jf. rapportens forslag i §11.4).

Dette er ikke en overraskelse gitt rapportens forhåndsanalyse i §11.4: med konstant
marginalverdi av vann, én deterministisk prisserie og perfekt framsyn, ligger optimum
strukturelt nært en terskelregel. Det som gjenstår av "vanskelighet" — fallhøydeavhengighet,
ikke-konkav turbinkurve, kvadratisk falltap — er reelt, men på denne 30-dagers,
ett-magasin-instansen er de samlede perturbasjonene fra terskelregelen tydeligvis for små til
å gi et gap over 1 %.

**Hva dette ikke sier:** dette er én instans. Rapportens §7.3 identifiserer
`mini_utahps_daily` som "den minste instansen som faktisk inneholder et problem" (fyllingsgrad
`R=0,87` — lagringen binder), i motsetning til timesoppløste mini-datasett (`R=13`, lagringen
binder ikke i det hele tatt) hvor gapet trolig er enda mindre. Målingen bør gjentas på
`utahps_daily` (4 magasin, kaskadekobling) hvis/når en håndterbar DP- eller sterk
heuristikk-referanse kan konstrueres der — kanaler mellom kraftverk i en kaskade kan ikke
neglisjeres slik de kan her (rapportens §4.3), så staten er ikke lenger éndimensjonal, og
eksakt DP er trolig ikke gjennomførbart (rapportens §11.5).

**Metodisk forbehold:** DP-verdien over er eksakt opp til diskretisering (verifisert
konvergent, §3), ikke en MILP-relaksasjon — CLAUDE.md §2s forbehold om at "MILP-optimum
begrenser den lineariserte modellen, ikke det sanne optimum" gjelder ikke her, fordi ingen
linearisering er gjort. DP-en løser den fulle ikke-lineære overgangsfunksjonen eksakt (innenfor
rutenett-oppløsning). Gap-tallet over er derfor et direkte, ikke et empirisk-tilnærmet, mål på
avstanden mellom en enkel terskelpolitikk og det sanne optimum på denne instansen.

## 7. Reproduserbarhet

```
cd analysis/mini_utahps_daily_dp
../../.venv/bin/python validate.py          # replika-vs-HERSS validering (8 tester)
../../.venv/bin/python final_measurement.py # DP + terskel + kryssvalidering -> result.json
```

Ingen filer under `data/` eller `src/` er endret. All generert kode ligger under
`analysis/mini_utahps_daily_dp/`, utenfor `data/`s reproduserbarhetsfelle (`CLAUDE.md` §5).
