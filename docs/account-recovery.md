# Account recovery and password changes

The customer account page provides **Change password**. It requires the current
password, validates the replacement using existing Django password policy and
logs out the current session. All other sessions become invalid through Django's
password-bound session hash. Credentials issued by that user are revoked; other
users' credentials and organization ownership are unchanged. The user must sign
in again. Recovery grants outstanding for the old password are invalidated.

The account recovery link on Sign in explains the operator-assisted flow.
Accounts use case-sensitive usernames; registration does not establish a verified
email address. Do not send recovery links to an unverified email supplied by a
caller, let an organization admin reset another account, or substitute organization
membership for proof of global account ownership.

An existing trusted active operator, using the isolated owner DB connection,
must verify the account holder through the established support channel and record
a non-personal support case identifier. On the Linux operator host/container,
create an owner-only directory and run:

```sh
umask 077
mkdir /tmp/recovery-case
python manage.py issue_recovery --actor OPERATOR --user USERNAME \
  --case-reference CASE-123 --output /tmp/recovery-case/link
```

Use a new directory/file per request. The command refuses a group/world-readable
parent, a different owner, an existing file and non-POSIX permission semantics;
the file is created exclusively with mode 0600. It never prints the link. Read
and deliver it only through the verified private channel, prefixed by the approved
HTTPS application origin. Do not paste it into chat, shell arguments, public
tickets or logs. Remove the temporary file through normal protected operator
handling after delivery. This command does not contact customers automatically.
Failed file creation rolls back issuance and does not revoke a previous link.

Links expire after fifteen minutes. Issuing another link revokes earlier links.
The DB retains the grant identity, issuer, case reference, timing and a one-way
verifier of the randomly generated 256-bit secret, never the secret itself.
The grant is also bound to the current password hash. Redemption is atomic under
the user lock: concurrent requests have one winner. Failed password validation
rolls back consumption. Revocation and consumption are final; PostgreSQL protects
immutable grant fields and denies issuance through the HTTP role. Staff and
superuser accounts are excluded from customer recovery; privileged identity
recovery remains a separately governed operator action.

The link uses a URL fragment so the recovery credential is not sent in a GET URL.
The page removes the fragment from history immediately, retains it in component
memory only and submits it in a CSRF-protected POST. No automatic login occurs.
The API returns generic invalid/expired errors and uses shared database limits
of ten attempts per hour. Browser evidence redacts recovery tokens and synthetic
passwords before writing host reports. Do not enable analytics/recording of
password or recovery form values.

Endpoints: `POST /api/v1/auth/password/` accepts `current_password,new_password`;
`POST /api/v1/auth/recover/` accepts `token,new_password`. Both return 204 on
success, never cache responses, reject unexpected fields and require CSRF.
No new session or privilege is granted. The usual login form is used afterward.
The frontend asks for confirmation; the server remains authoritative for policy.

Migrations are additive: `accounts.0001_initial` and `0002_recovery_guards`.
After controlled migration grant the runtime SELECT/UPDATE on
`accounts_recoverygrant` and revoke INSERT/DELETE, matching
`bootstrap_rehearsal`. Maintain existing auth-user password and audit permissions;
the owner-only trigger is an additional backstop. No schema reset is required.
Expired grant metadata remains protected audit material pending the approved
retention policy; it is not a store of usable recovery secrets.

The service does not verify identity documents, select a support vendor or send
email. Deployment must name the support owner/channel and identity-verification
procedure. These operational decisions do not justify unsafe email assumptions.
The synthetic acceptance fixture is guarded to isolated rehearsal databases and
creates new ordinary users/operators; it cannot run in production.

Session invalidation follows the existing [Django 5.2 authentication contract](https://docs.djangoproject.com/en/5.2/topics/auth/default/#session-invalidation-on-password-change).
Protected file creation uses [Python's exclusive low-level open](https://docs.python.org/3.13/library/os.html#os.open).
