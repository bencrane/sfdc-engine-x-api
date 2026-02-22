-- 006_analytics_deployment_types.sql
-- Add report/dashboard deployment type values for analytics metadata deploys.

ALTER TYPE deployment_type ADD VALUE IF NOT EXISTS 'report';
ALTER TYPE deployment_type ADD VALUE IF NOT EXISTS 'dashboard';
