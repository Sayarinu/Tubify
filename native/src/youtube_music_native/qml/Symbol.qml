import QtQuick
import QtQuick.Window
import "Theme.js" as Theme

Item {
    id: root
    property string name: "music"
    property color color: Theme.foreground
    implicitWidth: 24
    implicitHeight: 24
    Image {
        anchors.fill: parent
        sourceSize.width: Math.ceil(root.width * Screen.devicePixelRatio)
        sourceSize.height: Math.ceil(root.height * Screen.devicePixelRatio)
        source: {
            var color = "rgb(" + Math.round(root.color.r * 255) + "," + Math.round(root.color.g * 255) + "," + Math.round(root.color.b * 255) + ")"
            var filled = !!Theme.filled[root.name]
            var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="' + (Theme.paths[root.name] || Theme.paths.music) + '" fill="' + (filled ? color : "none") + '" stroke="' + color + '" stroke-width="' + (filled ? 0 : 1.8) + '" stroke-linecap="round" stroke-linejoin="round" opacity="' + root.color.a + '"/></svg>'
            return "data:image/svg+xml," + encodeURIComponent(svg)
        }
    }
}
