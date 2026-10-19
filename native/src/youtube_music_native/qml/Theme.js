.pragma library

var bodyFont = "Roboto"
var headingFont = "Roboto"
var cardWidth = 208
var cardHeight = 284
function gutter(width) { return width > 1200 ? 40 : 24 }
function timeLabel(value) {
    var seconds = Math.max(0, Math.floor(value || 0))
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
}
