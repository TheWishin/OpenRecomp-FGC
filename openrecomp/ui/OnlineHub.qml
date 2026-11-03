import QtQuick

// The Online section's lobby page: profile card + find-opponent card on top, chapters below, the chat panel at the
// right on every chapter. Everything shown comes from v.online (nav_online_layout); a click is the row's index.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online
    readonly property var prof: o.profile || ({})
    readonly property var fnd: o.find || ({})
    readonly property var acc: root.v.accent
    readonly property bool chatOpen: !!o.chatOpen
    readonly property int gap: 16
    readonly property int topH: 226
    readonly property int chatW: chatOpen ? 520 : 76
    readonly property color card: "#16181C"
    readonly property color raised: "#202328"
    readonly property color ink: "#0E0F11"

    function click(i) { if (i !== undefined && i >= 0) root.backend.clickRow(i) }
    function list(a) { return a || [] }

    // ---------------------------------------------------------------- a small button / option chip
    component Chip: Rectangle {
        id: chip
        property var b: ({})
        property int fontSize: 22
        property bool strong: false
        height: 44
        width: Math.min(maxW, chipRow.implicitWidth + 32)
        property int maxW: 420
        radius: 4
        color: b.focused ? page.root.bone : (strong ? page.raised : "transparent")
        border.width: b.focused ? 0 : 1
        border.color: page.root.line
        opacity: b.disabled ? 0.45 : 1
        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 10
            Text {
                textFormat: Text.PlainText; text: chip.b.label || ""
                width: Math.min(implicitWidth, chip.maxW - 40 - (chipValue.visible ? chipValue.width + 10 : 0)); elide: Text.ElideRight
                color: chip.b.focused ? page.ink : page.root.textC
                font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: chip.fontSize
            }
            Text {
                id: chipValue
                visible: !!chip.b.value
                textFormat: Text.PlainText; text: chip.b.cycler ? "‹ " + (chip.b.value || "") + " ›" : (chip.b.value || "")
                width: Math.min(implicitWidth, 220); elide: Text.ElideRight
                color: chip.b.focused ? page.ink : page.acc
                font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: chip.fontSize - 2
            }
        }
        TapHandler { onTapped: page.click(chip.b.index) }
    }

    // ================================================================ profile card: who you are, your ranked standing
    Rectangle {
        id: profile
        objectName: "onlineProfile"
        x: 24; y: 14; width: 640; height: page.topH
        color: page.card; border.width: 1; border.color: page.prof.focused ? page.acc : page.root.line
        Rectangle {
            id: face
            x: 16; y: 16; width: 112; height: 144; color: "#24272C"; clip: true
            Image { anchors.fill: parent; source: page.prof.face || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectCrop; visible: !!page.prof.face }
            Text {
                visible: !page.prof.face
                anchors.centerIn: parent; textFormat: Text.PlainText
                text: (page.prof.name || "?").substring(0, 1).toUpperCase()
                color: page.root.muted; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: 72
            }
            Rectangle {
                visible: !!page.prof.main
                anchors.bottom: parent.bottom; width: parent.width; height: 24; color: "#CC0E0F11"
                Text { anchors.centerIn: parent; width: parent.width - 8; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.main || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 17 }
            }
        }
        Column {
            x: 144; y: 10; width: parent.width - 160; spacing: 3
            Text { objectName: "profileName"; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.name || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: 36 }
            Row {
                spacing: 10; height: 28
                Image { visible: !!page.prof.plate; source: page.prof.plate || ""; height: 26; width: 52; fillMode: Image.PreserveAspectFit; asynchronous: true; anchors.verticalCenter: parent.verticalCenter }
                Text { textFormat: Text.PlainText; text: page.prof.rank || ""; color: page.acc; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 21; anchors.verticalCenter: parent.verticalCenter }
                Text { textFormat: Text.PlainText; text: page.list(page.prof.rows).join("  ·  "); color: page.root.textC; font.family: page.root.mono; font.pixelSize: 19; anchors.verticalCenter: parent.verticalCenter }
            }
            // progress to the next rank (or through the placement matches)
            Item {
                visible: (page.prof.progress === undefined ? -1 : page.prof.progress) >= 0
                width: parent.width; height: 26
                Rectangle {
                    y: 9; width: parent.width * 0.55; height: 8; radius: 4; color: "#2A2D32"
                    Rectangle { height: parent.height; radius: 4; width: parent.width * Math.max(0, page.prof.progress || 0); color: page.acc }
                }
                Text { x: parent.width * 0.55 + 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.45 - 12; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.progressText || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 17 }
            }
            Row {
                visible: page.list(page.prof.recent).length > 0
                spacing: 4; height: 26
                Text { textFormat: Text.PlainText; text: page.prof.recentLabel || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 16; anchors.verticalCenter: parent.verticalCenter; rightPadding: 6 }
                Repeater {
                    model: page.list(page.prof.recent).length
                    Rectangle {
                        id: result
                        required property int index
                        readonly property var c: page.root.ok(page.prof.recent, index)
                        width: 24; height: 24; color: c.win ? page.acc : "transparent"; border.width: 1; border.color: c.win ? page.acc : "#6B6E75"
                        Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: result.c.text || ""; color: result.c.win ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: 13 }
                    }
                }
            }
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.list(page.prof.conn).join("  ·  "); color: page.root.muted; font.family: page.root.sans; font.pixelSize: 17 }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 12; spacing: 8
            Repeater {
                model: page.list(page.prof.buttons).length
                Chip { required property int index; b: page.root.ok(page.prof.buttons, index); maxW: 170; fontSize: 17; height: 34 }
            }
        }
        TapHandler { onTapped: page.click(page.prof.index) }
    }

    // ================================================================ find an opponent
    Rectangle {
        id: find
        objectName: "onlineFind"
        x: profile.x + profile.width + 16; y: 14; width: 1920 - 24 - x; height: page.topH
        color: page.card; border.width: 1; border.color: page.root.line
        Text { x: 20; y: 10; textFormat: Text.PlainText; text: page.o.findTitle || ""; color: page.root.muted; font.family: page.root.mono; font.weight: Font.Medium; font.pixelSize: 17; font.capitalization: Font.AllUppercase }
        Row {
            x: 20; y: 36; spacing: 12
            Repeater {
                model: [page.fnd.ranked || ({}), page.fnd.quick || ({})]
                Item {
                    id: big
                    required property var modelData
                    required property int index
                    readonly property var b: modelData || ({})
                    width: (find.width - 40 - 12) / 2; height: 74
                    visible: !!b.present
                    Rectangle {
                        width: parent.width; height: 50
                        color: big.b.focused ? page.root.bone : (big.index === 0 ? page.acc : page.raised)
                        border.width: big.index === 0 || big.b.focused ? 0 : 1; border.color: page.root.line
                        opacity: big.b.disabled ? 0.45 : 1
                        Text {
                            anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                            textFormat: Text.PlainText; text: big.b.label || ""
                            color: big.b.focused || big.index === 0 ? page.ink : page.root.textC
                            font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 32
                        }
                        TapHandler { onTapped: page.click(big.b.index) }
                    }
                    Text {
                        y: 54; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText
                        text: big.index === 0 ? (page.fnd.rankedNote || "") : (page.fnd.quickNote || "")
                        color: page.root.muted; font.family: page.root.sans; font.pixelSize: 16
                    }
                }
            }
        }
        // the options: character, health, strict, side, delay, first to, stage ...
        Flow {
            x: 20; y: 110; width: find.width - 40; height: page.topH - 110 - 6; spacing: 5; clip: true
            Repeater {
                model: page.list(page.fnd.options).length
                Chip { required property int index; b: page.root.ok(page.fnd.options, index); maxW: 380; fontSize: 16; height: 31 }
            }
            Repeater {
                model: page.list(page.fnd.extra).length
                Chip { required property int index; b: page.root.ok(page.fnd.extra, index); maxW: 340; fontSize: 16; height: 31 }
            }
        }
        // an incoming challenge sits over the options until it is answered
        Rectangle {
            visible: !!page.fnd.incoming
            x: 20; y: 110; width: find.width - 40; height: page.topH - 110 - 10; color: page.acc
            Text { x: 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width - incomingRow.width - 50; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.fnd.incoming ? page.fnd.incoming.text : ""; color: page.ink; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 30 }
            Row {
                id: incomingRow
                anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                Repeater {
                    model: page.fnd.incoming ? page.list(page.fnd.incoming.buttons).length : 0
                    Chip { required property int index; b: page.root.ok(page.fnd.incoming.buttons, index); strong: true; maxW: 240; height: 36; fontSize: 18 }
                }
            }
        }
    }

    // ================================================================ chapters
    Item {
        id: chapters
        objectName: "onlineChapters"
        x: 24; y: 14 + page.topH + 10; width: 1920 - 48 - page.chatW - page.gap; height: 46
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 4
            Glyph { g: page.o.prevG || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
            Item { width: 8; height: 1 }
            Repeater {
                model: page.list(page.o.chapters).length
                Rectangle {
                    id: tab
                    required property int index
                    readonly property var c: page.root.ok(page.o.chapters, index)
                    width: tabRow.implicitWidth + 28; height: 46
                    color: "transparent"
                    Row {
                        id: tabRow
                        anchors.centerIn: parent; spacing: 10
                        Text { textFormat: Text.PlainText; text: tab.c.label || ""; color: tab.c.active ? page.root.textC : page.root.muted; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 26; anchors.verticalCenter: parent.verticalCenter }
                        Rectangle {
                            visible: !!tab.c.badge
                            width: Math.max(28, badgeText.implicitWidth + 12); height: 26; radius: 13; color: tab.c.active ? page.acc : "#2A2D32"
                            anchors.verticalCenter: parent.verticalCenter
                            Text { id: badgeText; anchors.centerIn: parent; textFormat: Text.PlainText; text: tab.c.badge || ""; color: tab.c.active ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: 16 }
                        }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: page.acc; visible: !!tab.c.active }
                    TapHandler { onTapped: page.root.backend.clickChapter(tab.c.id) }
                }
            }
            Item { width: 8; height: 1 }
            Glyph { g: page.o.nextG || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: page.root.line }
    }

    // ================================================================ the chapter's body
    Rectangle {
        id: body
        objectName: "onlineBody"
        x: 24; y: chapters.y + chapters.height + 12; width: chapters.width; height: page.height - y - 16
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        readonly property var b: page.o.body || ({})
        readonly property bool hasDetail: !!b.detail
        readonly property int tableW: width - 40 - (hasDetail ? 440 : 0)
        Text { visible: !!body.b.empty; anchors.centerIn: parent; textFormat: Text.PlainText; text: body.b.empty || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 24 }
        Column {
            x: 20; y: 12; width: body.tableW
            Repeater {
                model: page.list(body.b.lines).length
                Item {
                    id: line
                    required property int index
                    readonly property var l: page.root.ok(body.b.lines, index)
                    width: body.tableW
                    height: l.kind === "heading" ? 34 : (l.kind === "thead" ? 30 : (l.kind === "note" ? 30 : 38))
                    // a sub-heading of the chapter
                    Text {
                        visible: line.l.kind === "heading" || line.l.kind === "note"
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 4; width: parent.width; elide: Text.ElideRight
                        textFormat: Text.PlainText; text: line.l.label || ""
                        color: line.l.kind === "note" ? page.root.textC : page.root.muted
                        font.family: line.l.kind === "note" ? page.root.sans : page.root.mono; font.weight: Font.DemiBold
                        font.pixelSize: line.l.kind === "note" ? 21 : 19; font.capitalization: line.l.kind === "heading" ? Font.AllUppercase : Font.MixedCase
                    }
                    // the table's column titles
                    Row {
                        visible: line.l.kind === "thead"
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: line.l.kind === "thead" ? page.list(line.l.cols).length : 0
                            Text { required property int index; readonly property var c: page.root.ok(line.l.cols, index); width: body.tableW * (c.w || 0); elide: Text.ElideRight; leftPadding: 10; textFormat: Text.PlainText; text: c.label || ""; color: page.root.muted; font.family: page.root.mono; font.pixelSize: 17; font.capitalization: Font.AllUppercase }
                        }
                    }
                    Rectangle { visible: line.l.kind === "thead"; anchors.bottom: parent.bottom; width: parent.width; height: 1; color: page.root.line }
                    // a table row: cells, and its buttons when it has the focus
                    Rectangle {
                        visible: line.l.kind === "trow"
                        anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: 1
                        color: line.l.focused ? "#2A2E35" : (line.index % 2 ? "#191B1F" : "transparent")
                        opacity: line.l.dim && !line.l.focused ? 0.55 : 1
                        Rectangle { visible: !!line.l.focused; width: 4; height: parent.height; color: page.acc }
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            Repeater {
                                model: line.l.kind === "trow" ? page.list(line.l.cells).length : 0
                                Item {
                                    id: cell
                                    required property int index
                                    readonly property var c: page.root.ok(line.l.cells, index)
                                    readonly property real w: line.l.kind === "trow" ? page.colW(body.b.lines, line.index, index) : 0
                                    readonly property int nb: c.bars || 0
                                    width: body.tableW * w; height: 36
                                    Row {
                                        x: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                        Row {          // signal bars
                                            visible: cell.nb > 0; spacing: 2; height: 20; anchors.verticalCenter: parent.verticalCenter
                                            Repeater {
                                                model: 4
                                                Rectangle {
                                                    required property int index
                                                    width: 4; height: 6 + index * 4; anchors.bottom: parent.bottom
                                                    color: index < cell.nb ? (cell.nb >= 3 ? "#5FBF6A" : (cell.nb === 2 ? "#D9A441" : "#D9534F")) : "#3A3D42"
                                                }
                                            }
                                        }
                                        Image { visible: !!cell.c.plate; source: cell.c.plate || ""; height: 30; width: 60; fillMode: Image.PreserveAspectFit; asynchronous: true; anchors.verticalCenter: parent.verticalCenter }
                                        Image { visible: !!cell.c.face; source: cell.c.face || ""; height: 32; width: 32; fillMode: Image.PreserveAspectCrop; asynchronous: true; anchors.verticalCenter: parent.verticalCenter }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.max(0, body.tableW * cell.w - 20 - (cell.c.face ? 40 : 0) - (cell.nb > 0 ? 30 : 0) - (cell.c.plate ? 68 : 0))
                                            visible: width > 0 && text !== ""
                                            elide: Text.ElideRight; textFormat: Text.PlainText; text: cell.c.text || ""
                                            color: page.root.textC; font.family: page.root.sans
                                            font.weight: cell.c.bold ? Font.DemiBold : Font.Normal; font.pixelSize: 19
                                        }
                                    }
                                }
                            }
                        }
                        Row {
                            visible: !!line.l.focused
                            anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                            Repeater {
                                model: line.l.kind === "trow" ? page.list(line.l.buttons).length : 0
                                Chip { required property int index; b: page.root.ok(line.l.buttons, index); strong: true; height: 34; fontSize: 18; maxW: 200 }
                            }
                        }
                        TapHandler { onTapped: page.click(line.l.index) }
                    }
                    // a line of buttons
                    Row {
                        visible: line.l.kind === "bar"
                        anchors.verticalCenter: parent.verticalCenter; spacing: 8
                        Repeater {
                            model: line.l.kind === "bar" ? page.list(line.l.buttons).length : 0
                            Chip { required property int index; b: page.root.ok(line.l.buttons, index); height: 38; fontSize: 19; maxW: 320 }
                        }
                    }
                    // one row: label, value, the verb on focus
                    Rectangle {
                        visible: line.l.kind === "row"
                        anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: 1
                        color: line.l.focused ? page.root.bone : "transparent"
                        opacity: line.l.disabled ? 0.5 : 1
                        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.55; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""; color: line.l.focused ? page.ink : page.root.textC; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: 20 }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                            Text { visible: !!line.l.value; width: Math.min(implicitWidth, body.tableW * 0.38); elide: Text.ElideMiddle; textFormat: Text.PlainText; text: line.l.cycler ? "‹ " + (line.l.value || "") + " ›" : (line.l.value || ""); color: line.l.focused ? page.ink : page.root.muted; font.family: page.root.mono; font.pixelSize: 20; anchors.verticalCenter: parent.verticalCenter }
                            Text { visible: !!line.l.verb; textFormat: Text.PlainText; text: line.l.verb || ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 20; anchors.verticalCenter: parent.verticalCenter }
                        }
                        TapHandler { onTapped: page.click(line.l.index) }
                    }
                }
            }
        }
        Text { visible: !!body.b.up; x: body.tableW + 4; y: 4; textFormat: Text.PlainText; text: "▲"; color: page.root.muted; font.pixelSize: 16 }
        Text { visible: !!body.b.down; x: body.tableW + 4; anchors.bottom: parent.bottom; anchors.bottomMargin: 4; textFormat: Text.PlainText; text: "▼"; color: page.root.muted; font.pixelSize: 16 }
        // the focused row's details (profile, leaderboard, statistics, tournaments ...)
        Rectangle {
            visible: body.hasDetail
            x: body.width - 440; width: 440; height: parent.height; color: page.raised
            Column {
                x: 24; y: 20; width: parent.width - 48; spacing: 6
                Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText; text: body.hasDetail ? (body.b.detail.title || "") : ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 36 }
                Text { width: parent.width; visible: text !== ""; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; textFormat: Text.PlainText; text: body.hasDetail ? (body.b.detail.lead || "") : ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 19 }
                Item { width: 1; height: 6 }
                Repeater {
                    model: body.hasDetail ? page.list(body.b.detail.rows).length : 0
                    Item {
                        required property int index
                        readonly property var r: page.root.ok(body.b.detail.rows, index)
                        width: parent.width; height: 32
                        Rectangle { width: parent.width; height: 1; color: page.root.line }
                        Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.55; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.r.k || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 19 }
                        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.44; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.r.v || ""; color: page.root.textC; font.family: page.root.mono; font.pixelSize: 19 }
                    }
                }
            }
        }
    }

    // a table row's column width: from the nearest column titles above it
    function colW(lines, at, col) {
        for (var i = at; i >= 0; i--) {
            var l = lines[i]
            if (l && l.kind === "thead") return (l.cols[col] || {}).w || 0
        }
        return 0
    }

    // ================================================================ the chat panel (every chapter)
    Rectangle {
        id: chat
        objectName: "onlineChat"
        readonly property var c: page.o.chat || ({})
        x: 1920 - 24 - page.chatW; y: chapters.y; width: page.chatW; height: page.height - y - 16
        color: page.card; border.width: 1; border.color: page.o.focusRegion === "chat" ? page.acc : page.root.line
        clip: true
        // closed: a slim strip with the unread count
        Item {
            visible: !page.chatOpen
            anchors.fill: parent
            Rectangle {
                visible: (chat.c.unread || 0) > 0
                anchors.horizontalCenter: parent.horizontalCenter; y: 16; width: 44; height: 44; radius: 22; color: page.acc
                Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: String(chat.c.unread || 0); color: page.ink; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 18 }
            }
            Item {
                x: 0; y: 76; width: parent.width; height: parent.height - 76 - 76
                Text {
                    anchors.centerIn: parent; rotation: 90; width: parent.height; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                    textFormat: Text.PlainText; text: chat.c.title || ""; color: page.root.textC
                    font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 26
                }
            }
            Glyph { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; g: page.o.chatG || ({}); size: 40 }
            TapHandler { onTapped: page.click(chat.c.toggle ? chat.c.toggle.index : -1) }
        }
        Item {
            visible: page.chatOpen
            anchors.fill: parent
            Row {
                id: chatHead
                x: 18; y: 12; spacing: 12; height: 40
                Text { textFormat: Text.PlainText; text: chat.c.title || ""; color: page.root.muted; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 20; font.capitalization: Font.AllUppercase; anchors.verticalCenter: parent.verticalCenter }
                Rectangle {
                    visible: (chat.c.unread || 0) > 0; width: 30; height: 26; radius: 13; color: page.acc; anchors.verticalCenter: parent.verticalCenter
                    Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: String(chat.c.unread || 0); color: page.ink; font.family: page.root.mono; font.pixelSize: 16 }
                }
            }
            Chip { anchors.right: parent.right; anchors.rightMargin: 14; y: 10; b: chat.c.toggle || ({}); height: 36; fontSize: 18; maxW: 200 }
            // tabs: lobby chat and private conversations
            Flow {
                id: chatTabs
                x: 14; y: 58; width: parent.width - 28; spacing: 6
                Repeater {
                    model: page.list(chat.c.tabs).length
                    Chip {
                        required property int index
                        b: page.root.ok(chat.c.tabs, index); height: 34; fontSize: 18; maxW: 220
                        strong: !!b.active
                        Rectangle { visible: !!parent.b.active && !parent.b.focused; anchors.bottom: parent.bottom; width: parent.width; height: 3; color: page.acc }
                    }
                }
            }
            // the conversation, newest at the bottom
            Item {
                id: lines
                x: 14; y: chatTabs.y + chatTabs.height + 10; width: parent.width - 28
                height: compose.y - y - 10 - (otherRow.visible ? otherRow.height + 8 : 0)
                clip: true
                Column {
                    width: parent.width; anchors.bottom: parent.bottom; spacing: 6
                    Repeater {
                        model: page.list(chat.c.lines).length
                        Rectangle {
                            required property int index
                            readonly property var m: page.root.ok(chat.c.lines, index)
                            width: lines.width; height: msg.implicitHeight + 8
                            color: m.focused ? "#2A2E35" : "transparent"
                            Rectangle { visible: !!parent.m.focused; width: 3; height: parent.height; color: page.acc }
                            Column {
                                id: msg
                                x: 8; y: 4; width: parent.width - 16
                                Text { visible: !!parent.parent.m.name; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.m.name || ""; color: parent.parent.m.own ? page.root.textC : page.acc; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 19 }
                                Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.m.text || ""; color: parent.parent.m.system ? page.root.muted : page.root.textC; font.family: page.root.sans; font.pixelSize: 19 }
                            }
                            TapHandler { onTapped: page.click(parent.m.index) }
                        }
                    }
                }
            }
            Flow {
                id: otherRow
                visible: page.list(chat.c.other).length > 0
                x: 14; anchors.bottom: compose.top; anchors.bottomMargin: 8; width: parent.width - 28; spacing: 6
                Repeater {
                    model: page.list(chat.c.other).length
                    Chip { required property int index; b: page.root.ok(chat.c.other, index); height: 32; fontSize: 17; maxW: 230 }
                }
            }
            // text field + Send
            Row {
                id: compose
                x: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 14; spacing: 8
                Rectangle {
                    readonly property var f: chat.c.compose || ({})
                    width: chat.width - 28 - sendChip.width - 8; height: 48
                    color: f.focused ? page.root.bone : "#0E0F11"; border.width: 1; border.color: page.root.line
                    Text {
                        x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 24; elide: Text.ElideLeft; textFormat: Text.PlainText
                        text: parent.f.value || parent.f.label || ""
                        color: parent.f.focused ? page.ink : (parent.f.value ? page.root.textC : page.root.muted)
                        font.family: page.root.sans; font.pixelSize: 20
                    }
                    TapHandler { onTapped: page.click(parent.f.index) }
                }
                Chip { id: sendChip; b: chat.c.send || ({}); height: 48; strong: true; maxW: 230 }
            }
        }
    }
}
