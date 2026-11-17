import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"
import "../Theme.js" as Theme

// The two download styles: private offline copies inside Tubify, or tagged audio files in a folder.
SettingsPage {
    id: root
    property alias scrollView: optionsScroll
    objectName: "downloadsSettings"
    title: "Downloads"
    readonly property bool asFiles: downloadsState.downloadStyle === "files"
    function bytesLabel(value) {
        if (value >= 1073741824) return (value / 1073741824).toFixed(1) + " GB"
        return (value / 1048576).toFixed(1) + " MB"
    }
    FolderDialog {
        id: folderDialog
        title: "Choose Where to Save Audio Files"
        onAccepted: downloadsState.setFilesFolder(selectedFolder)
    }
    contentItem: ScrollView {
        id: optionsScroll
        contentWidth: availableWidth
        implicitHeight: options.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: options
            width: optionsScroll.availableWidth
            spacing: Theme.spacingLarge
            Text { Layout.fillWidth: true; text: "Download To"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textTitle }
            DownloadStyleChoice {}
            Text {
                objectName: "downloadStyleDescription"
                Layout.fillWidth: true
                text: downloadsState.downloadStyle === "files"
                    ? "Each download is saved as a tagged audio file, with artwork, in the folder below. Tubify plays it from there, and other apps and devices can use it too. Switching moves your existing downloads into the folder without downloading them again."
                    : "Downloads are kept privately inside Tubify and play without a connection, even when you're signed out. Switching copies any audio files back into Tubify and leaves them in their folder."
                color: themeState.secondary; wrapMode: Text.Wrap
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            // The space downloads take in the chosen style, then anything still on its way between the two.
            Text { Layout.fillWidth: true; text: "Storage"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textTitle }
            Text {
                objectName: "downloadStorageUsed"
                Layout.fillWidth: true
                text: root.asFiles ? "Songs: " + root.bytesLabel(downloadsState.fileBytes) + " as audio files in the folder below"
                                   : "Songs: " + root.bytesLabel(downloadsState.usedBytes) + " inside Tubify"
                textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap
            }
            Text {
                objectName: "downloadStorageVideos"
                Layout.fillWidth: true
                visible: downloadsState.videoBytes > 0
                text: "Music videos: " + root.bytesLabel(downloadsState.videoBytes) + " inside Tubify"
                textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap
            }
            Text {
                objectName: "downloadStorageMoving"
                Layout.fillWidth: true
                readonly property real waiting: root.asFiles ? downloadsState.usedBytes : downloadsState.fileBytes
                visible: waiting > 0
                text: root.asFiles ? root.bytesLabel(waiting) + " is still inside Tubify, waiting to be saved as audio files."
                                   : root.bytesLabel(waiting) + " still plays from audio files, waiting to be copied into Tubify."
                textFormat: Text.PlainText; color: themeState.secondary; wrapMode: Text.Wrap
            }
            Text {
                objectName: "downloadStorageFree"
                Layout.fillWidth: true
                text: root.bytesLabel(downloadsState.freeBytes) + " free"
                textFormat: Text.PlainText; color: themeState.secondary; wrapMode: Text.Wrap
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            SettingsCheckBox { objectName: "downloadVideosOption"; text: "Also Download Music Videos"; checked: downloadsState.downloadVideos; onToggled: downloadsState.setDownloadVideos(checked) }
            Text { Layout.fillWidth: true; text: "Songs that have a music video download it too, at up to 720p, so the Video switch works offline. A video takes about ten times the space of its song. Applies to new downloads; choose Refresh Download to add videos to one you have."; color: themeState.secondary; wrapMode: Text.Wrap }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Text { Layout.fillWidth: true; text: "Audio Files Folder"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textTitle }
            Text { Layout.fillWidth: true; text: "Where audio files are saved. In either style, choose Save as Audio Files from a song, album or playlist's menu to save it here too."; color: themeState.secondary; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMedium
                Text { objectName: "audioFilesFolder"; Layout.fillWidth: true; text: downloadsState.filesFolder; textFormat: Text.PlainText; color: themeState.foreground; elide: Text.ElideMiddle }
                ThemeActionButton { objectName: "audioFilesFolderChange"; text: "Change…"; onClicked: folderDialog.open() }
                ThemeActionButton { text: "Open"; onClicked: downloadsState.openFilesFolder() }
            }
            Text { Layout.fillWidth: true; text: "Saved files belong to you. Tubify never overwrites or moves them, and they appear in Local Music."; color: themeState.secondary; wrapMode: Text.Wrap }
        }
    }
}
