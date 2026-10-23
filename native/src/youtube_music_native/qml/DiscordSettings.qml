import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    property alias scrollView: scroll
    objectName: "discordSettingsDialog"
    title: "Discord Presence"
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        implicitHeight: Math.min(body.implicitHeight, Overlay.overlay ? Overlay.overlay.height - 160 : 480)
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: 12
            SettingsCheckBox { objectName: "discordEnabledOption"; text: "Share Listening Activity"; checked: discordState.enabled; onClicked: discordState.setEnabled(checked) }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Tubify automatically finds the running Discord desktop app and shares the current song. Pausing or disabling clears your activity."; color: themeState.secondary }
            SettingsCheckBox { id: advanced; text: "Use a Custom Application ID"; checked: discordState.clientId !== discordState.defaultClientId; onToggled: if (!checked) discordState.setClientId("") }
            ColumnLayout {
                visible: advanced.checked
                Layout.fillWidth: true
                spacing: 12
                Label { text: "Discord Application ID"; color: themeState.foreground }
                TextField { id: client; objectName: "discordClientId"; Layout.fillWidth: true; text: discordState.clientId; placeholderText: "Numeric Application ID"; maximumLength: 20; Accessible.name: "Discord Application ID"; onAccepted: discordState.setClientId(text) }
                ThemeActionButton { text: "Save ID"; onClicked: discordState.setClientId(client.text) }
                Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Tubify includes its own Application ID. Only change this if you use a separately registered Discord application. No bot token or client secret is needed."; color: themeState.secondary; font.pixelSize: 12 }
            }
            SettingsCheckBox { text: "Show Listen on YouTube Music Button"; checked: discordState.buttons; onClicked: discordState.setButtons(checked) }
            Label { objectName: "discordStatus"; Layout.fillWidth: true; wrapMode: Text.Wrap; text: discordState.status; color: themeState.foreground }
            ThemeActionButton { text: "Retry"; enabled: discordState.enabled; onClicked: discordState.retry() }
        }
    }
}
