.pragma library

var background = "#030303"
var surface = "#212121"
var hover = "#292929"
var foreground = "#ffffff"
var secondary = "#b3b3b3"
var border = "#292929"
var accent = "#ff0033"
var bodyFont = "Roboto"
var headingFont = "Roboto Condensed"
var filled = { play: true, pause: true, previous: true, next: true, home: true, music: true }
var paths = {
    menu: "M4 6h16M4 12h16M4 18h16",
    search: "M10.5 3a7.5 7.5 0 1 0 0 15a7.5 7.5 0 1 0 0-15M16 16l5 5",
    home: "M3 10l9-7l9 7v11h-6v-7H9v7H3z",
    explore: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20M16 8l-2.5 5.5L8 16l2.5-5.5z",
    library: "M5 3h14v18l-7-4l-7 4z",
    download: "M12 3v12M7 10l5 5l5-5M4 17v4h16v-4",
    plus: "M12 4v16M4 12h16",
    play: "M7 3l15 9L7 21z",
    pause: "M6 3h4v18H6zM15 3h4v18h-4z",
    previous: "M4 4h3v16H4zM20 4v16L8 12z",
    next: "M17 4h3v16h-3zM4 4l12 8L4 20z",
    volume: "M3 9h4l5-4v14l-5-4H3zM16 8q5 4 0 8M19 5q8 7 0 14",
    muted: "M3 9h4l5-4v14l-5-4H3zM16 9l6 6M22 9l-6 6",
    repeat: "M4 8h15l-3-3M20 16H5l3 3M20 8v5M4 16v-5",
    shuffle: "M3 6h3l12 12h3M3 18h3l4-4M14 10l4-4h3M18 3l3 3l-3 3M18 15l3 3l-3 3",
    like: "M8 10l4-7q3 0 1 7h7v3l-3 8H8zM3 10h4v11H3z",
    dislike: "M8 14l4 7q3 0 1-7h7v-3l-3-8H8zM3 3h4v11H3z",
    more: "M12 4v1M12 11v1M12 18v1",
    left: "M15 5l-7 7l7 7",
    right: "M9 5l7 7l-7 7",
    up: "M5 15l7-7l7 7",
    down: "M5 9l7 7l7-7",
    drag: "M5 8h14M5 12h14M5 16h14",
    music: "M9 4v12a4 3 0 1 1-2-2V6l12-3v11a4 3 0 1 1-2-2V1z",
    profile: "M12 3a4 4 0 1 0 0 8a4 4 0 1 0 0-8M4 22v-3a8 6 0 0 1 16 0v3",
    close: "M5 5l14 14M19 5L5 19",
    check: "M4 12l5 5L20 6",
    history: "M3 10a9 9 0 1 1 1 7M3 4v6h6M12 7v6l4 2",
    edit: "M4 16l12-12l4 4L8 20H4zM14 6l4 4"
}
