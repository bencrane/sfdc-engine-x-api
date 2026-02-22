-- 005_mapping_version.sql
-- Adds optimistic locking versioning for crm_field_mappings

ALTER TABLE crm_field_mappings
    ADD COLUMN mapping_version INTEGER NOT NULL DEFAULT 1;


CREATE OR REPLACE FUNCTION increment_crm_field_mappings_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.mapping_version = OLD.mapping_version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER trg_crm_field_mappings_mapping_version
    BEFORE UPDATE ON crm_field_mappings
    FOR EACH ROW EXECUTE FUNCTION increment_crm_field_mappings_version();
