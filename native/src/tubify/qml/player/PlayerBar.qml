import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme
import "../components"

Rectangle {
    id: root
    objectName: "playerBar"
    function focusPanelToggle(name) { (name === "Lyrics" ? lyricsToggle : name === "NowPlaying" ? nowPlayingToggle : queueToggle).forceActiveFocus() }
    function focusImmersiveToggle() { immersiveToggle.forceActiveFocus() }
    height: 92
    radius: Theme.radiusMedium
    color: themeState.surface
    border.color: themeState.border
    readonly property bool sleepMenuOpen: sleepMenu.opened
    property bool compact: width < 1100
    readonly property bool dense: width < 850
    Connections {
        target: appState
        function onAppearanceChanged() { titleViewport.updateScroll(); artistViewport.updateScroll() }
    }
    readonly property var primaryArtist: playerState.currentTrack.artists && playerState.currentTrack.artists.length ? playerState.currentTrack.artists[0] : ({})
    // Empty bar space acts like the immersive toggle; it sits below the seek slider (z: -1) and every control.
    MouseArea {
        objectName: "playerBarBackground"
        anchors.fill: parent; z: -2
        enabled: playerState.hasTrack
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: appState.requestAction("expandPlayer")
    }

    Item {
        id: track
        x: 16; width: root.dense ? root.width * 0.28 : Math.min(380, root.width * 0.34); height: parent.height
        Cover { id: cover; anchors.verticalCenter: parent.verticalCenter; width: root.dense ? 48 : 68; height: width; radius: Theme.radiusSmall; source: playerState.currentTrack.thumbnail || ""; mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""; accent: themeState.selected }
        Column {
            x: root.dense ? 56 : 80; width: parent.width - x; anchors.verticalCenter: parent.verticalCenter; spacing: 5
            Item {
                id: titleViewport
                width: parent.width
                height: titleText.implicitHeight
                implicitHeight: height
                clip: true
                function updateScroll() {
                    titleScroll.stop(); titleText.x = 0
                    if (!appState.reducedMotion && titleText.implicitWidth > width) titleScroll.start()
                }
                onWidthChanged: updateScroll()
                Text {
                    id: titleText
                    objectName: "playerTitleText"
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                    width: appState.reducedMotion ? parent.width : implicitWidth; elide: Text.ElideRight; height: parent.height
                    text: playerState.currentTrack.title || "Nothing Playing"
                    textFormat: Text.PlainText; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textBody
                    onImplicitWidthChanged: titleViewport.updateScroll()
                }
                SequentialAnimation {
                    id: titleScroll
                    running: !appState.reducedMotion && titleText.implicitWidth > titleViewport.width
                    loops: Animation.Infinite
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: titleText; property: "x"; to: titleViewport.width - titleText.implicitWidth; duration: Math.max(1200, (titleText.implicitWidth - titleViewport.width) * 35); easing: Easing.Linear }
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: titleText; property: "x"; to: 0; duration: Math.max(1200, (titleText.implicitWidth - titleViewport.width) * 35); easing: Easing.Linear }
                }
            }
            Item {
                id: artistViewport
                function updateScroll() {
                    artistScroll.stop(); artistContent.x = 0
                    if (!appState.reducedMotion && artistContent.width > width) artistScroll.start()
                }
                onWidthChanged: updateScroll()
                width: parent.width; height: 18; clip: true
                Row {
                    id: artistContent
                    x: 0; width: childrenRect.width; height: parent.height
                    onWidthChanged: artistViewport.updateScroll()
                    Repeater {
                        model: playerState.currentTrack.artists || []
                        delegate: Item {
                            required property var modelData
                            required property int index
                            width: artistName.implicitWidth + (separator.visible ? separator.implicitWidth : 0)
                            height: artistViewport.height
                            InlineLink {
                                id: artistName
                                width: implicitWidth; height: parent.height
                                text: modelData.name || ""
                                font.pixelSize: 11
                                linked: !!modelData.name
                                onActivated: {
                                    var artistId = modelData.id || modelData.browseId || modelData.channelId
                                    browseState.openArtist({id: artistId, browseId: modelData.browseId, channelId: modelData.channelId, name: modelData.name})
                                }
                            }
                            Text { id: separator; x: artistName.implicitWidth; visible: index < playerState.currentTrack.artists.length - 1; height: parent.height; text: " • "; color: themeState.secondary; font.pixelSize: 11 }
                        }
                    }
                    Text {
                        visible: !playerState.currentTrack.artists || !playerState.currentTrack.artists.length
                        text: playerState.currentTrack.artist || (playerState.currentTrack.title ? "" : "Choose a Song")
                        textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 11
                    }
                }
                SequentialAnimation {
                    id: artistScroll
                    running: !appState.reducedMotion && artistContent.width > artistViewport.width
                    loops: Animation.Infinite
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: artistContent; property: "x"; to: artistViewport.width - artistContent.width; duration: Math.max(1200, (artistContent.width - artistViewport.width) * 35); easing: Easing.Linear }
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: artistContent; property: "x"; to: 0; duration: Math.max(1200, (artistContent.width - artistViewport.width) * 35); easing: Easing.Linear }
                }
            }
            Item {
                id: albumViewport
                objectName: "playerAlbum"
                width: parent.width; height: 14; clip: true
                InlineLink {
                    width: Math.min(implicitWidth, parent.width); height: parent.height
                    text: typeof playerState.currentTrack.album === "string" ? playerState.currentTrack.album : playerState.currentTrack.album && playerState.currentTrack.album.name || playerState.currentTrack.albumName || playerState.currentTrack.albumTitle || ""
                    elide: Text.ElideRight; font.pixelSize: 11
                    linked: !!(playerState.currentTrack.album && (playerState.currentTrack.album.id || playerState.currentTrack.album.browseId))
                    onActivated: {
                        var album = playerState.currentTrack.album
                        browseState.open({kind: "album", id: album.id || album.browseId, title: album.name})
                    }
                }
            }
        }
    }
    Item {
        anchors.left: track.right; anchors.leftMargin: 8
        anchors.right: tools.left; anchors.rightMargin: 12
        height: parent.height
        AccentSlider {
            id: progress
            objectName: "playbackSeek"
            z: -1
            x: root.dense ? 0 : 46; y: 54; width: parent.width - 2 * x; height: 16
            from: 0; to: 1; value: playerState.progress
            enabled: playerState.hasTrack; Accessible.name: "Playback position"
            onMoved: playerState.seekFraction(value)
            HoverHandler { id: seekHover }
            ToolTip {
                objectName: "seekPreview"
                visible: progress.enabled && (seekHover.hovered || progress.pressed)
                delay: 150
                text: Theme.timeLabel(playerState.duration * (progress.pressed ? progress.value : Math.max(0, Math.min(1, (seekHover.point.position.x - progress.leftPadding) / Math.max(1, progress.availableWidth)))))
                x: Math.max(0, Math.min(progress.width - width, seekHover.point.position.x - width / 2))
                y: -height - 8
            }
        }
        Row {
            id: transport
            objectName: "playerTransport"
            anchors.horizontalCenter: parent.horizontalCenter; y: 8; spacing: 4
            IconButton { implicitWidth: root.dense ? 36 : 44; iconName: "shuffle"; iconColor: playerState.shuffled ? themeState.accent : themeState.secondary; tip: "Shuffle"; enabled: playerState.hasTrack; onClicked: appState.requestAction("shuffle") }
            IconButton { implicitWidth: root.dense ? 36 : 44; iconName: "previous"; tip: "Previous"; enabled: playerState.hasTrack; onClicked: playerState.previous() }
            IconButton { implicitWidth: root.dense ? 36 : 44; iconName: playerState.playing ? "pause" : "play"; iconSize: 28; iconColor: themeState.onAccent; tip: playerState.playing ? "Pause" : "Play"; enabled: playerState.hasTrack; onClicked: playerState.togglePlayback(); background: Rectangle { radius: 22; color: parent.hovered ? themeState.accentHover : themeState.accent; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.foreground } }
            IconButton { implicitWidth: root.dense ? 36 : 44; iconName: "next"; tip: "Next"; enabled: playerState.hasTrack; onClicked: playerState.next() }
            IconButton { implicitWidth: root.dense ? 36 : 44; iconName: playerState.repeat === "one" ? "repeatOne" : "repeat"; iconColor: playerState.repeat !== "off" ? themeState.accent : themeState.secondary; tip: "Repeat: " + playerState.repeat; enabled: playerState.hasTrack; onClicked: appState.requestAction("repeat") }
        }
        Text { objectName: "playbackElapsed"; x: progress.x + progress.leftPadding; y: progress.y + progress.height + 2; text: Theme.timeLabel(playerState.position); color: themeState.secondary; font.pixelSize: 11 }
        Text { objectName: "playbackDuration"; x: progress.x + progress.width - progress.rightPadding - width; y: progress.y + progress.height + 2; text: Theme.timeLabel(playerState.duration); color: themeState.secondary; font.pixelSize: 11 }
        BusyIndicator { anchors.right: parent.right; y: 10; width: 28; height: 28; visible: playerState.busy; running: visible }
    }
    Row {
        id: tools
        anchors.right: parent.right; anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        IconButton { implicitWidth: root.dense ? 36 : 44; iconName: "more"; tip: "Current Song Options"; enabled: playerState.hasTrack; onClicked: appState.showMenu(playerState.currentTrack, {nowPlaying: true}) }
        IconButton {
            id: sleepButton
            objectName: "sleepTimerButton"
            implicitWidth: root.dense ? 36 : 44
            visible: typeof playbackOptions !== "undefined"
            iconName: "timer"
            iconColor: visible && playbackOptions.sleepRemaining > 0 ? themeState.accent : themeState.secondary
            tip: visible && playbackOptions.sleepRemaining > 0 ? "Sleep Timer: pauses in " + Theme.timeLabel(playbackOptions.sleepRemaining) : "Sleep Timer"
            onClicked: sleepMenu.opened ? sleepMenu.close() : sleepMenu.popup(sleepButton, (sleepButton.width - sleepMenu.width) / 2, -sleepMenu.height - 8)
        }
        IconButton { implicitWidth: root.dense ? 36 : 44; id: nowPlayingToggle; objectName: "nowPlayingViewToggle"; iconName: "nowPlaying"; tip: appState.nowPlayingOpen ? "Close Now Playing" : "Now Playing"; iconColor: appState.nowPlayingOpen ? themeState.accent : themeState.secondary; onClicked: appState.toggleNowPlaying() }
        IconButton { implicitWidth: root.dense ? 36 : 44; id: queueToggle; objectName: "queueToggle"; iconName: "queue"; tip: appState.queueOpen ? "Close Queue" : "Queue"; iconColor: appState.queueOpen ? themeState.accent : themeState.secondary; onClicked: appState.toggleQueue() }
        IconButton { implicitWidth: root.dense ? 36 : 44; id: lyricsToggle; objectName: "lyricsToggle"; iconName: "music"; tip: appState.lyricsOpen ? "Close Lyrics" : "Lyrics"; iconColor: appState.lyricsOpen ? themeState.accent : themeState.secondary; onClicked: appState.toggleLyrics() }
        IconButton { implicitWidth: root.dense ? 36 : 44; id: volume; iconName: appState.volume > 0 ? "volume" : "muted"; tip: root.compact ? "Volume" : appState.volume > 0 ? "Mute" : "Unmute"; onClicked: root.compact ? volumePopup.open() : appState.toggleMute() }
        AccentSlider { width: 84; height: 44; visible: !root.compact; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        IconButton { implicitWidth: root.dense ? 36 : 44; id: immersiveToggle; objectName: "immersiveToggle"; enabled: playerState.hasTrack; iconName: appState.expanded ? "down" : "up"; tip: appState.expanded ? "Return to Browsing" : "Open Immersive Player"; onClicked: appState.requestAction("expandPlayer") }
    }
    // A small popover above the timer button, not a dialog: pick a time, turn it off, or click away.
    ThemedMenu {
        id: sleepMenu
        objectName: "sleepTimerMenu"
        implicitWidth: 200
        ContextMenuItem {
            objectName: "sleepTimerRemaining"
            visible: typeof playbackOptions !== "undefined" && playbackOptions.sleepRemaining > 0
            height: visible ? implicitHeight : 0
            enabled: false
            text: visible ? "Pauses in " + Theme.timeLabel(playbackOptions.sleepRemaining) : ""
        }
        ContextMenuItem { objectName: "sleepPreset-5"; text: "5 minutes"; onTriggered: playbackOptions.startSleep(5) }
        ContextMenuItem { objectName: "sleepPreset-10"; text: "10 minutes"; onTriggered: playbackOptions.startSleep(10) }
        ContextMenuItem { objectName: "sleepPreset-15"; text: "15 minutes"; onTriggered: playbackOptions.startSleep(15) }
        ContextMenuItem { objectName: "sleepPreset-30"; text: "30 minutes"; onTriggered: playbackOptions.startSleep(30) }
        ContextMenuItem { objectName: "sleepPreset-45"; text: "45 minutes"; onTriggered: playbackOptions.startSleep(45) }
        ContextMenuItem { objectName: "sleepPreset-60"; text: "60 minutes"; onTriggered: playbackOptions.startSleep(60) }
        ThemedMenuSeparator { visible: sleepOff.visible; height: visible ? implicitHeight : 0 }
        ContextMenuItem {
            id: sleepOff
            objectName: "cancelSleep"
            visible: typeof playbackOptions !== "undefined" && playbackOptions.sleepRemaining > 0
            height: visible ? implicitHeight : 0
            text: "Turn Off Timer"
            onTriggered: playbackOptions.cancelSleep()
        }
    }
    Popup {
        id: volumePopup
        x: root.width - width - 12; y: -height - 8; width: 220; height: 64; padding: 8
        background: Rectangle { color: themeState.surface; radius: Theme.radiusMedium; border.color: themeState.border }
        contentItem: Row {
            IconButton { iconName: appState.volume ? "volume" : "muted"; tip: appState.volume ? "Mute" : "Unmute"; onClicked: appState.toggleMute() }
            AccentSlider { width: 156; height: 44; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        }
    }
}
