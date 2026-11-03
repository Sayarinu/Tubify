import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

// Text that opens something (an artist, album or more text): underlined and highlighted on hover.
Button {
    id: root
    property color textColor: themeState.foreground
    property int pixelSize: Theme.textBody
    property bool bold: false
    property int horizontalAlignment: Text.AlignHCenter
    property int maximumLineCount: 1
    property bool underlineOnHover: true
    flat: true
    padding: 4
    Accessible.role: enabled ? Accessible.Link : Accessible.StaticText
    contentItem: Text {
        text: root.text
        textFormat: Text.PlainText
        color: root.textColor
        font.pixelSize: root.pixelSize
        font.bold: root.bold
        font.underline: root.underlineOnHover && root.hovered && root.enabled
        horizontalAlignment: root.horizontalAlignment
        verticalAlignment: Text.AlignVCenter
        wrapMode: root.maximumLineCount > 1 ? Text.Wrap : Text.NoWrap
        maximumLineCount: root.maximumLineCount
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.hovered && root.enabled ? themeState.hover : "transparent"
        border.width: root.visualFocus ? 2 : 0
        border.color: themeState.accent
    }
}
