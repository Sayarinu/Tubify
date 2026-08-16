#!/usr/bin/env bash

set -euo pipefail

required_elements=(qtdemux matroskademux opusdec avdec_h264 avdec_aac)
missing_elements=()

for element in "${required_elements[@]}"; do
  if ! gst-inspect-1.0 "$element" >/dev/null 2>&1; then
    missing_elements+=("$element")
  fi
done

if (( ${#missing_elements[@]} )); then
  printf 'Missing GStreamer elements: %s\n' "${missing_elements[*]}" >&2
  printf '%s\n' 'Install or repair gst-plugins-good, gst-plugins-bad, and gst-libav.' >&2
  exit 1
fi

printf '%s\n' 'Arch media stack is ready: MP4, Matroska, Opus, H.264, and AAC are available.'
