#!/bin/bash
set -euo pipefail
. /usr/local/env-activate.sh
export PATH="/opt/salmon-1.12.1/bin:${PATH}"
export LD_LIBRARY_PATH="/usr/local/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "$@"
