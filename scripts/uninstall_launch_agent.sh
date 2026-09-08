#!/usr/bin/env bash

set -euo pipefail

target="/Users/${USER}/Library/LaunchAgents/com.jielosc.csbaoyan-daily.plist"
launchctl bootout "gui/${UID}" "$target" >/dev/null 2>&1 || true
if [[ -f "$target" ]]; then
    rm "$target"
fi
printf '%s\n' "Removed com.jielosc.csbaoyan-daily."
