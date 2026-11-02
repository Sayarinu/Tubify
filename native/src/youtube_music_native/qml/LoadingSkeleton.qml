import QtQuick
import "Theme.js" as Theme

// Placeholder shapes shown while a page loads, so content fades into a familiar layout.
Item {
    id: root
    objectName: "loadingSkeleton"
    property string mode: "rows"   // "rows", "shelves" or "grid"
    property real gutter: 24
    clip: true
    Accessible.role: Accessible.Indicator
    Accessible.name: "Loading"
    readonly property color block: themeState.surface

    SequentialAnimation on opacity {
        running: root.visible && !appState.reducedMotion
        loops: Animation.Infinite
        alwaysRunToEnd: false
        NumberAnimation { from: 1; to: 0.5; duration: 750; easing.type: Easing.InOutSine }
        NumberAnimation { from: 0.5; to: 1; duration: 750; easing.type: Easing.InOutSine }
    }

    Column {
        x: root.gutter; y: 32; width: root.width - 2 * root.gutter; spacing: 18
        visible: root.mode === "rows"
        Rectangle { width: Math.min(parent.width, 320); height: 30; radius: 8; color: root.block }
        Repeater {
            model: Math.max(1, Math.ceil(root.height / 64))
            Row {
                spacing: 16
                Rectangle { width: 48; height: 48; radius: 8; color: root.block }
                Column {
                    anchors.verticalCenter: parent.verticalCenter; spacing: 8
                    Rectangle { width: Math.min(280, root.width * 0.4); height: 12; radius: 6; color: root.block }
                    Rectangle { width: Math.min(180, root.width * 0.25); height: 10; radius: 5; color: root.block; opacity: 0.7 }
                }
            }
        }
    }
    Column {
        x: root.gutter; y: 32; width: root.width - 2 * root.gutter; spacing: 40
        visible: root.mode === "shelves" || root.mode === "grid"
        Repeater {
            model: root.mode === "grid" ? 1 : Math.max(1, Math.ceil(root.height / (Theme.cardHeight + 80)))
            Column {
                spacing: 16
                Rectangle { width: 220; height: 26; radius: 8; color: root.block }
                Flow {
                    width: root.width - 2 * root.gutter; spacing: 24
                    height: root.mode === "grid" ? root.height : Theme.cardHeight
                    clip: true
                    Repeater {
                        model: Math.max(1, Math.ceil((root.width - 2 * root.gutter) / (Theme.cardWidth + 24))) * (root.mode === "grid" ? 3 : 1)
                        Column {
                            spacing: 12
                            Rectangle { width: Theme.cardWidth; height: Theme.cardWidth; radius: 12; color: root.block }
                            Rectangle { width: Theme.cardWidth * 0.7; height: 12; radius: 6; color: root.block }
                            Rectangle { width: Theme.cardWidth * 0.45; height: 10; radius: 5; color: root.block; opacity: 0.7 }
                        }
                    }
                }
            }
        }
    }
}
