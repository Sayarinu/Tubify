import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "apiSettings"
    property alias scrollView: optionsScroll
    title: "Local API"
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(600, Overlay.overlay.width - 32) : 600
    height: Overlay.overlay ? Math.min(implicitHeight, Overlay.overlay.height - 48) : implicitHeight
    standardButtons: Dialog.Close
    background: Rectangle { color: themeState.background; border.color: themeState.border; radius: 12 }
    contentItem: ScrollView {
        id: optionsScroll
        contentWidth: availableWidth
        implicitHeight: options.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: options
            width: optionsScroll.availableWidth
            spacing: 16
            CheckBox { objectName: "apiEnabled"; text: "Enable local API"; checked: apiState.enabled; onToggled: apiState.setEnabled(checked) }
            Text { Layout.fillWidth: true; text: "Allow paired apps on this computer to read now playing or control music. Access always requires a token. The server listens only on 127.0.0.1."; wrapMode: Text.Wrap; color: themeState.secondary }
            RowLayout {
                Text { text: "Port"; color: themeState.foreground }
                SpinBox { objectName: "apiPort"; from: 1024; to: 65535; value: apiState.port; editable: true; enabled: !apiState.enabled; onValueModified: apiState.setPort(value); Accessible.name: "Local API port" }
            }
            Text { objectName: "apiAddress"; Layout.fillWidth: true; text: apiState.active ? apiState.baseUrl : apiState.enabled ? (apiState.error ? "Local API is unavailable." : "Starting local API…") : "Local API is disabled."; wrapMode: Text.Wrap; color: themeState.foreground }
            Text { objectName: "apiError"; Layout.fillWidth: true; text: apiState.error; visible: !!text; wrapMode: Text.Wrap; color: themeState.foreground }
            ThemeActionButton { text: "Retry server"; visible: apiState.enabled && !!apiState.error; onClicked: apiState.retry() }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Text { text: "Pair a client"; font.bold: true; color: themeState.foreground }
            TextField { id: clientName; objectName: "apiClientName"; Layout.fillWidth: true; placeholderText: "Client name, such as Stream Deck"; maximumLength: 64; Accessible.name: "API client name" }
            ComboBox { id: clientScope; objectName: "apiClientScope"; Layout.fillWidth: true; model: ["Overlay · read now playing", "Playback control · read and control"]; Accessible.name: "API permission" }
            ThemeActionButton { objectName: "apiBeginPairing"; text: "Generate pairing code"; enabled: apiState.active && clientName.text.trim().length > 0; onClicked: apiState.beginPairing(clientName.text, clientScope.currentIndex === 0 ? "overlay" : "control") }
            Text { Layout.fillWidth: true; text: "Paste the one-time code into your client within two minutes. A new code replaces the previous one. Overlay access cannot change playback or read your queue."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            TextField { objectName: "apiPairingCode"; Layout.fillWidth: true; text: apiState.pairingCode; visible: !!text; readOnly: true; selectByMouse: true; Accessible.name: "One-time API pairing code" }
            RowLayout {
                visible: !!apiState.pairingCode
                ThemeActionButton { text: "Copy code"; onClicked: apiState.copyPairingCode() }
                ThemeActionButton { text: "Cancel pairing"; onClicked: apiState.cancelPairing() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Text { text: "Paired clients"; font.bold: true; color: themeState.foreground }
            Text { text: "No paired clients"; visible: apiState.clients.length === 0; color: themeState.secondary }
            Repeater {
                model: apiState.clients
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: modelData.name; color: themeState.foreground; elide: Text.ElideRight }
                        Text { text: modelData.scope === "control" ? "Playback control" : "Read-only overlay"; color: themeState.secondary; font.pixelSize: 12 }
                    }
                    ThemeActionButton { text: "Revoke"; Accessible.name: "Revoke " + modelData.name; onClicked: apiState.revokeClient(modelData.id) }
                }
            }
            ThemeActionButton { objectName: "apiRevokeAll"; text: "Revoke all clients"; onClicked: apiState.revokeAll() }
        }
    }
}
