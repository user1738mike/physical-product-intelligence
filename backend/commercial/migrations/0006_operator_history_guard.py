from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("commercial", "0005_operatorevent")]
    operations = [
        migrations.RunSQL(
            "CREATE TRIGGER ppi_commercial_immutable BEFORE UPDATE OR DELETE "
            "ON commercial_operatorevent FOR EACH ROW "
            "EXECUTE FUNCTION ppi_commercial_immutable()",
            "DROP TRIGGER ppi_commercial_immutable ON commercial_operatorevent",
        ),
    ]
