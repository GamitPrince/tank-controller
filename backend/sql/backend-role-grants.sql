-- The backend's own database role on every table (S-098 for audit_entries, S-104 for the rest).
--
-- Run as the owner of the tables, after `alembic upgrade head`, on PostgreSQL only:
--   psql -h <host> -U <table owner> -d <database> -f backend/sql/backend-role-grants.sql
-- Run it again after every migration: it first takes everything back, then grants exactly
-- what the backend's code runs, so a rerun leaves the same rights.
--
-- The role itself is made once by the database administrator, as a role with no
-- password and no login, and granted to the login the backend connects as:
--   CREATE ROLE tankapi_backend NOLOGIN;
-- No password or login is ever written in this repository.
--
-- The role owns nothing, so it cannot drop the append-only triggers or run any DDL, and it
-- never gets DELETE, TRUNCATE, REFERENCES or TRIGGER. Foreign keys are checked with the
-- owner's rights, so the role needs no REFERENCES. backend/tests/test_backend_role.py holds
-- the same decisions per table and fails when a table has none.

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM tankapi_backend;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM tankapi_backend;

-- Ownership: read to scope every request; written by no endpoint yet (the claim flow is later).
GRANT SELECT ON customers, plants, tanks, devices, device_assignments TO tankapi_backend;

-- Records stored at ingest, never changed afterwards. reading_samples is the TimescaleDB
-- hypertable (S-100): the grant reaches its chunks, existing and new.
GRANT SELECT, INSERT ON scan_records, readings, reading_samples, gap_records TO tankapi_backend;

-- Append-only by triggers (S-079, S-090, S-093, S-101): add and read only.
GRANT SELECT, INSERT ON audit_entries, alarm_events, alarm_acknowledgements, config_changes
    TO tankapi_backend;

-- Settings with history (S-102, S-103): a change closes the row in force at the server's
-- second, so the one column it sets is the only one the role may update.
GRANT SELECT, INSERT ON alarm_thresholds, level_configurations, strapping_points
    TO tankapi_backend;
GRANT UPDATE (valid_to_unix_s) ON alarm_thresholds, level_configurations TO tankapi_backend;

-- INSERT takes the next id from the table's sequence.
GRANT USAGE ON SEQUENCE scan_records_id_seq, gap_records_id_seq, audit_entries_id_seq,
    alarm_events_id_seq, alarm_acknowledgements_id_seq, config_changes_id_seq,
    alarm_thresholds_id_seq, level_configurations_id_seq TO tankapi_backend;

-- No access: alembic_version (migrations run as the owner) and the reading_minutes continuous
-- aggregate, which no endpoint reads yet.
