-- The backend's own database role on the audit trail (S-098, ADR-0008 decision 4).
--
-- Run as the owner of the tables, after `alembic upgrade head`, on PostgreSQL only:
--   psql -h <host> -U <table owner> -d <database> -f backend/sql/backend-role-grants.sql
--
-- The role itself is made once by the database administrator, as a role with no
-- password and no login, and granted to the login the backend connects as:
--   CREATE ROLE tankapi_backend NOLOGIN;
-- No password or login is ever written in this repository.
--
-- The role never owns the table, so it cannot drop the append-only triggers, and it
-- may only add and read entries: no UPDATE, DELETE, TRUNCATE, REFERENCES or TRIGGER.
-- Grants on the other tables belong to the deployment story.

REVOKE ALL ON audit_entries FROM tankapi_backend;
GRANT SELECT, INSERT ON audit_entries TO tankapi_backend;
-- INSERT takes the next id from the table's sequence.
REVOKE ALL ON SEQUENCE audit_entries_id_seq FROM tankapi_backend;
GRANT USAGE ON SEQUENCE audit_entries_id_seq TO tankapi_backend;
