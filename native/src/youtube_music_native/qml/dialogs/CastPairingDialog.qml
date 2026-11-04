import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

// Asks before a device on the network can see and control what Tubify plays.
ThemedDialog {
    id: root
    objectName: "castPairingDialog"
    title: "Allow This Device?"
    width: Math.min(parent ? parent.width - 48 : 420, 420)
    closePolicy: Popup.CloseOnEscape
    property var service: typeof castState !== "undefined" ? castState : null
    // Anything that closes this without Allow is a no. Allow has already taken the request by then.
    onClosed: if (service) service.declinePairing()
    Connections {
        target: root.service
        function onChanged() { if (!root.service.pairingPending) root.close() }
    }
    contentItem: ColumnLayout {
        spacing: 16
        Label {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.foreground
            text: "A device on your network wants to connect to Tubify. It will be able to see and control what's playing."
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12
            text: "Only allow this if you just chose Tubify from Cast in the YouTube Music app."
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8
            ThemeActionButton { objectName: "castPairingDecline"; text: "Don't Allow"; onClicked: root.close() }
            ThemeActionButton { objectName: "castPairingAllow"; text: "Allow"; onClicked: root.service.approvePairing() }
        }
    }
}
