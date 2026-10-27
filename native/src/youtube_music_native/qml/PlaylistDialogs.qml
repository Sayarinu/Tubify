import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: root
    property bool opened: editor.opened || removal.opened || chooser.opened
    property string operation: "playlist_create"
    property var target: ({})
    ThemedDialog {
        id: editor
        objectName: "playlistEditor"
        width: Math.min(root.width - 80, 440)
        title: root.operation === "playlist_create" ? "New Playlist" : "Rename Playlist"
        contentItem: ColumnLayout {
            spacing: 16
            ThemedTextField { id: name; objectName: "playlistNameField"; Layout.fillWidth: true; maximumLength: 150; placeholderText: "Playlist name"; Accessible.name: "Playlist name"; onAccepted: if (save.enabled) save.clicked() }
            Label { text: root.operation === "playlist_create" ? "New playlists are private." : ""; visible: text.length > 0; color: themeState.secondary }
            Label { Layout.fillWidth: true; text: actionsState.message; textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; enabled: !actionsState.busy; onClicked: editor.close() }
                ThemeActionButton { id: save; text: "Save"; primary: true; enabled: !!name.text.trim() && !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: if (root.operation === "playlist_create") libraryState.create(name.text); else libraryState.rename(root.target.id, name.text) }
            }
        }
        onOpened: { name.forceActiveFocus(); name.selectAll() }
    }
    ThemedDialog {
        id: removal
        width: Math.min(root.width - 80, 440)
        title: "Delete Playlist"
        contentItem: ColumnLayout {
            spacing: 16
            Label { Layout.fillWidth: true; text: "Delete “" + (root.target.title || "this playlist") + "” from YouTube Music?"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground }
            Label { Layout.fillWidth: true; text: actionsState.message; textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; enabled: !actionsState.busy; onClicked: removal.close() }
                ThemeActionButton { text: "Delete"; primary: true; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: libraryState.removePlaylist(root.target.id) }
            }
        }
    }
    ThemedDialog {
        id: chooser
        objectName: "playlistChooser"
        width: Math.min(root.width - 80, 440)
        title: "Add to Playlist"
        contentItem: ColumnLayout {
            spacing: 12
            ThemedTextField { id: find; objectName: "playlistChooserFind"; Layout.fillWidth: true; placeholderText: "Find a playlist"; Accessible.name: "Find a playlist" }
            ListView {
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(contentHeight, 280, Math.max(80, root.height - 240)); visible: count > 0; clip: true; model: libraryState.playlists
                spacing: 2
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    id: entry
                    required property var modelData
                    width: ListView.view.width; height: visible ? 40 : 0; visible: !find.text || modelData.title.toLowerCase().indexOf(find.text.toLowerCase()) >= 0
                    leftPadding: 12; rightPadding: 12
                    enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode)
                    contentItem: Text { text: entry.modelData.title; textFormat: Text.PlainText; color: entry.enabled ? themeState.foreground : themeState.muted; font.family: Theme.bodyFont; font.pixelSize: 14; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                    background: Rectangle { radius: 8; color: entry.down || entry.hovered || entry.highlighted ? themeState.hover : "transparent"; border.width: entry.visualFocus ? 1 : 0; border.color: themeState.accent }
                    onClicked: libraryState.add(modelData.id, root.target)
                }
            }
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: libraryState.loadingPlaylists; visible: running }
            Label { Layout.fillWidth: true; text: actionsState.message || libraryState.message || (!libraryState.loadingPlaylists && !libraryState.playlists.length ? "Create a playlist with New playlist, then add this song." : ""); textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Retry"; visible: !!libraryState.message; onClicked: libraryState.choosePlaylist(root.target) }
                ThemeActionButton { text: "Cancel"; onClicked: chooser.close() }
            }
        }
    }
    Connections {
        target: libraryState
        function onDialogRequested(operation, media) { actionsState.dismiss(); root.operation = operation; root.target = media; if (operation === "playlist_delete") removal.open(); else { name.text = media.title || ""; editor.open() } }
        function onChooserRequested(media) { actionsState.dismiss(); root.target = media; find.clear(); chooser.open(); find.forceActiveFocus() }
        function onEditFinished() { editor.close(); removal.close(); chooser.close() }
    }
}
