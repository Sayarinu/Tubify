"""Draw libmpv video frames in Qt Quick using mpv's software renderer.

The software render API works with every Qt graphics backend (Direct3D, Metal,
Vulkan, OpenGL and the software renderer), so video needs no platform-specific
window embedding. Frames are rendered at the on-screen size, capped to 720p.
"""

import ctypes

from PySide6.QtCore import Property, QObject, QRectF, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickPaintedItem

# libmpv/render.h parameter identifiers missing from python-mpv's table.
SW_SIZE, SW_FORMAT, SW_STRIDE, SW_POINTER = 17, 18, 19, 20
MAX_WIDTH, MAX_HEIGHT = 1280, 720
from .video_types import VIDEO_TYPES, has_video  # noqa: F401


def fit(width, height, video_width, video_height):
    """Largest size with the video's aspect ratio inside the box and the 720p cap."""
    if width <= 0 or height <= 0:
        return 0, 0
    if video_width <= 0 or video_height <= 0:
        video_width, video_height = 16, 9
    scale = min(width / video_width, height / video_height, MAX_WIDTH / video_width, MAX_HEIGHT / video_height)
    return max(2, int(video_width * scale) & ~1), max(2, int(video_height * scale) & ~1)


class VideoFrames(QObject):
    """Owns the mpv render context and produces QImages on the GUI thread."""

    frameReady = Signal()
    firstFrame = Signal()
    _wake = Signal()

    def __init__(self, player, parent=None):
        super().__init__(parent)
        import mpv

        self._mpv, self.player = mpv, player
        self.context = mpv.MpvRenderContext(player, "sw")
        self.image = QImage()
        self.target = QSize(640, 360)
        self._active, self._awaiting_first = False, False
        self._wake.connect(self._render, Qt.ConnectionType.QueuedConnection)
        # mpv calls this from its own thread; only a queued signal crosses back.
        self.context.update_cb = self._wake.emit

    def request_size(self, width, height):
        self.target = QSize(max(0, int(width)), max(0, int(height)))

    def start(self):
        """Expect a new video; the next frame drawn counts as its first."""
        self._active, self._awaiting_first = True, True

    @Slot()
    def _render(self):
        # A frame mpv queued before the video was hidden must not count as the next one.
        if self.context is None or not self.context.update() or not self._active:
            return
        try:
            video_width = int(self.player.width or 0)
            video_height = int(self.player.height or 0)
        except Exception:
            video_width = video_height = 0
        width, height = fit(self.target.width(), self.target.height(), video_width, video_height)
        if not width:
            return
        if self.image.size() != QSize(width, height):
            self.image = QImage(width, height, QImage.Format.Format_RGBX8888)
        buffer = (ctypes.c_char * self.image.sizeInBytes()).from_buffer(self.image.bits())
        size = (ctypes.c_int * 2)(width, height)
        pixel_format = ctypes.c_char_p(b"rgb0")
        stride = ctypes.c_size_t(self.image.bytesPerLine())

        def param(kind, data):
            value = self._mpv.MpvRenderParam("invalid")
            value.type_id, value.data = kind, data
            return value

        params = (self._mpv.MpvRenderParam * 5)(
            param(SW_SIZE, ctypes.cast(size, ctypes.c_void_p)),
            param(SW_FORMAT, ctypes.cast(pixel_format, ctypes.c_void_p)),
            param(SW_STRIDE, ctypes.cast(ctypes.pointer(stride), ctypes.c_void_p)),
            param(SW_POINTER, ctypes.cast(buffer, ctypes.c_void_p)),
            param(0, None),
        )
        self._mpv._mpv_render_context_render(self.context.handle, params)
        del buffer
        self.frameReady.emit()
        if self._awaiting_first:
            self._awaiting_first = False
            self.firstFrame.emit()

    def clear(self):
        self._active = False
        self.image = QImage()
        self.frameReady.emit()

    def close(self):
        if self.context is not None:
            self.context.update_cb = None
            self.context.free()
            self.context = None


class VideoSurface(QQuickPaintedItem):
    """QML item that paints the latest frame, letterboxed to its own size."""

    framesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames = None
        self.setFillColor(Qt.GlobalColor.black)

    def _get_frames(self):
        return self._frames

    def _set_frames(self, frames):
        if frames is self._frames:
            return
        if self._frames is not None:
            self._frames.frameReady.disconnect(self.update)
        self._frames = frames
        if frames is not None:
            frames.frameReady.connect(self.update)
            self._request()
        self.framesChanged.emit()
        self.update()

    frames = Property(QObject, _get_frames, _set_frames, notify=framesChanged)

    def geometryChange(self, new, old):
        super().geometryChange(new, old)
        self._request()

    def _request(self):
        if self._frames is not None:
            ratio = self.window().effectiveDevicePixelRatio() if self.window() else 1.
            self._frames.request_size(self.width() * ratio, self.height() * ratio)

    def paint(self, painter):
        image = self._frames.image if self._frames is not None else QImage()
        if image.isNull():
            return
        box = self.boundingRect()
        scale = min(box.width() / image.width(), box.height() / image.height())
        width, height = image.width() * scale, image.height() * scale
        target = QRectF(box.x() + (box.width() - width) / 2, box.y() + (box.height() - height) / 2, width, height)
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, image)
