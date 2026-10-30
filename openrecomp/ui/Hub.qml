import QtQuick

// One game: fixed section tabs, the list on the left, the live detail panel on the right.
Column {
    id: hub
    required property var root
    readonly property var v: root.v
    readonly property var d: v.detail

    Rectangle {
        width: 1920; height: 84; color: hub.root.bar
        Rectangle { width: parent.width; height: 1; color: hub.root.line }
        Row {
            anchors.fill: parent
            Item {
                width: 120; height: 84
                Glyph { anchors.centerIn: parent; g: hub.v.prevG }
                TapHandler { onTapped: hub.root.backend.press("prev") }
            }
            Repeater {
                model: hub.v.tabs.length
                Rectangle {
                    required property int index
                    readonly property var t: hub.root.ok(hub.v.tabs, index)
                    width: (1920 - 240) / Math.max(1, hub.v.tabs.length); height: 84
                    color: t.active ? hub.v.accent : "transparent"
                    Text { anchors.centerIn: parent; text: parent.t.label || ""; color: parent.t.active ? "#0E0F11" : hub.root.muted; font.family: hub.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 36 }
                    TapHandler { onTapped: hub.root.backend.clickTab(parent.t.id) }
                }
            }
            Item {
                width: 120; height: 84
                Glyph { anchors.centerIn: parent; g: hub.v.nextG }
                TapHandler { onTapped: hub.root.backend.press("next") }
            }
        }
    }

    Row {
        width: 1920; height: parent.height - 84
        // ---------------------------------------------------------------- the list
        Item {
            width: 760; height: parent.height
            Column {
                y: 16; width: parent.width
                Repeater {
                    model: hub.v.rows.length
                    Item {
                        id: row
                        required property int index
                        readonly property var r: hub.root.ok(hub.v.rows, index)
                        width: 760
                        height: r.heading ? 44 + (r.mt || 0) : (r.focused ? 100 : 84)
                        Behavior on height { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                        Text {
                            visible: !!row.r.heading
                            x: 48; anchors.bottom: parent.bottom
                            text: row.r.label || ""; color: hub.root.muted; font.family: hub.root.mono; font.pixelSize: 22
                        }
                        Rectangle {
                            visible: !row.r.heading
                            anchors.fill: parent
                            color: row.r.focused ? hub.root.bone : "transparent"
                            clip: true
                            Rectangle { height: parent.height; width: parent.width * (row.r.holdPct || 0); color: hub.v.accent }
                            Text {
                                x: 48; anchors.verticalCenter: parent.verticalCenter
                                text: row.r.label || ""
                                color: row.r.focused ? "#0E0F11" : (row.r.hold ? hub.v.accent : (row.r.disabled ? "#8A8D94" : hub.root.textC))
                                font.family: hub.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: row.r.focused ? 52 : 42
                            }
                            Row {
                                anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 16
                                Text {
                                    visible: !!row.r.value; anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, 320); elide: Text.ElideMiddle
                                    text: row.r.value || ""; color: row.r.focused ? "#0E0F11" : (row.r.missing ? hub.v.accent : hub.root.muted); font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 26
                                }
                                Text { visible: !!row.r.verb; anchors.verticalCenter: parent.verticalCenter; text: row.r.verb || ""; color: "#0E0F11"; font.family: hub.root.sans; font.weight: Font.DemiBold; font.pixelSize: 26 }
                                Glyph { visible: !!row.r.verb; g: hub.v.confirmInk; anchors.verticalCenter: parent.verticalCenter }
                            }
                            TapHandler { onTapped: hub.root.backend.clickRow(row.r.index) }
                        }
                    }
                }
            }
            Text { visible: hub.v.more.up; x: 720; y: 2; text: "▲"; color: hub.root.muted; font.pixelSize: 18 }
            Text { visible: hub.v.more.down; x: 720; anchors.bottom: parent.bottom; anchors.bottomMargin: 2; text: "▼"; color: hub.root.muted; font.pixelSize: 18 }
        }

        // ---------------------------------------------------------------- the detail panel
        Rectangle {
            width: 1160; height: parent.height
            color: hub.root.panel
            clip: true
            Text { x: 1160 - implicitWidth - 8; y: -90; text: hub.v.numeral; color: "#1A1C20"; font.family: hub.root.display; font.weight: Font.Black; font.pixelSize: 980 }
            Image {
                visible: !!hub.v.hero && hub.v.tabs.length > 0 && (hub.d.images || []).length === 0 && !hub.d.image
                source: hub.v.hero || ""
                width: 760; height: 760; x: 1160 - 640; y: 30
                opacity: 0.22; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit
            }
            Column {
                x: 72; y: 40; width: 860; spacing: 0
                Text { width: parent.width; text: hub.d.kicker || ""; elide: Text.ElideRight; color: hub.v.accent; font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 24 }
                Text { width: 1016; topPadding: 8; text: hub.d.title || ""; wrapMode: Text.Wrap; lineHeight: 0.95; color: hub.root.textC; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 96 }
                Text { width: parent.width; topPadding: 14; visible: !!hub.d.lead; text: hub.d.lead || ""; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; lineHeight: 1.15; color: hub.root.textC; font.family: hub.root.sans; font.pixelSize: 30 }
                Item { width: 1; height: 16 }
                Row {
                    visible: (hub.d.images || []).length > 0 || !!hub.d.image
                    spacing: 12
                    bottomPadding: 16
                    Repeater {
                        model: (hub.d.images || []).length
                        Rectangle {
                            required property int index
                            width: 140; height: 140; color: "#1B1D21"
                            Image { anchors.fill: parent; source: (hub.d.images || [])[parent.index] || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit }
                        }
                    }
                    Rectangle {
                        visible: !!hub.d.image
                        width: 140; height: 140; color: "#1B1D21"
                        Image { anchors.fill: parent; source: hub.d.image || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit }
                    }
                }
                Rectangle {
                    visible: (hub.d.progress === undefined ? -1 : hub.d.progress) >= 0
                    width: 860; height: 16; color: "#24272C"
                    Rectangle { height: parent.height; width: parent.width * Math.max(0, hub.d.progress === undefined ? 0 : hub.d.progress); color: hub.v.accent }
                }
                Repeater {
                    model: (hub.d.rows || []).length
                    Rectangle {
                        required property int index
                        readonly property var r: hub.root.ok(hub.d.rows, index)
                        width: 860; height: (hub.d.rows || []).length > 5 ? 38 : 50; color: "transparent"
                        Rectangle { width: parent.width; height: 1; color: hub.root.line }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.r.k || ""; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: 26 }
                        Text { anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; text: parent.r.v || ""; color: parent.r.accent ? hub.v.accent : hub.root.textC; font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 26 }
                    }
                }
                Row {
                    visible: (hub.d.results || []).length > 0
                    spacing: 8
                    topPadding: 16
                    Text { text: "Letzte Sets"; width: 160; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: 26; anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: (hub.d.results || []).length
                        ResultCell { required property int index; c: hub.root.ok(hub.d.results, index); accent: hub.v.accent; root: hub.root }
                    }
                }
            }
            Rectangle {
                visible: !!hub.d.primary
                x: 72; y: parent.height - 112 - 32
                width: 860; height: 112
                color: hub.v.accent
                Text { x: 40; anchors.verticalCenter: parent.verticalCenter; text: hub.d.primary || ""; color: "#0E0F11"; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 60 }
                Glyph { anchors.right: parent.right; anchors.rightMargin: 40; anchors.verticalCenter: parent.verticalCenter; size: 56; g: hub.d.primaryG || ({}) }
                TapHandler { onTapped: hub.root.backend.clickPrimary() }
            }
        }
    }
}
