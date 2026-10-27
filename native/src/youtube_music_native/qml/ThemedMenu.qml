import QtQuick
import QtQuick.Controls

// Context menu shell shared by every menu; fill it with ContextMenuItem and ThemedMenuSeparator.
Menu {
    implicitWidth: 232
    padding: 8
    spacing: 2
    background: Rectangle { radius: 12; color: themeState.surface; border.color: themeState.border; border.width: 1 }
}
