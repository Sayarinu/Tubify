import QtQuick
import "../Theme.js" as Theme

// Where downloads are kept: privately inside Tubify, or as audio files in a folder. Choosing converts existing downloads.
Row {
    id: root
    spacing: Theme.spacingSmall
    Accessible.role: Accessible.Grouping
    Accessible.name: "Save downloads"
    FilterChip {
        objectName: "downloadStyleTubify"
        text: "In Tubify"
        selected: downloadsState.downloadStyle === "tubify"
        Accessible.description: "Keep downloads privately inside Tubify"
        onClicked: downloadsState.setDownloadStyle("tubify")
    }
    FilterChip {
        objectName: "downloadStyleFiles"
        text: "As Audio Files"
        selected: downloadsState.downloadStyle === "files"
        Accessible.description: "Keep downloads as audio files in " + downloadsState.filesFolder
        onClicked: downloadsState.setDownloadStyle("files")
    }
}
