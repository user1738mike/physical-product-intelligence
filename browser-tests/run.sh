#!/bin/sh
set -eu
test "$(id -u)" != 0
test -f /rehearsal-ca.crt
umask 077
cat > /tmp/ppi-browser-journey.json
umask 022
# Trust only this synthetic environment, inside the disposable test container's home.
certutil -N --empty-password -d sql:/home/pwuser/.pki/nssdb
certutil -A -d sql:/home/pwuser/.pki/nssdb -n ppi-synthetic-rehearsal -t 'C,,' -i /rehearsal-ca.crt
node /tests/redaction-check.cjs
# Error contexts can contain reveal-once UI values; sanitize before copying to the host.
if npm test > /tmp/ppi-browser-console.log 2>&1; then result=0; else result=$?; fi
node /tests/redact-results.cjs
exit "$result"
