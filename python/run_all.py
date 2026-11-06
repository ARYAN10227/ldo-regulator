"""Run every LDO simulation in ngspice and save plots + a results summary.
Usage (from the repo root):  python3 python/run_all.py
Needs ngspice on PATH, plus numpy and matplotlib."""
import subprocess, re, os, json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NG = os.path.join(ROOT, "ngspice"); RES = os.path.join(ROOT, "results"); os.makedirs(RES, exist_ok=True)
LOADS = (0, 0.1e-3, 1e-3, 10e-3, 50e-3, 100e-3)

def ng(netlist):
    path = os.path.join(NG, "_run.cir"); open(path, "w").write(netlist)
    out = subprocess.run(["ngspice", "-b", "_run.cir"], cwd=NG, capture_output=True, text=True).stdout
    os.remove(path); return out
def meas(out, key):
    m = re.search(r"^" + key + r"\s*=\s*(\S+)", out, re.M); return float(m.group(1)) if m else float("nan")

def loop_gain(il, resr=0.5, save=None):
    """Middlebrook voltage injection: VINJ sits between the divider tap and the error-amp input."""
    out = ng(f""".include ldo_core.inc
.param RESR={resr}
VIN vin 0 5
VINJ fbx ein DC 0 AC 1
ILOAD out 0 {il}
.control
ac dec 50 0.1 100Meg
let T = -v(fbx)/v(ein)
let tdb = db(T)
let tph = 180/pi*cph(T)
meas ac fc when tdb=0 fall=last
meas ac ph find tph at=fc
{f'wrdata {save} tdb tph' if save else ''}
.endc
.end""")
    return 180 + meas(out, "ph"), meas(out, "fc")

R = {}
# DC: output voltage, load regulation, dropout
out = ng(open(os.path.join(NG, "dc.cir")).read())
R["vout_1mA"], R["vout_100mA"] = meas(out, "v1m"), meas(out, "v100m")
R["load_reg_mV"] = (R["vout_1mA"] - R["vout_100mA"]) * 1e3
R["dropout_mV_100mA"] = (meas(out, "vin_drop") - 0.99 * 3.288) * 1e3
# Loop gain / phase margin vs load
R["pm_vs_load"] = {}
for il in LOADS:
    pm, fc = loop_gain(il, save=f"loop_{il*1e3:g}mA.txt" if il in (1e-3, 100e-3) else None)
    R["pm_vs_load"][f"{il*1e3:g} mA"] = {"pm_deg": round(pm, 1), "fc_kHz": round(fc / 1e3, 1)}
# ESR sweep
esrs = np.round(np.logspace(-2, 1, 25), 4); pm_map = np.array([[loop_gain(il, e)[0] for il in LOADS] for e in esrs])
ok = esrs[pm_map.min(axis=1) >= 45]; R["esr_stable_range_ohm_pm45"] = [float(ok.min()), float(ok.max())]
# PSRR
out = ng(open(os.path.join(NG, "psrr.cir")).read())
R["psrr_dB"] = {"100mA_100Hz": meas(out, "p100"), "100mA_1kHz": meas(out, "p1k"), "100mA_10kHz": meas(out, "p10k"),
                "100mA_100kHz": meas(out, "p100k"), "1mA_1kHz": meas(out, "q1k")}
# Load transient
ng(open(os.path.join(NG, "tran.cir")).read())
d = np.loadtxt(os.path.join(NG, "tran_out.txt")); t, v = d[:, 0], d[:, 1]
pre = v[np.argmin(abs(t - 99e-6))]; s = (t > 100e-6) & (t < 500e-6); vf = v[np.argmin(abs(t - 499e-6))]
rec = lambda tol: (t[s][np.where(abs(v[s] - vf) > tol)[0][-1]] - 100e-6) * 1e6
R["load_step"] = {"undershoot_mV": (pre - v[s].min()) * 1e3, "recover_to_1pct_us": rec(0.01 * 3.288),
                  "recover_to_10mV_us": rec(10e-3), "recover_to_1mV_us": rec(1e-3),
                  "overshoot_on_unload_mV": (v[t > 500e-6].max() - v[-1]) * 1e3}
json.dump(R, open(os.path.join(RES, "results.json"), "w"), indent=2, default=float); print(json.dumps(R, indent=2, default=float))

# ---- plots ----
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6.5), sharex=True)
for f, lab, c in (("loop_1mA.txt", "1 mA", "#4a6fa5"), ("loop_100mA.txt", "100 mA", "#c0504d")):
    x = np.loadtxt(os.path.join(NG, f)); a1.semilogx(x[:, 0], x[:, 1], c=c, label=lab); a2.semilogx(x[:, 0], 180 + x[:, 3], c=c, label=lab)
a1.axhline(0, c="gray", lw=.8); a2.axhline(0, c="gray", lw=.8)
a1.set_ylabel("Loop gain (dB)"); a2.set_ylabel("Phase margin (deg)\n= 180 + ∠T"); a2.set_xlabel("Frequency (Hz)")
a1.set_title("LDO loop gain (Middlebrook injection), ESR = 0.5 Ω"); a1.legend(); a1.set_ylim(-60, 130); a2.set_ylim(-90, 200)
for a in (a1, a2): a.grid(True, which="both", alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(RES, "loop_gain.png"), dpi=150)
fig, ax = plt.subplots(figsize=(8, 4.5))
for j, il in enumerate(LOADS): ax.semilogx(esrs, pm_map[:, j], marker="o", ms=3, label=f"{il*1e3:g} mA")
ax.axhline(45, c="k", ls="--", lw=.8); ax.axvspan(ok.min(), ok.max(), color="#9bbb59", alpha=.15, label="PM ≥ 45° at every load")
ax.set_xlabel("Output-capacitor ESR (Ω)"); ax.set_ylabel("Phase margin (deg)"); ax.set_title("Stability vs ESR (4.7 µF)")
ax.legend(fontsize=8, ncol=2); ax.grid(True, which="both", alpha=.3); fig.tight_layout(); fig.savefig(os.path.join(RES, "esr_sweep.png"), dpi=150)
fig, ax = plt.subplots(figsize=(8, 4.5))
for f, lab, c in (("psrr_100m.txt", "100 mA", "#c0504d"), ("psrr_1m.txt", "1 mA", "#4a6fa5")):
    x = np.loadtxt(os.path.join(NG, f)); ax.semilogx(x[:, 0], x[:, 1], c=c, label=lab)
ax.set_xlabel("Frequency (Hz)"); ax.set_ylabel("PSRR (dB)"); ax.set_title("Power-supply rejection"); ax.legend(); ax.grid(True, which="both", alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(RES, "psrr.png"), dpi=150)
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
a1.plot(t * 1e6, v, c="#4a6fa5"); a1.set_ylabel("Vout (V)"); a1.set_title("Load step 1 mA → 100 mA → 1 mA (1 µs edges)")
il = np.where((t >= 100e-6) & (t < 501e-6), 100, 1); a2.plot(t * 1e6, il, c="#c0504d"); a2.set_ylabel("Load (mA)"); a2.set_xlabel("Time (µs)")
for a in (a1, a2): a.grid(True, alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(RES, "load_transient.png"), dpi=150)
for f in os.listdir(NG):
    if f.endswith(".txt"): os.remove(os.path.join(NG, f))
