from django.db import migrations

TABLES = {
    "revision": "products_revisionevidence",
    "measurement": "products_measurement",
    "packaging": "products_packagingprofile",
    "claim": "products_attributeclaim",
    "verification": "products_claimverification",
}

FUNCTION = """
CREATE OR REPLACE FUNCTION ppi_products_provenance_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_product uuid; source_product uuid; parent_revision uuid; parent_level text;
BEGIN
    IF TG_TABLE_NAME = 'products_revisionevidence' THEN
        SELECT product_id INTO owner_product FROM products_productrevision
            WHERE id = NEW.revision_id;
        SELECT product_id INTO source_product FROM products_evidence WHERE id = NEW.evidence_id;
        IF owner_product IS DISTINCT FROM source_product THEN
            RAISE EXCEPTION 'Invalid product provenance relation' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'products_measurement' THEN
        SELECT r.product_id INTO owner_product FROM products_packagingprofile p
            JOIN products_productrevision r ON r.id = p.revision_id WHERE p.id = NEW.packaging_id;
        SELECT product_id INTO source_product FROM products_evidence WHERE id = NEW.evidence_id;
        IF owner_product IS DISTINCT FROM source_product THEN
            RAISE EXCEPTION 'Invalid measurement provenance relation' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'products_packagingprofile' THEN
      IF NEW.contains_id IS NOT NULL THEN
        SELECT revision_id, level INTO parent_revision, parent_level
            FROM products_packagingprofile WHERE id = NEW.contains_id;
        IF parent_revision IS DISTINCT FROM NEW.revision_id
            OR array_position(ARRAY['unit','inner','case','pallet'], parent_level)
               >= array_position(ARRAY['unit','inner','case','pallet'], NEW.level) THEN
            RAISE EXCEPTION 'Invalid packaging containment relation' USING ERRCODE = '23514';
        END IF;
      END IF;
    ELSIF TG_TABLE_NAME = 'products_attributeclaim' THEN
        SELECT product_id INTO source_product FROM products_evidence WHERE id = NEW.evidence_id;
        IF NEW.product_id IS DISTINCT FROM source_product THEN
            RAISE EXCEPTION 'Invalid attribute source relation' USING ERRCODE = '23514';
        END IF;
        IF NEW.packaging_id IS NOT NULL THEN
            SELECT product_id INTO owner_product FROM products_packagingconfiguration
                WHERE id = NEW.packaging_id;
            IF NEW.product_id IS DISTINCT FROM owner_product THEN
                RAISE EXCEPTION 'Invalid attribute packaging relation' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF NEW.basis = 'measured' AND NOT EXISTS (
            SELECT 1 FROM products_claimverification WHERE measured_claim_id = NEW.id
        ) THEN
            RAISE EXCEPTION 'Physical verification record required' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'products_claimverification' THEN
        IF NOT EXISTS (
            SELECT 1 FROM products_attributeclaim a
            JOIN products_attributeclaim b ON b.id = NEW.measured_claim_id
            JOIN products_evidence e ON e.id = b.evidence_id
            WHERE a.id = NEW.claim_id AND a.product_id = b.product_id
              AND a.packaging_id IS NOT DISTINCT FROM b.packaging_id
              AND a.attribute = b.attribute AND b.basis = 'measured'
              AND e.source_type = 'physical_test'
        ) THEN
            RAISE EXCEPTION 'Invalid physical verification relation' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FUNCTION)
    for label, table in TABLES.items():
        schema_editor.execute(
            f"CREATE CONSTRAINT TRIGGER ppi_scope_{label} AFTER INSERT OR UPDATE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION ppi_products_provenance_guard()"
        )


def remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for label, table in TABLES.items():
        schema_editor.execute(f"DROP TRIGGER ppi_scope_{label} ON {table}")
    schema_editor.execute("DROP FUNCTION ppi_products_provenance_guard()")


class Migration(migrations.Migration):
    dependencies = [("products", "0002_catalog_workflows_and_attribute_claims")]
    operations = [migrations.RunPython(install, remove)]
