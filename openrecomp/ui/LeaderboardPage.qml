import QtQuick

Flickable {
    id: page
    required property var root
    readonly property var board: root.v.online.leaderboard || ({})
    readonly property var labels: board.labels || ({})
    readonly property bool compact: true
    contentWidth: width; contentHeight: content.height; clip: true; boundsBehavior: Flickable.StopAtBounds
    function revealFocus() {
        var target = null
        for (var n = 0; n < rankingRows.count; ++n) {
            var row = rankingRows.itemAt(n)
            if (row && row.modelData.focused) target = row
        }
        for (var repeater of [filterControls, sortControls, boardButtons, compactControls]) {
            for (var i = 0; i < repeater.count; ++i) {
                var control = repeater.itemAt(i)
                if (control && control.b.focused) target = control
            }
        }
        if (!target) return
        if (page.compact && target.parent === compactRow) {
            if (target.x < compactViewport.contentX) compactViewport.contentX = target.x
            else if (target.x + target.width > compactViewport.contentX + compactViewport.width)
                compactViewport.contentX = target.x + target.width - compactViewport.width
        }
        var top = target.mapToItem(content, 0, 0).y
        if (top < contentY) contentY = top
        else if (top + target.height > contentY + height) contentY = top + target.height - height
    }
    onBoardChanged: Qt.callLater(revealFocus)
    component RankingRow: Rectangle {
        id: row
        objectName: "rankingRow"
        property var entry: ({})
        width: parent.width; height: Math.max(40, values.implicitHeight + 16); radius: 4
        color: entry.focused ? Theme.highlighted : entry.own ? "#252C33" : "#1B1E23"
        border.width: entry.focused ? 4 : entry.own ? 2 : 1
        border.color: entry.focused ? "#F2EFE6" : entry.own ? (Theme.quiet ? Theme.value : "#D3B59D") : "#3A3D42"
        Accessible.role: Accessible.Button
        Accessible.name: [entry.place, entry.name, entry.rank, entry.rating, entry.record, entry.main].join(", ")
        Accessible.onPressAction: if (entry.index >= 0) page.root.backend.clickRow(entry.index)
        Row {
            id: values; x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 24; spacing: 0
            OnlineStyle.Value { width: values.width * 0.07; text: row.entry.place || "" }
            Row {
                width: values.width * 0.24; spacing: 6
                FighterPortrait { objectName: "rankingPlayerPortrait"; width: 24; height: 24; source: row.entry.face || ""; name: "" }
                OnlineStyle.FieldLabel { width: parent.width - 30; rightPadding: 12; text: row.entry.name || ""; font.weight: Font.DemiBold; wrapMode: Text.NoWrap; elide: Text.ElideRight }
            }
            Row {
                width: values.width * 0.19; spacing: 4
                Image { visible: !!row.entry.plate; source: row.entry.plate || ""; width: visible ? Math.min(parent.width * .38, 48) : 0; height: 24; fillMode: Image.PreserveAspectFit; asynchronous: true }
                OnlineStyle.FieldLabel { width: parent.width - (row.entry.plate ? Math.min(parent.width * .38, 48) + 4 : 0) - 8; text: row.entry.rank || "—"; wrapMode: Text.NoWrap; elide: Text.ElideRight }
            }
            OnlineStyle.Value { width: values.width * 0.13; text: row.entry.rating || "—" }
            OnlineStyle.FieldLabel { width: values.width * 0.15; rightPadding: 10; text: row.entry.record || "—" }
            OnlineStyle.FieldLabel { width: values.width * 0.22; text: row.entry.main || "—"; wrapMode: Text.NoWrap; elide: Text.ElideRight }
        }
        HoverHandler { id: hover }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: "#FFFFFF"; opacity: tap.pressed ? 0.14 : hover.hovered ? 0.07 : 0 }
        TapHandler { id: tap; enabled: row.entry.index >= 0; onTapped: page.root.backend.focusOnlineRow(row.entry.index); onDoubleTapped: page.root.backend.clickRow(row.entry.index) }
    }
    Column {
        id: content; width: page.width; spacing: 8
        OnlineStyle.PageTitle { width: parent.width; text: page.root.v.online.body.title || page.labels.ranking || "" }
        OnlineStyle.HelpText { width: parent.width; text: page.board.updated || "" }
        Column {
            width: parent.width; spacing: 4; visible: !!page.board.own
            OnlineStyle.SectionHeader { width: parent.width; text: page.labels.your_position || "" }
            RankingRow { width: parent.width; entry: page.board.own || ({}) }
        }
        Row {
            objectName: "rankingPodium"
            width: parent.width; spacing: 8; visible: !!page.board.podiumOpen && (page.board.podium || []).length > 0
            Repeater {
                model: page.board.podium || []
                OnlineStyle.SectionCard {
                    required property var modelData
                    width: (content.width - 16) / 3; height: podiumContent.height + 16
                    border.color: Theme.quiet ? Theme.border : "#D3B59D"
                    Accessible.role: Accessible.Button
                    Accessible.name: [modelData.place, modelData.name, modelData.rank, modelData.rating].join(", ")
                    Accessible.onPressAction: if (modelData.index >= 0) page.root.backend.clickRow(modelData.index)
                    Column {
                        id: podiumContent; x: 8; y: 8; width: parent.width - 16; spacing: 4
                        OnlineStyle.PageTitle { width: parent.width; text: "#" + parent.parent.modelData.place; font.pixelSize: Theme.onlinePx(24) }
                        FighterPortrait { objectName: "podiumPlayerPortrait"; width: 32; height: 32; source: parent.parent.modelData.face || ""; name: "" }
                        OnlineStyle.FieldLabel { width: parent.width; text: parent.parent.modelData.name; font.weight: Font.Bold }
                        OnlineStyle.HelpText { visible: !page.compact; width: parent.width; text: parent.parent.modelData.rank || "—" }
                        OnlineStyle.Value { visible: !page.compact; width: parent.width; text: parent.parent.modelData.rating }
                    }
                    TapHandler { onTapped: if (parent.modelData.index >= 0) page.root.backend.focusOnlineRow(parent.modelData.index); onDoubleTapped: if (parent.modelData.index >= 0) page.root.backend.clickRow(parent.modelData.index) }
                }
            }
        }
        OnlineStyle.SectionCard {
            width: parent.width; height: page.compact ? compactViewport.height + compactHelp.height + 32 : filters.height + 32
            Flickable {
                id: compactViewport
                objectName: "rankingCompactControls"
                visible: page.compact
                x: 12; y: 12; width: parent.width - 24; height: compactRow.height
                contentWidth: compactRow.width; contentHeight: height
                clip: true; boundsBehavior: Flickable.StopAtBounds
                Row {
                    id: compactRow; spacing: 8
                    onWidthChanged: Qt.callLater(page.revealFocus)
                    Repeater {
                        id: compactControls
                        model: page.compact ? (page.board.controls || []).concat(page.board.buttons || [], page.board.sorts || []) : []
                        OnlineStyle.Chip { required property var modelData; b: modelData; strong: true; maxW: compactViewport.width; onActivated: i => page.root.backend.clickRow(i) }
                    }
                }
            }
            OnlineStyle.HelpText {
                id: compactHelp; visible: page.compact
                x: 12; y: compactViewport.y + compactViewport.height + 8; width: parent.width - 24
                text: page.labels.page_filter || ""
            }
            Column {
                id: filters; visible: !page.compact; x: 16; y: 16; width: parent.width - 32; spacing: 10
                Flow {
                    width: parent.width; spacing: 8
                    Repeater { id: filterControls; model: page.board.controls || []; OnlineStyle.Chip { required property var modelData; b: modelData; strong: true; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                    Repeater { id: boardButtons; model: page.board.buttons || []; OnlineStyle.SecondaryButton { required property var modelData; b: modelData; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                }
                OnlineStyle.HelpText { width: parent.width; text: page.labels.page_filter || "" }
                Flow {
                    width: parent.width; spacing: 6
                    Repeater { id: sortControls; model: page.board.sorts || []; OnlineStyle.Chip { required property var modelData; b: modelData; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                }
            }
        }
        OnlineStyle.SectionHeader { width: parent.width; text: page.labels.ranking || "" }
        Row {
            id: columnHeadings
            objectName: "rankingColumnHeadings"
            width: parent.width - 28; x: 14
            OnlineStyle.HelpText { width: parent.width * 0.07; text: page.labels.rank || "" }
            OnlineStyle.HelpText { width: parent.width * 0.24; text: page.labels.player || "" }
            OnlineStyle.HelpText { width: parent.width * 0.19; text: page.labels.standing || "" }
            OnlineStyle.HelpText { width: parent.width * 0.13; text: page.labels.rating || "" }
            OnlineStyle.HelpText { width: parent.width * 0.15; text: page.labels.record || "" }
            OnlineStyle.HelpText { width: parent.width * 0.22; text: page.labels.main || "" }
        }
        OnlineStyle.HelpText { visible: !(page.board.rows || []).length; width: parent.width; text: page.labels.empty || "" }
        Repeater { id: rankingRows; model: page.board.rows || []; RankingRow { required property var modelData; width: content.width; entry: modelData } }
    }
    Rectangle {
        objectName: "rankingPinnedHeadings"
        x: 0; y: page.contentY; width: page.width; height: columnHeadings.height + 16; z: 10
        visible: page.contentY > columnHeadings.y
        color: Theme.card
        Row {
            x: 14; y: 8; width: parent.width - 28
            OnlineStyle.HelpText { width: parent.width * 0.07; text: page.labels.rank || "" }
            OnlineStyle.HelpText { width: parent.width * 0.24; text: page.labels.player || "" }
            OnlineStyle.HelpText { width: parent.width * 0.19; text: page.labels.standing || "" }
            OnlineStyle.HelpText { width: parent.width * 0.13; text: page.labels.rating || "" }
            OnlineStyle.HelpText { width: parent.width * 0.15; text: page.labels.record || "" }
            OnlineStyle.HelpText { width: parent.width * 0.22; text: page.labels.main || "" }
        }
    }

}
