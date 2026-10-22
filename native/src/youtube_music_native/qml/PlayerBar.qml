import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Rectangle {
    id: root
    objectName: "playerBar"
    function focusDockToggle(name) { if (name === "Lyrics") lyricsToggle.forceActiveFocus(); else queueToggle.forceActiveFocus() }
    height: 92
    radius: 12
    color: themeState.surface
    border.color: themeState.border
    property bool compact: width < 1100
    readonly property var primaryArtist: playerState.currentTrack.artists && playerState.currentTrack.artists.length ? playerState.currentTrack.artists[0] : ({})

    Item {
        id: track
        x: 16; width: Math.min(380, root.width * 0.34); height: parent.height
        Cover { id: cover; anchors.verticalCenter: parent.verticalCenter; width: 68; height: 68; radius: 8; source: playerState.currentTrack.thumbnail || ""; mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""; accent: themeState.selected }
        Column {
            x: 80; width: parent.width - x - like.width - dislike.width; anchors.verticalCenter: parent.verticalCenter; spacing: 5
            Item {
                id: titleViewport
                width: parent.width
                height: titleText.implicitHeight
                implicitHeight: height
                clip: true
                onWidthChanged: if (titleText.implicitWidth <= width) { titleText.x = 0; titleScroll.stop() } else titleScroll.restart()
                Text {
                    id: titleText
                    width: implicitWidth; height: parent.height
                    text: playerState.currentTrack.title || "Nothing playing"
                    textFormat: Text.PlainText; color: themeState.foreground; font.bold: true; font.pixelSize: 14
                    onImplicitWidthChanged: if (implicitWidth <= titleViewport.width) { x = 0; titleScroll.stop() } else titleScroll.restart()
                }
                SequentialAnimation {
                    id: titleScroll
                    running: titleText.implicitWidth > titleViewport.width
                    loops: Animation.Infinite
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: titleText; property: "x"; to: titleViewport.width - titleText.implicitWidth; duration: Math.max(1200, (titleText.implicitWidth - titleViewport.width) * 35); easing: Easing.Linear }
                    PauseAnimation { duration: 900 }
                    NumberAnimation { target: titleText; property: "x"; to: 0; duration: Math.max(1200, (titleText.implicitWidth - titleViewport.width) * 35); easing: Easing.Linear }
                }
            }
            Item {
                id: artistViewport
                width: parent.width; height: 18; clip: true
                Row {
                    id: artistContent
                    x: 0; width: childrenRect.width; height: parent.height
                    onWidthChanged: if (width <= artistViewport.width) { x = 0; artistScroll.stop() } else artistScroll.restart()
                    Repeater {
                        model: playerState.currentTrack.artists || []
                        delegate: Item {
                            required property var modelData
                            required property int index
                            width: artistName.implicitWidth + separator.implicitWidth
                            height: artistViewport.height
                            Text {
                                id: artistName
                                width: implicitWidth; height: parent.height
                                text: modelData.name || ""
                                textFormat: Text.PlainText
                                color: artistLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary
                                font.pixelSize: 11
                                font.underline: artistLink.containsMouse || activeFocus
                                activeFocusOnTab: !!modelData.name
                                Accessible.role: modelData.name ? Accessible.Link : Accessible.StaticText
                                Accessible.onPressAction: openArtist()
                                Keys.onReturnPressed: openArtist()
                                Keys.onSpacePressed: openArtist()
                                function openArtist() {
                                    var artistId = modelData.id || modelData.browseId || modelData.channelId
                                    browseState.openArtist({id: artistId, browseId: modelData.browseId, channelId: modelData.channelId, name: modelData.name})
                                }
                                MouseArea {
                                    id: artistLink
                                    anchors.fill: parent; z: 1
                                    enabled: !!modelData.name; hoverEnabled: enabled
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: artistName.openArtist()
                                }
                            }
                            Text { id: separator; x: artistName.implicitWidth; width: index < playerState.currentTrack.artists.length - 1 ? implicitWidth : 0; height: parent.height; text: " • "; color: themeState.secondary; font.pixelSize: 11 }
                        }
                    }
                    Text {
                        visible: !playerState.currentTrack.artists || !playerState.currentTrack.artists.length
                        text: playerState.currentTrack.artist || "Choose a song"
                        textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 11
                    }
                }
                SequentialAnimation {
                    id: artistScroll
                    running: artistContent.width > artistViewport.width
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
                Text {
                    id: albumName
                    width: parent.width; height: parent.height
                    text: typeof playerState.currentTrack.album === "string" ? playerState.currentTrack.album : playerState.currentTrack.album && playerState.currentTrack.album.name || playerState.currentTrack.albumName || playerState.currentTrack.albumTitle || ""
                    textFormat: Text.PlainText; elide: Text.ElideRight; color: albumLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary; font.pixelSize: 11
                    font.underline: albumLink.containsMouse || activeFocus
                    activeFocusOnTab: !!(playerState.currentTrack.album && (playerState.currentTrack.album.id || playerState.currentTrack.album.browseId))
                    Accessible.role: activeFocusOnTab ? Accessible.Link : Accessible.StaticText
                    Accessible.onPressAction: openAlbum()
                    Keys.onReturnPressed: openAlbum()
                    Keys.onSpacePressed: openAlbum()
                    function openAlbum() {
                        var album = playerState.currentTrack.album || ({})
                        var albumId = album.id || album.browseId
                        if (albumId) browseState.open({kind: "album", id: albumId, title: album.name})
                    }
                    MouseArea {
                        id: albumLink
                        anchors.fill: parent
                        enabled: !!(playerState.currentTrack.album && (playerState.currentTrack.album.id || playerState.currentTrack.album.browseId))
                        hoverEnabled: enabled
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: albumName.openAlbum()
                    }
                }
            }
        }
        IconButton { id: dislike; objectName: "playerDislike"; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; iconName: "dislike"; tip: playerState.currentTrack.rating === "DISLIKE" ? "Remove dislike" : "Dislike"; iconColor: playerState.currentTrack.rating === "DISLIKE" ? themeState.accent : themeState.secondary; enabled: playerState.hasTrack && !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: appState.requestAction("dislike") }
        IconButton { id: like; objectName: "playerLike"; anchors.right: dislike.left; anchors.verticalCenter: parent.verticalCenter; iconName: "like"; tip: playerState.currentTrack.rating === "LIKE" ? "Remove like" : "Like"; iconColor: playerState.currentTrack.rating === "LIKE" ? themeState.accent : themeState.secondary; enabled: playerState.hasTrack && !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: appState.requestAction("like") }
    }
    Item {
        anchors.left: track.right; anchors.leftMargin: 8
        anchors.right: tools.left; anchors.rightMargin: 12
        height: parent.height
        AccentSlider {
            id: progress
            objectName: "playbackSeek"
            z: -1
            x: 46; y: 54; width: parent.width - 92; height: 16
            from: 0; to: 1; value: playerState.progress
            enabled: playerState.hasTrack; Accessible.name: "Playback position"
            onMoved: playerState.seekFraction(value)
        }
        Row {
            id: transport
            objectName: "playerTransport"
            anchors.horizontalCenter: parent.horizontalCenter; y: 8; spacing: 4
            IconButton { iconName: "shuffle"; iconColor: playerState.shuffled ? themeState.accent : themeState.secondary; tip: "Shuffle"; enabled: playerState.hasTrack; onClicked: appState.requestAction("shuffle") }
            IconButton { iconName: "previous"; tip: "Previous"; enabled: playerState.hasTrack; onClicked: playerState.previous() }
            IconButton { iconName: playerState.playing ? "pause" : "play"; iconSize: 28; iconColor: themeState.onAccent; tip: playerState.playing ? "Pause" : "Play"; enabled: playerState.hasTrack; onClicked: playerState.togglePlayback(); background: Rectangle { radius: 22; color: parent.hovered ? themeState.accentHover : themeState.accent; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.foreground } }
            IconButton { iconName: "next"; tip: "Next"; enabled: playerState.hasTrack; onClicked: playerState.next() }
            IconButton { iconName: playerState.repeat === "one" ? "repeatOne" : "repeat"; iconColor: playerState.repeat !== "off" ? themeState.accent : themeState.secondary; tip: "Repeat: " + playerState.repeat; enabled: playerState.hasTrack; onClicked: appState.requestAction("repeat") }
        }
        Text { objectName: "playbackElapsed"; x: progress.x + progress.leftPadding; y: progress.y + progress.height + 2; text: Theme.timeLabel(playerState.position); color: themeState.secondary; font.pixelSize: 11 }
        Text { objectName: "playbackDuration"; x: progress.x + progress.width - progress.rightPadding - width; y: progress.y + progress.height + 2; text: Theme.timeLabel(playerState.duration); color: themeState.secondary; font.pixelSize: 11 }
        BusyIndicator { anchors.right: parent.right; y: 10; width: 28; height: 28; visible: playerState.busy; running: visible }
    }
    Row {
        id: tools
        anchors.right: parent.right; anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        IconButton { iconName: "more"; tip: "Current song options"; enabled: playerState.hasTrack; onClicked: appState.showMenu(playerState.currentTrack, {}) }
        IconButton { id: queueToggle; objectName: "queueToggle"; iconName: "queue"; tip: appState.queueOpen ? "Close Queue" : "Queue"; iconColor: appState.queueOpen ? themeState.accent : themeState.secondary; onClicked: { if (appState.expanded) appState.setExpanded(false); appState.toggleQueue() } }
        IconButton { id: lyricsToggle; objectName: "lyricsToggle"; iconName: "music"; tip: appState.lyricsOpen ? "Close Lyrics" : "Lyrics"; iconColor: appState.lyricsOpen ? themeState.accent : themeState.secondary; onClicked: { if (appState.expanded) appState.setExpanded(false); appState.toggleLyrics() } }
        IconButton { id: volume; iconName: appState.volume > 0 ? "volume" : "muted"; tip: root.compact ? "Volume" : appState.volume > 0 ? "Mute" : "Unmute"; onClicked: root.compact ? volumePopup.open() : appState.toggleMute() }
        AccentSlider { width: 84; height: 44; visible: !root.compact; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        IconButton { iconName: appState.expanded ? "down" : "up"; tip: appState.expanded ? "Close player page" : "Expand player"; onClicked: appState.requestAction("expandPlayer") }
    }
    Popup {
        id: volumePopup
        x: root.width - width - 12; y: -height - 8; width: 220; height: 64; padding: 8
        background: Rectangle { color: themeState.surface; radius: 12; border.color: themeState.border }
        contentItem: Row {
            IconButton { iconName: appState.volume ? "volume" : "muted"; tip: appState.volume ? "Mute" : "Unmute"; onClicked: appState.toggleMute() }
            AccentSlider { width: 156; height: 44; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        }
    }
}
