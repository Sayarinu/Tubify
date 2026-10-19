import QtQuick
import QtQuick.Effects
import QtQuick.Window
import "Theme.js" as Theme

Item {
    id: root
    property string source: ""
    property string mediaKey: ""
    clip: true
    Rectangle { anchors.fill: parent; gradient: Gradient { GradientStop { position: 0; color: Theme.selected } GradientStop { position: 1; color: Theme.background } } }
    Image {
        id: artwork
        objectName: "backdropImage"
        anchors.fill: parent; visible: false; asynchronous: true
        // The backdrop is deliberately low resolution; the foreground cover stays sharp.
        sourceSize.width: 640; sourceSize.height: 240
        source: {
            if (root.mediaKey && !downloadsState.initialized) return ""
            return root.mediaKey && downloadsState.artwork[root.mediaKey] !== undefined ? downloadsState.artwork[root.mediaKey] : root.source
        }
        fillMode: Image.PreserveAspectCrop
    }
    MultiEffect {
        anchors.fill: parent; source: artwork
        visible: artwork.status === Image.Ready && GraphicsInfo.api !== GraphicsInfo.Software
        blurEnabled: true; blur: 0.8; blurMax: 32; autoPaddingEnabled: false; opacity: 0.45
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#2014131b" }
            GradientStop { position: 0.55; color: "#9914131b" }
            GradientStop { position: 1; color: Theme.background }
        }
    }
}
