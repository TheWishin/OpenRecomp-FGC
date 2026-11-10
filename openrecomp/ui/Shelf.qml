import QtQuick

// The focused game is a card; adjacent games remain reachable as compact spines.
Item {
    id: shelf
    required property var root
    clip: true
    Rectangle { anchors.fill: parent; color: shelf.root.ground }
    Row {
        id: track
        height: parent.height
        spacing: 2
        x: shelf.root.v.shelf.x
        Behavior on x { enabled: !shelf.root.reducedMotion; NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Repeater {
            model: shelf.root.v.shelf.tiles.length
            Item {
                id: tile
                required property int index
                readonly property var t: shelf.root.ok(shelf.root.v.shelf.tiles, index)
                width: t.w || 0
                height: track.height
                clip: true
                Behavior on width { enabled: !shelf.root.reducedMotion; NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                Rectangle {
                    objectName: "shelfCard"
                    x: tile.t.focused ? 24 : 8; y: 20
                    width: tile.width - x * 2; height: tile.height - 40
                    color: tile.t.focused ? Theme.card : "#121417"
                    border.width: 1; border.color: tile.t.focused ? (Theme.readableAccent(tile.t.accent) || shelf.root.line) : shelf.root.line
                    clip: true
                    LivingBackground {
                        anchors.fill: parent
                        visible: !!tile.t.focused
                        scene: shelf.root.v.livingBackground || ({})
                        reducedMotion: shelf.root.reducedMotion
                        motionActive: visible && shelf.root.motionActive
                    }
                    Text {
                        objectName: "shelfDecoration"
                        Accessible.ignored: true
                        textFormat: Text.PlainText; text: tile.t.num || ""
                        anchors.right: parent.right; anchors.rightMargin: 24; y: tile.t.focused ? 36 : 220
                        color: "#22252B"; font.family: shelf.root.display; font.weight: Font.Black
                        font.pixelSize: Theme.px(tile.t.focused ? 560 : 200)
                    }
                    Image {
                        visible: !!tile.t.focused && !!tile.t.hero
                        source: tile.t.hero || ""
                        anchors.right: parent.right; anchors.top: parent.top
                        width: parent.width * 0.62; height: parent.height - 92
                        fillMode: Image.PreserveAspectFit; asynchronous: true; smooth: true; mipmap: true
                    }
                    Rectangle {
                        visible: !!tile.t.focused && !!tile.t.hero
                        width: parent.width * 0.74; height: parent.height
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "#FF16181C" }
                            GradientStop { position: 0.64; color: "#F016181C" }
                            GradientStop { position: 1; color: "#0016181C" }
                        }
                    }
                }
                Flickable {
                    objectName: "shelfContent"
                    x: tile.t.focused ? 52 : 24; y: 46
                    width: tile.t.focused ? Math.min(560, tile.width - 104) : tile.width - 48
                    height: Math.min(shelfDescription.implicitHeight, tile.t.focused ? tileAction.y - y - 16 : tile.height - y - 24)
                    contentWidth: width; contentHeight: shelfDescription.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
                    contentY: Math.min(Math.max(0, contentHeight - height), (tile.t.scrollStep || 0) * 96)
                    Accessible.name: [tile.t.name || "", tile.t.subtitle || "", tile.t.playtime || ""].join(". ")
                Column {
                    id: shelfDescription; width: parent.width
                    spacing: 0
                    Rectangle { width: 40; height: 4; color: Theme.quiet && !tile.t.focused ? shelf.root.line : Theme.readableAccent(tile.t.accent) || shelf.root.textC }
                    Item { width: 1; height: 16 }
                    Rectangle {
                        visible: !!tile.t.badge
                        width: Math.min(badgeText.implicitWidth + 20, parent.width); height: visible ? 28 : 0
                        radius: 4; color: "#24272C"
                        Text { textFormat: Text.PlainText; id: badgeText; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 20); elide: Text.ElideRight; text: tile.t.badge || ""; color: Theme.quiet ? Theme.value : Theme.readableAccent(tile.t.accent) || shelf.root.textC; font.family: shelf.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(16)}
                    }
                    Item { width: 1; height: 12 }
                    Text {
                        objectName: "shelfTileTitle"
                        textFormat: Text.PlainText; width: parent.width; text: tile.t.name || ""
                        wrapMode: Text.WrapAnywhere; lineHeight: 0.95
                        color: tile.t.focused ? shelf.root.textC : shelf.root.muted
                        font.family: shelf.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase
                        font.pixelSize: Theme.px(tile.t.focused ? 64 : 28)
                    }
                    Text {
                        textFormat: Text.PlainText; width: parent.width; topPadding: 8; text: tile.t.subtitle || ""
                        wrapMode: Text.Wrap
                        color: shelf.root.muted; font.family: shelf.root.sans; font.pixelSize: Theme.px(tile.t.focused ? 23 : 19)
                    }
                    Text {
                        objectName: "shelfPlaytime"
                        visible: !!text; width: parent.width; topPadding: 12
                        textFormat: Text.PlainText; text: tile.t.playtime || ""; wrapMode: Text.Wrap
                        color: shelf.root.textC; font.family: shelf.root.sans; font.pixelSize: Theme.px(tile.t.focused ? 21 : 18)
                    }
                    Item { width: 1; height: tile.t.focused ? 18 : 12 }
                    Rectangle {
                        objectName: "shelfStatus"
                        visible: !!tile.t.status
                        width: Math.min(statusText.implicitWidth + 24, parent.width); height: visible ? statusText.implicitHeight + 12 : 0
                        radius: 4; color: Theme.quiet ? "#24272C" : tile.t.statusKind === "ready" ? "#20342D" : "#382E20"
                        Text { id: statusText; objectName: "shelfStatusText"; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 24); wrapMode: Text.Wrap; textFormat: Text.PlainText; text: tile.t.status || ""; color: Theme.quiet ? (tile.t.statusKind === "ready" ? Theme.value : Theme.text) : tile.t.statusKind === "ready" ? Theme.success : "#F5C77D"; font.family: shelf.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(18)}
                    }
                    Rectangle {
                        objectName: "shelfUpdate"
                        visible: !!tile.t.update && !tile.t.status
                        width: Math.min(updateText.implicitWidth + 24, parent.width); height: visible ? updateText.implicitHeight + 12 : 0
                        radius: 4; color: Theme.quiet ? "#24272C" : "#382E20"
                        Text { textFormat: Text.PlainText; id: updateText; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 24); wrapMode: Text.Wrap; text: tile.t.update || ""; color: Theme.quiet ? Theme.text : "#F5C77D"; font.family: shelf.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(18)}
                    }
                    Item { width: 1; height: tile.t.focused ? 18 : 0 }
                    Repeater {
                        model: tile.t.focused ? (tile.t.rows || []).length : 0
                        Rectangle {
                            required property int index
                            readonly property var r: shelf.root.ok(tile.t.rows, index)
                            width: parent ? parent.width : 0; height: 42; color: "transparent"
                            Rectangle { width: parent.width; height: 1; color: shelf.root.line }
                            Text { textFormat: Text.PlainText; width: parent.width * 0.46; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: parent.r.k || ""; color: shelf.root.muted; font.family: shelf.root.sans; font.pixelSize: Theme.px(21)}
                            Text { textFormat: Text.PlainText; width: parent.width * 0.52; horizontalAlignment: Text.AlignRight; elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; text: parent.r.v || ""; color: shelf.root.textC; font.family: shelf.root.mono; font.weight: Font.Medium; font.pixelSize: Theme.px(20)}
                        }
                    }
                    Item { width: 1; height: tile.t.focused ? 16 : 0 }
                    Row {
                        visible: !!tile.t.focused; spacing: 8; height: 40
                        Repeater {
                            model: (tile.t.results || []).length
                            ResultCell { required property int index; c: shelf.root.ok(tile.t.results, index); accent: Theme.quiet ? Theme.value : Theme.readableAccent(tile.t.accent) || shelf.root.textC; root: shelf.root; width: 40; height: 40 }
                        }
                        Text { textFormat: Text.PlainText; visible: (tile.t.results || []).length === 0; width: tile.t.focused ? 560 : 0; elide: Text.ElideRight; text: tile.t.empty || ""; color: shelf.root.muted; font.family: shelf.root.sans; font.pixelSize: Theme.px(20); anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text {
                        textFormat: Text.PlainText; visible: !!tile.t.focused; topPadding: 12; width: parent.width
                        text: (tile.t.sections || []).join(" · "); wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                        color: Theme.muted; font.family: shelf.root.sans; font.pixelSize: Theme.px(19)
                    }
                }
                }
                Rectangle {
                    id: tileAction
                    objectName: "shelfAction"
                    visible: !!tile.t.focused
                    x: 52; anchors.bottom: parent.bottom; anchors.bottomMargin: 44
                    width: Math.min(560, tile.width - 104); height: 80
                    radius: 4; color: shelf.root.bone
                    Text { textFormat: Text.PlainText; x: 24; width: parent.width - 112; height: parent.height - 16; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(28); anchors.verticalCenter: parent.verticalCenter; text: tile.t.ready ? (tile.t.play || "") : (tile.t.bar || ""); color: Theme.ground; font.family: shelf.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(40)}
                    Glyph { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; size: 40; g: tile.t.ready ? (tile.t.playG || ({})) : shelf.root.v.confirmInk }
                    TapHandler { id: uiTap0; onTapped: tile.t.ready ? shelf.root.backend.press("play") : shelf.root.backend.clickTile(tile.index) }
                    Interaction { handler: uiTap0; selected: !!tile.t.focused; onActivated: tile.t.ready ? shelf.root.backend.press("play") : shelf.root.backend.clickTile(tile.index) }
                }
                Text {
                    objectName: "shelfOpenAction"
                    visible: !!tile.t.focused && !!tile.t.ready
                    x: 636; anchors.bottom: parent.bottom; anchors.bottomMargin: 67
                    width: Math.max(0, tile.width - x - 52); height: Math.max(34, implicitHeight); rightPadding: 44
                    textFormat: Text.PlainText; text: tile.t.bar || ""; elide: Text.ElideRight
                    color: shelf.root.muted; font.family: shelf.root.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(21)
                    Glyph { anchors.right: parent.right; size: 32; g: shelf.root.v.confirmInk }
                }
                TapHandler { id: uiTap1; onTapped: shelf.root.backend.clickTile(tile.index) }
                Interaction { handler: uiTap1; selected: !!tile.t.focused; onActivated: shelf.root.backend.clickTile(tile.index) }
            }
        }
    }
}
