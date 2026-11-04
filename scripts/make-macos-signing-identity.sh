#!/usr/bin/env bash
# Create a self-signed macOS code-signing identity in OUTPUT_DIR. Never commit the output.
# Store the results as the TUBIFY_MACOS_SIGNING_P12 (base64) and TUBIFY_MACOS_SIGNING_PASSWORD secrets.
set -euo pipefail
output="${1:?Usage: make-macos-signing-identity.sh OUTPUT_DIR}"
mkdir -p "$output"
chmod 700 "$output"
config="$output/tubify-signing.cnf"
cat > "$config" <<'CONFIG'
[req]
distinguished_name = name
x509_extensions = extensions
prompt = no
[name]
CN = Tubify Self-Signed
[extensions]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
CONFIG
# The certificate's expiry doesn't affect existing signatures; 20 years avoids rotating it.
openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -config "$config" -keyout "$output/tubify-signing.key" -out "$output/tubify-signing.crt" 2>/dev/null
password="$(openssl rand -hex 24)"
# macOS `security import` cannot read OpenSSL 3's default key encryption.
legacy=()
if openssl pkcs12 -help 2>&1 | grep -q -- '-legacy'; then legacy=(-legacy); fi
openssl pkcs12 -export "${legacy[@]}" -inkey "$output/tubify-signing.key" -in "$output/tubify-signing.crt" -out "$output/tubify-signing.p12" -passout "pass:$password"
printf '%s' "$password" > "$output/tubify-signing.password"
rm -f "$output/tubify-signing.key" "$config"
chmod 600 "$output"/tubify-signing.*
