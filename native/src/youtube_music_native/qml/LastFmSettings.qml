import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    objectName: "lastFmSettingsDialog"
    title: "Last.fm"
    property alias scrollView: scroll
    property var service: typeof lastFmState !== "undefined" ? lastFmState : null
    property bool editingCredentials: false
    onOpenedChanged: if (opened) { if (service) service.refresh() }
    onClosed: { apiKey.clear(); secret.clear(); editingCredentials = false }
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        implicitHeight: Overlay.overlay ? Math.min(570, Overlay.overlay.height - 180) : 570
        clip: true
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 12
            SettingsCheckBox { objectName: "lastFmEnabled"; text: "Scrobble to Last.fm"; enabled: !!root.service && (root.service.enabled || root.service.connected && !root.service.busy); checked: !!root.service && root.service.enabled; onClicked: root.service.setEnabled(checked) }
            Label { objectName: "lastFmAccount"; Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service && root.service.connected ? "Signed in as " + root.service.username : "Not signed in"; wrapMode: Text.Wrap; color: themeState.foreground }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "lastFmSignIn"; text: root.service && root.service.connected ? "Sign In Again" : "Sign In"; enabled: !!root.service && root.service.configured && !root.service.busy; onClicked: root.service.authorize() }
                ThemeActionButton { objectName: "lastFmComplete"; text: "Complete Sign-In"; visible: !!root.service && root.service.awaitingApproval; enabled: !!root.service && !root.service.busy; onClicked: root.service.complete() }
                ThemeActionButton { objectName: "lastFmSignOut"; text: root.service && root.service.pendingCount > 0 ? "Sign Out and Clear " + root.service.pendingCount + " Saved Listens" : "Sign Out"; visible: !!root.service && root.service.configured; enabled: !!root.service && !root.service.busy; onClicked: root.service.logout() }
                ThemeActionButton { text: "Retry Saved Listens (" + (root.service ? root.service.pendingCount : 0) + ")"; visible: !!root.service && root.service.pendingCount > 0; enabled: !!root.service && root.service.enabled && root.service.connected && !root.service.busy; onClicked: root.service.retry() }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Scrobble After"; color: themeState.foreground }
                SpinBox { objectName: "lastFmThreshold"; from: 50; to: 100; stepSize: 5; value: root.service ? root.service.thresholdPercent : 50; onValueModified: root.service.setThresholdPercent(value); Accessible.name: "Last.fm listening threshold percent" }
                Label { text: "% or 4 min"; color: themeState.foreground }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            SettingsCheckBox {
                objectName: "lastFmEditCredentials"
                text: "Change API Credentials"
                visible: !!root.service && root.service.configured
                checked: root.editingCredentials
                onToggled: root.editingCredentials = checked
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 12
                visible: !root.service || !root.service.configured || root.editingCredentials
                RowLayout {
                    Layout.fillWidth: true
                    Label { Layout.fillWidth: true; text: "API Credentials"; font.bold: true; color: themeState.foreground }
                    ThemeActionButton { text: "Get Credentials"; onClicked: Qt.openUrlExternally("https://www.last.fm/api/account/create") }
                }
                TextField { id: apiKey; objectName: "lastFmApiKey"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "API key"; maximumLength: 32; Accessible.name: "Last.fm API key" }
                TextField { id: secret; objectName: "lastFmSecret"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Shared secret"; maximumLength: 32; Accessible.name: "Last.fm shared secret" }
                ThemeActionButton { text: "Save Credentials"; enabled: !!root.service && !root.service.busy && apiKey.text.length === 32 && secret.text.length === 32; onClicked: { root.service.configure(apiKey.text, secret.text); apiKey.clear(); secret.clear(); root.editingCredentials = false } }
                Label { Layout.fillWidth: true; text: "Kept in your system keyring."; color: themeState.secondary; font.pixelSize: 12 }
            }
            Label { objectName: "lastFmStatus"; Layout.fillWidth: true; visible: !!text; text: root.service ? (root.service.busy ? "Contacting Last.fm…" : root.service.message) : "Last.fm is unavailable."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
        }
    }
}
