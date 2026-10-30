import QtQuick

// The game shelf: the focused game wide, the others as spines, free slots behind them.
Item {
    id: shelf
    required property var root
    clip: true
    Rectangle { anchors.fill: parent; color: "#000000" }
    Row {
        id: track
        height: parent.height
        spacing: 2
        x: shelf.root.v.shelf.x
        Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Repeater {
            model: shelf.root.v.shelf.tiles.length
            Item {
                id: tile
                required property int index
                readonly property var t: shelf.root.ok(shelf.root.v.shelf.tiles, index)
                width: t.w || 0
                height: track.height
                clip: true
                Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Rectangle { anchors.fill: parent; color: tile.t.focused ? "#15171A" : (tile.t.free ? "#090A0B" : "#0B0C0E") }

                // the numeral, in the game's colour when focused
                Text {
                    text: tile.t.num || ""
                    x: tile.t.focused ? tile.width - implicitWidth - 40 : tile.width - implicitWidth - 12
                    y: tile.t.focused ? (tile.t.free ? 60 : -60) : (tile.t.free ? 300 : 360)
                    color: tile.t.focused ? (tile.t.accent || "#ECE9E1") : "#24272C"
                    font.family: shelf.root.display
                    font.weight: Font.Black
                    font.pixelSize: tile.t.focused ? (tile.t.free ? 620 : 900) : (tile.t.free ? 200 : 420)
                }
                // the player's own game: a fighter in front of the numeral
                Image {
                    visible: tile.t.focused && !!tile.t.hero
                    source: tile.t.hero || ""
                    width: 860; height: 860
                    x: tile.width - 700; y: 0
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    smooth: true
                    mipmap: true
                }
                // keeps the text readable over the picture
                Rectangle {
                    visible: tile.t.focused && !!tile.t.hero
                    width: 660; height: tile.height
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#F515171A" }
                        GradientStop { position: 0.72; color: "#D015171A" }
                        GradientStop { position: 1.0; color: "#0015171A" }
                    }
                }

                Column {
                    x: tile.t.focused ? 64 : 24; y: 48
                    width: tile.t.focused ? 500 : tile.width - 40
                    spacing: 0
                    Rectangle { width: 56; height: 8; color: tile.t.accent || "#ECE9E1" }
                    Item { width: 1; height: 20 }
                    Text {
                        width: parent.width
                        text: tile.t.name || ""
                        wrapMode: Text.Wrap
                        lineHeight: 0.92
                        color: tile.t.focused ? "#ECE9E1" : "#A3A5AB"
                        font.family: shelf.root.display
                        font.weight: Font.Black
                        font.capitalization: Font.AllUppercase
                        font.pixelSize: tile.t.focused ? (tile.t.free ? 96 : 112) : (tile.t.free ? 34 : 48)
                    }
                    Text {
                        width: parent.width
                        text: tile.t.subtitle || ""
                        wrapMode: Text.Wrap
                        color: tile.t.focused ? (tile.t.accent || "#ECE9E1") : "#A3A5AB"
                        font.family: shelf.root.sans
                        font.pixelSize: tile.t.focused ? 34 : 22
                    }
                    Item { width: 1; height: tile.t.focused ? 24 : 0 }
                    Repeater {
                        model: tile.t.focused ? (tile.t.rows || []).length : 0
                        Rectangle {
                            required property int index
                            readonly property var r: shelf.root.ok(tile.t.rows, index)
                            width: 500; height: 48; color: "transparent"
                            Rectangle { width: parent.width; height: 1; color: "#2A2D32" }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: parent.r.k || ""; color: "#A3A5AB"; font.family: shelf.root.sans; font.pixelSize: 26 }
                            Text { anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; text: parent.r.v || ""; color: "#ECE9E1"; font.family: shelf.root.mono; font.weight: Font.Medium; font.pixelSize: 26 }
                        }
                    }
                    Item { width: 1; height: tile.t.focused ? 14 : 0 }
                    Row {
                        visible: tile.t.focused
                        spacing: 8
                        height: 48
                        Repeater {
                            model: (tile.t.results || []).length
                            ResultCell { required property int index; c: shelf.root.ok(tile.t.results, index); accent: tile.t.accent || "#ECE9E1"; root: shelf.root }
                        }
                        Text { visible: (tile.t.results || []).length === 0; text: tile.t.empty || ""; color: "#A3A5AB"; font.family: shelf.root.sans; font.pixelSize: 26; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Item { width: 1; height: tile.t.focused ? 12 : 0 }
                    Repeater {
                        model: tile.t.focused ? (tile.t.sections || []).length : 0
                        Text {
                            required property int index
                            text: (tile.t.sections || [])[index] || ""
                            color: "#8A8D94"
                            font.family: shelf.root.display
                            font.weight: Font.ExtraBold
                            font.capitalization: Font.AllUppercase
                            font.pixelSize: 30
                        }
                    }
                }

                // the bar that says what A does
                Rectangle {
                    visible: !!tile.t.focused
                    anchors.bottom: parent.bottom
                    width: parent.width; height: 104
                    color: "#F2EFE6"
                    Text { x: 64; anchors.verticalCenter: parent.verticalCenter; text: tile.t.bar || ""; color: "#0E0F11"; font.family: shelf.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 56 }
                    Glyph { anchors.right: parent.right; anchors.rightMargin: 64; anchors.verticalCenter: parent.verticalCenter; size: 56; g: shelf.root.v.confirmInk }
                }
                TapHandler { onTapped: shelf.root.backend.clickTile(tile.index) }
            }
        }
    }
}
