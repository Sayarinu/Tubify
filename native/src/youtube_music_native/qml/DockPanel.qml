import QtQuick
import "Theme.js" as Theme

// A side dock that slides in from the right edge when opened and back out when closed.
// Tab switches and responsive re-layouts show or hide it at once; only opening or closing the panel slides.
Rectangle {
    id: root
    // Whether the dock occupies its place in the layout.
    required property bool shown
    // "Queue" or "Lyrics": whose open intent decides whether a visibility change slides.
    required property string dock
    // Read from appState on demand: the dock tab can change before the open flag notifies.
    function isOpen() { return dock === "Queue" ? appState.queueOpen : appState.lyricsOpen }
    // Keeps the dock drawn while it slides out over the page that has already taken its space.
    readonly property bool leaving: slide.running && !shown
    property bool seenOpen: false
    Component.onCompleted: seenOpen = isOpen()
    visible: shown || leaving
    enabled: shown
    color: themeState.background
    transform: Translate { id: shift }
    onShownChanged: {
        var open = isOpen()
        var animate = open !== seenOpen && !appState.reducedMotion
        seenOpen = open
        var reversing = slide.running
        slide.stop()
        if (!animate) {
            shift.x = 0
            opacity = 1
            return
        }
        // A fresh open starts off the right edge, faded; a reversal continues from where the dock is.
        if (shown && !reversing) { shift.x = width; opacity = 0 }
        slideX.to = shown ? 0 : width
        slideX.easing.type = shown ? Easing.OutCubic : Easing.InCubic
        // Closing stays opaque: a dock beside it has already moved underneath, and fading would blend the two.
        fade.to = 1
        slide.start()
    }
    // Open intent can change without moving the dock (closing a hidden tab); record it after any slide decision.
    Connections {
        target: appState
        function onQueueOpenChanged() { Qt.callLater(root.recordIntent) }
        function onLyricsOpenChanged() { Qt.callLater(root.recordIntent) }
    }
    function recordIntent() { seenOpen = isOpen() }
    ParallelAnimation {
        id: slide
        NumberAnimation { id: slideX; target: shift; property: "x"; duration: Theme.motionSlow }
        NumberAnimation { id: fade; target: root; property: "opacity"; duration: Theme.motionSlow; easing.type: Easing.OutCubic }
    }
}
