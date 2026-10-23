import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    property alias scrollView: optionsScroll
    objectName: "desktopSettings"
    title: "Desktop"
    modal: true
    focus: true
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
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            CheckBox { objectName: "autostartOption"; text: "Start at login"; enabled: lifecycleState.startupAvailable; checked: lifecycleState.autostart; onToggled: lifecycleState.setAutostart(checked) }
            CheckBox { objectName: "startMinimizedOption"; text: "Start minimized"; checked: lifecycleState.startMinimized; onToggled: lifecycleState.setStartMinimized(checked) }
            Text { Layout.fillWidth: true; text: "Minimized startup keeps the app reachable from your taskbar or Dock. Restored music stays paused."; color: themeState.secondary; wrapMode: Text.Wrap }
            CheckBox { objectName: "closeToTrayOption"; text: "Close to tray"; checked: lifecycleState.closeToTray; onToggled: lifecycleState.setCloseToTray(checked) }
            Text { Layout.fillWidth: true; text: "Closing exits by default. With this option, closing hides the window only while the tray is available. Quit always exits."; color: themeState.secondary; wrapMode: Text.Wrap }
            CheckBox { objectName: "trackNotificationsOption"; text: "Notify when the track changes"; checked: lifecycleState.trackNotifications; onToggled: lifecycleState.setTrackNotifications(checked) }
            Text { Layout.fillWidth: true; text: "Notifications need an enabled tray and follow your desktop notification settings."; color: themeState.secondary; wrapMode: Text.Wrap }
            Text { objectName: "desktopCapability"; Layout.fillWidth: true; text: lifecycleState.capability; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
            Text { objectName: "desktopError"; Layout.fillWidth: true; text: lifecycleState.error; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
            ThemeActionButton { text: "Retry login startup"; visible: lifecycleState.startupError; onClicked: lifecycleState.retryAutostart() }
            RowLayout {
                Layout.fillWidth: true
                visible: !!lifecycleState.status
                Text { objectName: "desktopStatus"; Layout.fillWidth: true; text: lifecycleState.status; color: themeState.secondary; wrapMode: Text.Wrap }
                IconButton { implicitWidth: 32; implicitHeight: 32; iconName: "close"; tip: "Dismiss status"; onClicked: lifecycleState.dismissStatus() }
            }
        }
    }
}
