import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../components"
import "../Theme.js" as Theme

SettingsPage {
    id: root
    objectName: "troubleshootingSettings"
    property alias scrollView: scroll
    title: "Troubleshooting"
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        implicitHeight: body.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Theme.spacingLarge
            Label { Layout.fillWidth: true; text: "Save version numbers, renderer, window size and display scale. The report excludes account information, listening history, music metadata, paths, credentials and logs. Nothing is uploaded."; color: themeState.secondary; wrapMode: Text.Wrap }
            ThemeActionButton { objectName: "exportDiagnosticsButton"; text: "Save Diagnostics…"; enabled: !maintenanceState.busy; onClicked: saveReport.open() }
            Label { Layout.fillWidth: true; text: maintenanceState.exportStatus; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
        }
    }
    FileDialog {
        id: saveReport
        title: "Save Local Diagnostics"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON report (*.json)"]
        defaultSuffix: "json"
        onAccepted: maintenanceState.exportDiagnostics(selectedFile)
    }
}
