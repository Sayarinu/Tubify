import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

Item {
    id: root
    objectName: "shelf"
    required property var section
    property var profile: ({})
    property bool compact: section.layout === "rows"
    // A mixed shelf shows its songs as rows, then its albums, playlists and artists as cards.
    readonly property var songItems: (section.items || []).filter(item => (item.kind || "song") === "song")
    readonly property var collectionItems: (section.items || []).filter(item => (item.kind || "song") !== "song")
    readonly property bool mixed: !compact && section.layout === "mixed" && songItems.length > 0 && collectionItems.length > 0
    // Rows fill the first strip of a rows or mixed shelf; cards fill it otherwise.
    readonly property bool rowMode: compact || mixed
    readonly property var rowItems: mixed ? songItems : (section.items || [])
    property bool alwaysShowMore: false
    property string moreLabel: "More"
    // A positive rowLimit shows the first songs as one full-width list (an artist's Top songs).
    property int rowLimit: 0
    readonly property int rowCount: rowLimit > 0 ? Math.min(rowLimit, rowItems.length) : rowItems.length
    readonly property int rowsPerColumn: rowLimit > 0 ? rowLimit : mixed ? Math.max(1, Math.min(4, rowCount)) : 4
    readonly property real rowsHeight: rowLimit > 0 ? rowCount * 64 : rowsPerColumn * 64
    // Show all opens the full list (the artist's songs playlist) instead of playing the shelf.
    readonly property bool showAll: compact && !!section.showAll
    // Paging controls only make sense when part of the shelf is cut off.
    readonly property bool overflowing: cards.contentWidth > cards.width + 1
    readonly property real itemWidth: compact && rowLimit > 0 ? cards.width : rowMode ? Math.min(436, Math.max(280, cards.width * 0.53)) : Theme.cardWidth
    // Page by whole items and glide there, so arrows never land mid-card.
    function page(direction) {
        var stride = itemWidth + cards.spacing
        var step = Math.max(1, Math.floor((cards.width + cards.spacing) / stride)) * stride
        var minimum = cards.originX
        var maximum = cards.originX + Math.max(0, cards.contentWidth - cards.width)
        var start = glide.running ? glide.to : cards.contentX
        var destination = Math.max(minimum, Math.min(maximum, minimum + Math.round((start - minimum) / stride) * stride + direction * step))
        glide.stop()
        if (appState.reducedMotion) { cards.contentX = destination; return }
        glide.from = cards.contentX
        glide.to = destination
        glide.start()
    }
    NumberAnimation { id: glide; target: cards; property: "contentX"; duration: Theme.motionSlow + 120; easing.type: Easing.OutCubic }
    signal activated(var item)
    signal playRequested(var item)
    signal moreRequested()
    signal playAllRequested()
    implicitHeight: heading.height + (rowMode ? 4 : 16) + (rowMode ? rowsHeight : Theme.cardHeight) + (mixed ? 32 + Theme.cardHeight : 0)
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
            Text { width: parent.width; visible: !!root.section.subtitle; text: root.section.subtitle || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14 }
            Text { width: parent.width; text: root.section.title || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.foreground; font.bold: true; font.pixelSize: 24 }
        }
    }
    Row {
        id: actions
        anchors.right: parent.right; anchors.verticalCenter: heading.verticalCenter; spacing: 16
        ThemeActionButton {
            id: more
            objectName: "shelfPrimaryAction"
            text: root.showAll ? "Show all" : root.rowMode ? "Play All" : root.moreLabel
            visible: root.rowMode || root.overflowing || root.alwaysShowMore
            implicitHeight: 36
            onClicked: root.rowMode && !root.showAll ? root.playAllRequested() : root.moreRequested()
        }
        IconButton { objectName: "shelfPrevious"; visible: root.overflowing; iconName: "left"; tip: "Previous Items"; outlined: true; width: 36; height: 36; enabled: !cards.atXBeginning; onClicked: root.page(-1) }
        IconButton { objectName: "shelfNext"; visible: root.overflowing; iconName: "right"; tip: "More Items"; outlined: true; width: 36; height: 36; enabled: !cards.atXEnd; onClicked: root.page(1) }
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: cards
        anchors.top: heading.bottom; anchors.topMargin: root.rowMode ? 4 : 16
        width: parent.width; height: root.rowMode ? root.rowsHeight : Theme.cardHeight
        clip: true; orientation: ListView.Horizontal; spacing: root.rowMode ? 28 : 24
        model: root.rowMode ? Math.ceil(root.rowCount / root.rowsPerColumn) : (root.section.items || [])
        boundsBehavior: Flickable.StopAtBounds
        delegate: Loader {
            required property int index
            property var media: root.rowMode ? ({}) : root.section.items[index]
            width: root.itemWidth
            height: cards.height
            sourceComponent: root.rowMode ? rowColumn : mediaCard
            Component {
                id: rowColumn
                Column {
                    property int group: parent.index
                    width: parent.width
                    Repeater {
                        model: Math.min(root.rowsPerColumn, root.rowCount - parent.group * root.rowsPerColumn)
                        delegate: SongRow {
                            required property int index
                            width: parent.width
                            media: root.rowItems[parent.group * root.rowsPerColumn + index]
                            number: (root.section.title || "").toLowerCase() === "top songs" ? parent.group * root.rowsPerColumn + index + 1 : 0
                            onActivated: item => root.activated(item)
                        }
                    }
                }
            }
            Component { id: mediaCard; MediaCard { width: parent.width; media: parent.media; onActivated: item => root.activated(item); onPlayRequested: item => root.playRequested(item) } }
        }
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: collections
        objectName: "shelfCollections"
        visible: root.mixed
        anchors.top: cards.bottom; anchors.topMargin: 32
        width: parent.width; height: root.mixed ? Theme.cardHeight : 0
        clip: true; orientation: ListView.Horizontal; spacing: 24
        boundsBehavior: Flickable.StopAtBounds
        model: root.mixed ? root.collectionItems : []
        delegate: MediaCard {
            required property var modelData
            width: Theme.cardWidth; height: collections.height
            media: modelData
            onActivated: item => root.activated(item)
            onPlayRequested: item => root.playRequested(item)
        }
    }
    // The heading arrows page the songs, so the cards below page with their own edge arrows.
    EdgeArrows { target: collections; visible: root.mixed; step: Math.max(Theme.cardWidth + 24, Math.floor(collections.width / (Theme.cardWidth + 24)) * (Theme.cardWidth + 24)) }
}
