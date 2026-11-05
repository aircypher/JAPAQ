CALL db.labels() YIELD label RETURN collect(label) AS labels;
CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rel_types;
MATCH (n) WHERE NOT (n)--() RETURN count(n) AS orphan_nodes;
MATCH (p:ObservedPollutant) WITH p, COUNT { (p)-[:OBSERVED_AT]->() } AS a, COUNT { (p)-[:RECORDED_BY]->() } AS b WHERE a <> 1 OR b <> 1 RETURN count(p) AS bad_pollutant_links;
MATCH (t:ObservationTime) WHERE COUNT { (t)-[:AT_LOCATION]->() } <> 1 RETURN count(t) AS bad_time_links;
