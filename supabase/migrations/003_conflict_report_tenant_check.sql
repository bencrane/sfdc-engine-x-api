-- 003_conflict_report_tenant_check.sql
-- Enforce that crm_deployments.conflict_report_id belongs to the same org

CREATE OR REPLACE FUNCTION check_deployment_conflict_report_org_integrity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.conflict_report_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1
            FROM crm_conflict_reports
            WHERE id = NEW.conflict_report_id
              AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'conflict_report_id does not belong to org_id';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_crm_deployments_conflict_report_org_integrity
    BEFORE INSERT OR UPDATE ON crm_deployments
    FOR EACH ROW EXECUTE FUNCTION check_deployment_conflict_report_org_integrity();
