#!/bin/sh
# Самоподписанный сертификат для локального контура (п. 6.2), если своего нет в томе /etc/nginx/tls.
# TLS_SAN — дополнительные имена и адреса сервера через запятую, например: DNS:aiskra.local,IP:10.0.0.5
set -eu
DIR=/etc/nginx/tls
if [ -s "$DIR/server.crt" ] && [ -s "$DIR/server.key" ]; then
  echo "TLS: используется сертификат из $DIR"
  exit 0
fi
mkdir -p "$DIR"
SAN="DNS:localhost,IP:127.0.0.1"
[ -n "${TLS_SAN:-}" ] && SAN="$SAN,$TLS_SAN"
openssl req -x509 -newkey rsa:2048 -nodes -days 825 -sha256 \
  -subj "/CN=${TLS_CN:-localhost}/O=AIskra training" \
  -addext "subjectAltName=$SAN" \
  -keyout "$DIR/server.key" -out "$DIR/server.crt" 2>/dev/null
chmod 600 "$DIR/server.key"
echo "TLS: создан самоподписанный сертификат ($SAN), срок 825 дней"
