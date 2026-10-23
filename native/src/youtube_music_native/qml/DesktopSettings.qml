import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    property alias scrollView: optionsScroll
    objectName: "desktopSettings"
    title: "Desktop"
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(480, Overlay.overlay.width - 32) : 480
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
        CheckBox { objectName: "trayEnabledOption"; text: "Enable tray player"; checked: trayState.enabled; onToggled: trayState.setEnabled(checked) }
        Text { Layout.fillWidth: true; text: "Control music from the system tray. Pin the player to keep it open, or drag its title bar to move it."; color: themeState.secondary; wrapMode: Text.Wrap }
        ThemeActionButton { text: "Open tray player"; enabled: trayState.active; onClicked: { root.close(); trayState.showPlayer() } }
        Text { Layout.fillWidth: true; text: trayState.error; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
        ThemeActionButton { text: "Retry tray"; visible: !!trayState.error; onClicked: trayState.setEnabled(true) }
    }
    }
}
