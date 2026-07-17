#!/usr/bin/env sh
set -eu

batch_python="${KANGGAEMI_PYTHON:-python}"

# Sunday: refresh point-in-time membership before consuming it.
if [ "$(date +%u)" = "7" ]; then
  "$batch_python" -m app.batch.run universe-refresh
fi

"$batch_python" -m app.batch.run stock-prices
