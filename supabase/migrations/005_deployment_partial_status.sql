-- 005_deployment_partial_status.sql
-- Add 'partial' to deployment_status enum for partially successful deployments

ALTER TYPE deployment_status ADD VALUE IF NOT EXISTS 'partial' AFTER 'succeeded';
