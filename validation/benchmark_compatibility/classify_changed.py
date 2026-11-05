"""
classify_changed.py — classify every benchmark item that bench_impact.py reports as 'changed' or 'error'.

For each such item the gold query is re-run on the released graph and compared with the frozen
gold result using math.isclose (rel_tol=1e-9, abs_tol=1e-12) on numbers:
  float_tolerance  : same rows in the same order once numbers are compared with tolerance
  tie_order        : same rows (with tolerance) but in a different order
  real_difference  : anything else (rows differ)
  error            : query failed again (e.g. timeout)
Usage (with NEO4J_* of the released graph): python classify_changed.py <benchmark.csv> <gold.json> <progress.jsonl> <out.json>
"""
import csv, json, math, os, sys
from neo4j import GraphDatabase, Query

B, G, PR, OUT = sys.argv[1:5]
items = {r["id"]: r for r in csv.DictReader(open(B, encoding="utf-8"))}
gold = json.load(open(G))
todo = [json.loads(l) for l in open(PR)]
todo = [r for r in todo if r["status"] in ("changed", "error")]

def close(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    return a == b

def row_eq(r, s):
    return r.keys() == s.keys() and all(close(r[k], s[k]) for k in r)

def multiset_eq(xs, ys):
    ys = list(ys)
    for x in xs:
        for j, y in enumerate(ys):
            if row_eq(x, y):
                ys.pop(j); break
        else:
            return False
    return not ys

def py(v):
    if hasattr(v, "iso_format"): return v.iso_format()
    if isinstance(v, list): return [py(x) for x in v]
    if isinstance(v, dict): return {k: py(x) for k, x in v.items()}
    return v

drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"]))
res = []
with drv.session(default_access_mode="READ") as s:
    for t in todo:
        i = t["id"]; g = gold[i]["records"]
        try:
            new = [{k: py(v) for k, v in r.items()} for r in s.run(Query(items[i]["gold_cypher"], timeout=900))]
        except Exception as e:
            res.append({"id": i, "class": "error", "detail": str(e)[:200]}); continue
        if len(new) == len(g) and all(row_eq(a, b) for a, b in zip(new, g)):
            c = "float_tolerance"
        elif len(new) == len(g) and multiset_eq(new, g):
            c = "tie_order"
        else:
            c = "real_difference"
        res.append({"id": i, "class": c, "category": items[i]["category"], "n_gold": len(g), "n_new": len(new),
                    "gold_head": g[:3], "new_head": new[:3]})
drv.close()
summary = {}
for r in res:
    summary[r["class"]] = summary.get(r["class"], 0) + 1
json.dump({"summary": summary, "items": res}, open(OUT, "w"), indent=1, default=str)
print(json.dumps(summary))
for r in res:
    if r["class"] in ("real_difference", "error"):
        print(json.dumps(r, default=str)[:600])
