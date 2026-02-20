-- 004_nango_connection_id.sql
-- Add Nango connection id storage on crm_connections.

ALTER TABLE crm_connections
    ADD COLUMN nango_connection_id TEXT;
