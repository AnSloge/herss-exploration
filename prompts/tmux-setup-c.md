# tmux-oppsett for Fase C-kjøringen

Kjøres på din maskin, fra repo-roten. Claude Code kjøres inne i tmux-sesjonen slik at jobben
overlever at du lukker terminalen eller mister forbindelsen.

## 1. Start en navngitt sesjon

```bash
cd ~/herss-exploration          # eller hvor repoet ligger
tmux new-session -d -s fasec
```

`-d` starter den i bakgrunnen, `-s fasec` gir den et navn du kan koble deg til igjen.

## 2. Send prompten inn til Claude Code i sesjonen

Legg prompten (`prompt-fase-c.md`) i repoet først, f.eks. `analysis/prompts/fase_c.md`. Deretter,
inne i tmux — koble til med:

```bash
tmux attach -t fasec
```

Start Claude Code der og gi den prompten. Bruk plan-modus først, la den legge planen, og godkjenn.

## 3. Koble fra uten å stoppe jobben

```
Ctrl-b  deretter  d
```

Det er «detach». Jobben kjører videre. Du kan lukke terminalen, logge av SSH, hva som helst.

## 4. Koble til igjen senere

```bash
tmux attach -t fasec
```

For å se om sesjonen lever:

```bash
tmux ls
```

## 5. Logg til fil parallelt (anbefalt)

tmux-bufferen er begrenset, og du vil ha en fullstendig logg. Inne i sesjonen, før du starter
kjøringen, slå på logging:

```
Ctrl-b  deretter  :
```
skriv så:
```
pipe-pane -o "cat >> analysis/fasec_tmux.log"
```

Da skrives alt i sesjonen til `analysis/fasec_tmux.log`. Prompten ber uansett Claude Code skrive
`result_faseC_*.json` per celle, så selv om loggen skulle svikte, ligger tallene på disk.

## 6. Sjekk framgang uten å forstyrre

Fra en helt vanlig terminal, mens jobben går:

```bash
ls -la analysis/result_faseC_*.json        # hvilke celler er ferdige
tail -f analysis/fasec_tmux.log            # følg loggen live (Ctrl-c for å slutte å følge)
```

## 7. Stopp jobben hvis nødvendig

```bash
tmux attach -t fasec
```
Ctrl-c i Claude Code, eller:
```bash
tmux kill-session -t fasec
```

---

## Viktig før du starter

- **Verifiser at `.venv` og cppyy fungerer** med én rask testkjøring før du lar Fase C gå over
  natten. En jobb som feiler på import i celle 1 og står død til morgenen er bortkastet natt.
  Kjør f.eks. `validate_instance.py` på én eksisterende instans først.
- **Sjekk diskplass.** Hver celle skriver DP-mellomlagre og en `output/`-katalog. Ti celler med
  skalerte magasiner kan bli en del filer.
- **Ikke kjør andre tunge jobber samtidig** — DP-konvergenssjekken er minne- og CPU-tung, og
  parallelle B4-omstarter bruker flere kjerner.

## Rekkefølge cellene bør kjøres

Prompten prioriterer diagonal → kanter. Be Claude Code kjøre **diagonalcellene først**, siden de
replikerer det du allerede har sett og dermed validerer at oppsettet er riktig før de nye
kant-cellene. Hvis diagonalen gir uventede tall, stopper du før du har brukt natten på kant-celler
bygget på et feil oppsett.