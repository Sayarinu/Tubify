import QtQuick

// Loads the next page once a list comes within a screen of its end. It watches the list's size as
// well as its position, so a first page too short to scroll keeps loading until the list can.
QtObject {
    id: root
    property Flickable view: null
    property var cursor: null
    property bool active: true
    readonly property bool wanted: {
        if (!active || !view || !view.visible || cursor === undefined || cursor === null) return false
        // A failed page waits for Retry instead of asking again forever.
        if (catalogState.busy || catalogState.revalidating || catalogState.error) return false
        return view.contentY + 2 * view.height >= view.originY + view.contentHeight + view.bottomMargin
    }
    function load() { if (wanted) catalogState.more() }
    onWantedChanged: if (wanted) Qt.callLater(load)
    Component.onCompleted: load()
}
