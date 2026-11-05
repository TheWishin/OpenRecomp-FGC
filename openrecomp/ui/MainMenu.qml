import QtQuick

Item {
    id: menu
    required property var root
    readonly property var m: root.v.mainMenu || ({})
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .72) }
            GradientStop { position: 0.52; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .28) }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Rectangle { x: parent.width * 0.53; y: 32; width: 3; height: parent.height - 64; color: Theme.gameAccent }
    Column {
        id: identity
        x: parent.width * 0.53 + 24; y: 32; width: parent.width - x - 32; spacing: 12
        Column {
            id: playerDetails
            width: parent.width; spacing: 12
            OnlineStyle.HelpText { objectName: "mainMenuStatus"; width: parent.width; text: menu.m.status || ""; color: Theme.value; font.weight: Font.Bold }
            Text { width: parent.width; text: menu.m.title || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text; font.family: menu.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(48); lineHeight: 0.95 }
            OnlineStyle.HelpText { objectName: "mainMenuPlaytime"; width: parent.width; text: menu.m.playtime || ""; visible: !!text }
            OnlineStyle.SectionHeader { width: parent.width; text: menu.m.player || "" }
            Row {
                width: parent.width; spacing: 12; height: Math.max(rankText.implicitHeight, rankImage.visible ? 48 : 0)
                Image { id: rankImage; visible: !!menu.m.rankPlate; source: menu.m.rankPlate || ""; width: visible ? 150 : 0; height: 48; fillMode: Image.PreserveAspectFit; asynchronous: true; cache: true; sourceSize.height: 96 }
                OnlineStyle.Value { id: rankText; anchors.verticalCenter: parent.verticalCenter; width: parent.width - (rankImage.visible ? rankImage.width + parent.spacing : 0); text: menu.m.rank || ""; color: Theme.rankGold }
            }
            OnlineStyle.HelpText { objectName: "mainMenuMain"; width: parent.width; text: menu.m.main ? (menu.m.mainLabel || "") + menu.m.main : ""; visible: !!text; color: Theme.text; font.weight: Font.Bold }
            OnlineStyle.HelpText { width: parent.width; text: menu.m.activity || "" }
            Repeater {
                model: menu.m.delayOptions || []
                ArcadeAction {
                    required property var modelData
                    root: menu.root; b: modelData; width: parent.width
                    label: [b.label || "", b.value || ""].filter(s => s).join(": ")
                    onActivated: menu.root.backend.clickRow(b.index)
                }
            }
        }
        Row {
            objectName: "mainMenuFighters"
            width: parent.width; spacing: 8
            height: Math.max(0, Math.min(270, menu.height - identity.y - playerDetails.height - recentStats.height - 2 * identity.spacing - 16))
            clip: true
            Repeater {
                model: menu.m.fighters || []
                FighterPortrait { required property var modelData; required property int index; width: (parent.width - 16) * (index === 0 ? .52 : .24); height: parent.height; source: modelData.image || ""; name: modelData.name || ""; showcase: index === 0 }
            }
        }
        Column {
            id: recentStats
            width: parent.width; spacing: 12
            OnlineStyle.HelpText { width: parent.width; text: menu.m.recentLabel || ""; visible: (menu.m.recentResults || []).length > 0 }
            Row {
                objectName: "mainMenuRecentResults"
                width: parent.width; height: visible ? Theme.target(44) : 0; spacing: 8
                visible: (menu.m.recentResults || []).length > 0
                Repeater {
                    model: menu.m.recentResults || []
                    ResultCell { required property var modelData; root: menu.root; c: modelData; accent: Theme.success; width: Theme.target(44); height: width }
                }
            }
        }
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
                    readonly property bool matchAction: modelData.id === "ranked" || modelData.id === "quick"
                    readonly property real groupH: modelData.groupStart ? groupLabel.height + 12 : 0
                    width: entries.width - 12; height: Math.max(matchAction ? 80 / Theme.viewportScale : Theme.target(50), label.implicitHeight + (matchAction ? subtitle.height + 18 : 14)) + groupH
                    radius: 4; color: modelData.id === "ranked" ? Theme.primaryFill : matchAction || modelData.focused ? Theme.raised : "transparent"
                    border.width: matchAction ? 1 : 0; border.color: Theme.readableAccent(menu.root.v.accent)
                    Rectangle { visible: !!entry.modelData.focused; width: 6; height: parent.height; color: Theme.gameAccent }
                    OnlineStyle.HelpText { id: groupLabel; visible: !!entry.modelData.groupStart; x: 22; y: 6; width: parent.width - 40; text: entry.modelData.group || ""; color: entry.modelData.id === "ranked" ? Theme.primaryText : Theme.value }
                    Text { id: label; objectName: "mainMenuEntryLabel"; x: 22; y: entry.groupH + (entry.height - entry.groupH - height - (subtitle.visible ? subtitle.height + 2 : 0)) / 2; width: parent.width - 40; text: entry.modelData.label || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: entry.modelData.id === "ranked" ? Theme.primaryText : entry.matchAction || entry.modelData.focused ? Theme.text : Theme.muted; font.family: menu.root.display; font.weight: entry.modelData.focused ? Font.Black : Font.Bold; font.pixelSize: Theme.px(24) }
                    Text { id: subtitle; objectName: "mainMenuEntrySubtitle"; visible: entry.matchAction; x: 22; y: label.y + label.height + 2; width: parent.width - 40; text: entry.modelData.subtitle || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: entry.modelData.id === "ranked" ? Theme.primaryText : Theme.muted; font.family: menu.root.sans; font.pixelSize: Theme.onlinePx(14) }
                    TapHandler { id: tap; onTapped: menu.root.backend.clickMainEntry(entry.modelData.index) }
                    Interaction { handler: tap; selected: !!entry.modelData.focused; disabled: !!entry.modelData.disabled; disabledReason: entry.modelData.subtitle || ""; name: [entry.modelData.label || "", entry.modelData.subtitle || ""].join(". "); onActivated: menu.root.backend.clickMainEntry(entry.modelData.index) }
                }
            }
        }
    }
}
