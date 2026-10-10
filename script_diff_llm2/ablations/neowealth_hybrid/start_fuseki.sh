#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -z "${JAVA_HOME:-}" && -d /home/kritik/android-dev/jdk-21.0.11+10 ]]; then
  export JAVA_HOME=/home/kritik/android-dev/jdk-21.0.11+10
  export PATH="$JAVA_HOME/bin:$PATH"
fi
exec "$root/tools/apache-jena-fuseki-6.1.0/fuseki-server" --localhost --port=3031 --file="$root/kg_output_neowealth/neowealth_kg.ttl" /neowealth
