"""tie_check.py — explain 'changed' benchmark items: are they ties at a LIMIT boundary?

For each changed item: gold rows (benchmark cache), rows on the released graph, and the full ranked
result without LIMIT, to show whether the differing rows share the same sort value as the
boundary row. Usage (with NEO4J_* of the released graph): python tie_check.py <benchmark.csv> <gold.json> <progress.jsonl>
"""
import csv, json, os, re, sys
from neo4j import GraphDatabase, Query
B, G, PR = sys.argv[1:4]
items = {r["id"]: r for r in csv.DictReader(open(B, encoding="utf-8"))}
gold = json.load(open(G))
changed = [json.loads(l)["id"] for l in open(PR) if json.loads(l)["status"] == "changed"]
drv = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"]))
with drv.session(default_access_mode="READ") as s:
    for i in changed:
        q = items[i]["gold_cypher"]
        new = [dict(r) for r in s.run(Query(q, timeout=300))]
        m = re.search(r"\bLIMIT\s+(\d+)\s*$", q.strip(), re.I)
        full = [dict(r) for r in s.run(Query(re.sub(r"\bLIMIT\s+\d+\s*$", "", q.strip(), flags=re.I) if m else q, timeout=300))]
        print(f"id {i} ({items[i]['category']}), LIMIT {m.group(1) if m else '-'}")
        print("  gold:", gold[i]["records"])
        print("  new :", new)
        k = int(m.group(1)) if m else len(full)
        print(f"  ranked (first {k + 5} of {len(full)}):", full[:k + 5])
drv.close()
