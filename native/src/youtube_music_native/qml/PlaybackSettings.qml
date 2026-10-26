import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

SettingsPage {
    id: root
    property alias scrollView: optionsScroll
    objectName: "playbackSettings"
    title: "Playback"
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
        Text { text: "Sleep Timer"; color: themeState.foreground; font.bold: true; font.pixelSize: 16 }
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
            text: "Cancel Timer"
            visible: playbackOptions.sleepRemaining > 0
            onClicked: playbackOptions.cancelSleep()
        }
        SettingsCheckBox {
            objectName: "nonlinearVolumeOption"
            text: "Finer Volume at Low Levels"
            checked: playbackOptions.nonlinearVolume
            onToggled: playbackOptions.setNonlinearVolume(checked)
        }
        SettingsCheckBox {
            objectName: "speakerFillOption"
            text: "Fill Surround Speakers from Stereo"
            checked: playbackOptions.speakerFill
            enabled: !!playerState.audioOptions.available || checked
            onToggled: playbackOptions.setSpeakerFill(checked)
        }
        Text {
            Layout.fillWidth: true
            text: playerState.audioOptions.message || "Play a stereo song on a 5.1 or 7.1 output to use speaker fill."
            color: themeState.secondary; font.pixelSize: 12; wrapMode: Text.Wrap
            Accessible.role: Accessible.StaticText
        }
        ThemeActionButton {
            objectName: "retrySpeakerFill"
            visible: !!playerState.audioOptions.failed
            text: "Retry Speaker Fill"
            onClicked: playerState.retrySpeakerFill()
        }
        SettingsCheckBox {
            objectName: "skipDislikedOption"
            text: "Skip Disliked Songs"
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
}
