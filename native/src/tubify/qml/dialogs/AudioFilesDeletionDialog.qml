import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../Theme.js" as Theme

// Confirms deleting the audio files Tubify saved: one download's, or every one when entry is empty.
ThemedDialog {
    id: root
    objectName: "audioFilesDeletionDialog"
    property var entry: ({})
    readonly property bool all: !entry.key
    readonly property bool onlyFiles: !!(entry.files && entry.files.move)
    parent: Overlay.overlay
    width: Math.min(460, (parent ? parent.width : 460) - 48)
    title: all ? "Delete All Audio Files?" : "Delete Audio Files?"
    contentItem: ColumnLayout {
        spacing: Theme.spacingLarge
        Label {
            Layout.fillWidth: true
            text: root.all
                ? "Delete all " + downloadsState.savedFileCount + " audio files Tubify saved in " + downloadsState.filesFolder + "? Downloads kept as audio files are removed too. Other files in the folder aren't touched."
                : "Delete the audio files Tubify saved for “" + (root.entry.title || "this music") + "”?" + (root.onlyFiles ? " This download is kept as those files, so it's removed too." : " Its download in Tubify stays.")
            textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            ThemeActionButton { text: "Cancel"; onClicked: root.reject() }
            ThemeActionButton { objectName: "audioFilesDeletionConfirm"; text: "Delete"; primary: true; onClicked: root.accept() }
        }
    }
    onAccepted: root.all ? downloadsState.deleteAllFiles() : downloadsState.deleteFiles(root.entry.key)
    Connections {
        target: downloadsState
        function onFilesDeletionRequested(entry) { root.entry = entry; root.open() }
    }
}
