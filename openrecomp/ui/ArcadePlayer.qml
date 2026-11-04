import QtQuick

Rectangle {
    id: card
    objectName: "arcadePlayer"
    required property var root
    required property var player
    property var labels: ({})
    property var glyphs: ({})
    readonly property color accent: Theme.readableAccent(root.v.accent)
    readonly property var receipt: ((player.buttons || []).filter(b => (b.feedback || {}).text)[0] || {}).feedback || ({})
    readonly property real rankY: 120 + Theme.px(42)
    readonly property real statusY: rankY + Theme.px(26) + 8
    readonly property real actionsY: statusY + Theme.px(26) + 8
    readonly property real actionHeight: Math.max(40, Theme.px(20) + 20)
    readonly property real shortcutY: actionsY + actionHeight + 12
    height: player.focused ? shortcutY + Theme.px(26) + 10 : Math.max(278, statusY + Theme.px(26) + 16)
    radius: 10; color: Theme.card
    border.width: player.focused ? Theme.focusWidth : player.own ? 2 : 1
    border.color: player.focused ? Theme.focus : player.own ? accent : Theme.border
    property real selectionScale: player.focused || hover.hovered ? 1.018 : 1
    scale: root.reducedMotion ? 1 : selectionScale
    z: player.focused ? 2 : 0
    Behavior on selectionScale { enabled: !card.root.reducedMotion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    Rectangle {
        anchors.fill: parent; anchors.margins: -5; radius: 14; z: -1
        color: "transparent"; border.width: 5; border.color: card.accent
        opacity: card.player.focused ? 0.22 : hover.hovered ? 0.12 : 0
        Behavior on opacity { enabled: !card.root.reducedMotion; NumberAnimation { duration: 140 } }
    }
    Item {
        x: 3; y: 3; width: parent.width - 6; height: 160; clip: true
        Rectangle { anchors.fill: parent; color: card.player.own ? "#36302D" : "#232B34" }
        Image { anchors.fill: parent; source: card.player.face || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true; mipmap: true; visible: !!source }
        Text {
            visible: !card.player.face; anchors.right: parent.right; anchors.rightMargin: 22; y: 0
            width: parent.width - 44; height: 150; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText; text: (card.player.name || "?").substring(0, 1).toUpperCase()
            color: card.player.own ? "#78604D" : "#435363"; font.family: card.root.display; font.pixelSize: Theme.px(120); font.weight: Font.Black
            fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(50)
            Accessible.ignored: true
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient { GradientStop { position: 0; color: "#080E0F11" } GradientStop { position: 1; color: Theme.card } }
        }
        Rectangle {
            visible: !!card.player.own; x: 14; y: 12; width: ownLabel.implicitWidth + 20; height: 28; radius: 4; color: card.accent
            Text { id: ownLabel; anchors.centerIn: parent; textFormat: Text.PlainText; text: card.labels.you || ""; font.family: card.root.sans; font.weight: Font.Bold; font.pixelSize: Theme.px(16); color: Theme.ground }
        }
        Text { anchors.right: parent.right; anchors.rightMargin: 14; y: 16; width: parent.width * 0.6; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; textFormat: Text.PlainText; text: card.player.main || ""; color: Theme.text; font.family: card.root.sans; font.pixelSize: Theme.px(16) }
        Text { objectName: "onlineAreaLanguage"; visible: !!text; x: 18; y: 48; width: parent.width - 36; textFormat: Text.PlainText; text: card.player.areaLanguage || ""; elide: Text.ElideRight; color: Theme.muted; font.family: card.root.mono; font.pixelSize: Theme.px(16) }
    }
    Text {
        x: 18; y: 116; width: parent.width - 36; height: Theme.px(42)
        textFormat: Text.PlainText; text: card.player.name || ""; elide: Text.ElideRight
        color: Theme.text; font.family: card.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(32)
    }
    Row {
        x: 18; y: card.rankY; spacing: 8; height: Theme.px(26)
        Image { visible: !!card.player.plate; source: card.player.plate || ""; width: 44; height: 26; fillMode: Image.PreserveAspectFit; asynchronous: true }
        Text { width: Math.max(50, card.width - 210 - (card.player.plate ? 52 : 0)); elide: Text.ElideRight; textFormat: Text.PlainText; text: card.player.rank || ""; color: card.accent; font.family: card.root.sans; font.pixelSize: Theme.px(18) }
        PeerPing { connection: Object.assign({}, card.player.connection || {}, {path: ""}); ink: Theme.text; dim: Theme.border }
    }
    Row {
        visible: !card.receipt.text
        x: 18; y: card.statusY; spacing: 9; width: parent.width - 36
        Rectangle { width: 7; height: 7; radius: 4; color: card.player.own ? card.accent : Theme.success; anchors.verticalCenter: parent.verticalCenter }
        Text { width: parent.width - 16; textFormat: Text.PlainText; text: card.player.status || ""; elide: Text.ElideRight; color: Theme.muted; font.family: card.root.sans; font.pixelSize: Theme.px(17) }
    }
    ActionReceipt { x: 18; y: card.statusY; width: parent.width - 36; receipt: card.receipt; maximumLineCount: 1; elide: Text.ElideRight }
    HoverHandler { id: hover }
    TapHandler { id: select; onTapped: card.root.backend.focusOnlineRow(card.player.index) }
    Interaction { handler: select; selected: !!card.player.focused; name: [card.player.name, card.player.rank, card.player.status].join(". "); onActivated: card.root.backend.focusOnlineRow(card.player.index) }
    Row {
        visible: !!card.player.focused; x: 12; y: card.actionsY; spacing: 6; width: parent.width - 24; z: 21
        Repeater {
            model: card.player.buttons || []
            ArcadeAction {
                required property var modelData
                root: card.root; b: modelData
                width: (card.width - 24 - Math.max(0, (card.player.buttons || []).length - 1) * 6) / Math.max(1, (card.player.buttons || []).length)
                height: card.actionHeight
                glyph: card.glyphs[modelData.id && modelData.id.indexOf("profile") === 0 ? "y" : modelData.id && modelData.id.indexOf("watch") >= 0 ? "x" : "a"] || ({})
                onActivated: card.root.backend.clickRow(b.index)
            }
        }
    }
    Row {
        visible: !!card.player.focused; x: 14; y: card.shortcutY; width: parent.width - 28; spacing: 10; z: 21
        Repeater {
            model: [
                {action: "back", glyph: "b", label: ((card.root.v.prompts || []).filter(p => p.action === "back")[0] || {}).label || card.labels.close},
                {action: "x", glyph: "x", label: (card.root.v.online.chat || {}).title || "", show: !(card.player.buttons || []).some(b => b.id.indexOf("watch") >= 0)},
                {action: "play", glyph: "more", label: card.labels.more}
            ].filter(p => p.show !== false)
            Item {
                id: shortcut
                required property var modelData
                width: (card.width - 48) / 3; height: Theme.px(26)
                Glyph { id: shortcutGlyph; objectName: "arcadeShortcutGlyph"; g: card.glyphs[shortcut.modelData.glyph] || ({}); size: 22 }
                Text { objectName: "arcadeShortcutLabel"; x: shortcutGlyph.width + 8; width: parent.width - x; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: shortcut.modelData.label || ""; elide: Text.ElideRight; color: Theme.muted; font.family: card.root.sans; font.pixelSize: Theme.px(16) }
                TapHandler { id: shortcutTap; onTapped: card.root.backend.press(shortcut.modelData.action) }
                Interaction { handler: shortcutTap; name: shortcut.modelData.label || ""; onActivated: card.root.backend.press(shortcut.modelData.action) }
            }
        }
    }
}
