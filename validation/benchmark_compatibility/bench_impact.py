"""
bench_impact.py — does the released graph reproduce the AirCypher benchmark?

Executes every reference (gold) Cypher query of the benchmark against the released graph and
compares the result with the frozen gold result of the benchmark release (computed on the graph
on which the benchmark was defined, before the additions of this release).
Read-only. Per-query timeout 300 s (server-side). Runs 8 queries in parallel.

Comparison: rows compared as multisets (order-insensitive) and, separately, in order;
floats compared with relative tolerance 1e-9.
Output: bench_impact_results.csv, bench_impact_summary.json
Usage (with NEO4J_URI/USER/PASS of the released graph): python bench_impact.py <benchmark.csv> <gold_cache.json> <out_dir>
"""
import csv, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from neo4j import GraphDatabase, Query

BENCH, GOLD, OUT = sys.argv[1:4]
TIMEOUT = 300.0   # seconds; enforced server-side via Query(timeout=...)
items = list(csv.DictReader(open(BENCH, encoding="utf-8")))
gold = json.load(open(GOLD))
drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"]))

def norm(v):
    # distinct type tags so that None, numbers and strings never compare directly
    if v is None:
        return ("0",)
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)):
        return ("n", round(float(v), 9) if math.isfinite(float(v)) else str(v))
    if isinstance(v, str):
        return ("s", v)
    if isinstance(v, (list, tuple)):
        return ("l", tuple(norm(x) for x in v))
    if isinstance(v, dict):
        return ("d", tuple(sorted((k, norm(x)) for k, x in v.items())))
    return ("s", str(v))

def rowkey(r):
    return tuple(sorted((k, norm(v)) for k, v in r.items()))

def to_py(v):
    if hasattr(v, "iso_format"):
        return v.iso_format()
    if isinstance(v, list):
        return [to_py(x) for x in v]
    if isinstance(v, dict):
        return {k: to_py(x) for k, x in v.items()}
    return v

def run(it):
    t0 = time.time()
    try:
        with drv.session(default_access_mode="READ") as s:
            res = s.run(Query(it["gold_cypher"], timeout=TIMEOUT))
            rows = [{k: to_py(v) for k, v in r.items()} for r in res]
        err = ""
    except Exception as e:
        rows, err = None, type(e).__name__ + ": " + str(e)[:160]
    g = gold.get(it["id"], {}).get("records")
    if rows is None:
        status = "error"
    else:
        same_multiset = sorted(map(rowkey, rows)) == sorted(map(rowkey, g or []))
        same_order = [rowkey(r) for r in rows] == [rowkey(r) for r in (g or [])]
        status = "same" if same_order else ("same_rows_diff_order" if same_multiset else "changed")
    return {"id": it["id"], "category": it["category"], "split": it["split"], "status": status,
            "n_gold": len(g or []), "n_new": -1 if rows is None else len(rows),
            "secs": round(time.time() - t0, 2), "error": err,
            "cypher": it["gold_cypher"].replace("\n", " ")[:400]}

CK = f"{OUT}/bench_impact_progress.jsonl"
done = {}
if os.path.exists(CK):
    for line in open(CK):
        r = json.loads(line); done[r["id"]] = r
todo = [it for it in items if it["id"] not in done]
print(f"resuming: {len(done)} done, {len(todo)} to run", flush=True)
ck = open(CK, "a")
with ThreadPoolExecutor(8) as ex:
    for i, r in enumerate(ex.map(run, todo), 1):
        done[r["id"]] = r; ck.write(json.dumps(r) + "\n"); ck.flush()
        if i % 250 == 0:
            print(len(done), "done", flush=True)
ck.close()
out = [done[it["id"]] for it in items]
drv.close()
with open(f"{OUT}/bench_impact_results.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
summ = {}
for r in out:
    summ.setdefault(r["status"], 0); summ[r["status"]] += 1
by_split = {}
for r in out:
    by_split.setdefault(r["split"], {}).setdefault(r["status"], 0); by_split[r["split"]][r["status"]] += 1
json.dump({"overall": summ, "by_split": by_split}, open(f"{OUT}/bench_impact_summary.json", "w"), indent=1)
print(json.dumps({"overall": summ, "by_split": by_split}, indent=1))
