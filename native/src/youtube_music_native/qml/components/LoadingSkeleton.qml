import QtQuick
import "../Theme.js" as Theme

// Placeholder shapes shown beneath a list's real header while its first page loads.
// Use it as (part of) the ListView/GridView footer and pass the view, so the skeleton fills
// the space left under the header without covering it.
Item {
    id: root
    objectName: "loadingSkeleton"
    property Item view: null
    property string mode: "rows"   // "rows", "shelves" or "grid"
    // Loading with nothing to show yet; refreshes and further pages keep their content instead.
    property bool active: catalogState.busy && !populated
    readonly property bool populated: !!view && view.count > 0
    // Horizontal inset of the content inside the footer; views that already apply the page
    // gutter through their anchors leave this at 0.
    property real gutter: 0
    property real rightGutter: gutter
    property bool showTitle: false
    // Rows match SongRow: 64px tall, cover inset from the row edge, text after the cover.
    property real rowHeight: 64
    property real coverInset: 8
    property real coverSize: 48
    property real textInset: coverSize > 0 ? coverInset + coverSize + 16 : coverInset
    property bool showDuration: false
    // Shelves match Shelf.qml inside a list using shelfSpacing between delegates.
    property real headingHeight: 40
    property real shelfSpacing: 80
    // Grids match the page's GridView cells; each card fills its cell less the 24px gap.
    property real cellWidth: Theme.cardWidth + 24
    property real cellHeight: Theme.cardHeight + 24
    property int columns: Math.max(1, Math.floor(contentWidth / cellWidth))
    readonly property real contentWidth: Math.max(0, width - gutter - rightGutter)
    readonly property real titleHeight: showTitle ? 54 : 0
    // Fill what the viewport has left under the header, so the skeleton never adds scrolling.
    readonly property real available: view ? view.height - view.topMargin - view.bottomMargin - (view.headerItem ? view.headerItem.height : 0) : 0
    readonly property real minimumHeight: titleHeight + (mode === "rows" ? rowHeight : mode === "grid" ? cellHeight : headingHeight + 16 + Theme.cardHeight)
    readonly property color block: themeState.surface
    readonly property int fadeDuration: Theme.duration(Theme.motionMedium, appState.reducedMotion)
    // Height follows loading state, never effective visibility: hiding the page (for example
    // behind the expanded player) must not shrink the list and clamp its scroll position.
    // Once rows arrive the footer collapses at once so a populated list keeps its contentY;
    // the fade-out only plays when loading ends with nothing to show.
    readonly property bool holding: active || !populated && opacity > 0
    implicitHeight: holding ? Math.max(minimumHeight, available) : 0
    visible: holding
    clip: true
    Accessible.role: Accessible.Indicator
    Accessible.name: "Loading"
    Accessible.ignored: !active

    // Fade out once loading ends; the header above is never touched.
    opacity: active ? 1 : 0
    Behavior on opacity { OpacityAnimator { duration: root.fadeDuration } }

    Item {
        id: shapes
        x: root.gutter; width: root.contentWidth; height: root.height
        SequentialAnimation on opacity {
            running: root.visible && !appState.reducedMotion
            loops: Animation.Infinite
            alwaysRunToEnd: false
            NumberAnimation { from: 1; to: 0.5; duration: 750; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.5; to: 1; duration: 750; easing.type: Easing.InOutSine }
        }

        Rectangle { visible: root.showTitle; y: 12; width: Math.min(parent.width, 320); height: 30; radius: 8; color: root.block }

        Column {
            y: root.titleHeight; width: parent.width; spacing: 0
            visible: root.mode === "rows"
            Repeater {
                model: root.mode === "rows" ? Math.max(1, Math.ceil((root.height - root.titleHeight) / root.rowHeight)) : 0
                Item {
                    width: parent.width; height: root.rowHeight
                    Rectangle { x: root.coverInset; anchors.verticalCenter: parent.verticalCenter; width: root.coverSize; height: width; radius: 6; visible: root.coverSize > 0; color: root.block }
                    Column {
                        x: root.textInset; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                        Rectangle { width: Math.max(0, Math.min(280, root.contentWidth * 0.4)); height: 12; radius: 6; color: root.block }
                        Rectangle { width: Math.max(0, Math.min(180, root.contentWidth * 0.25)); height: 10; radius: 5; color: root.block; opacity: 0.7 }
                    }
                    Rectangle { visible: root.showDuration; anchors.right: parent.right; anchors.rightMargin: 56; anchors.verticalCenter: parent.verticalCenter; width: 32; height: 10; radius: 5; color: root.block; opacity: 0.7 }
                }
            }
        }

        Column {
            y: root.titleHeight; width: parent.width; spacing: root.shelfSpacing
            visible: root.mode === "shelves"
            Repeater {
                model: root.mode === "shelves" ? Math.max(1, Math.ceil((root.height - root.titleHeight + root.shelfSpacing) / (root.headingHeight + 16 + Theme.cardHeight + root.shelfSpacing))) : 0
                Column {
                    width: parent.width; spacing: 16
                    Item { width: parent.width; height: root.headingHeight; Rectangle { anchors.verticalCenter: parent.verticalCenter; width: Math.min(parent.width, 220); height: 26; radius: 8; color: root.block } }
                    Row {
                        width: parent.width; height: Theme.cardHeight; spacing: 24; clip: true
                        Repeater {
                            model: Math.max(1, Math.ceil((root.contentWidth + 24) / (Theme.cardWidth + 24)))
                            SkeletonCard { width: Theme.cardWidth; height: Theme.cardHeight; block: root.block }
                        }
                    }
                }
            }
        }

        Grid {
            y: root.titleHeight; columns: root.columns
            visible: root.mode === "grid"
            Repeater {
                model: root.mode === "grid" ? root.columns * Math.max(1, Math.ceil((root.height - root.titleHeight) / root.cellHeight)) : 0
                Item { width: root.cellWidth; height: root.cellHeight; SkeletonCard { width: parent.width - 24; height: parent.height - 24; block: root.block } }
            }
        }
    }

    // Same frame as MediaCard: rounded card, inset square cover, two lines of text.
    component SkeletonCard: Item {
        id: card
        property color block
        Rectangle { anchors.fill: parent; radius: 10; color: card.block; opacity: 0.45 }
        Rectangle { id: art; x: 16; y: 16; width: parent.width - 32; height: width; radius: 8; color: card.block }
        Rectangle { x: 16; y: art.y + art.height + 14; width: art.width * 0.7; height: 12; radius: 6; color: card.block }
        Rectangle { x: 16; y: art.y + art.height + 36; width: art.width * 0.45; height: 10; radius: 5; color: card.block; opacity: 0.7 }
    }
}
