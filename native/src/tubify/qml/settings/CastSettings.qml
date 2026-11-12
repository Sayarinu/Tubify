import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../Theme.js" as Theme

SettingsPage {
    id: root
    property alias scrollView: scroll
    objectName: "castSettingsDialog"
    title: "Mobile Sync"
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        implicitHeight: Math.min(body.implicitHeight, Overlay.overlay ? Overlay.overlay.height - 160 : 480)
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Theme.spacingMedium
            SettingsCheckBox { objectName: "castEnabledOption"; text: "Enable Mobile Sync"; checked: castState.enabled; onClicked: castState.setEnabled(checked) }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary
                text: "Experimental. Tubify shows up in the Cast menu of the YouTube Music app on phones connected to the same network. The phone can then play, pause, skip, seek and change the volume. This uses an unofficial YouTube connection that may stop working when YouTube changes it."
            }
            Label { text: "Device Name"; color: themeState.foreground }
            ThemedTextField {
                id: deviceName
                objectName: "castDeviceName"
                Layout.fillWidth: true
                text: castState.name
                maximumLength: 60
                Accessible.name: "Mobile Sync device name"
                onEditingFinished: castState.setName(text)
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: Theme.textSmall
                text: "Tubify listens on your local network only while this is on. Your computer may ask you to allow Tubify on private networks. No Google sign-in is shared with phones."
            }
            ThemeActionButton {
                objectName: "castForgetPairings"
                text: "Forget Paired Phones"
                Accessible.description: "Disconnects every paired phone. Each one needs approving again."
                onClicked: castState.forgetPairings()
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: Theme.textSmall
                text: "Turning this off stops Tubify listening on your network. Paired phones stay paired until you choose Forget Paired Phones."
            }
            Label { objectName: "castStatus"; Layout.fillWidth: true; wrapMode: Text.Wrap; text: castState.status; color: themeState.foreground }
        }
    }
}
