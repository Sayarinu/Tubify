import QtQuick
import QtQuick.Controls

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
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: themeState.accent; visible: root.current === tab.modelData }
            }
        }
    }
    Rectangle { y: 52; height: 1; width: parent.width; color: themeState.border }
}
