// example_queries.cypher — Cypher queries for JAPAQ-KG (run in Neo4j Browser or cypher-shell).
// Tip: start queries from an indexed property (station, place, year, severity label) so that the
// database does not have to scan all 110 million observations.

// 1. Stations per prefecture (complete metadata in the *_resolved properties)
MATCH (l:Location)
RETURN l.prefecture_resolved AS prefecture, count(*) AS stations
ORDER BY stations DESC LIMIT 5;

// 2. Hourly PM2.5 at one station on one day, without values flagged by quality control
MATCH (p:ObservedPollutant)-[:RECORDED_BY]->(s:Station {sid: '13101010'}),
      (p)-[:OBSERVED_AT]->(t:ObservationTime)
WHERE t.obsdate STARTS WITH '2023-07-01' AND p.pm25_flag IS NULL
RETURN t.obsdate AS hour, p.pm25 AS pm25, p.pm25_level AS level
ORDER BY hour;

// 3. Hours with Unhealthy PM2.5 in 2023, by prefecture
MATCH (p:ObservedPollutant {pm25_level: 'Unhealthy'})-[:OBSERVED_AT]->(t:ObservationTime {year: 2023}),
      (t)-[:AT_LOCATION]->(l:Location)
WHERE p.pm25_flag IS NULL
RETURN l.prefecture_resolved AS prefecture, count(*) AS hours
ORDER BY hours DESC LIMIT 5;

// 4. Photochemical oxidants and temperature on summer afternoons at one station
MATCH (p:ObservedPollutant)-[:RECORDED_BY]->(:Station {sid: '13101010'}),
      (p)-[:OBSERVED_AT]->(t:ObservationTime {year: 2023, season: 'Summer', timeCategory: 'Afternoon'})
WHERE p.ox IS NOT NULL AND p.temp IS NOT NULL AND p.temp_flag IS NULL
RETURN t.month AS month, round(avg(p.ox), 4) AS ox_ppm, round(avg(p.temp), 1) AS temp_c, count(*) AS hours
ORDER BY month;
