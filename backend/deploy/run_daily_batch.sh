#!/usr/bin/env sh
set -eu

batch_python="${KANGGAEMI_PYTHON:-python}"

# Sunday: refresh point-in-time membership before consuming it.
if [ "$(date +%u)" = "7" ]; then
  "$batch_python" -m app.batch.run futures-master-refresh
  "$batch_python" -m app.batch.run universe-refresh
  sleep 65
  "$batch_python" -m app.batch.run stock-financials
  sleep 65
fi

"$batch_python" -m app.batch.run active-contract-refresh
sleep 65
"$batch_python" -m app.batch.run futures-sync
sleep 65
"$batch_python" -m app.batch.run market-indices
sleep 65
"$batch_python" -m app.batch.run market-investor-flow
sleep 65
"$batch_python" -m app.batch.run market-program-trade
sleep 65
"$batch_python" -m app.batch.run market-funds
sleep 65
"$batch_python" -m app.batch.run stock-prices
sleep 65
"$batch_python" -m app.batch.run stock-investor-flow
sleep 65
"$batch_python" -m app.batch.run stock-program-trade

# These providers do not use the KIS access-token endpoint.
"$batch_python" -m app.batch.run macro-indicators
"$batch_python" -m app.batch.run yield-rates
"$batch_python" -m app.batch.run exchange-rates
