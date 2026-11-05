import QtQuick
import "../components"

Item {
    id: root
    required property string title
    signal closeRequested()
    function focusControl() { closeButton.forceActiveFocus() }
    width: parent.width
    height: 48
    Text {
        anchors.left: parent.left; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
        text: root.title
        font.bold: true; font.pixelSize: 16; color: themeState.foreground
    }
    IconButton {
        id: closeButton
        objectName: "dockClose"
        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
        width: 36; height: 36; iconName: "close"; tip: "Close " + root.title
        onClicked: root.closeRequested()
    }
}
