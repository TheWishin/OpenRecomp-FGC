import QtQuick

// Pad bindings (nav_controls_page): a tab per controller, the game's actions in Tekken notation with the button that
// does each one, the focused row's detail at the right and the live input along the bottom.
Item {
    id: page
    required property var root
    readonly property var b: root.v.bindingsPage || ({})
    readonly property var d: b.detail || ({})
    readonly property var t: b.test || ({})
    readonly property color acc: root.v.accent
    readonly property color card: "#16181C"
    readonly property color ink: "#0E0F11"
    function list(a) { return a || [] }
    function arrow(n) { return ({ UP: "↑", DOWN: "↓", LEFT: "←", RIGHT: "→" })[n] || n }

    // ---------------------------------------------------------------- one tab per controller
    Row {
        id: tabs
        objectName: "bindingsTabs"
        x: 24; y: 16; spacing: 10
        Repeater {
            model: page.list(page.b.tabs).length
            Rectangle {
                id: tab
                required property int index
                readonly property var tb: page.root.ok(page.b.tabs, index)
                width: Math.min(440, tabLabel.implicitWidth + tabType.implicitWidth + 64); height: 60; radius: 6
                color: tb.active ? page.root.bone : "#1C1E23"
                border.width: tb.active ? 0 : 1; border.color: page.root.line
                opacity: tb.disabled && !tb.active ? 0.6 : 1
                Rectangle { visible: !!tab.tb.active; anchors.bottom: parent.bottom; width: parent.width; height: 5; color: page.acc }
                Column {
                    x: 20; anchors.verticalCenter: parent.verticalCenter
                    Text { id: tabLabel; width: Math.min(implicitWidth, 380); elide: Text.ElideRight; textFormat: Text.PlainText; text: tab.tb.label || ""; color: tab.tb.active ? page.ink : page.root.textC; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(22) }
                    Text { id: tabType; textFormat: Text.PlainText; text: tab.tb.typeLabel || ""; color: tab.tb.active ? "#3A3D44" : page.root.muted; font.family: page.root.mono; font.pixelSize: Theme.px(15) }
                }
                TapHandler { onTapped: page.root.backend.clickChapter(tab.tb.id) }
            }
        }
    }

    // ---------------------------------------------------------------- actions and settings
    Rectangle {
        id: listBox
        objectName: "bindingsList"
        x: 24; y: 92; width: 1140; height: 600
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        Column {
            x: 16; y: 10; width: parent.width - 32
            Repeater {
                model: page.list(page.b.lines).length
                Item {
                    id: line
                    required property int index
                    readonly property var l: page.root.ok(page.b.lines, index)
                    readonly property bool slot: l.kind === "slot"
                    width: parent.width; height: l.kind === "group" ? 44 : 48
                    Text {
                        visible: line.l.kind === "group"
                        y: 12; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""
                        color: page.root.muted; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(22)
                    }
                    Rectangle {
                        objectName: line.slot ? "bindingsSlot" : "bindingsSetting"
                        visible: line.l.kind !== "group"
                        anchors.fill: parent; anchors.topMargin: 2; anchors.bottomMargin: 2
                        color: line.l.focused ? page.root.bone : (line.l.lit ? Qt.darker(page.acc, 1.9) : "#1C1E23")
                        border.width: line.l.lit ? 2 : 0; border.color: page.acc
                        opacity: line.l.disabled ? 0.5 : 1
                        Rectangle { visible: !!line.l.focused; width: 5; height: parent.height; color: page.acc }
                        // the action in Tekken notation
                        Rectangle {
                            id: chip
                            visible: line.slot
                            x: 16; anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(56, notation.implicitWidth + 20); height: 34; radius: 4
                            color: line.l.lit ? page.acc : (line.l.focused ? page.ink : "#2A2D33")
                            Text { id: notation; anchors.centerIn: parent; textFormat: Text.PlainText; text: page.arrow(line.l.notation || ""); color: line.l.lit ? page.ink : (line.l.focused ? page.root.bone : page.root.textC); font.family: page.root.mono; font.weight: Font.Bold; font.pixelSize: Theme.px(20) }
                        }
                        Text {
                            x: line.slot ? chip.x + Math.max(80, chip.width) + 18 : 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.62 - x
                            elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""
                            color: line.l.focused ? page.ink : page.root.textC; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(22)
                        }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 10
                            // a setting: its value
                            Text {
                                visible: !line.slot && !!line.l.value
                                width: Math.min(implicitWidth, listBox.width * 0.4); elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter
                                textFormat: Text.PlainText; text: line.l.cycler ? "‹  " + (line.l.value || "") + "  ›" : (line.l.value || "")
                                color: line.l.focused ? page.ink : page.acc; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(20)
                            }
                            // an action: the buttons that do it, as the controller draws them
                            Repeater {
                                model: line.slot ? Math.min(4, page.list(line.l.glyphs).length) : 0
                                PadGlyph { required property int index; g: page.root.ok(line.l.glyphs, index); size: 38; anchors.verticalCenter: parent.verticalCenter }
                            }
                            Text {
                                visible: line.slot && page.list(line.l.glyphs).length === 0
                                anchors.verticalCenter: parent.verticalCenter
                                textFormat: Text.PlainText; text: line.l.value || ""; color: line.l.focused ? "#5A5D64" : page.root.muted
                                font.family: page.root.sans; font.italic: true; font.pixelSize: Theme.px(19)
                            }
                            Text { visible: !!line.l.verb; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: line.l.verb || ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(19) }
                            Glyph { visible: !!line.l.verb; g: page.root.v.confirmInk || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
                        }
                        TapHandler { onTapped: page.root.backend.clickRow(line.l.index) }
                    }
                }
            }
        }
        Text { visible: !!page.b.up; x: listBox.width - 26; y: 2; textFormat: Text.PlainText; text: "▲"; color: page.root.muted; font.pixelSize: Theme.px(16) }
        Text { visible: !!page.b.down; x: listBox.width - 26; anchors.bottom: parent.bottom; anchors.bottomMargin: 2; textFormat: Text.PlainText; text: "▼"; color: page.root.muted; font.pixelSize: Theme.px(16) }
    }

    // ---------------------------------------------------------------- the focused row
    Rectangle {
        objectName: "bindingsDetail"
        x: listBox.x + listBox.width + 20; y: listBox.y; width: 1920 - 24 - x; height: listBox.height
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        Column {
            x: 36; y: 28; width: parent.width - 72; spacing: 12
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.kicker || ""; color: page.acc; font.family: page.root.mono; font.weight: Font.Medium; font.pixelSize: Theme.px(20) }
            Row {
                spacing: 18
                Rectangle {
                    visible: !!page.d.slot
                    width: Math.max(84, bigNotation.implicitWidth + 28); height: 84; radius: 6; color: page.acc
                    anchors.verticalCenter: parent.verticalCenter
                    Text { id: bigNotation; anchors.centerIn: parent; textFormat: Text.PlainText; text: page.arrow(page.d.notation || ""); color: page.ink; font.family: page.root.mono; font.weight: Font.Black; font.pixelSize: Theme.px(40) }
                }
                Text {
                    width: 712 - 72 - (page.d.slot ? bigNotation.implicitWidth + 60 : 0)
                    anchors.verticalCenter: parent.verticalCenter
                    wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.title || ""
                    color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(46); lineHeight: 0.95
                }
            }
            Text { width: parent.width; visible: text !== ""; wrapMode: Text.Wrap; maximumLineCount: 5; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.lead || ""; color: page.root.textC; font.family: page.root.sans; font.pixelSize: Theme.px(22); lineHeight: 1.1 }
            // the buttons that do the focused action, large
            Flow {
                visible: !!page.d.slot
                width: parent.width; spacing: 16; topPadding: 10
                Repeater {
                    model: page.list(page.d.glyphs).length
                    PadGlyph { required property int index; g: page.root.ok(page.d.glyphs, index); size: 92 }
                }
                Text {
                    visible: page.list(page.d.glyphs).length === 0
                    textFormat: Text.PlainText; text: page.b.unbound || ""; color: page.root.muted; font.family: page.root.sans; font.italic: true; font.pixelSize: Theme.px(26)
                }
            }
            Flow {
                width: parent.width; spacing: 8
                visible: page.list(page.d.options).length > 0
                Repeater {
                    model: page.list(page.d.options).length
                    Rectangle {
                        id: option
                        required property int index
                        readonly property var o: page.root.ok(page.d.options, index)
                        width: Math.min(optionText.implicitWidth + 28, parent.width); height: 40; radius: 4
                        color: o.current ? page.acc : "transparent"; border.width: o.current ? 0 : 1; border.color: page.root.line
                        Text { id: optionText; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 20); elide: Text.ElideRight; textFormat: Text.PlainText; text: option.o.label || ""; color: option.o.current ? page.ink : page.root.muted; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(19) }
                    }
                }
            }
        }
        // what this controller is and which layout it has
        Column {
            x: 36; anchors.bottom: parent.bottom; anchors.bottomMargin: 24; width: parent.width - 72; spacing: 4
            Rectangle { width: parent.width; height: 1; color: page.root.line }
            Text { topPadding: 10; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.b.typeLabel || ""; color: page.root.muted; font.family: page.root.mono; font.pixelSize: Theme.px(18) }
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.b.preset || ""; color: page.root.textC; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(22) }
        }
    }

    // ---------------------------------------------------------------- live input, in Tekken notation
    Rectangle {
        objectName: "bindingsInput"
        x: 24; y: listBox.y + listBox.height + 16; width: 1920 - 48; height: page.height - y - 16
        color: page.t.active ? "#20232A" : page.card
        border.width: page.t.active ? 3 : 1; border.color: page.t.active ? page.acc : page.root.line
        Text {
            x: 28; anchors.verticalCenter: parent.verticalCenter; width: 220
            textFormat: Text.PlainText; text: page.t.label || ""; color: page.acc
            font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(34)
        }
        Text {
            objectName: "bindingsNotation"
            x: 260; anchors.verticalCenter: parent.verticalCenter; width: 900; elide: Text.ElideRight
            textFormat: Text.PlainText; text: page.t.notation || page.t.idle || ""
            color: page.t.notation ? page.root.textC : page.root.muted
            font.family: page.root.mono; font.weight: Font.Bold; font.pixelSize: Theme.px(page.t.notation ? 54 : 30)
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 28; anchors.verticalCenter: parent.verticalCenter; width: 660
            horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
            textFormat: Text.PlainText; text: page.t.hint || ""; color: page.t.active ? page.root.textC : page.root.muted
            font.family: page.root.sans; font.pixelSize: Theme.px(20)
        }
    }
}
