#!/usr/bin/env bash
set -euo pipefail
experiment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pipeline_root="$(cd -- "$experiment_dir/../.." && pwd)"
if [[ -z "${JAVA_HOME:-}" && -d /home/kritik/android-dev/jdk-21.0.11+10 ]]; then
  export JAVA_HOME=/home/kritik/android-dev/jdk-21.0.11+10
  export PATH="$JAVA_HOME/bin:$PATH"
fi
exec "$pipeline_root/tools/apache-jena-fuseki-6.1.0/fuseki-server" \
  --localhost --port=3030 \
  --file="$pipeline_root/data/kg/wealth_management_diverse_kg.ttl" \
  /wealth
