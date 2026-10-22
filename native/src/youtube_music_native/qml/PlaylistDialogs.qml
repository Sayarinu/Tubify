import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: root
    property bool opened: editor.opened || removal.opened || chooser.opened
    property string operation: "playlist_create"
    property var target: ({})
    Dialog {
        id: editor
        objectName: "playlistEditor"
        anchors.centerIn: parent; width: Math.min(root.width - 80, 440); modal: true
        title: root.operation === "playlist_create" ? "New playlist" : "Rename playlist"
        palette.window: themeState.surface; palette.windowText: themeState.foreground; palette.text: themeState.foreground
        contentItem: ColumnLayout {
            spacing: 16
            TextField { id: name; objectName: "playlistNameField"; Layout.fillWidth: true; maximumLength: 150; placeholderText: "Playlist name"; color: themeState.foreground; placeholderTextColor: themeState.secondary; selectByMouse: true; Accessible.name: "Playlist name"; background: Rectangle { color: themeState.hover; radius: 4; border.color: name.activeFocus ? themeState.foreground : themeState.muted } onAccepted: if (save.enabled) save.clicked() }
            Label { text: root.operation === "playlist_create" ? "New playlists are private." : ""; visible: text.length > 0; color: themeState.secondary }
            Label { Layout.fillWidth: true; text: actionsState.message; textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
        }
        footer: DialogButtonBox {
            Button { text: "Cancel"; enabled: !actionsState.busy; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            Button { id: save; text: "Save"; enabled: !!name.text.trim() && !actionsState.busy && (accountState.connected || appState.fixtureMode); DialogButtonBox.buttonRole: DialogButtonBox.ActionRole; onClicked: if (root.operation === "playlist_create") libraryState.create(name.text); else libraryState.rename(root.target.id, name.text) }
            onRejected: editor.close()
        }
        onOpened: { name.forceActiveFocus(); name.selectAll() }
    }
    Dialog {
        id: removal
        anchors.centerIn: parent; width: Math.min(root.width - 80, 440); modal: true
        title: "Delete playlist"
        palette.window: themeState.surface; palette.windowText: themeState.foreground; palette.text: themeState.foreground
        contentItem: ColumnLayout {
            spacing: 16
            Label { Layout.fillWidth: true; text: "Delete “" + (root.target.title || "this playlist") + "” from YouTube Music?"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground }
            Label { Layout.fillWidth: true; text: actionsState.message; textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
        }
        footer: DialogButtonBox {
            Button { text: "Cancel"; enabled: !actionsState.busy; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            Button { text: "Delete"; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode); DialogButtonBox.buttonRole: DialogButtonBox.ActionRole; onClicked: libraryState.removePlaylist(root.target.id) }
            onRejected: removal.close()
        }
    }
    Dialog {
        id: chooser
        anchors.centerIn: parent; width: Math.min(root.width - 80, 440); modal: true
        title: "Add to playlist"; standardButtons: Dialog.Cancel
        palette.window: themeState.surface; palette.windowText: themeState.foreground; palette.text: themeState.foreground
        contentItem: ColumnLayout {
            spacing: 16
            TextField { id: find; Layout.fillWidth: true; placeholderText: "Find a playlist"; color: themeState.foreground; placeholderTextColor: themeState.secondary; Accessible.name: "Find a playlist"; background: Rectangle { color: themeState.hover; radius: 4 } }
            ListView {
                Layout.fillWidth: true; Layout.preferredHeight: Math.max(80, Math.min(280, root.height - 240)); clip: true; model: libraryState.playlists
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width; height: visible ? 48 : 0; visible: !find.text || modelData.title.toLowerCase().indexOf(find.text.toLowerCase()) >= 0
                    enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode)
                    contentItem: Text { text: modelData.title; textFormat: Text.PlainText; color: themeState.foreground; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                    onClicked: libraryState.add(modelData.id, root.target)
                }
            }
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: libraryState.loadingPlaylists; visible: running }
            Label { Layout.fillWidth: true; text: actionsState.message || libraryState.message || (!libraryState.loadingPlaylists && !libraryState.playlists.length ? "Create a playlist with New playlist, then add this song." : ""); textFormat: Text.PlainText; visible: !!text; wrapMode: Text.Wrap; color: themeState.secondary }
            Button { text: "Retry"; visible: !!libraryState.message; onClicked: libraryState.choosePlaylist(root.target) }
        }
    }
    Connections {
        target: libraryState
        function onDialogRequested(operation, media) { actionsState.dismiss(); root.operation = operation; root.target = media; if (operation === "playlist_delete") removal.open(); else { name.text = media.title || ""; editor.open() } }
        function onChooserRequested(media) { actionsState.dismiss(); root.target = media; find.clear(); chooser.open() }
        function onEditFinished() { editor.close(); removal.close(); chooser.close() }
    }
}
