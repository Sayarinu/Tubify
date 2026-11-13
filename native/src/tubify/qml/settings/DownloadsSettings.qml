import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"
import "../Theme.js" as Theme

// The two download styles: offline copies that play inside Tubify, and, if chosen,
// tagged audio files in a folder for other apps and devices.
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
            Text { Layout.fillWidth: true; text: "Offline Copies"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textTitle }
            Text { Layout.fillWidth: true; text: "Every download is kept inside Tubify, so it plays without a connection, even when you're signed out. Remove Download deletes only this copy."; color: themeState.secondary; wrapMode: Text.Wrap }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            SettingsCheckBox { objectName: "saveAudioFilesOption"; text: "Also Save Audio Files"; checked: downloadsState.filesEnabled; onToggled: downloadsState.setFilesEnabled(checked) }
            Text { Layout.fillWidth: true; text: "New downloads are also saved as tagged audio files, with artwork, for other apps and devices. The audio isn't re-encoded. To save one song, album or playlist, choose Save Audio Files from its menu."; color: themeState.secondary; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMedium
                Text { objectName: "audioFilesFolder"; Layout.fillWidth: true; text: downloadsState.filesFolder; textFormat: Text.PlainText; color: themeState.foreground; elide: Text.ElideMiddle }
                ThemeActionButton { objectName: "audioFilesFolderChange"; text: "Change…"; onClicked: folderDialog.open() }
                ThemeActionButton { text: "Open"; onClicked: downloadsState.openFilesFolder() }
            }
            Text { Layout.fillWidth: true; text: "Saved files belong to you. Tubify never overwrites, moves or deletes them, and they appear in Local Music."; color: themeState.secondary; wrapMode: Text.Wrap }
        }
    }
}
