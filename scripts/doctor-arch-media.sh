#!/usr/bin/env bash

set -euo pipefail

required_plugins=(isomp4 matroska opus avdec_h264 avdec_aac)
missing_plugins=()

for plugin in "${required_plugins[@]}"; do
  if ! gst-inspect-1.0 "$plugin" >/dev/null 2>&1; then
    missing_plugins+=("$plugin")
  fi
done

if (( ${#missing_plugins[@]} )); then
  printf 'Missing GStreamer elements: %s\n' "${missing_plugins[*]}" >&2
  printf '%s\n' 'Install or repair gst-plugins-good, gst-plugins-bad, and gst-libav.' >&2
  exit 1
fi

printf '%s\n' 'Arch media stack is ready: MP4, Matroska, Opus, H.264, and AAC are available.'
