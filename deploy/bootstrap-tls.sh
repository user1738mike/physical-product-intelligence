#!/bin/sh
set -eu
umask 077
if [ -f /certs/initialized ]; then exit 0; fi
test ! -f /certs/ca.key
openssl req -x509 -newkey rsa:3072 -nodes -days 7 -subj '/CN=PPI isolated rehearsal CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' -addext 'subjectKeyIdentifier=hash' -keyout /certs/ca.key -out /certs/ca.crt 2>/dev/null
for service in db edge; do
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$service" -keyout "/certs/$service.key" -out "/certs/$service.csr" 2>/dev/null
  if [ "$service" = db ]; then san='DNS:db'; uid=999; else san='DNS:edge,DNS:localhost,IP:127.0.0.1'; uid=101; fi
  printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n' "$san" > "/certs/$service.ext"
  openssl x509 -req -days 7 -in "/certs/$service.csr" -CA /certs/ca.crt -CAkey /certs/ca.key -CAcreateserial -extfile "/certs/$service.ext" -out "/certs/$service.crt" 2>/dev/null
  chown "$uid:$uid" "/certs/$service.key"
  chmod 600 "/certs/$service.key"
  chmod 644 "/certs/$service.crt"
done
chmod 644 /certs/ca.crt
touch /certs/initialized
