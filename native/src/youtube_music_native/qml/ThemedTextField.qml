import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

TextField {
    id: root
    implicitHeight: 40
    leftPadding: 12
    rightPadding: 12
    color: themeState.foreground
    placeholderTextColor: themeState.secondary
    selectionColor: themeState.accent
    selectedTextColor: themeState.onAccent
    selectByMouse: true
    font.family: Theme.bodyFont
    font.pixelSize: 14
    background: Rectangle { radius: 8; color: themeState.hover; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? themeState.accent : themeState.border }
}
