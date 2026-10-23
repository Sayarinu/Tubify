import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "linkPreviewDialog"
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(480, Overlay.overlay.width - 48) : 480
    modal: true
    focus: true
    title: "Shared music"
    standardButtons: Dialog.Close
    property alias scrollView: scroll
    property var service: typeof linkState !== "undefined" ? linkState : null
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        implicitHeight: Math.min(body.implicitHeight, Overlay.overlay ? Overlay.overlay.height - 160 : 420)
        ColumnLayout {
        id: body
        width: scroll.availableWidth
        spacing: 16
        Label { objectName: "linkPreviewTitle"; Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service ? root.service.media.title || "Music link" : "Music link"; color: themeState.foreground; font.pixelSize: 20; font.bold: true; wrapMode: Text.Wrap }
        Label { Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service ? root.service.media.artist || (root.service.media.artists || []).map(a => a.name).join(" · ") : ""; color: themeState.secondary; wrapMode: Text.Wrap }
        Label { Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service ? root.service.url : ""; color: themeState.secondary; wrapMode: Text.WrapAnywhere; font.pixelSize: 12 }
        Label { Layout.fillWidth: true; visible: !!root.service && root.service.previewOnly; text: "Choose Play or Add to queue to change playback."; color: themeState.secondary; wrapMode: Text.Wrap; font.pixelSize: 12 }
        Label { objectName: "linkPreviewMessage"; Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service ? root.service.message : ""; color: themeState.foreground; wrapMode: Text.Wrap }
        RowLayout {
            Layout.fillWidth: true
            ThemeActionButton { objectName: "linkOpenPage"; text: "Open page"; visible: !!root.service && !!root.service.media.kind && root.service.media.kind !== "song"; enabled: !!root.service && !root.service.busy; onClicked: { root.service.perform("open"); root.close() } }
            ThemeActionButton { objectName: "linkPlay"; text: "Play"; enabled: !!root.service && root.service.canPlay && !root.service.busy; onClicked: root.service.perform("play") }
            ThemeActionButton { objectName: "linkQueue"; text: "Add to queue"; enabled: !!root.service && root.service.canPlay && !root.service.busy; onClicked: root.service.perform("queue") }
            ThemeActionButton { text: "Retry"; visible: !!root.service && !!root.service.url && !root.service.canPlay && root.service.media.kind !== "artist"; enabled: !!root.service && !root.service.busy; onClicked: root.service.retry() }
        }
        }
    }
}
