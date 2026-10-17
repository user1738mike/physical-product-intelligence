# ruff: noqa: E501
from django.db import migrations

SQL = """
CREATE FUNCTION ppi_recovery_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Recovery history is retained' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' AND NOT EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database() AND pg_get_userbyid(datdba)=current_user) THEN
   RAISE EXCEPTION 'Recovery issuance requires owner connection' USING ERRCODE='23514';
 END IF;
 IF NEW.verifier !~ '^[a-f0-9]{64}$' OR NEW.password_fingerprint !~ '^[a-f0-9]{64}$' OR NEW.expires_at<=NEW.created_at OR NEW.expires_at>NEW.created_at+interval '16 minutes' THEN
   RAISE EXCEPTION 'Invalid recovery grant' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' THEN
   IF (NEW.id,NEW.user_id,NEW.issued_by_id,NEW.created_at,NEW.expires_at,NEW.verifier,NEW.password_fingerprint,NEW.case_reference) IS DISTINCT FROM (OLD.id,OLD.user_id,OLD.issued_by_id,OLD.created_at,OLD.expires_at,OLD.verifier,OLD.password_fingerprint,OLD.case_reference) THEN
     RAISE EXCEPTION 'Recovery identity is immutable' USING ERRCODE='23514';
   END IF;
   IF (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at) OR (OLD.consumed_at IS NOT NULL AND NEW.consumed_at IS DISTINCT FROM OLD.consumed_at) THEN
     RAISE EXCEPTION 'Recovery terminal state is final' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recovery_guard BEFORE INSERT OR UPDATE OR DELETE ON accounts_recoverygrant FOR EACH ROW EXECUTE FUNCTION ppi_recovery_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.RunSQL(
            SQL,
            "DROP TRIGGER recovery_guard ON accounts_recoverygrant; DROP FUNCTION ppi_recovery_guard();",
        )
    ]
