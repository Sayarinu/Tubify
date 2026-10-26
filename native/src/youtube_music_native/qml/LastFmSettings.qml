import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    objectName: "lastFmSettingsDialog"
    title: "Last.fm"
    property alias scrollView: scroll
    property var service: typeof lastFmState !== "undefined" ? lastFmState : null
    onOpenedChanged: if (opened) { if (service) service.refresh() }
    onClosed: { apiKey.clear(); secret.clear() }
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        implicitHeight: Overlay.overlay ? Math.min(570, Overlay.overlay.height - 180) : 570
        clip: true
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 12
            Label { Layout.fillWidth: true; text: "Share Now Playing and qualifying listens with your Last.fm profile. Song, artist, album, duration and listen time are sent when enabled."; wrapMode: Text.Wrap; color: themeState.secondary }
            SettingsCheckBox { objectName: "lastFmEnabled"; text: "Send Listening Updates to Last.fm"; enabled: !!root.service && (root.service.enabled || root.service.connected && !root.service.busy); checked: !!root.service && root.service.enabled; onClicked: root.service.setEnabled(checked) }
            Label { Layout.fillWidth: true; textFormat: Text.PlainText; text: root.service && root.service.connected ? "Signed in as " + root.service.username : "Sign in to enable listening updates."; wrapMode: Text.Wrap; color: themeState.foreground }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Listen Threshold"; color: themeState.foreground }
                SpinBox { objectName: "lastFmThreshold"; from: 50; to: 100; stepSize: 5; value: root.service ? root.service.thresholdPercent : 50; onValueModified: root.service.setThresholdPercent(value); Accessible.name: "Last.fm listening threshold percent" }
                Label { text: "%"; color: themeState.foreground }
            }
            Label { Layout.fillWidth: true; text: "A listen qualifies after this percentage or four minutes of actual playback, whichever comes first. Songs of 30 seconds or less are excluded. Seeking and paused time do not count."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Label { text: "App Credentials"; font.bold: true; color: themeState.foreground }
            Label { Layout.fillWidth: true; text: "This build needs your Last.fm API key and shared secret. They and your sign-in session are kept in the system keyring. Replacing credentials clears pending listens."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            ThemeActionButton { text: "Get API Credentials"; onClicked: Qt.openUrlExternally("https://www.last.fm/api/account/create") }
            TextField { id: apiKey; objectName: "lastFmApiKey"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "API key"; maximumLength: 32; Accessible.name: "Last.fm API key" }
            TextField { id: secret; objectName: "lastFmSecret"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Shared secret"; maximumLength: 32; Accessible.name: "Last.fm shared secret" }
            ThemeActionButton { text: "Save Credentials"; enabled: !!root.service && !root.service.busy && apiKey.text.length === 32 && secret.text.length === 32; onClicked: { root.service.configure(apiKey.text, secret.text); apiKey.clear(); secret.clear() } }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "lastFmSignIn"; text: root.service && root.service.connected ? "Sign In Again" : "Sign In"; enabled: !!root.service && root.service.configured && !root.service.busy; onClicked: root.service.authorize() }
                ThemeActionButton { objectName: "lastFmComplete"; text: "Complete Sign-In"; enabled: !!root.service && root.service.awaitingApproval && !root.service.busy; onClicked: root.service.complete() }
            }
            ThemeActionButton { text: "Sign Out and Clear Saved Listens"; enabled: !!root.service && root.service.configured && !root.service.busy; onClicked: root.service.logout() }
            Label { Layout.fillWidth: true; visible: !!root.service && root.service.pendingCount > 0; text: root.service ? root.service.pendingCount + " saved listens waiting to send (up to 1,000 retained)." : ""; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            ThemeActionButton { text: "Retry Saved Listens"; visible: !!root.service && root.service.pendingCount > 0; enabled: !!root.service && root.service.enabled && root.service.connected && !root.service.busy; onClicked: root.service.retry() }
            Label { objectName: "lastFmStatus"; Layout.fillWidth: true; text: root.service ? (root.service.busy ? "Contacting Last.fm…" : root.service.message) : "Last.fm is unavailable."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
        }
    }
}
