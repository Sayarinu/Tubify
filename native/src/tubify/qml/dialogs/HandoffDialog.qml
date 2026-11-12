import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../settings"
import "../Theme.js" as Theme

// Continue the current song in the YouTube Music phone app by scanning a QR code.
ThemedDialog {
    id: root
    objectName: "handoffDialog"
    width: Overlay.overlay ? Math.min(400, Overlay.overlay.width - 48) : 400
    title: "Continue on Phone"
    property var service: typeof handoffState !== "undefined" ? handoffState : null
    property alias pauseOnClose: pause.checked
    onOpened: pause.checked = true
    onClosed: if (service) service.finish(pause.checked)
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        implicitHeight: Math.min(body.implicitHeight, Overlay.overlay ? Overlay.overlay.height - 160 : 520)
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Theme.spacingMedium
            Label {
                Layout.fillWidth: true
                text: "Scan with your phone's camera to open this song in YouTube Music."
                color: themeState.secondary; wrapMode: Text.Wrap
            }
            // QR codes need dark modules on a light background in every theme.
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: Math.min(232, body.width); implicitHeight: implicitWidth
                radius: Theme.radiusMedium; color: "white"
                Image {
                    objectName: "handoffQr"
                    // Whole pixels per module keep every square the same size for scanners.
                    anchors.centerIn: parent
                    width: implicitWidth > 0 ? Math.max(1, Math.floor((parent.width - 8) / implicitWidth)) * implicitWidth : 0
                    height: width
                    source: root.service ? root.service.qrImage : ""
                    smooth: false; fillMode: Image.PreserveAspectFit
                    Accessible.name: "QR code for this song"
                }
            }
            Label {
                objectName: "handoffUrl"
                Layout.fillWidth: true
                text: root.service ? root.service.url : ""; textFormat: Text.PlainText
                color: themeState.secondary; wrapMode: Text.WrapAnywhere; font.pixelSize: Theme.textSmall
            }
            SettingsCheckBox { id: pause; objectName: "handoffPause"; text: "Pause Tubify"; checked: true }
            RowLayout {
                Layout.fillWidth: true
                ThemeActionButton { objectName: "handoffCopy"; text: "Copy Link"; enabled: !!root.service && !!root.service.url; onClicked: root.service.copy() }
                Item { Layout.fillWidth: true }
                ThemeActionButton { objectName: "handoffDone"; text: "Done"; onClicked: root.close() }
            }
        }
    }
}
