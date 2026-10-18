# ruff: noqa: E501
from django.db import migrations

SQL = r"""
CREATE FUNCTION ppi_integration_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_role boolean; v record; j jsonb;
BEGIN
 SELECT pg_get_userbyid(datdba)=current_user INTO owner_role FROM pg_database WHERE datname=current_database();
 IF TG_TABLE_NAME IN ('integrations_event','integrations_planpolicy','integrations_deliveryattempt') AND TG_OP <> 'INSERT' THEN
   RAISE EXCEPTION 'Integration history is immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Integration identities are retained' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='integrations_planpolicy' THEN
   IF NOT owner_role OR NEW.credentials_limit > 20 OR NEW.destinations_limit > 10 OR NOT EXISTS(SELECT 1 FROM commercial_plan p WHERE p.id=NEW.plan_id AND p.version>=2) OR EXISTS(SELECT 1 FROM commercial_assignment a WHERE a.plan_id=NEW.plan_id) THEN RAISE EXCEPTION 'Policy requires a new unassigned plan version and owner publication' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='integrations_credential' THEN
   IF TG_OP='UPDATE' AND (NEW.organization_id,NEW.issuer_id,NEW.verifier,NEW.scopes,NEW.created_at,NEW.expires_at,NEW.name) IS DISTINCT FROM (OLD.organization_id,OLD.issuer_id,OLD.verifier,OLD.scopes,OLD.created_at,OLD.expires_at,OLD.name) THEN RAISE EXCEPTION 'Credential identity is immutable' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' AND OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN RAISE EXCEPTION 'Credential revocation is final' USING ERRCODE='23514'; END IF;
   IF NEW.verifier !~ '^[0-9a-f]{64}$' OR jsonb_typeof(NEW.scopes)<>'array' OR jsonb_array_length(NEW.scopes) NOT BETWEEN 1 AND 3 OR NOT (NEW.scopes <@ '["catalog:read","assessments:read","assessments:export"]'::jsonb) OR NEW.expires_at<=NEW.created_at OR NEW.expires_at>NEW.created_at+interval '91 days' THEN RAISE EXCEPTION 'Invalid credential contract' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='integrations_event' THEN
   SELECT * INTO v FROM compatibility_assessment WHERE id=NEW.assessment_id;
   j := NEW.body::jsonb;
   IF v.organization_id IS DISTINCT FROM NEW.organization_id OR octet_length(NEW.body)>8192 OR NEW.kind<>'assessment.completed' OR j->>'id' IS DISTINCT FROM NEW.id::text OR j->>'organization_id' IS DISTINCT FROM NEW.organization_id::text OR j->>'type' IS DISTINCT FROM NEW.kind OR j->'data'->>'assessment_id' IS DISTINCT FROM NEW.assessment_id::text OR j->'data'->>'overall' IS DISTINCT FROM v.overall THEN RAISE EXCEPTION 'Invalid event ownership or envelope' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='integrations_destination' THEN
   IF TG_OP='UPDATE' AND (NEW.organization_id,NEW.issuer_id,NEW.created_at,NEW.root_version) IS DISTINCT FROM (OLD.organization_id,OLD.issuer_id,OLD.created_at,OLD.root_version) THEN RAISE EXCEPTION 'Destination identity is immutable' USING ERRCODE='23514'; END IF;
   IF NEW.subscriptions <> '["assessment.completed"]'::jsonb AND NEW.subscriptions <> '[]'::jsonb THEN RAISE EXCEPTION 'Unsupported event subscription' USING ERRCODE='23514'; END IF;
   IF NEW.revision<1 OR NEW.key_version<1 THEN RAISE EXCEPTION 'Invalid revision' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' AND (NEW.revision<OLD.revision OR NEW.key_version<OLD.key_version OR NEW.key_version>OLD.key_version+1 OR ((NEW.url,NEW.subscriptions) IS DISTINCT FROM (OLD.url,OLD.subscriptions) AND NEW.revision<>OLD.revision+1)) THEN RAISE EXCEPTION 'Destination revision must advance' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='integrations_delivery' THEN
   IF NOT EXISTS (SELECT 1 FROM integrations_event e JOIN integrations_destination d ON e.organization_id=d.organization_id WHERE e.id=NEW.event_id AND d.id=NEW.destination_id) THEN RAISE EXCEPTION 'Cross-tenant delivery denied' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' AND (NEW.event_id,NEW.destination_id,NEW.revision) IS DISTINCT FROM (OLD.event_id,OLD.destination_id,OLD.revision) THEN RAISE EXCEPTION 'Delivery binding is immutable' USING ERRCODE='23514'; END IF;
   IF NEW.attempts>6 OR NEW.replays>3 OR (NEW.state='claimed' AND (NEW.lease IS NULL OR NEW.lease_until IS NULL)) THEN RAISE EXCEPTION 'Invalid bounded delivery state' USING ERRCODE='23514'; END IF;
   IF NOT owner_role THEN
     IF TG_OP='INSERT' AND (NEW.state<>'pending' OR NEW.attempts<>0 OR NEW.lease IS NOT NULL) THEN RAISE EXCEPTION 'Runtime may enqueue only' USING ERRCODE='23514'; END IF;
     IF TG_OP='UPDATE' AND NOT (NEW.state='paused' OR (OLD.state<>'claimed' AND NEW.state='pending' AND NEW.replays=OLD.replays+1 AND NEW.replays<=3 AND NEW.attempts=0)) THEN RAISE EXCEPTION 'Delivery processing requires isolated owner role' USING ERRCODE='23514'; END IF;
   END IF;
 ELSIF TG_TABLE_NAME='integrations_deliveryattempt' THEN
   IF NOT owner_role THEN RAISE EXCEPTION 'Attempt history requires isolated owner role' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
"""
TABLES = ("credential", "destination", "event", "delivery", "deliveryattempt", "planpolicy")


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_initial")]
    operations = [
        migrations.RunSQL(
            SQL
            + "\n".join(
                f"CREATE TRIGGER integration_{table}_guard BEFORE INSERT OR UPDATE OR DELETE ON integrations_{table} FOR EACH ROW EXECUTE FUNCTION ppi_integration_guard();"
                for table in TABLES
            ),
            "\n".join(
                f"DROP TRIGGER integration_{table}_guard ON integrations_{table};"
                for table in TABLES
            )
            + "DROP FUNCTION ppi_integration_guard();",
        )
    ]
