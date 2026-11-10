import QtQuick

Rectangle {
    id: card
    objectName: "arcadePlayer"
    required property var root
    required property var player
    property var labels: ({})
    property var glyphs: ({})
    readonly property color accent: Theme.readableAccent(root.v.accent)
    readonly property bool warmSelection: Theme.gameKind === "t5dr" && !Theme.highContrast && !Theme.calm && (player.focused || player.selected)
    readonly property bool narrow: Theme.viewportScale < .85 || Theme.textScale > 1.1
    readonly property real actionWidth: narrow ? 108 : 230
    readonly property real dataWidth: width - 48
    readonly property var receipt: ((player.buttons || []).filter(b => (b.feedback || {}).text)[0] || {}).feedback || ({})
    height: Theme.playerRowHeight
    color: player.focused || player.selected ? Theme.highlighted : player.own ? Theme.raised : Theme.card
    border.width: player.focused ? 2 : 0; border.color: Theme.focus
    Rectangle {
        objectName: "arcadePlayerSelection"
        visible: card.warmSelection
        anchors.fill: parent; anchors.margins: card.border.width
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.highlightStart }
            GradientStop { position: 1; color: Theme.highlightEnd }
        }
    }
    Rectangle {
        objectName: "arcadePlayerPortrait"
        x: 8; anchors.verticalCenter: parent.verticalCenter; width: 24; height: 24; color: Theme.raised; clip: true
        Image { anchors.fill: parent; source: card.player.face || ""; visible: !!source; asynchronous: true; fillMode: Image.PreserveAspectCrop }
        Text { visible: !card.player.face; anchors.centerIn: parent; text: (card.player.name || "?").substring(0, 1).toUpperCase(); textFormat: Text.PlainText; color: Theme.muted; font.family: card.root.sans; font.pixelSize: Theme.onlinePx(14) * Math.min(1, Theme.viewportScale); Accessible.ignored: true }
    }
    Row {
        x: 40; width: card.dataWidth; height: parent.height
        Repeater {
            model: [{key:"name", value:card.player.name, part:.25}, {key:"rank", value:card.player.rank, part:.17}, {key:"rating", value:card.player.rating, part:.11}, {key:"main", value:card.player.main, part:.15}, {key:"status", value:card.player.status, part:.15}]
            Item {
                required property var modelData
                width: card.dataWidth * modelData.part; height: card.height
                opacity: (card.player.selected || card.player.focused) && ["main", "status"].indexOf(modelData.key) >= 0 ? 0 : 1
                Image { visible: parent.modelData.key === "rank" && !!card.player.plate; width: 32; height: 18; anchors.verticalCenter: parent.verticalCenter; source: card.player.plate || ""; fillMode: Image.PreserveAspectFit }
                Text {
                    objectName: parent.modelData.key === "name" ? "arcadePlayerName" : parent.modelData.key === "status" ? "arcadePlayerStatus" : "arcadePlayerCell"
                    x: parent.modelData.key === "rank" && card.player.plate ? 36 : 0; width: parent.width - x - 6; anchors.verticalCenter: parent.verticalCenter
                    text: parent.modelData.value || ""; textFormat: Text.PlainText; elide: Text.ElideRight
                    Accessible.name: text
                    color: parent.modelData.key === "rank" ? Theme.rankGold : card.warmSelection || parent.modelData.key === "name" ? Theme.text : Theme.muted
                    font.family: card.root.sans; font.pixelSize: Theme.onlinePx(14); font.weight: parent.modelData.key === "name" ? Font.DemiBold : Font.Normal
                }
            }
        }
        Item {
            width: card.dataWidth * .17; height: card.height
            opacity: card.player.selected || card.player.focused ? 0 : 1
            Row {
                x: 0; spacing: 2; anchors.verticalCenter: parent.verticalCenter
                Repeater { model: 4; Rectangle { required property int index; width: 3; height: 4 + index * 3; anchors.bottom: parent.bottom; color: index < (card.player.connection.bars || 0) ? (Theme.quiet ? Theme.mark : card.accent) : Theme.border } }
                height: 14
            }
            Text { x: 22; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter; text: card.player.connection.text || ""; elide: Text.ElideRight; textFormat: Text.PlainText; color: Theme.muted; font.family: card.root.sans; font.pixelSize: Theme.onlinePx(14) }
        }
    }
    TapHandler {
        id: select
        exclusiveSignals: TapHandler.SingleTap | TapHandler.DoubleTap
        onSingleTapped: card.root.backend.focusOnlineRow(card.player.index)
        onDoubleTapped: { if (card.player.own) card.root.backend.focusOnlineRow(card.player.index); else card.root.backend.challengePlayer(card.player.id) }
    }
    Interaction { handler: select; selected: !!card.player.focused; role: Accessible.ListItem; name: [card.player.name, card.player.rank, card.player.rating, card.player.main, card.player.status, card.player.connection.text, card.player.areaLanguage].join(". "); onActivated: card.root.backend.focusOnlineRow(card.player.index) }
    Row {
        objectName: "playerInlineActions"
        visible: card.player.selected || card.player.focused
        x: parent.width - card.actionWidth; width: card.actionWidth - 4; height: parent.height; spacing: 4
        Repeater {
            model: (card.player.buttons || []).filter(b => b.semantic !== "watch").slice(0, 3)
            ArcadeAction {
                required property var modelData
                root: card.root; b: modelData; compact: true; primary: b.semantic === "challenge"
                iconOnly: card.narrow || b.semantic !== "challenge"; icon: iconOnly ? b.semantic || "message" : ""
                width: card.narrow ? 32 : b.semantic === "challenge" ? 138 : 40
                height: Math.min(card.height - 4, implicitHeight); anchors.verticalCenter: parent.verticalCenter
                onActivated: card.root.backend.clickRow(b.index)
            }
        }
    }
}
