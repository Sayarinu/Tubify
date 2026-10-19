import QtQuick
import QtQuick.Effects
import QtQuick.Window
import "Theme.js" as Theme

Rectangle {
    id: root
    property string source: ""
    property string mediaKey: ""
    property string placeholder: "music"
    property color accent: Theme.selected
    readonly property bool ready: artwork.status === Image.Ready
    radius: 8
    clip: true
    gradient: Gradient {
        GradientStop { position: 0; color: root.accent }
        GradientStop { position: 1; color: Qt.darker(root.accent, 2.4) }
    }
    Image {
        id: artwork
        anchors.fill: parent
        visible: !softwareMask.active
        source: {
            if (!root.mediaKey) return root.source
            if (!downloadsState.initialized) return ""
            var cached = downloadsState.artwork[root.mediaKey]
            return cached !== undefined ? cached : root.source
        }
        onStatusChanged: if (softwareMask.active) softwareMask.requestPaint()
        onPaintedWidthChanged: if (softwareMask.active) softwareMask.requestPaint()
        onPaintedHeightChanged: if (softwareMask.active) softwareMask.requestPaint()
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: Math.ceil(root.width * Screen.devicePixelRatio)
        sourceSize.height: Math.ceil(root.height * Screen.devicePixelRatio)
        layer.enabled: root.ready && root.radius > 0 && GraphicsInfo.api !== GraphicsInfo.Software
        layer.effect: MultiEffect { maskEnabled: true; maskSource: roundedMask; autoPaddingEnabled: false }
    }
    Canvas {
        id: softwareMask
        anchors.fill: parent
        readonly property bool active: root.radius > 0 && GraphicsInfo.api === GraphicsInfo.Software
        visible: active && root.ready
        antialiasing: true
        renderTarget: Canvas.Image
        onVisibleChanged: if (visible) requestPaint()
        onAvailableChanged: if (available && visible) requestPaint()
        onWidthChanged: if (active) requestPaint()
        onHeightChanged: if (active) requestPaint()
        Connections { target: root; function onRadiusChanged() { if (softwareMask.active) softwareMask.requestPaint() } }
        onPaint: {
            if (!visible || !root.ready) return
            var ctx = getContext("2d")
            ctx.reset()
            ctx.beginPath()
            ctx.roundedRect(0, 0, width, height, root.radius, root.radius)
            ctx.clip()
            ctx.drawImage(artwork, (width - artwork.paintedWidth) / 2, (height - artwork.paintedHeight) / 2, artwork.paintedWidth, artwork.paintedHeight)
        }
    }
    Image {
        id: roundedMask
        visible: false
        sourceSize.width: Math.ceil(root.width * Screen.devicePixelRatio)
        sourceSize.height: Math.ceil(root.height * Screen.devicePixelRatio)
        source: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + root.width + '" height="' + root.height + '"><rect width="' + root.width + '" height="' + root.height + '" rx="' + root.radius + '" fill="white"/></svg>')
    }
    Symbol {
        name: root.placeholder
        anchors.centerIn: parent
        width: Math.min(root.width * 0.4, 54)
        height: width
        color: "#66ffffff"
        visible: artwork.status !== Image.Ready
    }
}
