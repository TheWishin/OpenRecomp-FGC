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
    readonly property real drawerWidth: Math.min(660, width - 16)
    readonly property real panesY: notice.visible ? notice.y + notice.height + 8 : 0
    readonly property var selected: (arcade.players || []).filter(p => p.id === arcade.selected)[0] || ({})
    property string revealedId: ""
    function click(b) { if (b && b.index >= 0 && !b.disabled) root.backend.clickRow(b.index) }
    function revealFocus() {
        var focused = (arcade.players || []).filter(p => p.focused)[0]
        if (!focused || revealedId === focused.id) return
        revealedId = focused.id
        for (var i = 0; i < playerCards.count; ++i) {
            var card = playerCards.itemAt(i)
            if (card && card.player.id === focused.id) {
                if (card.y < players.contentY) players.contentY = card.y
                else if (card.y + card.height > players.contentY + players.height) players.contentY = card.y + card.height - players.height
                players.contentY = Math.max(0, Math.min(players.contentY, players.contentHeight - players.height))
            }
        }
    }
    Connections { target: floor.root.backend; function onViewChanged() { Qt.callLater(floor.revealFocus) } }
    Rectangle { anchors.fill: parent; color: Theme.ground }
    Rectangle {
        id: notice
        objectName: "lobbyNotice"
        readonly property var offer: floor.find.outgoing || floor.find.notice || floor.arcade.result || ({})
        visible: !!offer.text
        x: 0; y: 0; width: parent.width
        height: visible ? Math.max(88, Theme.target(44) + 24) : 0
        color: Theme.raised; border.width: 1; border.color: offer.error ? Theme.error : floor.accent
        Column {
            id: noticeBody; x: 16; anchors.verticalCenter: parent.verticalCenter
            width: noticeButtons.visible ? noticeButtons.x - x - 16 : parent.width - 32; spacing: 4
            Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: notice.offer.text || ""; color: notice.offer.error ? Theme.error : Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(18) }
            Row {
                width: parent.width; spacing: 8
                PeerPing { id: offerPing; objectName: "arcadeOfferPing"; visible: !!notice.offer.connection; compact: true; connection: notice.offer.connection || ({}); ink: Theme.text; dim: Theme.border }
                Text { objectName: "challengeBannerTerms"; width: parent.width - (offerPing.visible ? offerPing.width + 8 : 0); text: [notice.offer.status || ""].concat((notice.offer.details || []).map(r => r.k + ": " + r.v)).filter(s => s).join(" \u00b7 "); textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14); Accessible.name: text }
            }
        }
        Row {
            id: noticeButtons; visible: (notice.offer.buttons || []).length > 0
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
            width: Math.min(560, parent.width * .42); spacing: 8
            Repeater {
                model: notice.offer.buttons || []
                ArcadeAction { required property var modelData; root: floor.root; b: modelData; width: (noticeButtons.width - Math.max(0, (notice.offer.buttons || []).length - 1) * 8) / Math.max(1, (notice.offer.buttons || []).length); primary: b.id === "accept_challenge"; onActivated: floor.click(b) }
            }
        }
    }
    Rectangle {
        id: playerPane
        objectName: "lobbyPlayersPane"
        x: 0; y: floor.panesY; width: floor.width - sidePanel.width - 16; height: floor.height - y
        color: Theme.card; border.width: 1; border.color: Theme.border
        Text { x: 8; y: 6; width: parent.width - 280; text: (floor.labels.players || "") + "  /  " + (floor.arcade.players || []).length; textFormat: Text.PlainText; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(18) }
        ArcadeAction { id: sortButton; root: floor.root; b: floor.arcade.sort || ({}); compact: true; label: [b.label || "", b.value || ""].join(": "); anchors.right: moreButton.left; anchors.rightMargin: 8; y: 2; onActivated: floor.click(b) }
        ArcadeAction { id: moreButton; root: floor.root; b: floor.controls.more || ({}); compact: true; anchors.right: parent.right; anchors.rightMargin: 4; y: 2; onActivated: floor.click(b) }
        Row {
            id: tableHeaders; x: 48; y: Math.max(34, sortButton.height + 4); height: Theme.onlinePx(14) + 8
            readonly property real dataWidth: playerPane.width - 8 - 48
            Repeater {
                model: floor.arcade.headers || []
                Rectangle {
                    objectName: "lobbyPlayerHeader"
                    required property var modelData
                    required property int index
                    readonly property var b: modelData
                    width: tableHeaders.dataWidth * [.25, .17, .11, .15, .15, .17][index]; height: tableHeaders.height
                    color: "transparent"
                    Text { objectName: "lobbyPlayerHeaderText"; width: parent.width - 4; anchors.verticalCenter: parent.verticalCenter; text: (parent.b.label || "") + (parent.b.active ? parent.b.descending ? " \u25be" : " \u25b4" : ""); textFormat: Text.PlainText; elide: Text.ElideRight; color: parent.b.active ? floor.accent : Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14); Accessible.name: text }
                    TapHandler { id: headerTap; onTapped: floor.click(parent.b) }
                    Interaction { handler: headerTap; selected: !!b.focused; name: b.label || ""; onActivated: floor.click(b) }
                }
            }
        }
        Flickable {
            id: players
            objectName: "arcadePlayersViewport"
            x: 4; y: tableHeaders.y + tableHeaders.height; width: parent.width - 8; height: parent.height - y - 4
            clip: true; contentHeight: playerRows.height; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: playerRows; width: players.width; spacing: 0
                Repeater {
                    id: playerCards; model: floor.arcade.players || []
                    ArcadePlayer { required property var modelData; root: floor.root; player: Object.assign({}, modelData, {selected: modelData.id === floor.arcade.selected}); labels: floor.labels; glyphs: floor.arcade.glyphs || ({}); width: playerRows.width }
                }
            }
        }
    }
    Column {
        id: sidePanel; x: playerPane.width + 16; y: floor.panesY; width: Math.max(280, floor.width * .25); height: floor.height - y; spacing: 16
        Rectangle {
            objectName: "lobbyLivePane"
            width: parent.width; height: Math.min(parent.height * .4, liveRows.height + 48)
            color: Theme.card; border.width: 1; border.color: Theme.border
            Text { x: 12; y: 8; width: parent.width - 24; text: floor.labels.cabinets || ""; textFormat: Text.PlainText; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(18) }
            Flickable {
                x: 8; y: 38; width: parent.width - 16; height: parent.height - y - 8; contentHeight: liveRows.height; clip: true
                Column {
                    id: liveRows; width: parent.width; spacing: 8
                    Text { visible: !(floor.arcade.cabinets || []).length; width: parent.width; text: floor.labels.no_matches || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14) }
                    Repeater {
                        model: floor.arcade.cabinets || []
                        Rectangle {
                            id: live; objectName: "arcadeCabinet"; required property var modelData
                            width: liveRows.width; height: liveNames.height + liveWatch.height + 20; color: Theme.raised; radius: 4
                            Text { id: liveNames; x: 8; y: 6; width: parent.width - 16; text: (live.modelData.players || []).map(p => p.name).join(" vs ") + "  " + (live.modelData.score || ""); wrapMode: Text.Wrap; textFormat: Text.PlainText; color: Theme.text; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14) }
                            ArcadeAction { id: liveWatch; x: 8; y: liveNames.y + liveNames.height + 6; root: floor.root; b: live.modelData.watch || ({}); compact: true; onActivated: floor.click(b) }
                        }
                    }
                }
            }
        }
        Rectangle {
            objectName: "lobbyRoomsPane"
            width: parent.width; height: parent.height - y
            color: Theme.card; border.width: 1; border.color: Theme.border
            Text { x: 12; y: 8; width: parent.width - 24; text: floor.labels.rooms || ""; textFormat: Text.PlainText; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(18) }
            Flow {
                id: roomActions; x: 8; y: 38; width: parent.width - 16; spacing: 6
                ArcadeAction { objectName: "lobbyCreateRoom"; root: floor.root; b: floor.arcade.createRoom || ({}); compact: true; height: Theme.target(44); primary: true; onActivated: floor.click(b) }
                ArcadeAction { root: floor.root; b: floor.arcade.joinCode || ({}); compact: true; height: Theme.target(44); onActivated: floor.click(b) }
            }
            Flickable {
                x: 8; y: roomActions.y + roomActions.height + 8; width: parent.width - 16; height: parent.height - y - 8; contentHeight: roomRows.height; clip: true
                Column {
                    id: roomRows; width: parent.width; spacing: 8
                    Text { visible: !(floor.arcade.rooms || []).length; width: parent.width; text: floor.labels.no_rooms || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.muted; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14) }
                    Repeater {
                        model: floor.arcade.rooms || []
                        Rectangle {
                            id: room; required property var modelData
                            width: roomRows.width; height: roomName.height + roomButtons.height + 20; color: Theme.raised; radius: 4
                            Text { id: roomName; x: 8; y: 6; width: parent.width - 16; text: room.modelData.name + "  " + room.modelData.count; wrapMode: Text.Wrap; textFormat: Text.PlainText; color: Theme.text; font.family: floor.root.sans; font.pixelSize: Theme.onlinePx(14) }
                            Flow { id: roomButtons; objectName: "lobbyRoomActions"; x: 8; y: roomName.y + roomName.height + 6; width: parent.width - 16; spacing: 6
                                ArcadeAction { root: floor.root; b: room.modelData.join || ({}); compact: true; onActivated: floor.click(b) }
                                ArcadeAction { visible: !!room.modelData.watch && room.modelData.watch.index !== undefined; root: floor.root; b: room.modelData.watch || ({}); compact: true; onActivated: floor.click(b) }
                            }
                        }
                    }
                }
            }
        }
    }
    Rectangle {
        id: drawer
        objectName: "arcadeOptionsDrawer"
        visible: floor.drawerOpen
        x: floor.width - floor.drawerWidth; y: panesY; width: floor.drawerWidth; height: floor.height - y
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
                var groups = [drawerFields, drawerCabinets, drawerDestinations]
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
                    model: floor.arcade.optionsOpen ? floor.arcade.options || [] : (floor.arcade.more || []).concat(floor.arcade.secondary || []).filter((b, i, rows) => b.id.indexOf("arcade_watch:") !== 0 && rows.findIndex(other => other.index === b.index) === i)
                    OnlineStyle.FieldRow {
                        required property var modelData
                        width: drawerRows.width
                        root: floor.root; b: Object.assign({}, modelData, {hint: ""})
                        onActivated: i => floor.root.backend.clickRow(i)
                    }
                }
                OnlineStyle.SectionHeader { visible: !!floor.arcade.moreOpen && (floor.arcade.cabinets || []).length > 0; width: parent.width; text: floor.labels.cabinets || "" }
                Repeater {
                    id: drawerCabinets
                    model: floor.arcade.moreOpen ? floor.arcade.cabinets || [] : []
                    Rectangle {
                        id: cabinet
                        objectName: "arcadeCabinet"
                        required property var modelData
                        width: drawerRows.width; height: Math.max(152, cabinetNames.height + cabinetWatch.height + 40)
                        radius: 8; color: Theme.raised; border.width: modelData.focused ? Theme.focusWidth : 1; border.color: modelData.focused ? Theme.focus : Theme.border
                        Row {
                            id: cabinetNames; x: 12; y: 12; width: parent.width - 24; spacing: 12
                            Repeater {
                                model: cabinet.modelData.players || []
                                Column {
                                    required property var modelData
                                    width: (cabinetNames.width - 24 - cabinetScore.width) / 2; spacing: 8
                                    Text { width: parent.width; text: parent.modelData.name || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text; font.family: floor.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(18) }
                                }
                            }
                            Text { id: cabinetScore; text: cabinet.modelData.score || floor.labels.score || ""; textFormat: Text.PlainText; color: Theme.value; font.family: floor.root.mono; font.pixelSize: Theme.px(22) }
                        }
                        ArcadeAction { id: cabinetWatch; root: floor.root; x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 12; width: parent.width - 24; b: cabinet.modelData.watch || ({}); label: floor.labels.watch || ""; onActivated: floor.click(b) }
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
        x: floor.width - floor.drawerWidth; y: panesY; width: floor.drawerWidth; height: floor.height - y; z: 40
        radius: 10; color: Theme.card; border.width: 2; border.color: floor.accent
        OnlineStyle.SectionHeader { x: 22; y: 22; width: parent.width - 44; text: (floor.arcade.help || {}).title || floor.labels.help || "" }
        OnlineStyle.HelpText { x: 22; y: 84; width: parent.width - 44; text: (floor.arcade.help || {}).text || floor.labels.options_note || "" }
        ArcadeAction { x: 22; anchors.bottom: parent.bottom; anchors.bottomMargin: 22; width: parent.width - 44; root: floor.root; b: floor.controls.help || ({}); label: floor.labels.close || ""; onActivated: floor.click(b) }
    }
}
