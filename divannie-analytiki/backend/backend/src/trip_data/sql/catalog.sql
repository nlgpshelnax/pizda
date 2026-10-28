PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS catalog_schema(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingest_sources(
 id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, last_success_at TEXT NOT NULL, row_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ingest_runs(
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, status TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT NOT NULL, row_count INTEGER NOT NULL DEFAULT 0,
 error_code TEXT);
CREATE TABLE IF NOT EXISTS destinations(
 id TEXT PRIMARY KEY, city TEXT NOT NULL UNIQUE, country TEXT NOT NULL,
 latitude REAL NOT NULL, longitude REAL NOT NULL, timezone TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hotels(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), name TEXT NOT NULL,
 category TEXT NOT NULL, latitude REAL, longitude REAL, stars INTEGER CHECK(stars BETWEEN 0 AND 5),
 rating REAL, review_count INTEGER, website TEXT, address TEXT,
 source_mode TEXT NOT NULL CHECK(source_mode IN ('mock','snapshot','live')),
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), source_url TEXT,
 fetched_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS hotels_city_stars ON hotels(city_id,source_mode,active,stars);
CREATE TABLE IF NOT EXISTS guests(
 id TEXT PRIMARY KEY, adults INTEGER NOT NULL CHECK(adults>=1),
 children_ages_json TEXT NOT NULL CHECK(json_valid(children_ages_json)), pets INTEGER NOT NULL,
 children_count INTEGER GENERATED ALWAYS AS (json_array_length(children_ages_json)) VIRTUAL,
 total_guests INTEGER GENERATED ALWAYS AS (adults+json_array_length(children_ages_json)) VIRTUAL);
CREATE TABLE IF NOT EXISTS calendar_dates(
 date TEXT PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL,
 day_of_week INTEGER NOT NULL, is_weekend INTEGER NOT NULL, season TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hotel_quotes(
 id TEXT PRIMARY KEY, hotel_id TEXT NOT NULL REFERENCES hotels(id),
 guest_id TEXT NOT NULL REFERENCES guests(id), check_in TEXT NOT NULL REFERENCES calendar_dates(date),
 check_out TEXT NOT NULL REFERENCES calendar_dates(date), currency TEXT NOT NULL,
 amount_minor INTEGER NOT NULL CHECK(amount_minor>=0), price_basis TEXT NOT NULL,
 breakfast INTEGER, pets_allowed INTEGER, max_guests INTEGER, mandatory_fees_known INTEGER NOT NULL,
 source_mode TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 fetched_at TEXT NOT NULL, valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS hotel_quotes_scope ON hotel_quotes(hotel_id,check_in,check_out,guest_id);
CREATE TABLE IF NOT EXISTS transport_quotes(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id),
 guest_id TEXT NOT NULL REFERENCES guests(id), direction TEXT NOT NULL, mode TEXT NOT NULL,
 origin TEXT NOT NULL, destination TEXT NOT NULL, departure_at TEXT NOT NULL, arrival_at TEXT NOT NULL,
 currency TEXT NOT NULL, amount_minor INTEGER NOT NULL, price_basis TEXT NOT NULL,
 source_mode TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 fetched_at TEXT NOT NULL, valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS transport_scope ON transport_quotes(origin,destination,departure_at,guest_id);
CREATE TABLE IF NOT EXISTS transfer_quotes(
 id TEXT PRIMARY KEY, hotel_id TEXT NOT NULL REFERENCES hotels(id),
 guest_id TEXT NOT NULL REFERENCES guests(id), direction TEXT NOT NULL,
 duration_minutes INTEGER NOT NULL, capacity INTEGER NOT NULL, child_seats INTEGER,
 currency TEXT NOT NULL, amount_minor INTEGER NOT NULL, price_basis TEXT NOT NULL,
 source_mode TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 fetched_at TEXT NOT NULL, valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bundles(
 id TEXT PRIMARY KEY, destination TEXT NOT NULL, source_mode TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS bundles_destination ON bundles(destination,source_mode);
CREATE TABLE IF NOT EXISTS weather(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), date TEXT NOT NULL,
 kind TEXT NOT NULL, min_c REAL, max_c REAL, source_mode TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), fetched_at TEXT NOT NULL,
 valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS weather_city_date ON weather(city_id,date,kind);
CREATE TABLE IF NOT EXISTS routes(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), hotel_id TEXT REFERENCES hotels(id),
 origin_lat REAL NOT NULL, origin_lon REAL NOT NULL, destination_lat REAL NOT NULL,
 destination_lon REAL NOT NULL, distance_m REAL NOT NULL, duration_seconds REAL NOT NULL,
 fare_minor INTEGER, source_mode TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 fetched_at TEXT NOT NULL, valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), name TEXT,
 category TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
 source_mode TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 source_url TEXT NOT NULL, fetched_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS activities_city ON activities(city_id,category,active);
CREATE TABLE IF NOT EXISTS transport_estimates(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), origin TEXT NOT NULL,
 destination TEXT NOT NULL, departure_at TEXT NOT NULL, return_at TEXT NOT NULL, airline TEXT,
 currency TEXT NOT NULL, amount_minor INTEGER NOT NULL, price_basis TEXT NOT NULL,
 bookable INTEGER NOT NULL DEFAULT 0 CHECK(bookable=0), source_mode TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), fetched_at TEXT NOT NULL,
 valid_until TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS estimates_scope ON transport_estimates(origin,destination,departure_at);
CREATE TABLE IF NOT EXISTS visa_rules(
 id TEXT PRIMARY KEY, passport_country TEXT NOT NULL, destination_country TEXT NOT NULL,
 passport_type TEXT NOT NULL, purpose TEXT NOT NULL, visa_status TEXT NOT NULL,
 days_allowed INTEGER, source_url TEXT, checked_at TEXT, valid_until TEXT,
 source_mode TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget_statistics(
 id TEXT PRIMARY KEY, city_id TEXT NOT NULL REFERENCES destinations(id), month INTEGER NOT NULL,
 guest_id TEXT NOT NULL REFERENCES guests(id), nights INTEGER NOT NULL,
 currency TEXT NOT NULL, price_basis TEXT NOT NULL, source_mode TEXT NOT NULL,
 sample_count INTEGER NOT NULL, min_minor INTEGER NOT NULL, p25_minor INTEGER NOT NULL,
 median_minor INTEGER NOT NULL, p75_minor INTEGER NOT NULL, max_minor INTEGER NOT NULL,
 computed_at TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS hotel_catalog AS
 SELECT h.id,d.city,d.country,h.name,h.stars,h.rating,h.review_count,
 h.latitude,h.longitude,h.website,h.address,h.source_mode,h.source_url,h.fetched_at,
 NULL AS current_price,NULL AS availability
 FROM hotels h JOIN destinations d ON d.id=h.city_id WHERE h.active=1;
CREATE TABLE IF NOT EXISTS context_fixtures(
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, query_hash TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), data_json TEXT NOT NULL,
 UNIQUE(provider,query_hash));
CREATE TABLE IF NOT EXISTS catalog_metadata(id TEXT PRIMARY KEY,payload_json TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS activity_counts AS
 SELECT a.city_id,d.city,a.category,count(*) AS count
 FROM activities a JOIN destinations d ON d.id=a.city_id WHERE a.active=1
 GROUP BY a.city_id,d.city,a.category;

-- Agent-facing relational views retain scope, provenance and nullable unknowns.
CREATE INDEX IF NOT EXISTS hotel_quotes_pets_dates ON hotel_quotes(pets_allowed,check_in,check_out,hotel_id);
CREATE INDEX IF NOT EXISTS transport_type_dates ON transport_quotes(mode,departure_at,origin,destination);
CREATE VIEW IF NOT EXISTS agent_hotels AS
 SELECT h.id,d.city,h.name,h.rating,h.review_count,h.stars,h.latitude,h.longitude,
 h.website AS url,h.address,h.source_mode,h.source_id,h.source_url,h.fetched_at,
 h.active,q.id AS quote_id,q.check_in,q.check_out,q.guest_id,q.amount_minor,
 q.currency,q.price_basis,q.pets_allowed,q.breakfast,q.max_guests,q.valid_until
 FROM hotels h JOIN destinations d ON d.id=h.city_id
 LEFT JOIN hotel_quotes q ON q.hotel_id=h.id WHERE h.active=1;
CREATE VIEW IF NOT EXISTS transport AS
 SELECT t.*,d.city FROM transport_quotes t JOIN destinations d ON d.id=t.city_id;
CREATE VIEW IF NOT EXISTS guest_rules AS
 SELECT q.id,q.hotel_id,g.adults AS guest_adults,g.children_count AS guest_children,
 g.children_ages_json AS children_ages,g.pets,g.total_guests,q.max_guests,
 q.pets_allowed,q.check_in,q.check_out,q.source_mode,q.valid_until
 FROM hotel_quotes q JOIN guests g ON g.id=q.guest_id;
CREATE VIEW IF NOT EXISTS dates_calendar AS
 SELECT date,month,season,day_of_week,is_weekend FROM calendar_dates;
CREATE VIEW IF NOT EXISTS budget_benchmarks AS
 SELECT b.*,d.city FROM budget_statistics b JOIN destinations d ON d.id=b.city_id;
CREATE VIEW IF NOT EXISTS city_vibes AS
 SELECT * FROM activity_counts;
CREATE TABLE IF NOT EXISTS xotelo_hotels (
 id TEXT PRIMARY KEY, city TEXT NOT NULL, name TEXT NOT NULL, url TEXT,
 latitude REAL, longitude REAL, rating REAL, review_count INTEGER,
 fetched_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'xotelo');
CREATE INDEX IF NOT EXISTS xotelo_hotels_city ON xotelo_hotels(city);
CREATE TABLE IF NOT EXISTS xotelo_rates (
 id TEXT PRIMARY KEY, hotel_id TEXT NOT NULL REFERENCES xotelo_hotels(id),
 check_in TEXT NOT NULL, check_out TEXT NOT NULL, adults INTEGER NOT NULL,
 children_ages_json TEXT NOT NULL, rooms INTEGER NOT NULL,
 provider TEXT NOT NULL, currency TEXT NOT NULL, nightly_minor INTEGER NOT NULL,
 tax_known INTEGER NOT NULL DEFAULT 0, fetched_at TEXT NOT NULL, valid_until TEXT NOT NULL,
 bookable INTEGER NOT NULL DEFAULT 0 CHECK(bookable=0));
CREATE INDEX IF NOT EXISTS xotelo_rate_scope ON xotelo_rates(hotel_id,check_in,check_out,adults);
CREATE TABLE IF NOT EXISTS rail_schedule_estimates (
 id TEXT PRIMARY KEY, origin TEXT NOT NULL, destination TEXT NOT NULL,
 origin_code TEXT NOT NULL, destination_code TEXT NOT NULL,
 train_number TEXT NOT NULL, departure_time TEXT NOT NULL, arrival_time TEXT NOT NULL,
 duration_seconds INTEGER NOT NULL, categories_json TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id), fetched_at TEXT NOT NULL,
 valid_until TEXT NOT NULL, bookable INTEGER NOT NULL DEFAULT 0 CHECK(bookable=0));
CREATE INDEX IF NOT EXISTS rail_schedule_route ON rail_schedule_estimates(origin,destination,valid_until);
CREATE TABLE IF NOT EXISTS passport_index_reference (
 id TEXT PRIMARY KEY, passport_country TEXT NOT NULL, destination_country TEXT NOT NULL,
 status_raw TEXT NOT NULL, days INTEGER, dataset_date TEXT NOT NULL,
 commit_sha TEXT NOT NULL, source_url TEXT NOT NULL, fetched_at TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES ingest_sources(id),
 UNIQUE(passport_country,destination_country));
CREATE INDEX IF NOT EXISTS passport_index_route ON passport_index_reference(passport_country,destination_country);
