import QtQuick

// Online before the lobby and around a match (log in, guest, searching, match found, result): one card with the
// status as its title and message, text fields and actions as compact rows, the focused row's details at the right.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var d: o.detail || ({})
    readonly property var acc: root.v.accent
    readonly property color card: "#16181C"
    readonly property color ink: "#0E0F11"
    function list(a) { return a || [] }

    Rectangle {
        id: card
        objectName: "onlineCard"
        x: 24; y: 18; width: 1100; height: page.height - y - 16
        color: page.card; border.width: 1; border.color: page.o.statusFocused ? page.acc : page.root.line
        clip: true
        Rectangle { width: 6; height: 96; y: 28; color: page.acc }
        Column {
            id: cardHeader
            x: 36; y: 22; width: parent.width - 72; spacing: 4
            Text { objectName: "onlineCardTitle"; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.o.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 52 }
            Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.o.message || ""; color: page.o.error ? page.acc : page.root.muted; font.family: page.root.sans; font.weight: page.o.error ? Font.DemiBold : Font.Normal; font.pixelSize: 21 }
            PeerPing { visible: !!page.o.connection; connection: page.o.connection || ({}); ink: page.root.textC; dim: page.root.muted }
        }
        TapHandler { onTapped: if (page.o.statusIndex >= 0) page.root.backend.clickRow(page.o.statusIndex) }
        Column {
            objectName: "onlineCardRows"
            x: 28; y: Math.max(150, cardHeader.y + cardHeader.implicitHeight + 16); width: parent.width - 56
            Repeater {
                model: page.list(page.o.lines).length
                Item {
                    id: line
                    required property int index
                    readonly property var l: page.root.ok(page.o.lines, index)
                    width: parent.width; height: l.kind === "heading" ? 42 : (l.kind === "field" ? 54 : 46)
                    Text {
                        visible: line.l.kind === "heading"
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 6; width: parent.width; elide: Text.ElideRight
                        textFormat: Text.PlainText; text: line.l.label || ""; color: page.root.muted
                        font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 18; font.capitalization: Font.AllUppercase
                    }
                    // a text field: its name above-left, the typed value in a box
                    Rectangle {
                        visible: line.l.kind === "field"
                        anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: 3
                        color: line.l.focused ? page.root.bone : "#0E0F11"; border.width: 1; border.color: line.l.focused ? page.acc : page.root.line
                        Text { x: 16; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.32; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""; color: line.l.focused ? page.ink : page.root.muted; font.family: page.root.sans; font.pixelSize: 20 }
                        Text { x: parent.width * 0.34; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.5; elide: Text.ElideLeft; textFormat: Text.PlainText; text: line.l.value || ""; color: line.l.focused ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: 21 }
                        Text { visible: !!line.l.verb; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: line.l.verb || ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 19 }
                        TapHandler { onTapped: page.root.backend.clickRow(line.l.index) }
                    }
                    // an action
                    Rectangle {
                        visible: line.l.kind === "row"
                        anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: 3
                        color: line.l.focused ? page.root.bone : "#1C1E23"
                        opacity: line.l.disabled ? 0.5 : 1
                        Rectangle { visible: !!line.l.focused; width: 5; height: parent.height; color: page.acc }
                        Text { x: 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.6; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""; color: line.l.focused ? page.ink : page.root.textC; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: 22 }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                            Text { visible: !!line.l.value; width: Math.min(implicitWidth, card.width * 0.32); elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: line.l.cycler ? "‹  " + (line.l.value || "") + "  ›" : (line.l.value || ""); color: line.l.focused ? page.ink : page.acc; font.family: page.root.mono; font.pixelSize: 19 }
                            Text { visible: !!line.l.verb; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: line.l.verb || ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 19 }
                            Glyph { visible: !!line.l.verb; g: page.root.v.confirmInk || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
                        }
                        TapHandler { onTapped: page.root.backend.clickRow(line.l.index) }
                    }
                }
            }
        }
        Text { visible: !!page.o.up; x: card.width - 26; y: 140; textFormat: Text.PlainText; text: "▲"; color: page.root.muted; font.pixelSize: 16 }
        Text { visible: !!page.o.down; x: card.width - 26; anchors.bottom: parent.bottom; anchors.bottomMargin: 4; textFormat: Text.PlainText; text: "▼"; color: page.root.muted; font.pixelSize: 16 }
    }

    Rectangle {
        objectName: "onlineCardDetail"
        x: card.x + card.width + 20; y: card.y; width: 1920 - 24 - x; height: card.height
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        Column {
            x: 32; y: 28; width: parent.width - 64; spacing: 10
            Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 40 }
            Text { width: parent.width; visible: text !== ""; wrapMode: Text.Wrap; maximumLineCount: 8; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.lead || ""; color: page.root.textC; font.family: page.root.sans; font.pixelSize: 21; lineHeight: 1.1 }
            Item { width: 1; height: 6 }
            Repeater {
                model: page.list(page.d.rows).length
                Item {
                    required property int index
                    readonly property var r: page.root.ok(page.d.rows, index)
                    width: parent.width; height: 38
                    Rectangle { width: parent.width; height: 1; color: page.root.line }
                    Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.5; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.r.k || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 19 }
                    Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.48; horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle; textFormat: Text.PlainText; text: parent.r.v || ""; color: parent.r.accent ? page.acc : page.root.textC; font.family: page.root.mono; font.pixelSize: 19 }
                }
            }
        }
    }
}
