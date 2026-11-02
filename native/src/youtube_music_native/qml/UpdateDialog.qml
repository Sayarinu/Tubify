import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Asks whether to install a newer stable release; Update Now runs the verified installer.
ThemedDialog {
    id: root
    objectName: "updateDialog"
    title: "Update Available"
    width: Math.min(460, (parent ? parent.width : 460) - 32)
    contentItem: ColumnLayout {
        spacing: 14
        Label {
            Layout.fillWidth: true
            text: "Tubify " + (maintenanceState.latestVersion || "") + " is ready to install."
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            color: themeState.foreground; font.pixelSize: 18; font.bold: true
        }
        Label {
            Layout.fillWidth: true
            text: "You have version " + maintenanceState.currentVersion + ". Updating keeps your settings, queue and downloaded music."
            textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.secondary
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(notes.implicitHeight + 24, 180)
            visible: !!maintenanceState.releaseNotes
            radius: 10; color: themeState.background
            ScrollView {
                anchors.fill: parent; anchors.margins: 12
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Label {
                    id: notes
                    objectName: "updateNotes"
                    width: parent.width
                    text: maintenanceState.releaseNotes
                    textFormat: Text.PlainText; wrapMode: Text.Wrap
                    color: themeState.foreground; font.pixelSize: 13
                }
            }
        }
        ProgressBar {
            Layout.fillWidth: true
            visible: maintenanceState.downloading
            value: maintenanceState.progress / 100
        }
        Label {
            Layout.fillWidth: true
            visible: maintenanceState.busy || maintenanceState.downloading || !maintenanceState.installSupported
            text: maintenanceState.installSupported ? maintenanceState.status : maintenanceState.updateGuidance
            textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 13
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ThemeActionButton { text: "Release Notes"; visible: !!maintenanceState.releaseUrl; onClicked: Qt.openUrlExternally(maintenanceState.releaseUrl) }
            Item { Layout.fillWidth: true }
            ThemeActionButton { objectName: "updateLater"; text: maintenanceState.downloading ? "Cancel" : "Later"; onClicked: { if (maintenanceState.downloading) maintenanceState.cancelUpdate(); else root.close() } }
            ThemeActionButton {
                objectName: "updateNow"
                primary: true
                text: !maintenanceState.installSupported ? "Download" : Qt.platform.os === "osx" ? "Update…" : "Update & Restart"
                enabled: !maintenanceState.busy
                onClicked: maintenanceState.installSupported ? maintenanceState.installUpdate() : Qt.openUrlExternally(maintenanceState.releaseUrl)
            }
        }
    }
}
