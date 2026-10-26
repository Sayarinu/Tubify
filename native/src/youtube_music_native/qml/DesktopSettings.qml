import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    property alias scrollView: optionsScroll
    objectName: "desktopSettings"
    title: "Desktop"
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
            SettingsCheckBox { objectName: "trayEnabledOption"; text: "Enable Tray Player"; checked: trayState.enabled; onToggled: trayState.setEnabled(checked) }
            Text { Layout.fillWidth: true; text: "Control music from the system tray. Pin the player to keep it open, or drag its title bar to move it."; color: themeState.secondary; wrapMode: Text.Wrap }
            ThemeActionButton { text: "Open Tray Player"; enabled: trayState.active; onClicked: { root.close(); trayState.showPlayer() } }
            Text { Layout.fillWidth: true; text: trayState.error; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
            ThemeActionButton { text: "Retry Tray"; visible: !!trayState.error; onClicked: trayState.setEnabled(true) }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            SettingsCheckBox { objectName: "autostartOption"; text: "Start at Login"; enabled: lifecycleState.startupAvailable; checked: lifecycleState.autostart; onToggled: lifecycleState.setAutostart(checked) }
            SettingsCheckBox { objectName: "startMinimizedOption"; text: "Start Minimized"; checked: lifecycleState.startMinimized; onToggled: lifecycleState.setStartMinimized(checked) }
            Text { Layout.fillWidth: true; text: "Minimized startup keeps the app reachable from your taskbar or Dock. Restored music stays paused."; color: themeState.secondary; wrapMode: Text.Wrap }
            SettingsCheckBox { objectName: "closeToTrayOption"; text: "Close to Tray"; checked: lifecycleState.closeToTray; onToggled: lifecycleState.setCloseToTray(checked) }
            Text { Layout.fillWidth: true; text: "Closing exits by default. With this option, closing hides the window only while the tray is available. Quit always exits."; color: themeState.secondary; wrapMode: Text.Wrap }
            SettingsCheckBox { objectName: "trackNotificationsOption"; text: "Track Notifications"; checked: lifecycleState.trackNotifications; onToggled: lifecycleState.setTrackNotifications(checked) }
            Text { Layout.fillWidth: true; text: "Notifications need an enabled tray and follow your desktop notification settings."; color: themeState.secondary; wrapMode: Text.Wrap }
            Text { objectName: "desktopCapability"; Layout.fillWidth: true; text: lifecycleState.capability; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
            Text { objectName: "desktopError"; Layout.fillWidth: true; text: lifecycleState.error; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
            ThemeActionButton { text: "Retry Login Startup"; visible: lifecycleState.startupError; onClicked: lifecycleState.retryAutostart() }
            RowLayout {
                Layout.fillWidth: true
                visible: !!lifecycleState.status
                Text { objectName: "desktopStatus"; Layout.fillWidth: true; text: lifecycleState.status; color: themeState.secondary; wrapMode: Text.Wrap }
                IconButton { implicitWidth: 32; implicitHeight: 32; iconName: "close"; tip: "Dismiss Status"; onClicked: lifecycleState.dismissStatus() }
            }
        }
    }
}
