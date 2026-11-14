"""Build research_data.js for research.html from research.json and frozen backtest run folders.
Supports multiple experiments. Never rewrites a run's results.json.
Not touched by build_data.py. Re-run only when experiments are added or page wiring changes.
Every strategy must carry a 'why' (required)."""
import json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f"{HERE}/research.json"))


def monthly(pts):
    out = {}
    for d, v in pts:
        out[d[:7]] = [d, v]
    m = list(out.values())
    return [pts[0]] + [p for p in m if p[0] != pts[0][0]]


def pct(x):
    return ("+" if x > 0 else "−" if x < 0 else "") + "{:,.1f}%".format(abs(x))


def resolve_run(folder):
    """Accept absolute paths or paths relative to the site root."""
    if os.path.isabs(folder) and os.path.isdir(folder):
        return folder
    rel = os.path.join(HERE, folder)
    if os.path.isdir(rel):
        return rel
    # basename under research/
    alt = os.path.join(HERE, "research", os.path.basename(folder.rstrip("/")))
    if os.path.isdir(alt):
        return alt
    raise FileNotFoundError(f"run folder not found: {folder}")


def load_results(run_dir):
    for cand in (f"{run_dir}/results/results.json", f"{run_dir}/results.json"):
        if os.path.exists(cand):
            return json.load(open(cand))
    raise FileNotFoundError(f"results.json missing under {run_dir}")


def load_curves(run_dir):
    for cand in (f"{run_dir}/results/curves_weekly.json", f"{run_dir}/curves_weekly.json"):
        if os.path.exists(cand):
            return json.load(open(cand))
    raise FileNotFoundError(f"curves_weekly.json missing under {run_dir} (needed for charts; not a results rewrite)")


def load_manifest(run_dir):
    for cand in (f"{run_dir}/data/manifest.json", f"{run_dir}/manifest.json"):
        if os.path.exists(cand):
            return json.load(open(cand))
    return {}


def enrich_strategies(strategies, res, curves):
    out = []
    for s in strategies:
        k = s["key"]
        r = res[k]
        f, n = r["windows"]["full"], r["windows"]["recent"]
        fo, fb, no, nb = f["open"], f["buy_hold"], n["open"], n["buy_hold"]
        s = dict(s)
        s["verdict"] = r["verdict"]
        s["ddLimit"] = r["dd_limit_10pct"]
        s["feePct"] = r["fee_per_side_pct"]
        s["full"] = {
            "from": fo["first"], "to": fo["last"], "strat": fo, "hold": fb,
            "closeFill": f["close"], "doubleFeeReturn": f["open_double_fee_total_return_pct"],
        }
        s["recent"] = {"from": no["first"], "to": no["last"], "strat": no, "hold": nb}
        s["curve"] = monthly(curves[k])
        s["holdCurve"] = monthly(curves[k + "__bh"])
        if not s.get("why"):
            s["why"] = (
                "Picked for testing because it is widely shared online with fixed, checkable rules (source linked). "
                "Historical backtest, next-open fills, fees included: {} to {}: {} (max drawdown {}%) vs buy-and-hold {} ({}%). "
                "Recent window {} to {}: {} vs buy-and-hold {}. Verdict by the pre-written rule: {}. 10% drawdown limit: {}."
            ).format(
                fo["first"], fo["last"], pct(fo["total_return_pct"]), fo["max_dd_pct"],
                pct(fb["total_return_pct"]), fb["max_dd_pct"],
                no["first"], no["last"], pct(no["total_return_pct"]), pct(nb["total_return_pct"]),
                r["verdict"], r["dd_limit_10pct"],
            )
        for req in ("name", "plain", "sources", "rules", "why", "verdict"):
            assert s.get(req), f"{k}: missing required field {req}"
        out.append(s)
    order = {"Promising": 0, "Mixed": 1, "Failed": 2}
    out.sort(key=lambda s: (order[s["verdict"]], -(s["full"]["strat"]["sharpe"] - s["full"]["hold"]["sharpe"])))
    return out


def publish_copies(run_dir):
    """Flatten a few public check files into research/<basename>/ without touching results.json contents."""
    dst = f"{HERE}/research/{os.path.basename(run_dir)}"
    os.makedirs(dst, exist_ok=True)
    for rel in [
        "fetch.py", "backtest.py", "crosscheck_vbt.py", "README.md",
        "data/manifest.json", "manifest.json",
        "results/results.json", "results.json",
        "results/crosscheck_vbt.txt", "crosscheck_vbt.txt",
        "results/curves_weekly.json", "curves_weekly.json",
    ]:
        src = f"{run_dir}/{rel}"
        if not os.path.exists(src):
            continue
        target = f"{dst}/{os.path.basename(rel)}"
        if os.path.abspath(src) == os.path.abspath(target):
            continue
        shutil.copy(src, target)


# Backward compatible: single-run research.json still works; prefer experiments[].
if "experiments" in R:
    experiments_in = R["experiments"]
else:
    experiments_in = [{
        "id": os.path.basename(R["run"].rstrip("/")),
        "date": "",
        "label": R.get("label", ""),
        "folder": R["run"],
        "method": R.get("method", []),
        "strategies": R["strategies"],
    }]

experiments_out = []
for exp in experiments_in:
    run_dir = resolve_run(exp["folder"])
    res = load_results(run_dir)
    curves = load_curves(run_dir)
    man = load_manifest(run_dir)
    strategies = enrich_strategies(exp["strategies"], res, curves)
    experiments_out.append({
        "id": exp.get("id") or os.path.basename(run_dir),
        "date": exp.get("date") or "",
        "label": exp.get("label") or os.path.basename(run_dir),
        "folder": f"research/{os.path.basename(run_dir)}",
        "method": exp.get("method", []),
        "dataManifest": man,
        "strategies": strategies,
    })
    publish_copies(run_dir)

data = {
    "title": R.get("title", "Researched strategies"),
    "label": R.get("label", "Historical backtests"),
    "experiments": experiments_out,
}
# Flat convenience fields for older readers: first experiment.
data["method"] = experiments_out[0]["method"] if experiments_out else []
data["dataManifest"] = experiments_out[0]["dataManifest"] if experiments_out else {}
data["strategies"] = [s for e in experiments_out for s in e["strategies"]]

ids = ", ".join(e["id"] for e in experiments_out)
js = (
    "/* Generated by build_research.py from research.json and frozen runs: {}. Historical backtests only. */\n"
    "const RESEARCH = {};\n"
).format(ids, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
open(f"{HERE}/research_data.js", "w").write(js)
print("research_data.js:", len(experiments_out), "experiments,", sum(len(e["strategies"]) for e in experiments_out), "strategies,", len(js), "bytes")
