-- 002_field_mappings_and_fixes.sql
-- Adds: crm_field_mappings table, conflict_report_id FK on deployments,
--        users tenant integrity trigger

-- ============================================================
-- CRM Field Mappings (canonical-to-SFDC per client per object)
-- ============================================================

CREATE TABLE crm_field_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    canonical_object TEXT NOT NULL,
    sfdc_object TEXT NOT NULL,
    field_mappings JSONB NOT NULL DEFAULT '{}',
    external_id_field TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, client_id, canonical_object)
);

CREATE INDEX idx_crm_field_mappings_org_id ON crm_field_mappings(org_id);
CREATE INDEX idx_crm_field_mappings_client_id ON crm_field_mappings(client_id);

CREATE TRIGGER trg_crm_field_mappings_updated_at
    BEFORE UPDATE ON crm_field_mappings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_crm_field_mappings_org_integrity
    BEFORE INSERT OR UPDATE ON crm_field_mappings
    FOR EACH ROW EXECUTE FUNCTION check_client_org_integrity();

ALTER TABLE crm_field_mappings ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Link deployments to conflict reports
-- ============================================================

ALTER TABLE crm_deployments
    ADD COLUMN conflict_report_id UUID REFERENCES crm_conflict_reports(id);

-- ============================================================
-- Users: enforce client_id belongs to org_id
-- ============================================================

CREATE OR REPLACE FUNCTION check_user_client_org_integrity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.client_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM clients WHERE id = NEW.client_id AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'client_id does not belong to org_id';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_client_org_integrity
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION check_user_client_org_integrity();
