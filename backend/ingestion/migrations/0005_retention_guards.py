from django.db import migrations

SQL = """
CREATE FUNCTION ppi_retention_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE src ingestion_importjob%%ROWTYPE;
DECLARE pol ingestion_retentionpolicy%%ROWTYPE;
BEGIN
  IF TG_TABLE_NAME = 'ingestion_retentionpolicy' THEN
    RAISE EXCEPTION 'Retention history is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Removal history is protected' USING ERRCODE='23514';
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT * INTO src FROM ingestion_importjob WHERE id=NEW.source_id;
    SELECT * INTO pol FROM ingestion_retentionpolicy WHERE id=NEW.policy_id;
    IF src.id IS NULL OR pol.id IS NULL OR src.organization_id <> pol.organization_id
      OR NEW.state <> 'queued' OR NEW.claimed_at IS NOT NULL OR NEW.finished_at IS NOT NULL
      OR src.mode <> 'deterministic' OR src.version <> NEW.source_version
      OR src.sha256 <> NEW.sha256 OR src.storage_key <> NEW.storage_key THEN
      RAISE EXCEPTION 'Invalid source removal scope' USING ERRCODE='23514';
    END IF;
  ELSE
    IF (to_jsonb(NEW)-'state'-'claimed_at'-'finished_at') <>
       (to_jsonb(OLD)-'state'-'claimed_at'-'finished_at')
      OR NOT EXISTS (SELECT 1 FROM pg_database d
        WHERE d.datname=current_database() AND pg_has_role(current_user,d.datdba,'MEMBER'))
      OR NOT ((OLD.state='queued' AND NEW.state IN ('claimed','cancelled'))
        OR (OLD.state='claimed' AND NEW.state IN ('removed','needs_review'))
        OR (OLD.state='needs_review' AND NEW.state IN ('removed','cancelled')))
      OR (NEW.state='claimed' AND NEW.claimed_at IS NULL)
      OR (OLD.state <> 'queued' AND NEW.claimed_at IS DISTINCT FROM OLD.claimed_at)
      OR (NEW.state <> 'claimed' AND NEW.finished_at IS NULL) THEN
      RAISE EXCEPTION 'Invalid source removal transition' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER ppi_retention_history BEFORE UPDATE OR DELETE ON ingestion_retentionpolicy
FOR EACH ROW EXECUTE FUNCTION ppi_retention_guard();
CREATE TRIGGER ppi_source_removal_guard BEFORE INSERT OR UPDATE OR DELETE ON ingestion_sourceremoval
FOR EACH ROW EXECUTE FUNCTION ppi_retention_guard();

CREATE FUNCTION ppi_removed_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.mode='ai' AND EXISTS (SELECT 1 FROM ingestion_sourceremoval
    WHERE source_id=NEW.source_job_id AND state IN ('claimed','needs_review','removed')) THEN
    RAISE EXCEPTION 'Source unavailable after removal intent' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND EXISTS (SELECT 1 FROM ingestion_sourceremoval
    WHERE source_id=NEW.id AND state IN ('claimed','needs_review','removed')) AND
    (NEW.storage_key IS DISTINCT FROM OLD.storage_key OR NEW.sha256 <> OLD.sha256
      OR NEW.size <> OLD.size OR NEW.organization_id <> OLD.organization_id
      OR NEW.status NOT IN ('failed','cancelled')) THEN
    RAISE EXCEPTION 'Removed source identity is protected' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER ppi_removed_source BEFORE INSERT OR UPDATE ON ingestion_importjob
FOR EACH ROW EXECUTE FUNCTION ppi_removed_source_guard();
"""


def forwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute(SQL)


def backwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute("DROP TRIGGER ppi_removed_source ON ingestion_importjob")
        editor.execute("DROP FUNCTION ppi_removed_source_guard()")
        editor.execute("DROP TRIGGER ppi_source_removal_guard ON ingestion_sourceremoval")
        editor.execute("DROP TRIGGER ppi_retention_history ON ingestion_retentionpolicy")
        editor.execute("DROP FUNCTION ppi_retention_guard()")


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0004_source_retention")]
    operations = [migrations.RunPython(forwards, backwards)]
