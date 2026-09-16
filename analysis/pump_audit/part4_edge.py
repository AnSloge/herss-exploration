"""Edge-case / robustness probes for the PUMP node, relevant to oracle use.

Cases that are expected to terminate the HERSS process (LOG_ERR calls
std::exit) are run in a subprocess so they do not take this script down.
"""
import json, subprocess, sys, os

PY = os.path.join("..", "..", ".venv", "bin", "python")
out = {}

def probe(inst, pump, pst=None, B_fr="-", A_fr="-"):
    acts = {"pump": pump}
    if pst is not None:
        acts["pst"] = pst
    p = subprocess.run([PY, "_probe.py", inst, json.dumps(acts), str(B_fr), str(A_fr)],
                       capture_output=True, text=True, timeout=600)
    res = None
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            res = json.loads(line[7:])
    return dict(returncode=p.returncode, result=res,
                stdout_tail=p.stdout.strip().splitlines()[-4:],
                stderr_tail=p.stderr.strip().splitlines()[-4:])

Z24 = [0.0] * 24

print("=== 4.1  action out of range ===")
for label, a in [("action = 1.5", 1.5), ("action = -0.1", -0.1),
                 ("action = 1.0000005 (inside 1e-6 tol)", 1.0000005),
                 ("action = 1.000002 (outside tol)", 1.000002)]:
    s = list(Z24); s[3] = a
    r = probe("inst_min", s)
    ok = r["returncode"] == 0
    print(f"  {label:<40} exit={r['returncode']:<3} "
          f"{'survived' if ok else 'PROCESS TERMINATED'}")
    if not ok:
        print(f"      -> {r['stdout_tail'][0] if r['stdout_tail'] else ''}")
    out[f"range_{label}"] = r

print("\n=== 4.2  source runs dry (PUMP_INLET_MASL clipping) ===")
# reservoir_B init_fr 0.001 -> 10.01 Mm3, only 0.01 Mm3 above PUMP_INLET_MASL 50.0
r = probe("inst_min", [1.0] * 6 + [0.0] * 18, B_fr=0.001)
print(f"  exit={r['returncode']}")
print(f"  {'t':>2} {'action':>7} {'pumped_Mm3':>12} {'B_Mm3':>10} {'MWh':>10} "
      f"{'cost':>10} {'startstop':>10}")
for row in r["result"]["rows"][:8]:
    print(f"  {row['t']:>2} {row['action']:>7.2f} {row['pumped']:>12.8f} "
          f"{row['B']:>10.6f} {row['MWh']:>10.6f} {row['cost']:>10.5f} {row['ss']:>10.2f}")
out["source_dry"] = r

print("\n=== 4.3  start/stop cost is charged on the ACTION, not on actual flow ===")
# Same as 4.2 but on inst_fixture, which has PUMP_STARTSTOP = 100.
r2 = probe("inst_fixture", [1.0] * 8, B_fr=0.0)
print(f"  exit={r2['returncode']}")
if r2["result"]:
    print(f"  {'t':>2} {'action':>7} {'pumped_Mm3':>12} {'MWh':>8} {'cost':>9} {'startstop':>10}")
    for row in r2["result"]["rows"]:
        print(f"  {row['t']:>2} {row['action']:>7.2f} {row['pumped']:>12.8f} "
              f"{row['MWh']:>8.4f} {row['cost']:>9.4f} {row['ss']:>10.2f}")
out["startstop_on_action"] = r2

print("\n=== 4.4  pump overfills the target above HRW ===")
# reservoir_A starts at HRW; pumping more must spill, i.e. energy paid for water
# that is then thrown away and valued at zero.
r3 = probe("inst_min", [1.0] * 24, A_fr=1.0, B_fr=1.0)
print(f"  exit={r3['returncode']}")
if r3["result"]:
    print(f"  {'t':>2} {'pumped':>10} {'A_Mm3':>10} {'A_masl':>9} {'A_overflow_m3s':>15} {'cost':>9}")
    for row in r3["result"]["rows"][:6]:
        print(f"  {row['t']:>2} {row['pumped']:>10.6f} {row['A']:>10.6f} "
              f"{row['A_masl']:>9.4f} {row['A_overflow']:>15.6f} {row['cost']:>9.4f}")
    tot_sp = sum(x["A_overflow"] for x in r3["result"]["rows"])
    print(f"  total overflow from reservoir_A = {tot_sp:.4f} m3/s-steps  VF={r3['result']['vf']:.4f}")
out["overfill_target"] = r3

print("\n=== 4.5  negative net head (target below source) ===")
# inst_invhead: target reservoir sits BELOW the source reservoir.
r4 = probe("inst_invhead", [1.0] + [0.0] * 23)
ok = r4["returncode"] == 0
print(f"  exit={r4['returncode']}  {'survived' if ok else 'PROCESS TERMINATED'}")
for line in r4["stdout_tail"]:
    if "ERROR" in line or "error" in line:
        print(f"      -> {line}")
out["negative_head"] = r4

with open("part4_results.json", "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote part4_results.json")
