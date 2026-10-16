# SQL tuples and trigger declarations are kept together for migration review.
# ruff: noqa: E501
from django.db import migrations
from django.utils import timezone


def seed(apps, editor):
    Plan = apps.get_model("commercial", "Plan")
    Assignment = apps.get_model("commercial", "Assignment")
    Account = apps.get_model("commercial", "Account")
    Event = apps.get_model("commercial", "AssignmentEvent")
    Org = apps.get_model("organizations", "Organization")
    plan, _ = Plan.objects.get_or_create(
        code="manual-pilot", version=1, defaults={"name": "Manual pilot"}
    )
    now = timezone.now()
    for org in Org.objects.order_by("pk").iterator(chunk_size=500):
        account, _ = Account.objects.get_or_create(
            organization=org, defaults={"metering_started_at": now}
        )
        if not Assignment.objects.filter(organization=org).exists():
            assignment = Assignment.objects.create(
                organization=org,
                plan=plan,
                starts_at=account.metering_started_at,
                reason="Initial manual pilot backfill",
            )
            Event.objects.create(
                assignment=assignment,
                action="enrolled",
                reason=assignment.reason,
                state={
                    "status": "active",
                    "starts_at": assignment.starts_at.isoformat(),
                    "ends_at": None,
                    "plan_id": str(plan.pk),
                },
            )


