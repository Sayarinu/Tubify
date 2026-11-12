import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// Left/right arrows over a horizontal list; shown only when content is cut off on that side.
Item {
    id: root
    required property Flickable target
    property real step: target.width * 0.7
    readonly property bool overflowing: target.contentWidth > target.width + 1
    anchors.fill: target
    z: 2

    function scrollBy(delta) {
        var minimum = target.originX
        var maximum = target.originX + Math.max(0, target.contentWidth - target.width)
        var destination = Math.max(minimum, Math.min(maximum, (glide.running ? glide.to : target.contentX) + delta))
        glide.stop()
        if (appState.reducedMotion) { target.contentX = destination; return }
        glide.from = target.contentX
        glide.to = destination
        glide.start()
    }
    NumberAnimation { id: glide; target: root.target; property: "contentX"; duration: Theme.motionSlow + 80; easing.type: Easing.OutCubic }

    Repeater {
        model: [{ side: -1, icon: "left", tip: "Scroll left" }, { side: 1, icon: "right", tip: "Scroll right" }]
        delegate: Item {
            required property var modelData
            readonly property bool shown: root.overflowing && (modelData.side < 0 ? !root.target.atXBeginning : !root.target.atXEnd)
            width: Math.min(32, root.height); height: root.height
            x: modelData.side < 0 ? 0 : root.width - width
            opacity: shown ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionFast } }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width; height: width
                outlined: true; iconName: modelData.icon; tip: modelData.tip
                background: Rectangle { radius: width / 2; color: parent.hovered ? themeState.hover : themeState.surface; border.width: 1; border.color: themeState.border }
                onClicked: root.scrollBy(modelData.side * root.step)
            }
        }
    }
}
