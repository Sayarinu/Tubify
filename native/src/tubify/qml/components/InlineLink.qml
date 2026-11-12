import QtQuick

// Secondary metadata text, such as an artist or album name, that opens something.
// It brightens and underlines on hover or focus. TextLink is the padded button version.
Text {
    id: root
    property bool linked: true
    readonly property bool hovered: area.containsMouse
    signal activated()
    textFormat: Text.PlainText
    color: hovered || activeFocus ? themeState.foreground : themeState.secondary
    font.underline: linked && (hovered || activeFocus)
    activeFocusOnTab: linked
    Accessible.role: linked ? Accessible.Link : Accessible.StaticText
    Accessible.name: text
    Accessible.onPressAction: if (linked) activated()
    Keys.onReturnPressed: if (linked) activated()
    Keys.onSpacePressed: if (linked) activated()
    MouseArea {
        id: area
        anchors.fill: parent; z: 2
        enabled: root.linked; hoverEnabled: enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.activated()
    }
}
