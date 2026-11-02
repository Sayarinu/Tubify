import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "shelf"
    required property var section
    property var profile: ({})
    property bool compact: section.layout === "rows"
    // Paging controls only make sense when part of the shelf is cut off.
    readonly property bool overflowing: cards.contentWidth > cards.width + 1
    signal activated(var item)
    signal playRequested(var item)
    signal moreRequested()
    signal playAllRequested()
    implicitHeight: heading.height + (compact ? 4 : 16) + (compact ? 256 : Theme.cardHeight)
    Row {
        id: heading
        width: parent.width - actions.width - 24
        spacing: 16
        height: root.section.subtitle ? 56 : 40
        Avatar {
            width: 56; height: 56; visible: !!root.section.subtitle
            source: root.profile.avatar || ""
        }
        Column {
            width: parent.width - (root.section.subtitle ? 72 : 0)
            anchors.verticalCenter: parent.verticalCenter; spacing: 4
            Text { width: parent.width; visible: !!root.section.subtitle; text: root.section.subtitle || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14; font.family: Theme.bodyFont }
            Text { width: parent.width; text: root.section.title || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 24 }
        }
    }
    Row {
        id: actions
        anchors.right: parent.right; anchors.verticalCenter: heading.verticalCenter; spacing: 16
        ThemeActionButton {
            id: more
            objectName: "shelfPrimaryAction"
            text: root.compact ? "Play All" : "More"
            visible: root.compact || root.overflowing
            implicitHeight: 36
            onClicked: root.compact ? root.playAllRequested() : root.moreRequested()
        }
        IconButton { objectName: "shelfPrevious"; visible: root.overflowing; iconName: "left"; tip: "Previous Items"; outlined: true; width: 36; height: 36; enabled: !cards.atXBeginning; onClicked: cards.contentX = Math.max(0, cards.contentX - cards.width) }
        IconButton { objectName: "shelfNext"; visible: root.overflowing; iconName: "right"; tip: "More Items"; outlined: true; width: 36; height: 36; enabled: !cards.atXEnd; onClicked: cards.contentX = Math.min(Math.max(0, cards.contentWidth - cards.width), cards.contentX + cards.width) }
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: cards
        anchors.top: heading.bottom; anchors.topMargin: root.compact ? 4 : 16
        width: parent.width; height: root.compact ? 256 : Theme.cardHeight
        clip: true; orientation: ListView.Horizontal; spacing: root.compact ? 28 : 24
        model: root.compact ? Math.ceil((root.section.items || []).length / 4) : (root.section.items || [])
        boundsBehavior: Flickable.StopAtBounds
        delegate: Loader {
            required property int index
            property var media: root.compact ? ({}) : root.section.items[index]
            width: root.compact ? Math.min(436, Math.max(280, cards.width * 0.53)) : Theme.cardWidth
            height: cards.height
            sourceComponent: root.compact ? rowColumn : mediaCard
            Component {
                id: rowColumn
                Column {
                    property int group: parent.index
                    width: parent.width
                    Repeater {
                        model: Math.min(4, root.section.items.length - parent.group * 4)
                        delegate: SongRow {
                            required property int index
                            width: parent.width
                            media: root.section.items[parent.group * 4 + index]
                            number: (root.section.title || "").toLowerCase() === "top songs" ? parent.group * 4 + index + 1 : 0
                            onActivated: item => root.activated(item)
                        }
                    }
                }
            }
            Component { id: mediaCard; MediaCard { width: parent.width; media: parent.media; onActivated: item => root.activated(item); onPlayRequested: item => root.playRequested(item) } }
        }
    }
}