SQL = """
CREATE FUNCTION ppi_commercial_owner() RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT pg_has_role(current_user, c.relowner, 'USAGE') FROM pg_class c
 WHERE c.oid='commercial_plan'::regclass
$$;
CREATE FUNCTION ppi_commercial_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Commercial history is append-only' USING ERRCODE='23514';
END; $$;
CREATE FUNCTION ppi_commercial_policy_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='commercial_plan' THEN
   IF NOT ppi_commercial_owner() AND NOT (
      NEW.code='manual-pilot' AND NEW.version=1 AND NEW.name='Manual pilot'
      AND NEW.catalog_write AND NEW.evidence_import AND NEW.equipment_write
      AND NEW.assessments AND NEW.ai_extraction
      AND NEW.active_products_limit IS NULL AND NEW.assessments_limit IS NULL
      AND NEW.extractions_limit IS NULL) THEN
     RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501';
   END IF;
 ELSIF TG_TABLE_NAME='commercial_assignment' THEN
   IF TG_OP='DELETE' THEN
     RAISE EXCEPTION 'Assignments cannot be deleted' USING ERRCODE='23514';
   END IF;
   IF TG_OP='UPDATE' THEN
     IF NOT ppi_commercial_owner() THEN
       RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501';
     END IF;
     IF (NEW.organization_id,NEW.plan_id,NEW.starts_at,NEW.source,NEW.actor_id,NEW.reason,NEW.created_at)
       IS DISTINCT FROM (OLD.organization_id,OLD.plan_id,OLD.starts_at,OLD.source,OLD.actor_id,OLD.reason,OLD.created_at)
       OR (OLD.ends_at IS NOT NULL AND (NEW.ends_at IS NULL OR NEW.ends_at > OLD.ends_at)) THEN
       RAISE EXCEPTION 'Assignment identity/period is immutable' USING ERRCODE='23514';
     END IF;
   ELSIF NOT ppi_commercial_owner() THEN
     PERFORM 1 FROM organizations_organization WHERE id=NEW.organization_id FOR UPDATE;
     IF EXISTS(SELECT 1 FROM commercial_assignment WHERE organization_id=NEW.organization_id)
       OR NEW.status <> 'active' OR NEW.source <> 'manual_pilot' OR NEW.ends_at IS NOT NULL
       OR NOT EXISTS(SELECT 1 FROM commercial_plan p WHERE p.id=NEW.plan_id AND p.code='manual-pilot' AND p.version=1) THEN
       RAISE EXCEPTION 'Only initial pilot enrollment permitted' USING ERRCODE='42501';
     END IF;
   END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER ppi_plan_insert BEFORE INSERT ON commercial_plan FOR EACH ROW EXECUTE FUNCTION ppi_commercial_policy_guard();
CREATE TRIGGER ppi_assignment_policy BEFORE INSERT OR UPDATE OR DELETE ON commercial_assignment FOR EACH ROW EXECUTE FUNCTION ppi_commercial_policy_guard();

CREATE FUNCTION ppi_commercial_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r commercial_reservation; u commercial_usage; a commercial_assignment;
BEGIN
 IF TG_TABLE_NAME='commercial_reservation' THEN
   IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Reservations cannot be deleted' USING ERRCODE='23514'; END IF;
   SELECT * INTO a FROM commercial_assignment WHERE id=NEW.assignment_id;
   IF a.organization_id IS DISTINCT FROM NEW.organization_id THEN
     RAISE EXCEPTION 'Reservation tenant mismatch' USING ERRCODE='23514';
   END IF;
   IF TG_OP='UPDATE' THEN
     IF (NEW.organization_id,NEW.meter,NEW.operation,NEW.fingerprint,NEW.period_start,NEW.period_end,NEW.created_at)
       IS DISTINCT FROM (OLD.organization_id,OLD.meter,OLD.operation,OLD.fingerprint,OLD.period_start,OLD.period_end,OLD.created_at)
       OR OLD.state='finalized'
       OR (NEW.assignment_id IS DISTINCT FROM OLD.assignment_id AND NOT(OLD.state='released' AND NEW.state='reserved')) THEN
       RAISE EXCEPTION 'Reservation identity/state is immutable' USING ERRCODE='23514';
     END IF;
   END IF;
 ELSIF TG_TABLE_NAME='commercial_usage' THEN
   SELECT * INTO a FROM commercial_assignment WHERE id=NEW.assignment_id;
   IF a.organization_id IS DISTINCT FROM NEW.organization_id THEN RAISE EXCEPTION 'Usage tenant mismatch' USING ERRCODE='23514'; END IF;
   IF NEW.reservation_id IS NOT NULL THEN
     SELECT * INTO r FROM commercial_reservation WHERE id=NEW.reservation_id;
     IF (r.organization_id,r.assignment_id,r.operation,r.meter,r.period_start,r.period_end)
       IS DISTINCT FROM (NEW.organization_id,NEW.assignment_id,NEW.operation,NEW.meter,NEW.period_start,NEW.period_end)
       OR r.state NOT IN ('reserved','finalized') THEN
       RAISE EXCEPTION 'Usage reservation mismatch' USING ERRCODE='23514';
     END IF;
   ELSE
     IF NOT ppi_commercial_owner() THEN RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501'; END IF;
     SELECT * INTO u FROM commercial_usage WHERE id=NEW.adjustment_of_id;
     IF u.adjustment_of_id IS NOT NULL OR (u.organization_id,u.assignment_id,u.meter,u.period_start,u.period_end)
       IS DISTINCT FROM (NEW.organization_id,NEW.assignment_id,NEW.meter,NEW.period_start,NEW.period_end)
       OR NEW.actor_id IS NULL OR trim(NEW.reason)='' THEN
       RAISE EXCEPTION 'Adjustment scope mismatch' USING ERRCODE='23514';
     END IF;
   END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER ppi_reservation_scope BEFORE INSERT OR UPDATE OR DELETE ON commercial_reservation FOR EACH ROW EXECUTE FUNCTION ppi_commercial_scope();
CREATE TRIGGER ppi_usage_scope BEFORE INSERT ON commercial_usage FOR EACH ROW EXECUTE FUNCTION ppi_commercial_scope();
CREATE FUNCTION ppi_commercial_finalization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS (SELECT 1 FROM commercial_reservation r WHERE r.id=NEW.id AND
   ((r.state='finalized') IS DISTINCT FROM EXISTS(SELECT 1 FROM commercial_usage u WHERE u.reservation_id=r.id))) THEN
   RAISE EXCEPTION 'Finalized reservation requires exactly one usage event' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER ppi_reservation_finalized AFTER INSERT OR UPDATE ON commercial_reservation DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_commercial_finalization();
CREATE FUNCTION ppi_commercial_usage_finalized() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.reservation_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM commercial_reservation WHERE id=NEW.reservation_id AND state='finalized'
 ) THEN
   RAISE EXCEPTION 'Usage requires finalized reservation' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER ppi_usage_finalized AFTER INSERT ON commercial_usage
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ppi_commercial_usage_finalized();
"""


def install(apps, editor):
    if editor.connection.vendor != "postgresql":
        raise RuntimeError("Commercial guarantees require PostgreSQL")
    editor.execute(SQL)
    for table in ("plan", "usage", "assignmentevent", "reservationevent", "account"):
        editor.execute(
            f"CREATE TRIGGER ppi_commercial_immutable BEFORE UPDATE OR DELETE ON commercial_{table} FOR EACH ROW EXECUTE FUNCTION ppi_commercial_immutable()"
        )


def remove(apps, editor):
    editor.execute(
        "DROP FUNCTION ppi_commercial_immutable() CASCADE; DROP FUNCTION ppi_commercial_policy_guard() CASCADE; DROP FUNCTION ppi_commercial_scope() CASCADE; DROP FUNCTION ppi_commercial_finalization() CASCADE; DROP FUNCTION ppi_commercial_usage_finalized() CASCADE; DROP FUNCTION ppi_commercial_owner();"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("commercial", "0002_reservationevent"),
        ("ingestion", "0003_extraction_scope_guards"),
        ("compatibility", "0002_scope_guards"),
    ]
    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
        migrations.RunPython(install, remove),
    ]
