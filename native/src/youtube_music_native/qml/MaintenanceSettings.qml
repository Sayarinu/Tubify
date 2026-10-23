import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Dialog {
    id: root
    objectName: "maintenanceSettings"
    property alias scrollView: scroll
    title: "Updates and troubleshooting"
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(560, Overlay.overlay.width - 32) : 560
    height: Math.min(implicitHeight, Overlay.overlay ? Overlay.overlay.height - 48 : 560)
    modal: true; focus: true
    standardButtons: Dialog.Close
    background: Rectangle { color: themeState.background; border.color: themeState.border; radius: 12 }
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
            Label { text: "Native client " + maintenanceState.currentVersion; color: themeState.foreground; font.bold: true }
            Label { Layout.fillWidth: true; text: maintenanceState.status; color: themeState.foreground; wrapMode: Text.Wrap }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "checkReleaseButton"; text: "Check for releases"; enabled: !maintenanceState.busy; onClicked: maintenanceState.checkRelease() }
                ThemeActionButton { text: "Release details"; visible: !!maintenanceState.releaseUrl; onClicked: Qt.openUrlExternally(maintenanceState.releaseUrl) }
            }
            Label { Layout.fillWidth: true; text: maintenanceState.updateGuidance; color: themeState.secondary; wrapMode: Text.Wrap }
            Label { text: "Rendering issues"; color: themeState.foreground; font.bold: true }
            Label { Layout.fillWidth: true; text: "For blank artwork or drawing glitches, close the app and start it with:\nyoutube-music-native --software-rendering\n\nThis applies to that launch only. Start normally to return to automatic graphics. Software rendering may use more CPU."; color: themeState.foreground; wrapMode: Text.Wrap }
            Label { text: "Local diagnostics"; color: themeState.foreground; font.bold: true }
            Label { Layout.fillWidth: true; text: "Save version numbers, renderer, window size and display scale. The report excludes account information, listening history, music metadata, paths, credentials and logs. Nothing is uploaded."; color: themeState.secondary; wrapMode: Text.Wrap }
            ThemeActionButton { objectName: "exportDiagnosticsButton"; text: "Save diagnostics…"; enabled: !maintenanceState.busy; onClicked: saveReport.open() }
            Label { Layout.fillWidth: true; text: maintenanceState.exportStatus; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
        }
    }
    FileDialog {
        id: saveReport
        title: "Save local diagnostics"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON report (*.json)"]
        defaultSuffix: "json"
        onAccepted: maintenanceState.exportDiagnostics(selectedFile)
    }
}
