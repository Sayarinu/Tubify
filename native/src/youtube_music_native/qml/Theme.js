.pragma library

var background = "#14131b"
var surface = "#22212b"
var hover = "#302d3e"
var foreground = "#f6f4fb"
var secondary = "#aaa6b8"
var border = "#36323f"
var accent = "#a78bfa"
var accentHover = "#c4b5fd"
var onAccent = "#201630"
var selected = "#332b49"
var muted = "#716b80"
var bodyFont = "Roboto"
var headingFont = "Roboto"
var cardWidth = 208
var cardHeight = 284
function gutter(width) { return width > 1200 ? 40 : 24 }
function timeLabel(value) {
    var seconds = Math.max(0, Math.floor(value || 0))
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
}
