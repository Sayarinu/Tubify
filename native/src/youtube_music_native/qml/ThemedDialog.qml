import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

// Modal dialog matching the app's popups: rounded surface card, bold title with a close button.
Dialog {
    id: root
    anchors.centerIn: Overlay.overlay
    modal: true
    focus: true
    padding: 20
    topPadding: 4
    standardButtons: Dialog.NoButton
    background: Rectangle { radius: 16; color: themeState.surface; border.color: themeState.border; border.width: 1 }
    header: RowLayout {
        spacing: 8
        Label {
            Layout.fillWidth: true; Layout.leftMargin: 20; Layout.topMargin: 16
            text: root.title; textFormat: Text.PlainText; elide: Text.ElideRight
            color: themeState.foreground; font.family: Theme.bodyFont; font.pixelSize: 15; font.bold: true
        }
        IconButton { Layout.rightMargin: 12; Layout.topMargin: 12; iconName: "close"; tip: "Close"; iconSize: 18; implicitWidth: 34; implicitHeight: 34; onClicked: root.reject() }
    }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
}
