import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Slider {
    id: root
    property color trackColor: Theme.border
    background: Rectangle {
        x: root.leftPadding; y: root.topPadding + root.availableHeight / 2 - 2
        width: root.availableWidth; height: 4; radius: 2; color: root.trackColor
        Rectangle { width: root.visualPosition * parent.width; height: parent.height; radius: 2; color: Theme.accent }
    }
    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: 12; height: 12; radius: 6; color: root.enabled ? Theme.accent : Theme.muted
        border.width: root.visualFocus ? 2 : 0; border.color: Theme.foreground
    }
}
