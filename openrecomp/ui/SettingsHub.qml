import QtQuick

// The Settings section as grouped cards (nav_settings_page): group headers with a one-line note, compact rows that
// show their value, the focused setting's description and every choice at the right.
Item {
    id: page
    required property var root
    readonly property var s: root.v.settingsPage || ({})
    readonly property var d: s.detail || ({})
    readonly property var acc: root.v.accent
    readonly property color card: "#16181C"
    readonly property color ink: "#0E0F11"
    function list(a) { return a || [] }

    // the groups, as a strip: where the focus is, and how many there are
    Row {
        x: 24; y: 18; spacing: 8
        Repeater {
            model: page.list(page.s.groups).length
            Rectangle {
                id: groupTab
                required property int index
                readonly property var gr: page.root.ok(page.s.groups, index)
                width: groupText.implicitWidth + 28; height: 40; radius: 20
                color: gr.active ? page.acc : "transparent"; border.width: gr.active ? 0 : 1; border.color: page.root.line
                Text { id: groupText; anchors.centerIn: parent; textFormat: Text.PlainText; text: groupTab.gr.label || ""; color: groupTab.gr.active ? page.ink : page.root.muted; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 19 }
            }
        }
    }

    Rectangle {
        id: list
        objectName: "settingsList"
        x: 24; y: 74; width: 1120; height: page.height - y - 16
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        Column {
            x: 20; y: 8; width: parent.width - 40
            Repeater {
                model: page.list(page.s.lines).length
                Item {
                    id: line
                    required property int index
                    readonly property var l: page.root.ok(page.s.lines, index)
                    width: parent.width
                    height: l.kind === "group" ? 74 : 56
                    // group header: name + what it is about
                    Item {
                        visible: line.l.kind === "group"
                        anchors.fill: parent
                        Text { y: 18; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 32 }
                        Text { y: 52; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.note || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 17 }
                    }
                    // a setting: label + short description left, the value right
                    Rectangle {
                        visible: line.l.kind === "setting"
                        anchors.fill: parent; anchors.topMargin: 2; anchors.bottomMargin: 2
                        color: line.l.focused ? page.root.bone : "#1C1E23"
                        opacity: line.l.disabled ? 0.5 : 1
                        Rectangle { visible: !!line.l.focused; width: 5; height: parent.height; color: page.acc }
                        Text {
                            x: 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.5
                            elide: Text.ElideRight; textFormat: Text.PlainText; text: line.l.label || ""
                            color: line.l.focused ? page.ink : page.root.textC; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: 23
                        }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                            Text {
                                visible: !!line.l.value
                                width: Math.min(implicitWidth, list.width * 0.42); elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter
                                textFormat: Text.PlainText; text: line.l.cycler ? "‹  " + (line.l.value || "") + "  ›" : (line.l.value || "")
                                color: line.l.focused ? page.ink : page.acc; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 21
                            }
                            Text { visible: !!line.l.verb; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: line.l.verb || ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 20 }
                            Glyph { visible: !!line.l.verb; g: page.root.v.confirmInk || ({}); size: 32; anchors.verticalCenter: parent.verticalCenter }
                        }
                        TapHandler { onTapped: page.root.backend.clickRow(line.l.index) }
                    }
                }
            }
        }
        Text { visible: !!page.s.up; x: list.width - 26; y: 4; textFormat: Text.PlainText; text: "▲"; color: page.root.muted; font.pixelSize: 16 }
        Text { visible: !!page.s.down; x: list.width - 26; anchors.bottom: parent.bottom; anchors.bottomMargin: 4; textFormat: Text.PlainText; text: "▼"; color: page.root.muted; font.pixelSize: 16 }
    }

    // the focused setting: what it does, its value, all its choices
    Rectangle {
        objectName: "settingsDetail"
        x: list.x + list.width + 20; y: list.y; width: 1920 - 24 - x; height: list.height
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        Column {
            x: 36; y: 28; width: parent.width - 72; spacing: 10
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.kicker || ""; color: page.acc; font.family: page.root.mono; font.weight: Font.Medium; font.pixelSize: 20 }
            Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 50; lineHeight: 0.95 }
            Text { width: parent.width; visible: text !== ""; wrapMode: Text.Wrap; maximumLineCount: 6; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.d.lead || ""; color: page.root.textC; font.family: page.root.sans; font.pixelSize: 23; lineHeight: 1.1 }
            Item { width: 1; height: 8 }
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
                        Text { id: optionText; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 20); elide: Text.ElideRight; textFormat: Text.PlainText; text: option.o.label || ""; color: option.o.current ? page.ink : page.root.muted; font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: 19 }
                    }
                }
            }
            Repeater {
                model: page.list(page.d.rows).length
                Item {
                    required property int index
                    readonly property var r: page.root.ok(page.d.rows, index)
                    width: parent.width; height: 38
                    Rectangle { width: parent.width; height: 1; color: page.root.line }
                    Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.5; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.r.k || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 20 }
                    Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.48; horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle; textFormat: Text.PlainText; text: parent.r.v || ""; color: page.root.textC; font.family: page.root.mono; font.pixelSize: 20 }
                }
            }
        }
    }
}
