import QtQuick
import QtQuick.Controls

Button {
    id: root
    property bool primary: false
    property string disabledReason: ""
    implicitHeight: 38
    leftPadding: 16
    rightPadding: 16
    font.pixelSize: 13
    ToolTip.text: !root.enabled ? root.disabledReason : ""
    ToolTip.visible: !root.enabled && root.disabledReason.length > 0 && disabledHover.hovered
    ToolTip.delay: 450

    HoverHandler {
        id: disabledHover
        objectName: "disabledActionHover"
        enabled: !root.enabled && root.disabledReason.length > 0
    }

    contentItem: Text {
        text: root.text
        color: !root.enabled ? themeState.secondary : root.primary ? themeState.onAccent : themeState.foreground
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 19
        color: !root.enabled ? themeState.surface
            : root.primary ? (root.down ? themeState.accent : root.hovered ? themeState.accentHover : themeState.accent)
            : root.down ? themeState.border : root.hovered ? themeState.hover : themeState.surface
        border.width: root.visualFocus ? 2 : root.primary ? 0 : 1
        border.color: root.visualFocus ? themeState.accent : themeState.border
    }
}
