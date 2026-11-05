import QtQuick
import QtQuick.Controls
import "../components"

// A panel's header: its title, or tabs when it has more than one view, and a close button.
Item {
    id: root
    required property string title
    property var tabs: []
    property string currentTab: ""
    signal tabSelected(string tab)
    signal closeRequested()
    function focusControl() {
        var index = tabs.indexOf(currentTab)
        if (index >= 0) tabButtons.itemAt(index).forceActiveFocus()
        else closeButton.forceActiveFocus()
    }
    width: parent.width
    height: 48
    Rectangle { objectName: "panelHeaderDivider"; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: themeState.border }
    Text {
        anchors.left: parent.left; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter
        anchors.right: closeButton.left; anchors.rightMargin: 8
        visible: root.tabs.length === 0
        text: root.title
        elide: Text.ElideRight
        font.bold: true; font.pixelSize: 16; color: themeState.foreground
    }
    Row {
        x: 16; height: parent.height; spacing: 20
        visible: root.tabs.length > 0
        Repeater {
            id: tabButtons
            model: root.tabs
            Button {
                id: tab
                required property string modelData
                readonly property bool selected: root.currentTab === modelData
                objectName: "dockTab-" + modelData
                height: parent.height
                padding: 0
                text: modelData
                Accessible.name: modelData + " tab"
                onClicked: root.tabSelected(modelData)
                contentItem: Text {
                    text: tab.text
                    color: tab.selected || tab.hovered ? themeState.foreground : themeState.secondary
                    font.bold: true; font.pixelSize: 14
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: "transparent"
                    border.width: tab.visualFocus ? 2 : 0
                    border.color: themeState.accent
                    radius: 4
                    Rectangle {
                        objectName: "dockTabUnderline-" + tab.modelData
                        visible: tab.selected
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 2; radius: 1
                        color: themeState.accent
                    }
                }
            }
        }
    }
    IconButton {
        id: closeButton
        objectName: "dockClose"
        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
        width: 36; height: 36; iconName: "close"; tip: "Close " + root.title
        onClicked: root.closeRequested()
    }
}
