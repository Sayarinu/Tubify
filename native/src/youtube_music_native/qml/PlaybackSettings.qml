import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Dialog {
    id: root
    objectName: "playbackSettings"
    title: "Playback"
    modal: true
    anchors.centerIn: parent
    width: Math.min(480, parent.width - 32)
    standardButtons: Dialog.Close
    background: Rectangle { color: themeState.background; border.color: themeState.border; radius: 12 }
    contentItem: ColumnLayout {
        spacing: 16
        Text { text: "Sleep timer"; color: themeState.foreground; font.bold: true; font.pixelSize: 16 }
        Text {
            Layout.fillWidth: true
            text: playbackOptions.sleepRemaining > 0 ? "Pause in " + Theme.timeLabel(playbackOptions.sleepRemaining) : playbackOptions.sleepStatus || "Pause playback after a set time."
            color: themeState.secondary; wrapMode: Text.Wrap
            Accessible.role: Accessible.StaticText
        }
        Flow {
            Layout.fillWidth: true
            Layout.preferredHeight: childrenRect.height
            spacing: 8
            Repeater {
                model: [5, 10, 15, 30, 45, 60]
                ThemeActionButton {
                    required property int modelData
                    objectName: "sleepPreset-" + modelData
                    text: modelData + " min"
                    onClicked: playbackOptions.startSleep(modelData)
                }
            }
        }
        ThemeActionButton {
            objectName: "cancelSleep"
            text: "Cancel timer"
            visible: playbackOptions.sleepRemaining > 0
            onClicked: playbackOptions.cancelSleep()
        }
        CheckBox {
            objectName: "nonlinearVolumeOption"
            text: "Finer volume control at low levels"
            checked: playbackOptions.nonlinearVolume
            onToggled: playbackOptions.setNonlinearVolume(checked)
        }
        CheckBox {
            objectName: "skipDislikedOption"
            text: "Skip disliked songs when advancing"
            checked: playbackOptions.skipDisliked
            onToggled: playbackOptions.setSkipDisliked(checked)
        }
        Text {
            Layout.fillWidth: true
            text: "Changing skip behavior leaves the current song playing. Previous remains available."
            color: themeState.secondary; font.pixelSize: 12; wrapMode: Text.Wrap
        }
    }
}
