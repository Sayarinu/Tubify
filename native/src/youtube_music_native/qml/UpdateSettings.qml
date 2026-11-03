import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    objectName: "updateSettings"
    property alias scrollView: scroll
    title: "Updates"
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        implicitHeight: body.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: 16
            Label { objectName: "installedVersion"; text: maintenanceState.versionName; textFormat: Text.PlainText; color: themeState.foreground; font.bold: true }
            Label { objectName: "updateStatus"; Layout.fillWidth: true; text: maintenanceState.status; textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Update Channel"; color: themeState.foreground }
                ThemedComboBox {
                    objectName: "updateChannelOption"
                    Layout.fillWidth: true
                    model: ["Stable", "Experimental"]
                    currentIndex: ["stable", "experimental"].indexOf(maintenanceState.channel)
                    enabled: !maintenanceState.busy
                    Accessible.name: "Update channel"
                    onActivated: maintenanceState.setChannel(["stable", "experimental"][currentIndex])
                }
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12
                text: "Experimental builds get new features first and may have rough edges. Choose Stable to return to the latest full release at any time."
            }
            SettingsCheckBox {
                text: "Check Automatically for Updates"
                checked: maintenanceState.automaticChecks
                onToggled: maintenanceState.setAutomaticChecks(checked)
            }
            ProgressBar { Layout.fillWidth: true; visible: maintenanceState.downloading; value: maintenanceState.progress / 100 }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "checkReleaseButton"; text: "Check for Updates"; enabled: !maintenanceState.busy; onClicked: maintenanceState.checkRelease() }
                ThemeActionButton { objectName: "installUpdateButton"; text: maintenanceState.switchingChannel ? "Switch to Stable" : Qt.platform.os === "osx" ? "Update…" : "Update & Restart"; visible: maintenanceState.updateAvailable && maintenanceState.installSupported; enabled: !maintenanceState.busy; onClicked: maintenanceState.installUpdate() }
                ThemeActionButton { text: "Cancel Download"; visible: maintenanceState.downloading; onClicked: maintenanceState.cancelUpdate() }
                ThemeActionButton { text: "Release Details"; visible: !!maintenanceState.releaseUrl; onClicked: Qt.openUrlExternally(maintenanceState.releaseUrl) }
            }
            Label { Layout.fillWidth: true; text: maintenanceState.updateGuidance; color: themeState.secondary; wrapMode: Text.Wrap; font.pixelSize: 12 }
            Label { text: "About"; color: themeState.foreground; font.bold: true }
            Label { Layout.fillWidth: true; text: "Tubify is open source under the MIT License. It is not affiliated with Google or YouTube."; color: themeState.secondary; wrapMode: Text.Wrap }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "licensesButton"; text: "Open-Source Licenses"; onClicked: Qt.openUrlExternally(maintenanceState.noticesUrl) }
                ThemeActionButton { text: "Project Page"; onClicked: Qt.openUrlExternally("https://github.com/Sayarinu/Tubify") }
            }
        }
    }
}
