// neosemantics_export.cypher — export JAPAQ-KG (or a subset) as SOSA/SSN RDF.
//
// Requires the Neosemantics (n10s) plug-in for Neo4j and the HTTP endpoint /rdf/<db>/cypher.
// Each ObservedPollutant node becomes one sosa:Observation per non-null measurement, following
// japaq_kg_sosa_mapping.ttl. Exporting all 110 million records produces several billion triples;
// restrict the MATCH (station, period, pollutant) to the subset you need.
//
// Usage (example: one station, one month), POST to http://<host>:7474/rdf/neo4j/cypher with
//   {"cypher": "<the query below>", "format": "Turtle"}
// or run the query in Neo4j Browser and serialise the returned triples.

// 1. Namespace prefixes (once per database)
CALL n10s.nsprefixes.add('sosa',  'http://www.w3.org/ns/sosa/');
CALL n10s.nsprefixes.add('time',  'http://www.w3.org/2006/time#');
CALL n10s.nsprefixes.add('wgs84', 'http://www.w3.org/2003/01/geo/wgs84_pos#');
CALL n10s.nsprefixes.add('japaq', 'https://w3id.org/japaq/schema#');

// 2. Triples for a subset, one sosa:Observation per measurement
WITH 'https://w3id.org/japaq/data/' AS base,
     [['pm25','pm25_level','PM25'], ['so2','so2_level','SO2'], ['no','no_level','NO'],
      ['spm','spm_level','SPM'], ['ox','ox_level','Ox'], ['ws','ws_level','WindSpeed'],
      ['temp',null,'Temperature'], ['hum',null,'RelativeHumidity']] AS vars
MATCH (p:ObservedPollutant)-[:RECORDED_BY]->(s:Station {sid: $sid}),
      (p)-[:OBSERVED_AT]->(t:ObservationTime)-[:AT_LOCATION]->(l:Location)
WHERE t.obsdate >= $from AND t.obsdate < $to
UNWIND vars AS v
WITH base, p, s, t, l, v WHERE p[v[0]] IS NOT NULL
WITH base + 'obs/' + p.tid + '/' + v[0] AS o, base, p, s, t, l, v
UNWIND [
  [o, 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', 'http://www.w3.org/ns/sosa/Observation', false],
  [o, 'http://www.w3.org/ns/sosa/observedProperty', 'https://w3id.org/japaq/schema#' + v[2], false],
  [o, 'http://www.w3.org/ns/sosa/madeBySensor', base + 'sensor/' + s.sid + '/' + v[0], false],
  [o, 'http://www.w3.org/ns/sosa/hasFeatureOfInterest', base + 'location/' + l.sid, false],
  [o, 'http://www.w3.org/ns/sosa/hasSimpleResult', toString(p[v[0]]), true],
  [o, 'http://www.w3.org/ns/sosa/resultTime', replace(t.obsdate, ' ', 'T') + '+09:00', true],
  [base + 'sensor/' + s.sid + '/' + v[0], 'http://www.w3.org/ns/sosa/isHostedBy', base + 'station/' + s.sid, false],
  [base + 'location/' + l.sid, 'http://www.w3.org/2003/01/geo/wgs84_pos#lat', toString(l.lat), true],
  [base + 'location/' + l.sid, 'http://www.w3.org/2003/01/geo/wgs84_pos#long', toString(l.lon), true]
] + CASE WHEN v[1] IS NOT NULL AND p[v[1]] IS NOT NULL
         THEN [[o, 'https://w3id.org/japaq/schema#severityLevel', p[v[1]], true]] ELSE [] END
  + CASE WHEN p[v[0] + '_flag'] IS NOT NULL
         THEN [[o, 'https://w3id.org/japaq/schema#qualityFlag', p[v[0] + '_flag'], true]] ELSE [] END AS triple
WITH triple WHERE triple[2] IS NOT NULL
RETURN triple[0] AS subject, triple[1] AS predicate, triple[2] AS object, triple[3] AS isLiteral;
// Parameters example: {sid: '13101010', from: '2023-07-01 00:00:00', to: '2023-08-01 00:00:00'}
