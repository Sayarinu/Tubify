import QtQuick

// A small count on a button or tab, such as how many downloads failed; hidden at zero.
// Screen readers hear the count through the owner's accessible name instead.
Rectangle {
    id: root
    property int count: 0
    visible: count > 0
    height: 18
    width: Math.max(height, label.implicitWidth + 10)
    radius: height / 2
    color: themeState.accent
    Accessible.ignored: true
    Text {
        id: label
        anchors.centerIn: parent
        text: root.count > 99 ? "99+" : String(root.count)
        textFormat: Text.PlainText
        color: themeState.onAccent
        font.pixelSize: 11
        font.bold: true
    }
}
