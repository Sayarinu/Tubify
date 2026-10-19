import QtQuick
import "Theme.js" as Theme

Rectangle {
    id: root
    property string source: ""
    property string mediaKey: ""
    property color accent: "#283238"
    radius: 8
    clip: true
    gradient: Gradient {
        GradientStop { position: 0; color: root.accent }
        GradientStop { position: 1; color: Qt.darker(root.accent, 2.4) }
    }
    Image {
        id: artwork
        anchors.fill: parent
        source: root.mediaKey ? !downloadsState.initialized ? "" : downloadsState.artwork[root.mediaKey] || root.source : root.source
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: Math.ceil(root.width * 2)
        sourceSize.height: Math.ceil(root.height * 2)
    }
    Symbol {
        anchors.centerIn: parent
        width: Math.min(root.width * 0.4, 54)
        height: width
        color: "#66ffffff"
        visible: artwork.status !== Image.Ready
    }
}
