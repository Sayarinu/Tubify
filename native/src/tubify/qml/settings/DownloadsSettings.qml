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
            Text { Layout.fillWidth: true; text: "Save Downloads"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textTitle }
            DownloadStyleChoice { Layout.fillWidth: true }
            Text {
                objectName: "downloadStyleDescription"
                Layout.fillWidth: true
                text: downloadsState.downloadStyle === "files"
                    ? "Each download is saved as a tagged audio file, with artwork, in the folder below. Tubify plays it from there, and other apps and devices can use it too. Switching moves your existing downloads into the folder without downloading them again."
                    : "Downloads are kept privately inside Tubify and play without a connection, even when you're signed out. Switching copies any audio files back into Tubify and leaves them in their folder."
                color: themeState.secondary; wrapMode: Text.Wrap
            }
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
