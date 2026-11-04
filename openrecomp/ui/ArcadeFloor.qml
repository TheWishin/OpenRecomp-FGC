import QtQuick

Item {
    id: floor
    objectName: "arcadeFloor"
    required property var root
    readonly property var online: root.v.online || ({})
    readonly property var arcade: online.arcade || ({})
    readonly property var labels: arcade.labels || ({})
    readonly property var controls: arcade.controls || ({})
    readonly property var find: online.find || ({})
    readonly property bool drawerOpen: !!arcade.optionsOpen || !!arcade.moreOpen
    readonly property color accent: Theme.readableAccent(root.v.accent)
    readonly property int columns: arcade.columns || 3
    readonly property real railWidth: 496
    readonly property real contentWidth: width - railWidth - 72
    readonly property var selected: (arcade.players || []).filter(p => p.id === arcade.selected)[0] || ({})
    function click(b) { if (b && b.index >= 0 && !b.disabled) root.backend.clickRow(b.index) }
    function revealFocus() {
        for (var i = 0; i < playerCards.count; ++i) {
            var card = playerCards.itemAt(i)
            if (card && card.player.focused) {
                if (card.y < players.contentY) players.contentY = card.y
                else if (card.y + card.height > players.contentY + players.height) players.contentY = card.y + card.height - players.height
                players.contentY = Math.max(0, Math.min(players.contentY, players.contentHeight - players.height))
            }
        }
    }
    Connections { target: floor.root.backend; function onViewChanged() { Qt.callLater(floor.revealFocus) } }
    Rectangle { anchors.fill: parent; color: Theme.ground }
    Image {
        anchors.fill: parent; source: (floor.online.profile || {}).face || ""; visible: !!source
        asynchronous: true; fillMode: Image.PreserveAspectCrop; opacity: Theme.highContrast ? 0.05 : 0.15
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient { GradientStop { position: 0; color: "#88101620" } GradientStop { position: 1; color: Theme.ground } }
    }
    // Perspective lines give the art-free fallback the same arcade depth.
    Item {
        anchors.fill: parent; clip: true; opacity: Theme.highContrast ? 0.04 : 0.13
        Repeater {
            model: 11
            Rectangle {
                required property int index
                x: floor.width * 0.5; y: floor.height * 0.45; width: 2; height: floor.height * 1.5
                color: floor.accent; rotation: (index - 5) * 17; transformOrigin: Item.Top
            }
        }
        Repeater {
            model: 5
            Rectangle { required property int index; x: 0; y: floor.height * 0.55 + index * index * 18; width: floor.width; height: 1; color: floor.accent }
        }
    }
    OnlineStyle.PageTitle { x: 32; y: 15; width: floor.contentWidth - 200; text: floor.labels.title || "" }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 32; y: 15; spacing: 10
        ArcadeAction { root: floor.root; b: floor.controls.options || ({}); label: floor.labels.options || ""; icon: "options"; onActivated: floor.click(b) }
        ArcadeAction { root: floor.root; b: floor.controls.more || ({}); label: floor.labels.more || ""; icon: "more"; onActivated: floor.click(b) }
    }
    Row {
        id: primaryTiles
        x: 32; y: 86; spacing: 18; width: floor.contentWidth; height: 160
        Repeater {
            model: [floor.find.quick || ({}), floor.find.ranked || ({})].filter(b => b.present)
            Rectangle {
                id: tile
                required property var modelData
                required property int index
                readonly property bool ranked: modelData.id === "search_ranked"
                width: (primaryTiles.width - ((floor.find.ranked || {}).present ? 18 : 0)) / ((floor.find.ranked || {}).present ? 2 : 1)
                height: primaryTiles.height; radius: 10; clip: true
                color: ranked ? "#2C2827" : "#25353A"
                border.width: modelData.focused ? Theme.focusWidth : 1; border.color: modelData.focused ? Theme.focus : Theme.border
                property real selectionScale: modelData.focused || tileHover.hovered ? 1.015 : 1
                scale: floor.root.reducedMotion ? 1 : selectionScale
                Behavior on selectionScale { enabled: !floor.root.reducedMotion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                Image { anchors.right: parent.right; height: parent.height; width: parent.width * 0.6; source: (floor.online.profile || {}).face || ""; visible: !!source; opacity: 0.35; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                Rectangle { anchors.fill: parent; gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: tile.color } GradientStop { position: 1; color: "#3320252C" } } }
                ArcadeIcon { x: 22; y: 22; width: 38; height: 38; kind: tile.ranked ? "ranked" : "quick"; ink: floor.accent }
                Text { x: 22; y: 66; width: parent.width - 44; elide: Text.ElideRight; textFormat: Text.PlainText; text: tile.ranked ? floor.labels.ranked || "" : floor.labels.quick || ""; color: Theme.text; font.family: floor.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(38) }
                Text { x: 22; y: 117; width: parent.width - 44; elide: Text.ElideRight; textFormat: Text.PlainText; text: tile.modelData.disabled ? tile.modelData.value || "" : tile.ranked ? floor.labels.ranked_note || "" : floor.labels.quick_note || ""; color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.px(18) }
                HoverHandler { id: tileHover }
                TapHandler { id: tileTap; onTapped: floor.click(tile.modelData) }
                Interaction { handler: tileTap; selected: !!tile.modelData.focused; disabled: !!tile.modelData.disabled; name: tile.ranked ? floor.labels.ranked || "" : floor.labels.quick || ""; onActivated: floor.click(tile.modelData) }
            }
        }
    }
    OnlineStyle.SectionHeader { x: 32; y: 269; width: floor.contentWidth; text: (floor.labels.players || "") + "  /  " + (floor.arcade.players || []).length }
    Flickable {
        id: players
        objectName: "arcadePlayersViewport"
        x: 26; y: 316; width: floor.contentWidth + 12; height: floor.height - y - 20
        clip: true; contentHeight: playerGrid.height + 14; boundsBehavior: Flickable.StopAtBounds
        Grid {
            id: playerGrid
            x: 6; y: 6; width: floor.contentWidth; columns: floor.columns; spacing: 18
            onPositioningComplete: Qt.callLater(floor.revealFocus)
            Repeater {
                id: playerCards
                model: floor.arcade.players || []
                ArcadePlayer {
                    required property var modelData
                    root: floor.root; player: modelData; labels: floor.labels; glyphs: floor.arcade.glyphs || ({})
                    width: (playerGrid.width - (floor.columns - 1) * playerGrid.spacing) / floor.columns
                }
            }
        }
    }
    Rectangle {
        visible: players.contentHeight > players.height
        x: players.x + players.width - 2; y: players.y + Math.max(0, players.contentY) / Math.max(1, players.contentHeight) * players.height
        width: 3; height: Math.max(24, players.height * players.height / Math.max(1, players.contentHeight)); radius: 2; color: Theme.muted
    }
    Flickable {
        id: rail
        objectName: "arcadeCabinetsViewport"
        x: floor.width - floor.railWidth - 32; y: 86; width: floor.railWidth; height: floor.height - y - 20
        visible: !floor.drawerOpen; clip: true; contentHeight: railContent.height + 8; boundsBehavior: Flickable.StopAtBounds
        function revealFocus() {
            var groups = [cabinets, rooms]
            for (var g = 0; g < groups.length; ++g) for (var i = 0; i < groups[g].count; ++i) {
                var card = groups[g].itemAt(i)
                if (card && card.modelData.focused) {
                    if (card.y < contentY) contentY = card.y
                    else if (card.y + card.height > contentY + height) contentY = card.y + card.height - height
                    contentY = Math.max(0, Math.min(contentY, contentHeight - height))
                }
            }
        }
        Connections { target: floor.root.backend; function onViewChanged() { Qt.callLater(rail.revealFocus) } }
        Column {
            id: railContent; width: rail.width; spacing: 14
            Row {
                spacing: 12; width: parent.width; height: 42
                ArcadeIcon { kind: "cabinet"; ink: floor.accent }
                OnlineStyle.SectionHeader { width: parent.width - 44; text: floor.labels.cabinets || "" }
            }
            Repeater {
                id: cabinets; model: floor.arcade.cabinets || []
                Rectangle {
                    id: cabinet
                    objectName: "arcadeCabinet"
                    required property var modelData
                    width: rail.width; height: 248; radius: 12; color: "#171E26"
                    border.width: modelData.focused ? Theme.focusWidth : 2; border.color: modelData.focused ? Theme.focus : "#5E7183"
                    Rectangle { x: 14; y: 10; width: parent.width - 28; height: 4; radius: 2; color: floor.accent }
                    Row {
                        x: 14; y: 24; width: parent.width - 28; spacing: 4
                        Repeater {
                            model: cabinet.modelData.players || []
                            Rectangle {
                                id: opponent
                                required property var modelData
                                width: (cabinet.width - 32) / 2; height: 132; color: "#26323F"; clip: true
                                Image { anchors.fill: parent; source: opponent.modelData.face || ""; visible: !!source; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                                Text { visible: !opponent.modelData.face; x: 10; y: 0; width: parent.width - 20; height: 94; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: (opponent.modelData.name || "?").substring(0, 1); textFormat: Text.PlainText; color: "#71869B"; font.family: floor.root.display; font.pixelSize: Theme.px(72); font.weight: Font.Black; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(40); Accessible.ignored: true }
                                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 38; color: "#D00E0F11" }
                                Text { x: 10; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; width: parent.width - 20; elide: Text.ElideRight; textFormat: Text.PlainText; text: opponent.modelData.name || ""; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(18) }
                            }
                        }
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter; y: 53; width: Theme.px(104); height: Theme.px(48); radius: 5; color: Theme.ground; border.width: 1; border.color: floor.accent
                        Text { anchors.centerIn: parent; width: parent.width - 8; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; textFormat: Text.PlainText; text: String(cabinet.modelData.score || floor.labels.score || ""); color: Theme.text; font.family: floor.root.mono; font.weight: Font.Bold; font.pixelSize: Theme.px(24) }
                    }
                    ArcadeAction { x: 14; y: 177; width: parent.width - 28; height: 52; root: floor.root; b: cabinet.modelData.watch || ({}); label: floor.labels.watch || ""; icon: "watch"; onActivated: floor.click(b) }
                }
            }
            OnlineStyle.HelpText { visible: !(floor.arcade.cabinets || []).length; width: parent.width; text: floor.labels.no_matches || "" }
            OnlineStyle.SectionHeader { width: parent.width; topPadding: 8; text: floor.labels.rooms || "" }
            Repeater {
                id: rooms; model: floor.arcade.rooms || []
                Rectangle {
                    id: room
                    objectName: "arcadeRoom"
                    required property var modelData
                    width: rail.width; height: 100; radius: 8; color: Theme.card
                    border.width: modelData.focused ? Theme.focusWidth : 1; border.color: modelData.focused ? Theme.focus : Theme.border
                    Text { x: 16; y: 15; width: parent.width - 156; elide: Text.ElideRight; textFormat: Text.PlainText; text: room.modelData.name || ""; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(22) }
                    Text { objectName: "onlineAreaLanguage"; x: 16; y: 54; width: parent.width - 156; elide: Text.ElideRight; textFormat: Text.PlainText; text: [room.modelData.count || "", room.modelData.mode || "", room.modelData.areaLanguage || ""].filter(s => s).join("  ·  "); color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.px(18) }
                    ArcadeAction { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; width: 116; root: floor.root; b: room.modelData.join || ({}); label: floor.labels.join || ""; onActivated: floor.click(b) }
                }
            }
            OnlineStyle.HelpText { visible: !(floor.arcade.rooms || []).length; width: parent.width; text: floor.labels.no_rooms || "" }
        }
    }
    Rectangle {
        id: drawer
        objectName: "arcadeOptionsDrawer"
        visible: floor.drawerOpen
        x: floor.width - floor.railWidth - 32; y: 86; width: floor.railWidth; height: floor.height - y - 20
        radius: 10; color: Theme.card; border.width: 1; border.color: floor.accent
        OnlineStyle.SectionHeader { x: 22; y: 20; width: parent.width - 160; text: floor.arcade.optionsOpen ? floor.labels.options || "" : floor.labels.more || "" }
        ArcadeAction { anchors.right: parent.right; anchors.rightMargin: 16; y: 14; root: floor.root; b: floor.controls.help || ({}); label: floor.labels.help || ""; onActivated: floor.click(b) }
        Flickable {
            id: drawerScroll
            x: 16; y: 76; width: parent.width - 32; height: parent.height - y - 14
            clip: true; contentHeight: drawerRows.height; boundsBehavior: Flickable.StopAtBounds
            onContentHeightChanged: Qt.callLater(revealFocus)
            onHeightChanged: Qt.callLater(revealFocus)
            function revealFocus() {
                var groups = [drawerFields, drawerDestinations]
                for (var g = 0; g < groups.length; ++g) for (var i = 0; i < groups[g].count; ++i) {
                    var row = groups[g].itemAt(i)
                    if (row && row.modelData.focused) {
                        var top = row.mapToItem(drawerRows, 0, 0).y
                        if (top < contentY) contentY = top
                        else if (top + row.height > contentY + height) contentY = top + row.height - height
                        contentY = Math.max(0, Math.min(contentY, contentHeight - height))
                    }
                }
            }
            Connections { target: floor.root.backend; function onViewChanged() { Qt.callLater(drawerScroll.revealFocus) } }
            Column {
                id: drawerRows; width: drawerScroll.width; spacing: 10
                onPositioningComplete: Qt.callLater(drawerScroll.revealFocus)
                Repeater {
                    id: drawerFields
                    model: floor.arcade.optionsOpen ? floor.arcade.options || [] : (floor.arcade.more || []).concat(floor.arcade.secondary || []).filter((b, i, rows) => rows.findIndex(other => other.index === b.index) === i)
                    OnlineStyle.FieldRow {
                        required property var modelData
                        width: drawerRows.width
                        b: Object.assign({}, modelData, {hint: ""})
                        onActivated: i => floor.root.backend.clickRow(i)
                    }
                }
                Repeater {
                    id: drawerDestinations
                    model: floor.arcade.moreOpen ? floor.arcade.destinations || [] : []
                    ArcadeAction {
                        required property var modelData
                        root: floor.root; b: modelData; width: drawerRows.width
                        onActivated: floor.click(b)
                    }
                }
            }
        }
    }
    Rectangle {
        objectName: "arcadeHelp"
        visible: !!floor.arcade.helpOpen
        x: floor.width - floor.railWidth - 32; y: 86; width: floor.railWidth; height: floor.height - y - 20; z: 40
        radius: 10; color: Theme.card; border.width: 2; border.color: floor.accent
        OnlineStyle.SectionHeader { x: 22; y: 22; width: parent.width - 44; text: (floor.arcade.help || {}).title || floor.labels.help || "" }
        OnlineStyle.HelpText { x: 22; y: 84; width: parent.width - 44; text: (floor.arcade.help || {}).text || floor.labels.options_note || "" }
        ArcadeAction { x: 22; anchors.bottom: parent.bottom; anchors.bottomMargin: 22; width: parent.width - 44; root: floor.root; b: floor.controls.help || ({}); label: floor.labels.close || ""; onActivated: floor.click(b) }
    }
    Rectangle {
        id: notice
        readonly property var offer: floor.find.incoming || floor.find.outgoing || floor.find.notice || ({})
        visible: !!(floor.find.incoming || floor.find.outgoing || floor.find.notice)
        x: 32; y: 252; width: floor.contentWidth; height: noticeBody.height + 30; radius: 8; z: 30
        color: Theme.raised; border.width: 2; border.color: floor.accent
        Column {
            id: noticeBody; x: 16; y: 14; width: parent.width - 32; spacing: 8
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: notice.offer.text || ""; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(20) }
            PeerPing { objectName: "arcadeOfferPing"; visible: !!notice.offer.connection; connection: notice.offer.connection || ({}); ink: Theme.text; dim: Theme.border }
            Text {
                objectName: "challengeBannerTerms"; visible: !!text; width: parent.width
                text: (notice.offer.details || []).map(r => r.k + ": " + r.v).join(" · ")
                textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.px(16)
            }
            Row { spacing: 10; Repeater { model: notice.offer.buttons || []; ArcadeAction { required property var modelData; root: floor.root; b: modelData; onActivated: floor.click(b) } } }
        }
    }
}
