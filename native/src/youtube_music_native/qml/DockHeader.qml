import QtQuick
import QtQuick.Controls

Item {
    id: root
    required property string title
    property bool tabbed: false
    signal closeRequested()
    function focusControl() {
        if (tabbed) tabs.itemAt(appState.activeDock === "Lyrics" ? 0 : 1).forceActiveFocus()
        else closeButton.forceActiveFocus()
    }
    width: parent.width
    height: 48
    Text {
        anchors.left: parent.left; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
        text: root.title; visible: !root.tabbed
        font.bold: true; font.pixelSize: 16; color: themeState.foreground
    }
    Row {
        x: 8; height: parent.height; spacing: 4; visible: root.tabbed
        Repeater {
            id: tabs
            model: ["Lyrics", "Queue"]
            Button {
                required property string modelData
                objectName: "dockTab-" + root.title + "-" + modelData
                text: modelData; height: 40; y: 4
                Accessible.name: modelData + " panel"
                onClicked: appState.setActiveDock(modelData)
                contentItem: Text { text: parent.text; color: themeState.foreground; font.bold: appState.activeDock === parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 8; color: appState.activeDock === parent.text ? themeState.selected : parent.hovered ? themeState.hover : "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.accent }
            }
        }
    }
    IconButton {
        id: closeButton
        objectName: "dockClose-" + root.title
        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
        width: 36; height: 36; iconName: "close"; tip: "Close " + root.title
        onClicked: root.closeRequested()
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.border }
}
