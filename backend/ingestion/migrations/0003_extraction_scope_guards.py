from django.db import migrations

SQL = """
CREATE FUNCTION ppi_extraction_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE src ingestion_importjob%%ROWTYPE;
DECLARE task ingestion_importjob%%ROWTYPE;
BEGIN
  IF TG_TABLE_NAME = 'ingestion_importjob' THEN
    IF NEW.mode = 'ai' THEN
      SELECT * INTO src FROM ingestion_importjob WHERE id = NEW.source_job_id;
      IF src.id IS NULL OR src.mode <> 'deterministic'
        OR src.organization_id <> NEW.organization_id
        OR src.storage_key <> NEW.storage_key OR src.sha256 <> NEW.sha256
        OR src.size <> NEW.size OR src.format <> NEW.format THEN
        RAISE EXCEPTION 'Invalid extraction source scope' USING ERRCODE = '23514';
      END IF;
    END IF;
  ELSE
    SELECT * INTO task FROM ingestion_importjob WHERE id = NEW.job_id;
    IF task.mode = 'ai' THEN
      IF NEW.product_id::text IS DISTINCT FROM task.extraction->>'product_id'
        OR NEW.packaging_id::text IS DISTINCT FROM task.extraction->>'packaging_id'
        OR NOT EXISTS (SELECT 1 FROM products_product p
          WHERE p.id = NEW.product_id AND p.organization_id = task.organization_id)
        OR (NEW.packaging_id IS NOT NULL AND NOT EXISTS
          (SELECT 1 FROM products_packagingconfiguration c
            WHERE c.id = NEW.packaging_id AND c.product_id = NEW.product_id))
        OR (NEW.evidence_id IS NOT NULL AND NOT EXISTS
          (SELECT 1 FROM products_evidence e
            WHERE e.id = NEW.evidence_id AND e.product_id = NEW.product_id)) THEN
        RAISE EXCEPTION 'Invalid extraction target scope' USING ERRCODE = '23514';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER ppi_extraction_source AFTER INSERT OR UPDATE ON ingestion_importjob
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_extraction_scope_guard();
CREATE CONSTRAINT TRIGGER ppi_extraction_target AFTER INSERT OR UPDATE ON ingestion_importrow
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_extraction_scope_guard();
"""


def forwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute(SQL)


def backwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute("DROP TRIGGER ppi_extraction_target ON ingestion_importrow;")
        editor.execute("DROP TRIGGER ppi_extraction_source ON ingestion_importjob;")
        editor.execute("DROP FUNCTION ppi_extraction_scope_guard();")


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0002_candidate_extraction_importjob_extraction_and_more"),
        ("products", "0004_finite_physical_values"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
