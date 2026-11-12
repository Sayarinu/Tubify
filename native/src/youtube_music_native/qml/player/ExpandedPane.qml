import QtQuick
import QtQuick.Controls
import Tubify.Video
import "../components"

Item {
    id: root
    objectName: "expandedPlayer"
    // Space taken by the side panel floating on the right. The background still runs underneath it.
    property real rightInset: 0
    // Where that space is right now while the panel slides. Only the stage's position follows it:
    // sizing from it would reload the artwork on every frame.
    property real slidingInset: rightInset
    readonly property real stageWidth: width - rightInset
    readonly property var track: playerState.currentTrack
    readonly property var artists: track.artists && track.artists.length ? track.artists : track.artist ? [{name: track.artist}] : []
    readonly property var album: typeof track.album === "object" && track.album ? track.album : ({})
    readonly property string albumName: typeof track.album === "string" ? track.album : album.name || track.albumName || track.albumTitle || ""
    readonly property string albumId: album.id || album.browseId || ""
    readonly property real coverSize: Math.max(80, Math.min(stageWidth - 48, height - metadata.height - 64 - (modeSwitch.visible ? 52 : 0), 720))
    // Music videos play here once they have a picture; leaving the expanded player returns to audio only.
    readonly property bool videoShown: playerState.showingVideo
    readonly property real videoWidth: Math.max(160, Math.min(stageWidth - 48, (height - metadata.height - 116) * 16 / 9, 1280))
    Component.onCompleted: playerState.setVideoSurface(visible)
    Component.onDestruction: playerState.setVideoSurface(false)
    onVisibleChanged: playerState.setVideoSurface(visible)
    function focusStage() { title.forceActiveFocus() }

    ArtworkBackdrop {
        anchors.fill: parent
        source: root.track.thumbnail || ""
        mediaKey: root.track.videoId || root.track.id || ""
    }
    Column {
        x: (root.width - root.slidingInset - width) / 2
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(root.stageWidth - 48, 760)
        spacing: 24
        Row {
            id: modeSwitch
            objectName: "videoModeSwitch"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: playerState.videoAvailable
            spacing: 4
            Repeater {
                model: [{ label: "Song", video: false }, { label: "Video", video: true }]
                delegate: FilterChip {
                    required property var modelData
                    selected: playerState.videoPreferred === modelData.video
                    text: modelData.label; height: 32; leftPadding: 18; rightPadding: 18
                    Accessible.name: "Play " + modelData.label.toLowerCase()
                    onClicked: playerState.setVideoPreferred(modelData.video)
                }
            }
        }
        Item {
            objectName: "videoStage"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.videoShown
            width: root.videoWidth; height: width * 9 / 16
            Rectangle { anchors.fill: parent; radius: 12; color: "black" }
            VideoSurface {
                objectName: "videoSurface"
                anchors.fill: parent
                frames: root.videoShown ? playerState.videoFrames : null
                Accessible.role: Accessible.Graphic
                Accessible.name: "Video for " + (root.track.title || "current song")
            }
        }
        Cover {
            objectName: "immersiveArtwork"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: !root.videoShown
            width: root.coverSize; height: width; radius: 12
            largeArtwork: true
            prefetchMedia: playerState.upcomingTracks || []
            media: root.track
            source: root.track.largeThumbnail || root.track.thumbnail || ""
            mediaKey: root.track.videoId || root.track.id || ""
            Accessible.role: Accessible.Graphic
            Accessible.name: "Artwork for " + (root.track.title || "current song")
            Rectangle {
                objectName: "videoLoading"
                anchors.centerIn: parent
                width: 72; height: 72; radius: width / 2
                color: Qt.rgba(0, 0, 0, 0.6)
                visible: playerState.videoLoading
                Accessible.role: Accessible.Indicator
                Accessible.name: "Loading video"
                // Drawn here because it must read clearly over any artwork, whatever the theme.
                Rectangle { anchors.centerIn: parent; width: 36; height: 36; radius: width / 2; color: "transparent"; border.width: 3; border.color: Qt.rgba(1, 1, 1, 0.3) }
                Item {
                    anchors.centerIn: parent
                    width: 36; height: 36
                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 9; height: 9; radius: width / 2; y: -3; color: "white" }
                    RotationAnimator on rotation { from: 0; to: 360; duration: 1000; loops: Animation.Infinite; running: playerState.videoLoading && !appState.reducedMotion }
                }
            }
        }
        Column {
            id: metadata
            width: parent.width
            spacing: 4
            TextLink {
                id: title
                objectName: "immersiveTrackTitle"
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, parent.width)
                text: root.track.title || "Nothing Playing"
                pixelSize: root.stageWidth < 600 ? 24 : 32; bold: true
                maximumLineCount: 2
                underlineOnHover: false
                Accessible.role: Accessible.Button
                Accessible.name: (root.track.title || "Current song") + " options"
                enabled: playerState.hasTrack
                onClicked: appState.showMenu(root.track, {nowPlaying: true})
            }
            Item {
                id: artistLine
                width: parent.width
                height: 36
                clip: true
                Row {
                    id: artistRow
                    x: Math.max(0, (artistLine.width - width) / 2)
                    height: parent.height
                    Repeater {
                        model: root.artists
                        Row {
                            required property var modelData
                            required property int index
                            height: artistRow.height
                            TextLink {
                                objectName: "immersiveArtist-" + index
                                height: parent.height
                                text: modelData.name || ""
                                pixelSize: 16
                                onClicked: browseState.openArtist(modelData)
                            }
                            Text { visible: index < root.artists.length - 1; height: parent.height; text: "•"; color: themeState.secondary; font.pixelSize: 16; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
            }
            TextLink {
                objectName: "immersiveAlbum"
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, parent.width)
                height: 36
                visible: !!root.albumName
                enabled: !!root.albumId
                text: root.albumName
                textColor: themeState.secondary
                onClicked: browseState.open({kind: "album", id: root.albumId, title: root.albumName})
            }
        }
    }
}
