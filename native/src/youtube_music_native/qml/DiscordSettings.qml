import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    property alias scrollView: scroll
    objectName: "discordSettingsDialog"
    title: "Discord presence"
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(520, Overlay.overlay.width - 48) : 520
    modal: true; focus: true
    standardButtons: Dialog.Close
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        implicitHeight: Math.min(body.implicitHeight, Overlay.overlay ? Overlay.overlay.height - 160 : 480)
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: 12
            CheckBox { objectName: "discordEnabledOption"; text: "Share listening activity on Discord"; checked: discordState.enabled; onClicked: discordState.setEnabled(checked) }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Shows the song and artist while music plays. Pausing or disabling clears your activity. Discord desktop must be running."; color: themeState.secondary }
            Label { text: "Discord Application ID"; color: themeState.foreground }
            TextField { id: client; objectName: "discordClientId"; Layout.fillWidth: true; text: discordState.clientId; placeholderText: "Numeric Application ID"; maximumLength: 20; Accessible.name: "Discord Application ID"; onAccepted: discordState.setClientId(text) }
            RowLayout {
                ThemeActionButton { text: "Save ID"; onClicked: discordState.setClientId(client.text) }
                ThemeActionButton { text: "Developer Portal"; onClicked: Qt.openUrlExternally("https://discord.com/developers/applications") }
            }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Create an application named YouTube Music in the Developer Portal, then copy its Application ID from General Information. No bot token or client secret is needed."; color: themeState.secondary; font.pixelSize: 12 }
            CheckBox { text: "Include a Listen on YouTube Music button"; checked: discordState.buttons; onClicked: discordState.setButtons(checked) }
            Label { objectName: "discordStatus"; Layout.fillWidth: true; wrapMode: Text.Wrap; text: discordState.status; color: themeState.foreground }
            ThemeActionButton { text: "Retry"; enabled: discordState.enabled; onClicked: discordState.retry() }
        }
    }
}
