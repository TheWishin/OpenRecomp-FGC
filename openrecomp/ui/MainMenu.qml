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
    Rectangle { x: 1050; y: 70; width: 6; height: parent.height - 140; color: Theme.readableAccent(menu.root.v.accent) }
    Column {
        x: 1110; y: 130; width: parent.width - x - 70; spacing: 26
        OnlineStyle.HelpText { width: parent.width; text: menu.m.status || ""; color: Theme.value; font.weight: Font.Bold }
        Text { width: parent.width; text: menu.m.title || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text; font.family: menu.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(104); lineHeight: 0.95 }
        OnlineStyle.SectionHeader { width: parent.width; text: menu.m.player || "" }
        OnlineStyle.HelpText { width: parent.width; text: menu.m.activity || "" }
    }
    OnlineStyle.HelpText { id: caption; x: 64; y: 24; width: 900; text: menu.m.kicker || ""; font.weight: Font.Bold; color: Theme.value }
    Flickable {
        id: scroll
        objectName: "mainMenuList"
        x: 48; y: caption.y + caption.height + 16; width: 960; height: parent.height - y - 20
        contentHeight: entries.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        function reveal() {
            var item = rows.itemAt(menu.m.selected || 0)
            if (!item) return
            if (item.y < contentY) contentY = item.y
            else if (item.y + item.height > contentY + height) contentY = item.y + item.height - height
        }
        Connections { target: menu.root.backend; function onViewChanged() { Qt.callLater(scroll.reveal) } }
        Column {
            id: entries; width: scroll.width; spacing: 5
            Repeater {
                id: rows; model: menu.m.entries || []
                Rectangle {
                    id: entry
                    required property var modelData
                    width: entries.width - 12; height: Math.max(50, label.implicitHeight + 14)
                    radius: 4; color: modelData.focused ? Theme.raised : "transparent"
                    Rectangle { visible: !!entry.modelData.focused; width: 6; height: parent.height; color: Theme.readableAccent(menu.root.v.accent) }
                    Text { id: label; x: 22; y: 7; width: parent.width - 40; text: entry.modelData.label || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: entry.modelData.focused ? Theme.text : Theme.muted; font.family: menu.root.display; font.weight: entry.modelData.focused ? Font.Black : Font.Bold; font.pixelSize: Theme.px(32) }
                    TapHandler { id: tap; onTapped: menu.root.backend.clickMainEntry(entry.modelData.index) }
                    Interaction { handler: tap; selected: !!entry.modelData.focused; name: entry.modelData.label || ""; onActivated: menu.root.backend.clickMainEntry(entry.modelData.index) }
                }
            }
        }
    }
}
