#!/bin/sh

# Some Wayland compositors terminate the current GTK/WebKit path with a protocol
# error. When XWayland is available, prefer the stable X11 backend on Wayland.
if [ "${XDG_SESSION_TYPE-}" = wayland ] && [ -n "${DISPLAY-}" ]; then
  export GDK_BACKEND=x11
fi

exec /usr/lib/youtube-music-app/youtube-music-app "$@"
