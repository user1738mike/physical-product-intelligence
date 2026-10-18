# Embedded SQL keeps financial identity tuples together for review.
# ruff: noqa: E501
from django.db import migrations

SQL = """
CREATE FUNCTION ppi_billing_owner() RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT pg_has_role(current_user,c.relowner,'USAGE') FROM pg_class c WHERE c.oid='billing_price'::regclass
$$;
CREATE FUNCTION ppi_billing_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a billing_billingaccount; s billing_statement; p billing_price; r billing_moneyevent;
 original billing_moneyevent; alloc billing_allocation; adjustment bigint; paid bigint; used bigint;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Billing records cannot be deleted' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='billing_billingaccount' THEN
   IF TG_OP='UPDATE' AND NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501'; END IF;
   IF TG_OP='UPDATE' AND (NEW.id,NEW.organization_id,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.created_at) THEN RAISE EXCEPTION 'Account identity immutable' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' AND OLD.provider<>'' AND (NEW.provider,NEW.merchant,NEW.mode,NEW.customer_ref) IS DISTINCT FROM (OLD.provider,OLD.merchant,OLD.mode,OLD.customer_ref) THEN RAISE EXCEPTION 'Bound provider identity immutable' USING ERRCODE='23514'; END IF;
   IF TG_OP='INSERT' AND NOT ppi_billing_owner() AND (NEW.provider<>'' OR NEW.merchant<>'' OR NEW.customer_ref<>'' OR NEW.mode<>'test') THEN RAISE EXCEPTION 'Only unconfigured enrollment permitted' USING ERRCODE='42501'; END IF;
   RETURN NEW;
 ELSIF TG_TABLE_NAME='billing_price' THEN
   IF NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501'; END IF;
   IF NOT ((NEW.currency IN ('USD','EUR','KES') AND NEW.exponent=2) OR (NEW.currency='JPY' AND NEW.exponent=0) OR (NEW.currency='KWD' AND NEW.exponent=3) OR (NEW.currency='XTS' AND NEW.exponent=0 AND NEW.mode='test')) THEN RAISE EXCEPTION 'Unsupported currency exponent' USING ERRCODE='23514'; END IF;
   RETURN NEW;
 ELSIF TG_TABLE_NAME='billing_statement' THEN
   IF NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Operator connection required' USING ERRCODE='42501'; END IF;
   IF TG_OP='UPDATE' AND (OLD.state='finalized' OR (NEW.id,NEW.account_id,NEW.price_id,NEW.period_start,NEW.period_end,NEW.mode,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.account_id,OLD.price_id,OLD.period_start,OLD.period_end,OLD.mode,OLD.created_at)) THEN RAISE EXCEPTION 'Statement identity/final history immutable' USING ERRCODE='23514'; END IF;
   SELECT * INTO a FROM billing_billingaccount WHERE id=NEW.account_id;
   SELECT * INTO p FROM billing_price WHERE id=NEW.price_id;
   IF NEW.mode<>a.mode OR NEW.mode<>p.mode THEN RAISE EXCEPTION 'Statement mode mismatch' USING ERRCODE='23514'; END IF;
   IF NEW.state='finalized' AND (NEW.total_minor<>p.unit_minor*NEW.quantity OR NEW.finalized_at IS NULL OR NEW.snapshot->>'price_id' IS DISTINCT FROM p.id::text OR NEW.snapshot->>'currency' IS DISTINCT FROM p.currency OR (NEW.snapshot->>'total_minor')::bigint IS DISTINCT FROM NEW.total_minor) THEN RAISE EXCEPTION 'Invalid finalized calculation' USING ERRCODE='23514'; END IF;
   RETURN NEW;
 ELSIF TG_TABLE_NAME='billing_inbox' THEN
   IF TG_OP='UPDATE' AND (NEW.id,NEW.account_id,NEW.provider,NEW.merchant,NEW.mode,NEW.event_id,NEW.semantic_sha256,NEW.raw_sha256,NEW.payload,NEW.received_at) IS DISTINCT FROM (OLD.id,OLD.account_id,OLD.provider,OLD.merchant,OLD.mode,OLD.event_id,OLD.semantic_sha256,OLD.raw_sha256,OLD.payload,OLD.received_at) THEN RAISE EXCEPTION 'Received evidence immutable' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' AND NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Operator processing connection required' USING ERRCODE='42501'; END IF;
   IF NEW.account_id IS NOT NULL THEN
     SELECT * INTO a FROM billing_billingaccount WHERE id=NEW.account_id;
     IF (a.provider,a.merchant,a.mode,a.customer_ref) IS DISTINCT FROM (NEW.provider,NEW.merchant,NEW.mode,NEW.payload->>'customer') THEN RAISE EXCEPTION 'Event account scope mismatch' USING ERRCODE='23514'; END IF;
   END IF;
   IF NEW.state NOT IN ('received','processing','retry','applied','ignored','quarantined') OR NEW.attempts>5 THEN RAISE EXCEPTION 'Invalid inbox state' USING ERRCODE='23514'; END IF;
   RETURN NEW;
 ELSIF TG_TABLE_NAME='billing_paymentoperation' THEN
   SELECT * INTO s FROM billing_statement WHERE id=NEW.statement_id;
   SELECT * INTO a FROM billing_billingaccount WHERE id=s.account_id;
   PERFORM 1 FROM organizations_organization WHERE id=a.organization_id FOR UPDATE;
   IF NEW.account_id IS DISTINCT FROM s.account_id THEN RAISE EXCEPTION 'Operation account mismatch' USING ERRCODE='23514'; END IF;
   IF (NEW.provider,NEW.merchant,NEW.mode,NEW.currency) IS DISTINCT FROM (a.provider,a.merchant,a.mode,s.snapshot->>'currency') OR s.state<>'finalized' OR NEW.mode<>s.mode THEN RAISE EXCEPTION 'Operation statement scope mismatch' USING ERRCODE='23514'; END IF;
   IF TG_OP='UPDATE' THEN
     IF NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Operator processing connection required' USING ERRCODE='42501'; END IF;
     IF (NEW.id,NEW.account_id,NEW.statement_id,NEW.principal_id,NEW.request_id,NEW.fingerprint,NEW.provider,NEW.merchant,NEW.mode,NEW.currency,NEW.amount_minor,NEW.expires_at,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.account_id,OLD.statement_id,OLD.principal_id,OLD.request_id,OLD.fingerprint,OLD.provider,OLD.merchant,OLD.mode,OLD.currency,OLD.amount_minor,OLD.expires_at,OLD.created_at) OR (OLD.external_ref<>'' AND NEW.external_ref<>OLD.external_ref) OR NEW.provider_version<OLD.provider_version THEN RAISE EXCEPTION 'Operation identity immutable' USING ERRCODE='23514'; END IF;
   ELSE
     IF EXISTS(SELECT 1 FROM billing_paymentoperation WHERE statement_id=s.id AND state IN ('pending','processing','unknown','ready')) THEN RAISE EXCEPTION 'Operation already in progress' USING ERRCODE='23514'; END IF;
     SELECT COALESCE(SUM(delta_minor),0) INTO adjustment FROM billing_statementadjustment WHERE statement_id=s.id;
     SELECT COALESCE(SUM(amount_minor),0) INTO paid FROM billing_allocation WHERE statement_id=s.id;
     IF NEW.amount_minor>s.total_minor+adjustment-paid THEN RAISE EXCEPTION 'Operation exceeds remaining balance' USING ERRCODE='23514'; END IF;
   END IF;
   RETURN NEW;
 END IF;
 IF NOT ppi_billing_owner() THEN RAISE EXCEPTION 'Financial processing requires operator connection' USING ERRCODE='42501'; END IF;
 IF TG_TABLE_NAME='billing_moneyevent' THEN
   SELECT * INTO a FROM billing_billingaccount WHERE id=NEW.account_id;
   PERFORM 1 FROM organizations_organization WHERE id=a.organization_id FOR UPDATE;
   IF NOT EXISTS(SELECT 1 FROM billing_inbox i JOIN billing_paymentoperation o ON o.id=NEW.operation_id JOIN billing_statement st ON st.id=o.statement_id WHERE i.id=NEW.inbox_id AND i.account_id=a.id AND st.account_id=a.id AND i.mode=a.mode AND o.mode=a.mode AND i.provider=a.provider AND i.merchant=a.merchant AND o.currency=NEW.currency) OR abs(NEW.amount_minor)>1000000000000000 THEN RAISE EXCEPTION 'Financial evidence scope mismatch' USING ERRCODE='23514'; END IF;
   IF NEW.reverses_id IS NOT NULL THEN
     SELECT * INTO original FROM billing_moneyevent WHERE id=NEW.reverses_id;
     SELECT COALESCE(SUM(amount_minor),0) INTO used FROM billing_moneyevent WHERE reverses_id=original.id;
     IF original.kind<>'payment' OR (original.account_id,original.operation_id,original.currency) IS DISTINCT FROM (NEW.account_id,NEW.operation_id,NEW.currency) OR original.amount_minor+used+NEW.amount_minor<0 THEN RAISE EXCEPTION 'Invalid observed refund' USING ERRCODE='23514'; END IF;
   END IF;
 ELSIF TG_TABLE_NAME='billing_allocation' THEN
   SELECT * INTO s FROM billing_statement WHERE id=NEW.statement_id;
   SELECT * INTO a FROM billing_billingaccount WHERE id=s.account_id;
   PERFORM 1 FROM organizations_organization WHERE id=a.organization_id FOR UPDATE;
   SELECT * INTO r FROM billing_moneyevent WHERE id=NEW.money_id;
   IF r.account_id<>s.account_id OR r.currency IS DISTINCT FROM s.snapshot->>'currency' OR NOT EXISTS(SELECT 1 FROM billing_paymentoperation WHERE id=r.operation_id AND statement_id=s.id) THEN RAISE EXCEPTION 'Allocation scope mismatch' USING ERRCODE='23514'; END IF;
   SELECT COALESCE(SUM(amount_minor),0) INTO paid FROM billing_allocation WHERE statement_id=s.id;
   SELECT COALESCE(SUM(delta_minor),0) INTO adjustment FROM billing_statementadjustment WHERE statement_id=s.id;
   IF paid+NEW.amount_minor<0 OR paid+NEW.amount_minor>s.total_minor+adjustment THEN RAISE EXCEPTION 'Allocation outside statement balance' USING ERRCODE='23514'; END IF;
   IF NEW.amount_minor>0 THEN
     SELECT COALESCE(SUM(amount_minor),0) INTO used FROM billing_allocation WHERE money_id=r.id;
     IF r.kind<>'payment' OR used+NEW.amount_minor>r.amount_minor THEN RAISE EXCEPTION 'Allocation exceeds receipt' USING ERRCODE='23514'; END IF;
   ELSE
     SELECT * INTO alloc FROM billing_allocation WHERE id=NEW.reverses_id;
     SELECT COALESCE(SUM(amount_minor),0) INTO used FROM billing_allocation WHERE reverses_id=alloc.id;
     IF r.kind<>'refund' OR alloc.statement_id<>s.id OR alloc.money_id<>r.reverses_id OR alloc.amount_minor+used+NEW.amount_minor<0 OR NEW.amount_minor<r.amount_minor THEN RAISE EXCEPTION 'Invalid reversed allocation' USING ERRCODE='23514'; END IF;
   END IF;
 ELSIF TG_TABLE_NAME='billing_accessgrant' THEN
   SELECT * INTO s FROM billing_statement WHERE id=NEW.statement_id;
   SELECT * INTO a FROM billing_billingaccount WHERE id=s.account_id;
   SELECT COALESCE(SUM(amount_minor),0) INTO paid FROM billing_allocation WHERE statement_id=s.id;
   SELECT COALESCE(SUM(delta_minor),0) INTO adjustment FROM billing_statementadjustment WHERE statement_id=s.id;
   IF NOT s.access_transition OR paid<>s.total_minor+adjustment OR s.mode<>a.mode OR NOT EXISTS(SELECT 1 FROM billing_inbox i WHERE i.id=NEW.event_id AND i.account_id=a.id AND i.mode=s.mode AND i.payload->>'kind'='payment.succeeded' AND i.state IN ('processing','applied')) OR NOT EXISTS(SELECT 1 FROM commercial_assignment ca JOIN billing_price pr ON pr.id=s.price_id WHERE ca.id=NEW.assignment_id AND ca.organization_id=a.organization_id AND ca.plan_id=pr.plan_id AND ca.source='verified_payment' AND ca.ends_at=s.period_end AND ca.starts_at>=s.period_start AND ca.starts_at<s.period_end) THEN RAISE EXCEPTION 'Unverified access grant' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='billing_statementadjustment' THEN
   SELECT * INTO s FROM billing_statement WHERE id=NEW.statement_id;
   SELECT * INTO a FROM billing_billingaccount WHERE id=s.account_id;
   PERFORM 1 FROM organizations_organization WHERE id=a.organization_id FOR UPDATE;
   SELECT COALESCE(SUM(delta_minor),0) INTO adjustment FROM billing_statementadjustment WHERE statement_id=s.id;
   SELECT COALESCE(SUM(amount_minor),0) INTO paid FROM billing_allocation WHERE statement_id=s.id;
   IF s.state<>'finalized' OR s.total_minor+adjustment+NEW.delta_minor<paid OR s.total_minor+adjustment+NEW.delta_minor<0 OR s.total_minor+adjustment+NEW.delta_minor>1000000000000000 OR trim(NEW.reason)='' THEN RAISE EXCEPTION 'Invalid linked correction' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
"""


