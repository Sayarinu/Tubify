import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Rectangle {
    id: root
    required property string message
    property bool busy: false
    signal retry()
    anchors.left: parent.left; anchors.right: parent.right
    anchors.leftMargin: 24; anchors.rightMargin: 24
    anchors.bottom: parent.bottom; anchors.bottomMargin: 12
    height: Math.max(48, label.implicitHeight + 24)
    radius: 6; color: Theme.surface; visible: !!message
    Text { id: label; anchors.left: parent.left; anchors.leftMargin: 12; anchors.right: button.left; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: root.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.secondary; font.pixelSize: 14 }
    Button { id: button; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "Retry"; enabled: !root.busy; palette.windowText: "white"; onClicked: root.retry() }
}
