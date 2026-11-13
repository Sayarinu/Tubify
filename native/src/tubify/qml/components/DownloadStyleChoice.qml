import QtQuick

// Where downloads are kept: privately inside Tubify, or as audio files in a folder. Choosing converts existing downloads.
SegmentedToggle {
    Accessible.name: "Download to"
    options: [
        {value: "tubify", label: "Tubify", description: "Keep downloads privately inside Tubify"},
        {value: "files", label: "Local Files", description: "Keep downloads as audio files in " + downloadsState.filesFolder}
    ]
    current: downloadsState.downloadStyle
    onChosen: value => downloadsState.setDownloadStyle(value)
}
