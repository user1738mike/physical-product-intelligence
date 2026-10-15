from django.db import migrations

SQL = """
CREATE FUNCTION ppi_compatibility_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'compatibility_ruleset' THEN
    IF NOT EXISTS (SELECT 1 FROM compatibility_equipmentrevision r
                   WHERE r.id=NEW.equipment_revision_id AND r.equipment_id=NEW.equipment_id) THEN
      RAISE EXCEPTION 'invalid ruleset specification scope' USING ERRCODE='23514';
    END IF;
  ELSE
    IF NOT EXISTS (
      SELECT 1 FROM products_product p, products_productrevision pr,
                    compatibility_equipment e, compatibility_equipmentrevision er,
                    compatibility_ruleset rs
      WHERE p.id=NEW.product_id AND p.organization_id=NEW.organization_id
        AND pr.id=NEW.product_revision_id AND pr.product_id=p.id
        AND e.id=NEW.equipment_id AND e.organization_id=NEW.organization_id
        AND er.id=NEW.equipment_revision_id AND er.equipment_id=e.id
        AND rs.id=NEW.rule_set_id AND rs.equipment_id=e.id
        AND rs.equipment_revision_id=er.id
    ) THEN
      RAISE EXCEPTION 'invalid assessment tenant or revision scope' USING ERRCODE='23514';
    END IF;
    IF (NEW.packaging_id IS NULL) <> (NEW.packaging_revision_id IS NULL) THEN
      RAISE EXCEPTION 'incomplete assessment package scope' USING ERRCODE='23514';
    END IF;
    IF NEW.packaging_id IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM products_packagingconfiguration p,
                            products_configurationrevision r
                     WHERE p.id=NEW.packaging_id AND p.product_id=NEW.product_id
                       AND r.id=NEW.packaging_revision_id AND r.packaging_id=p.id) THEN
        RAISE EXCEPTION 'invalid assessment package revision' USING ERRCODE='23514';
      END IF;
    END IF;
    IF NEW.parent_id IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM compatibility_assessment a WHERE a.id=NEW.parent_id
                     AND a.organization_id=NEW.organization_id AND a.product_id=NEW.product_id
                     AND a.equipment_id=NEW.equipment_id
                     AND a.packaging_id IS NOT DISTINCT FROM NEW.packaging_id) THEN
        RAISE EXCEPTION 'invalid prior assessment scope' USING ERRCODE='23514';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER ppi_ruleset_scope AFTER INSERT OR UPDATE ON compatibility_ruleset
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_compatibility_scope_guard();
CREATE CONSTRAINT TRIGGER ppi_assessment_scope AFTER INSERT OR UPDATE ON compatibility_assessment
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_compatibility_scope_guard();
"""


def forwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute(SQL)


def backwards(apps, editor):
    if editor.connection.vendor == "postgresql":
        editor.execute("DROP TRIGGER ppi_assessment_scope ON compatibility_assessment;")
        editor.execute("DROP TRIGGER ppi_ruleset_scope ON compatibility_ruleset;")
        editor.execute("DROP FUNCTION ppi_compatibility_scope_guard();")


class Migration(migrations.Migration):
    dependencies = [("compatibility", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
