import QtQuick
import QtQuick.Window
import "Theme.js" as Theme
import "Icons.js" as Icons

Item {
    id: root
    property string name: "music"
    property color color: themeState.foreground
    implicitWidth: 24
    implicitHeight: 24
    Image {
        anchors.fill: parent
        opacity: root.color.a
        sourceSize.width: Math.ceil(root.width * Screen.devicePixelRatio)
        sourceSize.height: Math.ceil(root.height * Screen.devicePixelRatio)
        source: {
            var color = "rgb(" + Math.round(root.color.r * 255) + "," + Math.round(root.color.g * 255) + "," + Math.round(root.color.b * 255) + ")"
            var svg = (Icons.svg[root.name] || Icons.svg.music).replace(/currentColor/g, color)
            return "data:image/svg+xml," + encodeURIComponent(svg)
        }
    }
}
