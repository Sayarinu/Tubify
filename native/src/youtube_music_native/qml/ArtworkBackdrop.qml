import QtQuick
import QtQuick.Effects
import QtQuick.Window
import "Theme.js" as Theme

Item {
    id: root
    property string source: ""
    property string mediaKey: ""
    clip: true
    readonly property bool useBlur: appState.artworkBlur && GraphicsInfo.api !== GraphicsInfo.Software
    Rectangle { anchors.fill: parent; gradient: Gradient { GradientStop { position: 0; color: themeState.selected } GradientStop { position: 1; color: themeState.background } } }
    Image {
        id: artwork
        objectName: "backdropImage"
        anchors.fill: parent; visible: appState.artworkBackground && !root.useBlur; asynchronous: true; opacity: 0.45
        // The backdrop is deliberately low resolution; the foreground cover stays sharp.
        sourceSize.width: appState.artworkBlur ? 640 : Math.ceil(width * Screen.devicePixelRatio * appState.uiScaleFactor)
        sourceSize.height: appState.artworkBlur ? 240 : Math.ceil(height * Screen.devicePixelRatio * appState.uiScaleFactor)
        source: {
            if (!appState.artworkBackground) return ""
            if (root.mediaKey && !downloadsState.initialized) return ""
            return root.mediaKey && downloadsState.artwork[root.mediaKey] !== undefined ? downloadsState.artwork[root.mediaKey] : root.source
        }
        fillMode: Image.PreserveAspectCrop
    }
    MultiEffect {
        anchors.fill: parent; source: artwork
        visible: appState.artworkBackground && root.useBlur && artwork.status === Image.Ready
        blurEnabled: true; blur: 0.8; blurMax: 32; autoPaddingEnabled: false; opacity: 0.45
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.alpha(themeState.background, 0.13) }
            GradientStop { position: 0.55; color: Qt.alpha(themeState.background, 0.6) }
            GradientStop { position: 1; color: themeState.background }
        }
    }
}