def seed_and_install(apps, editor):
    Account = apps.get_model("billing", "BillingAccount")
    Org = apps.get_model("organizations", "Organization")
    for org in Org.objects.order_by("pk").iterator(chunk_size=500):
        Account.objects.get_or_create(organization=org)
    editor.execute(SQL)
    for table in (
        "billingaccount",
        "price",
        "statement",
        "inbox",
        "paymentoperation",
        "moneyevent",
        "allocation",
        "accessgrant",
        "statementadjustment",
    ):
        event = (
            "INSERT OR UPDATE OR DELETE"
            if table in {"billingaccount", "statement", "inbox", "paymentoperation"}
            else "INSERT"
        )
        editor.execute(
            f"CREATE TRIGGER ppi_billing_scope BEFORE {event} ON billing_{table} FOR EACH ROW EXECUTE FUNCTION ppi_billing_guard()"
        )
    for table in (
        "price",
        "moneyevent",
        "allocation",
        "accessgrant",
        "statementadjustment",
        "billingaudit",
        "gatewaycall",
    ):
        editor.execute(
            f"CREATE TRIGGER ppi_billing_immutable BEFORE UPDATE OR DELETE ON billing_{table} FOR EACH ROW EXECUTE FUNCTION ppi_commercial_immutable()"
        )


def remove(apps, editor):
    for table in (
        "price",
        "moneyevent",
        "allocation",
        "accessgrant",
        "statementadjustment",
        "billingaudit",
        "gatewaycall",
    ):
        editor.execute(f"DROP TRIGGER ppi_billing_immutable ON billing_{table}")
    editor.execute("DROP FUNCTION ppi_billing_guard() CASCADE; DROP FUNCTION ppi_billing_owner();")


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed_and_install, remove)]
