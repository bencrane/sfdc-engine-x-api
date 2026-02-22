-- 007_per_connection_provider_config.sql
-- Add per-connection Nango provider config key override.

ALTER TABLE crm_connections
    ADD COLUMN nango_provider_config_key TEXT;
