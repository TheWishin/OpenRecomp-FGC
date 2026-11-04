import QtQuick

Item {
    id: menu
    required property var root
    readonly property var m: root.v.mainMenu || ({})
    Image { anchors.fill: parent; source: menu.root.v.hero || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#FA0E0F11" }
            GradientStop { position: 0.55; color: "#E00E0F11" }
            GradientStop { position: 1; color: "#D90E0F11" }
        }
    }
    Rectangle { x: parent.width * 0.53; y: 32; width: 3; height: parent.height - 64; color: Theme.readableAccent(menu.root.v.accent) }
    Column {
        x: parent.width * 0.53 + 24; y: 64; width: parent.width - x - 32; spacing: 16
        OnlineStyle.HelpText { objectName: "mainMenuStatus"; width: parent.width; text: menu.m.status || ""; color: Theme.value; font.weight: Font.Bold }
        Text { width: parent.width; text: menu.m.title || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text; font.family: menu.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(48); lineHeight: 0.95 }
        OnlineStyle.SectionHeader { width: parent.width; text: menu.m.player || "" }
        OnlineStyle.HelpText { width: parent.width; text: menu.m.activity || "" }
    }
    OnlineStyle.HelpText { id: caption; x: 32; y: 16; width: parent.width * 0.53 - 64; text: menu.m.kicker || ""; font.weight: Font.Bold; color: Theme.value }
    Flickable {
        id: scroll
        objectName: "mainMenuList"
        x: 24; y: caption.y + caption.height + 8; width: parent.width * 0.53 - 48; height: parent.height - y - 16
        contentHeight: entries.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        function reveal() {
            var item = rows.itemAt(menu.m.selected || 0)
            if (!item) return
            if (item.y < contentY) contentY = item.y
            else if (item.y + item.height > contentY + height) contentY = item.y + item.height - height
        }
        onHeightChanged: Qt.callLater(reveal)
        onContentHeightChanged: Qt.callLater(reveal)
        Connections { target: menu.root.backend; function onViewChanged() { Qt.callLater(scroll.reveal) } }
        Column {
            id: entries; width: scroll.width; spacing: 5
            onPositioningComplete: Qt.callLater(scroll.reveal)
            Repeater {
                id: rows; model: menu.m.entries || []
                Rectangle {
                    id: entry
                    required property var modelData
                    objectName: "mainMenuEntry"
                    width: entries.width - 12; height: Math.max(Theme.target(50), label.implicitHeight + 14) + (modelData.groupStart ? groupLabel.height + 12 : 0)
                    radius: 4; color: modelData.focused ? Theme.raised : "transparent"
                    Rectangle { visible: !!entry.modelData.focused; width: 6; height: parent.height; color: Theme.readableAccent(menu.root.v.accent) }
                    OnlineStyle.HelpText { id: groupLabel; visible: !!entry.modelData.groupStart; x: 22; y: 6; width: parent.width - 40; text: entry.modelData.group || ""; color: Theme.value }
                    Text { id: label; x: 22; y: entry.modelData.groupStart ? groupLabel.height + 18 : 7; width: parent.width - 40; text: entry.modelData.label || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: entry.modelData.focused ? Theme.text : Theme.muted; font.family: menu.root.display; font.weight: entry.modelData.focused ? Font.Black : Font.Bold; font.pixelSize: Theme.px(24) }
                    TapHandler { id: tap; onTapped: menu.root.backend.clickMainEntry(entry.modelData.index) }
                    Interaction { handler: tap; selected: !!entry.modelData.focused; name: entry.modelData.label || ""; onActivated: menu.root.backend.clickMainEntry(entry.modelData.index) }
                }
            }
        }
    }
}
