import QtQuick
import QtQuick.Controls
import "../components"

// Library / Downloads switch at the top of both panes, with an accent underline on the current tab.
Item {
    id: root
    // "Library", "Downloads" or "Local Music".
    required property string current
    height: 53
    Row {
        height: 52
        spacing: 24
        Repeater {
            model: ["Library", "Downloads", "Local Music"]
            Button {
                id: tab
                required property string modelData
                text: modelData
                flat: true
                height: parent.height
                palette.windowText: root.current === modelData ? themeState.foreground : themeState.secondary
                onClicked: if (root.current !== modelData) modelData === "Library" ? libraryState.select("Playlists") : appState.navigate(modelData)
                readonly property int failed: modelData === "Downloads" ? downloadsState.retryableCount : 0
                Accessible.name: failed > 0 ? text + ", " + failed + " failed" : text
                rightPadding: failed > 0 ? badge.width + 14 : leftPadding
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: themeState.accent; visible: root.current === tab.modelData }
                // How many downloads failed, beside the Downloads tab's name.
                CountBadge { id: badge; objectName: "downloadsTabBadge"; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; count: tab.failed }
            }
        }
    }
    Rectangle { y: 52; height: 1; width: parent.width; color: themeState.border }
}
