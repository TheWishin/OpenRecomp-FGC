import QtQuick

Item {
    id: body
    objectName: "onlineBody"
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var b: o.body || ({})
    readonly property var rooms: o.rooms || ({})
    readonly property var labels: o.labels || ({})
    readonly property bool roomPage: o.chapter === "rooms"
    readonly property bool officialPage: o.chapter === "ranked" || o.chapter === "leaderboard"
    readonly property bool sideDetail: !!b.detail && width >= 1100 && Theme.textScale <= 1.15
    function sections() {
        var rows = body.b.sections || []
        if (body.sideDetail || !body.b.detail) return rows
        var d = body.b.detail
        var lines = d.lead ? [{kind: "note", label: d.lead}] : []
        for (var r of d.rows || []) lines.push({kind: "note", label: r.k + ": " + r.v})
        return rows.concat([{title: d.title || "", lines: lines}])
    }
    PageLoader { anchors.fill: parent; active: body.o.chapter === "ranked"; page: "RankedPage.qml"; root: body.root }
    PageLoader { anchors.fill: parent; active: body.o.chapter === "leaderboard"; page: "LeaderboardPage.qml"; root: body.root }
    OnlineStyle.PageTitle { id: title; visible: !body.officialPage; x: 0; y: 2; width: parent.width - (roomHeaderActions.visible ? roomHeaderActions.width + 16 : 0); text: body.rooms.createOpen ? body.labels.create_room || "" : body.b.title || "" }
    Row {
        id: roomHeaderActions
        visible: body.roomPage && !body.rooms.joined
        x: parent.width - width; spacing: 8
        OnlineStyle.PrimaryButton {
            objectName: "roomsCreateOpen"; b: body.rooms.openCreate || ({}); maxW: 240
            primary: !body.rooms.createOpen
            accent: Theme.readableAccent(body.root.v.accent)
            onActivated: i => body.root.backend.clickRow(i)
        }
        OnlineStyle.SecondaryButton {
            objectName: "roomsJoinCodeOpen"; visible: b.index !== undefined
            b: body.rooms.openJoin || ({}); maxW: 240
            onActivated: i => body.root.backend.clickRow(i)
        }
    }
    OnlineSections {
        visible: !body.roomPage && !body.officialPage
        x: 0; y: title.height + 12; width: parent.width - (body.sideDetail ? 334 : 0); height: parent.height - y
        root: body.root; sections: !body.roomPage && !body.officialPage ? body.sections() : []
    }
    OnlineStyle.SectionCard {
        visible: !body.roomPage && !body.officialPage && body.sideDetail
        x: parent.width - 318; y: title.height + 12; width: 318; height: parent.height - y
        Flickable {
            anchors.fill: parent; anchors.margins: 20; contentHeight: details.height; clip: true
            Column {
                id: details; width: parent.width; spacing: 12
                OnlineStyle.SectionHeader { width: parent.width; text: body.b.detail ? body.b.detail.title || "" : "" }
                OnlineStyle.HelpText { width: parent.width; text: body.b.detail ? body.b.detail.lead || "" : ""; visible: !!text }
                Repeater {
                    model: body.b.detail ? body.b.detail.rows || [] : []
                    Column {
                        required property var modelData; width: details.width; spacing: 3
                        OnlineStyle.FieldLabel { width: parent.width; text: parent.modelData.k || "" }
                        OnlineStyle.Value { width: parent.width; text: parent.modelData.v || "" }
                    }
                }
            }
        }
    }
    Item {
        id: joinedRoom
        visible: body.roomPage && !!body.rooms.joined
        readonly property var room: body.rooms.joined || ({})
        x: 0; y: Math.max(title.y + title.height, roomHeaderActions.visible ? roomHeaderActions.height : 0) + 12; width: parent.width; height: parent.height - y
        OnlineStyle.SectionCard {
            width: (parent.width - 16) * 0.55; height: parent.height
            Flickable {
                id: roomPeople
                objectName: "communityRoomViewport"
                anchors.fill: parent; anchors.margins: 20; contentHeight: roomSummary.height
                clip: true; boundsBehavior: Flickable.StopAtBounds
                function revealFocus() {
                    for (var repeater of [queueRows, memberRows, tableRows]) {
                        for (var n = 0; n < repeater.count; ++n) {
                            var row = repeater.itemAt(n)
                            if (row && row.b.focused) {
                                var top = row.mapToItem(roomSummary, 0, 0).y
                                if (top < contentY) contentY = top
                                else if (top + row.height > contentY + height) contentY = top + row.height - height
                                return
                            }
                        }
                    }
                }
                Connections { target: body.root.backend; function onViewChanged() { Qt.callLater(roomPeople.revealFocus) } }
                Column {
                    id: roomSummary; width: roomPeople.width; spacing: 12
                    OnlineStyle.SectionHeader { objectName: "communityRoomName"; width: parent.width; text: joinedRoom.room.name || "" }
                    OnlineStyle.HelpText { objectName: "communityRoomMode"; width: parent.width; text: [joinedRoom.room.mode || "", joinedRoom.room.rotation || ""].filter(s => s).join(" \u00b7 ") }
                    OnlineStyle.SectionHeader { objectName: "communityQueueHeader"; width: parent.width; text: (joinedRoom.room.labels || {}).queue || "" }
                    OnlineStyle.HelpText { visible: !(joinedRoom.room.queue || []).length; width: parent.width; text: (joinedRoom.room.labels || {}).empty || "" }
                    Repeater {
                        id: queueRows; model: joinedRoom.room.queue || []
                        OnlineStyle.FieldRow {
                            objectName: "communityQueueRow"
                            required property var modelData; b: modelData; root: body.root; width: roomSummary.width
                            onActivated: i => body.root.backend.clickRow(i)
                        }
                    }
                    OnlineStyle.SectionHeader { visible: (joinedRoom.room.members || []).length > 0; width: parent.width; text: (joinedRoom.room.labels || {}).members || "" }
                    Repeater {
                        id: memberRows; model: joinedRoom.room.members || []
                        OnlineStyle.FieldRow {
                            required property var modelData; b: modelData; root: body.root; width: roomSummary.width
                            onActivated: i => body.root.backend.clickRow(i)
                        }
                    }
                    Repeater {
                        id: tableRows; model: joinedRoom.room.tables || []
                        OnlineStyle.FieldRow {
                            required property var modelData; b: modelData; root: body.root; width: roomSummary.width
                            onActivated: i => body.root.backend.clickRow(i)
                        }
                    }
                }
            }
        }
        OnlineStyle.SectionCard {
            x: (parent.width - 16) * 0.55 + 16; width: parent.width - x; height: parent.height
            OnlineStyle.SectionHeader { id: roomControlsTitle; x: 20; y: 16; width: parent.width - 40; text: (joinedRoom.room.labels || {}).controls || "" }
            Flickable {
                id: roomControls
                objectName: "communityControlsViewport"
                x: 16; y: roomControlsTitle.y + roomControlsTitle.height + 12; width: parent.width - 32; height: joinedPrimary.y - y - 12
                contentHeight: roomControlRows.height; clip: true; boundsBehavior: Flickable.StopAtBounds
                function revealFocus() {
                    for (var n = 0; n < roomControlFields.count; ++n) {
                        var row = roomControlFields.itemAt(n)
                        if (row && row.b.focused) {
                            if (row.y < contentY) contentY = row.y
                            else if (row.y + row.height > contentY + height) contentY = row.y + row.height - height
                            return
                        }
                    }
                }
                Connections { target: body.root.backend; function onViewChanged() { Qt.callLater(roomControls.revealFocus) } }
                Column {
                    id: roomControlRows; width: roomControls.width; spacing: 8
                    Repeater {
                        id: roomControlFields; model: joinedRoom.room.controls || []
                        OnlineStyle.FieldRow {
                            required property var modelData; b: modelData; root: body.root; width: roomControlRows.width
                            onActivated: i => body.root.backend.clickRow(i)
                        }
                    }
                }
            }
            OnlineStyle.PrimaryButton {
                id: joinedPrimary
                x: 16; y: parent.height - height - 16; width: parent.width - 32; maxW: width
                b: joinedRoom.room.primary || ({}); accent: Theme.readableAccent(body.root.v.accent)
                onActivated: i => body.root.backend.clickRow(i)
            }
        }
    }
    Item {
        visible: body.roomPage && !body.rooms.joined
        x: 0; y: Math.max(title.y + title.height, roomHeaderActions.visible ? roomHeaderActions.height : 0) + 12; width: parent.width; height: parent.height - y
        OnlineStyle.SectionCard {
            id: browser
            visible: !body.rooms.createOpen
            width: (parent.width - 16) * 0.52; height: parent.height
            OnlineStyle.SectionHeader { id: browserTitle; x: 20; y: 16; width: parent.width - 40; text: body.labels.open_rooms || "" }
            Flow {
                id: browserActions
                objectName: "roomBrowserActions"
                x: 20; y: browserTitle.y + browserTitle.height + 12; width: parent.width - 40; spacing: 12
                OnlineStyle.SecondaryButton {
                    id: refresh; maxW: browserActions.width
                    b: body.rooms.refresh || ({}); onActivated: i => body.root.backend.clickRow(i)
                }
                OnlineStyle.SecondaryButton {
                    id: roomSort; maxW: browserActions.width; b: body.rooms.sort || ({})
                    onActivated: i => body.root.backend.clickRow(i)
                }
            }
            OnlineSections {
                objectName: "roomBrowserRows"
                x: 4; y: browserActions.y + browserActions.height + 8; width: parent.width - 8; height: parent.height - y - 4
                root: body.root
                sections: [{title: "", lines: body.rooms.browser || []}]
                visible: (body.rooms.browser || []).length > 0
            }
            OnlineStyle.FieldRow { root: body.root;
                visible: !(body.rooms.browser || []).length
                x: 20; y: browserActions.y + browserActions.height + 32; width: parent.width - 40
                b: body.rooms.empty || ({}); onActivated: i => body.root.backend.clickRow(i)
            }
        }
        Flickable {
            id: draftScroll
            objectName: "roomDraftViewport"
            x: body.rooms.createOpen ? 0 : browser.width + 16; width: parent.width - x; height: parent.height - (inviteCard.visible ? inviteCard.height + 14 : 0) - createButton.height - 14
            contentHeight: draftCards.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            function revealFocus() {
                var target = null
                for (var n = 0; n < draftFields.count; ++n) {
                    var row = draftFields.itemAt(n)
                    if (row && row.b.focused) target = row
                }
                if (modeChoices.focused) target = modeChoices
                for (var m = 0; m < hostFields.count; ++m) {
                    var host = hostFields.itemAt(m)
                    if (host && host.b.focused) target = host
                }
                if (!target) return
                var top = target.mapToItem(draftCards, 0, 0).y
                if (target.height > height || top < contentY) contentY = top
                else if (top + target.height > contentY + height) contentY = top + target.height - height
                contentY = Math.max(0, Math.min(contentY, Math.max(0, contentHeight - height)))
            }
            Connections { target: body.root.backend; function onViewChanged() { Qt.callLater(draftScroll.revealFocus) } }
            onHeightChanged: Qt.callLater(revealFocus)
            onContentHeightChanged: Qt.callLater(revealFocus)
            Column {
                id: draftCards; width: parent.width; spacing: 14
                OnlineStyle.SectionCard {
                    width: parent.width; height: draftContent.height + (body.rooms.createOpen ? 24 : 36)
                    Column {
                        id: draftContent; x: body.rooms.createOpen ? 12 : 18; y: x; width: parent.width - 2 * x; spacing: 8
                        OnlineStyle.SectionHeader { visible: !body.rooms.createOpen; width: parent.width; text: body.labels.create_room || "" }
                        OnlineStyle.HelpText { width: parent.width; visible: !body.rooms.createOpen && !!text; text: body.rooms.hint || "" }
                        Flow {
                            id: draftRows; width: parent.width; spacing: 8
                            Repeater {
                            id: draftFields; model: body.rooms.draft || []
                            Item {
                                id: draftField; required property var modelData; readonly property var b: modelData
                                readonly property bool inlineNative: body.rooms.createOpen && !!b.fieldId
                                width: body.rooms.createOpen ? (draftRows.width - 8) / 2 : draftRows.width; height: inlineNative ? inlineField.height : b.segments ? segmentColumn.height : draftRow.height
                                OnlineStyle.FieldRow { root: body.root; id: draftRow; visible: !draftField.inlineNative && !draftField.b.segments; b: draftField.b; width: parent.width; onActivated: i => body.root.backend.clickRow(i) }
                                Item {
                                    id: inlineField; visible: draftField.inlineNative; width: parent.width; height: inlineEditor.height
                                    OnlineStyle.FieldLabel { x: 4; width: parent.width * 0.28 - 8; anchors.verticalCenter: parent.verticalCenter; text: draftField.b.label || "" }
                                    EditableField { id: inlineEditor; root: body.root; field: draftField.b; showLabel: false; x: parent.width * 0.28; width: parent.width - x }
                                }
                                Column {
                                    id: segmentColumn; visible: !!draftField.b.segments; width: parent.width; spacing: 8
                                    OnlineStyle.FieldLabel { width: parent.width; text: draftField.b.label || "" }
                                    Flow {
                                        width: parent.width; spacing: 6
                                        Repeater {
                                            model: draftField.b.segments || []
                                            OnlineStyle.Chip {
                                                required property var modelData
                                                b: ({label: modelData.label, focused: draftField.b.focused && modelData.selected})
                                                strong: modelData.selected; maxW: segmentColumn.width
                                                onActivated: body.root.backend.selectOnlineOption(draftField.b.index, modelData.option)
                                                Rectangle { visible: parent.modelData.selected; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width - 20; height: 3; color: Theme.readableAccent(body.root.v.accent) }
                                            }
                                        }
                                    }
                                    OnlineStyle.HelpText { objectName: "roomAccessHelp"; width: parent.width; visible: !!text; text: draftField.b.hint || "" }
                                }
                            }
                            }
                        }
                        Flow {
                            id: modeChoices; width: parent.width; spacing: 6
                            readonly property bool focused: (body.rooms.modes || []).some(b => b.focused)
                            Repeater {
                                model: body.rooms.modes || []
                                OnlineStyle.Chip {
                                    required property var modelData; b: modelData; strong: !!b.active; maxW: modeChoices.width
                                    onActivated: i => body.root.backend.focusOnlineRow(i)
                                    Rectangle { visible: !!parent.b.active; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width - 20; height: 3; color: Theme.readableAccent(body.root.v.accent) }
                                }
                            }
                        }
                    }
                }
                OnlineStyle.SectionCard {
                    visible: (body.rooms.other || []).length > 0
                    width: parent.width; height: visible ? hostContent.height + 36 : 0
                    Column {
                        id: hostContent; x: 18; y: 18; width: parent.width - 36; spacing: 8
                        OnlineStyle.SectionHeader { width: parent.width; text: body.labels.advanced_options || "" }
                        Repeater {
                            id: hostFields; model: body.rooms.other || []
                            OnlineStyle.FieldRow { root: body.root; required property var modelData; b: modelData; width: hostContent.width; onActivated: i => body.root.backend.clickRow(i) }
                        }
                    }
                }
            }
        }
        Rectangle {
            visible: draftScroll.contentHeight > draftScroll.height
            x: draftScroll.x + draftScroll.width - 4
            y: Math.max(0, draftScroll.contentY) / Math.max(1, draftScroll.contentHeight - draftScroll.height) * (draftScroll.height - height)
            width: 3; height: Math.max(24, draftScroll.height * draftScroll.height / Math.max(1, draftScroll.contentHeight))
            radius: 2; color: Theme.muted
        }
        OnlineStyle.PrimaryButton {
            id: createButton
            x: draftScroll.x; y: draftScroll.height + 7; width: draftScroll.width; maxW: width
            b: body.rooms.create || ({}); accent: Theme.readableAccent(body.root.v.accent)
            onActivated: i => body.root.backend.clickRow(i)
        }
        OnlineStyle.SectionCard {
            id: inviteCard
            visible: !body.rooms.createOpen && (body.rooms.invite || []).length > 0
            x: draftScroll.x; y: parent.height - height; width: draftScroll.width; height: visible ? inviteContent.height + 32 : 0
            Column {
                id: inviteContent; x: 16; y: 16; width: parent.width - 32; spacing: 8
                OnlineStyle.SectionHeader { width: parent.width; text: body.labels.join_invite || "" }
                Repeater {
                    model: body.rooms.invite || []
                    Item {
                        id: inviteField
                        required property var modelData
                        width: inviteContent.width; height: modelData.id === "join_room_code" ? joinButton.height : codeField.height
                        OnlineStyle.FieldRow { root: body.root; id: codeField; visible: inviteField.modelData.id !== "join_room_code"; b: inviteField.modelData; width: parent.width; onActivated: i => body.root.backend.clickRow(i) }
                        OnlineStyle.SecondaryButton { id: joinButton; visible: inviteField.modelData.id === "join_room_code"; b: inviteField.modelData; width: parent.width; maxW: width; onActivated: i => body.root.backend.clickRow(i) }
                    }
                }
            }
        }
    }
}
