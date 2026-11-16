import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../Theme.js" as Theme

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
            spacing: Theme.spacingMedium
            SettingsCheckBox { objectName: "discordEnabledOption"; text: "Share Listening Activity"; checked: discordState.enabled; onClicked: discordState.setEnabled(checked) }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Tubify automatically finds the running Discord desktop app and shares the current song and its public album-art link. Discord may fetch that image while music plays. Pausing or disabling clears your activity."; color: themeState.secondary }
            SettingsCheckBox { id: advanced; text: "Use a Custom Application ID"; checked: discordState.clientId !== discordState.defaultClientId; onToggled: if (!checked) discordState.setClientId("") }
            ColumnLayout {
                visible: advanced.checked
                Layout.fillWidth: true
                spacing: Theme.spacingMedium
                Label { text: "Discord Application ID"; color: themeState.foreground }
                ThemedTextField { id: client; objectName: "discordClientId"; Layout.fillWidth: true; text: discordState.clientId; placeholderText: "Numeric Application ID"; maximumLength: 20; Accessible.name: "Discord Application ID"; onAccepted: discordState.setClientId(text) }
                ThemeActionButton { text: "Save ID"; onClicked: discordState.setClientId(client.text) }
                Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Tubify includes its own Application ID. Only change this if you use a separately registered Discord application. No bot token or client secret is needed."; color: themeState.secondary; font.pixelSize: Theme.textSmall }
            }
            SettingsCheckBox { text: "Show Listen on Tubify Button"; enabled: !discordState.listenAlong; checked: discordState.buttons; onClicked: discordState.setButtons(checked) }
            SettingsCheckBox { objectName: "discordListenAlongOption"; text: "Let Friends Listen Along"; checked: discordState.listenAlong; onClicked: discordState.setListenAlong(checked) }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Friends who click Join on your Discord activity play what you play in their Tubify, and you can join theirs. Tubify stays connected to Discord while this is on. Discord can't show the Listen on Tubify button alongside Join, so it is hidden."; color: themeState.secondary; font.pixelSize: Theme.textSmall }
            RowLayout {
                visible: discordState.listenAlong
                Layout.fillWidth: true
                spacing: Theme.spacingMedium
                Label { objectName: "discordListenFollowers"; Layout.fillWidth: true; text: discordState.listenFollowers === 1 ? "1 friend listening along" : discordState.listenFollowers + " friends listening along"; color: themeState.foreground }
                ThemeActionButton { text: "Reset Listen Along Link"; onClicked: discordState.resetListenAlong() }
            }
            Label { objectName: "listenAlongStatus"; visible: typeof listenAlongState !== "undefined" && listenAlongState.status !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap; text: visible ? listenAlongState.status : ""; color: themeState.foreground }
            ThemeActionButton { visible: typeof listenAlongState !== "undefined" && listenAlongState.following; text: "Stop Listening Along"; onClicked: listenAlongState.stop() }
            Label { objectName: "discordStatus"; Layout.fillWidth: true; wrapMode: Text.Wrap; text: discordState.status; color: themeState.foreground }
            ThemeActionButton { text: "Retry"; enabled: discordState.enabled; onClicked: discordState.retry() }
        }
    }
}
