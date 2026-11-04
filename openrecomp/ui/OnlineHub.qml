import QtQuick

// The release layout: identity on the left, matchmaking beside it, chapters below.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var prof: o.profile || ({})
    readonly property var fnd: o.find || ({})
    readonly property color acc: Theme.readableAccent(root.v.accent)
    readonly property bool arcadeFloor: o.chapter === "lobby" && !!o.arcade
    readonly property bool showCards: arcadeFloor
    readonly property bool wideProfileMeta: Theme.viewportScale < .85 && Theme.textScale > 1.1
    readonly property real topH: Math.max(226, findOptions.y + findOptions.height + 12, profileIdentity.y + profileIdentity.height + profileActions.height + 20,
                                         wideProfileMeta ? profileMeta.y + profileMeta.height + profileActions.height + 20 : 0)
    function click(b) { if (b && b.index >= 0 && !b.disabled) root.backend.clickRow(b.index) }
    component Caption: Text {
        textFormat: Text.PlainText; color: Theme.text; font.family: page.root.sans
        font.pixelSize: Theme.onlinePx(14); elide: Text.ElideRight
    }
    Rectangle {
        id: profile
        objectName: "onlineProfile"
        visible: page.showCards
        x: 16; y: 8; width: (page.width - 48) * 0.36; height: page.topH
        color: Theme.card; border.width: 1; border.color: page.prof.focused ? page.acc : Theme.border
        Rectangle {
            objectName: "lobbyProfileChip"
            property var b: ({id: "online_status", index: page.prof.index})
            id: face; x: 12; y: 12; width: 72; height: page.wideProfileMeta ? 72 : 96; color: Theme.raised; clip: true
            Image { anchors.fill: parent; source: page.prof.face || ""; visible: !!source; fillMode: Image.PreserveAspectCrop }
            Item {
                visible: !page.prof.face; anchors.fill: parent
                Rectangle { width: 24; height: 24; radius: 12; anchors.horizontalCenter: parent.horizontalCenter; y: 8; color: Theme.muted; opacity: .45 }
                Rectangle { width: 56; height: 56; radius: 18; anchors.horizontalCenter: parent.horizontalCenter; y: 36; color: Theme.muted; opacity: .3 }
            }
            Rectangle {
                visible: !!page.prof.main; anchors.bottom: parent.bottom; width: parent.width; height: Math.max(22, Theme.onlinePx(14) * 1.4); color: Theme.ground
                Caption { objectName: "profileMainFighter"; anchors.centerIn: parent; width: parent.width - 8; horizontalAlignment: Text.AlignHCenter; text: page.prof.main || "" }
            }
            TapHandler { id: profileTap; onTapped: page.click(face.b) }
            Interaction { handler: profileTap; selected: !!page.prof.focused; name: [page.prof.name || "", page.prof.main || ""].filter(s => s).join(". "); onActivated: page.click(face.b) }
        }
        Column {
            id: profileIdentity
            x: 96; y: 10; width: parent.width - 108; spacing: 4
            Caption { objectName: "profileName"; width: parent.width; text: page.prof.name || ""; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: Theme.onlinePx(28) }
            Row {
                width: parent.width; spacing: 8
                Image { width: 42; height: 22; visible: !!page.prof.plate; source: page.prof.plate || ""; fillMode: Image.PreserveAspectFit }
                Caption { width: parent.width - (page.prof.plate ? 50 : 0); text: page.prof.rank || ""; color: page.acc; font.weight: Font.DemiBold }
            }
            Caption { visible: !page.wideProfileMeta; width: parent.width; text: (page.prof.rows || []).join("  \u00b7  "); font.family: page.root.mono }
            Caption { visible: !page.wideProfileMeta; width: parent.width; text: (page.prof.conn || []).join("  \u00b7  "); color: Theme.muted }
            Caption { objectName: "profileBuild"; width: parent.width; text: (page.prof.build || []).join("  \u00b7  "); color: Theme.muted; visible: !!text }
            Caption { objectName: "profilePlaytime"; width: parent.width; text: page.prof.playtime || ""; visible: !page.wideProfileMeta && !!text; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        Column {
            id: profileMeta; visible: page.wideProfileMeta
            x: 12; y: 92; width: parent.width - 24; spacing: 4
            Caption { width: parent.width; text: (page.prof.rows || []).join("  \u00b7  "); font.family: page.root.mono; wrapMode: Text.Wrap; elide: Text.ElideNone }
            Caption { width: parent.width; text: (page.prof.conn || []).join("  \u00b7  "); color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
            Caption { objectName: "profilePlaytimeWide"; width: parent.width; text: page.prof.playtime || ""; visible: !!text; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        Row {
            id: profileActions
            x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; spacing: 8
            Repeater {
                model: page.prof.buttons || []
                ArcadeAction { objectName: "lobbyProfileAction"; required property var modelData; root: page.root; b: modelData; compact: true; height: Theme.target(44); onActivated: page.click(b) }
            }
        }
    }
    Rectangle {
        id: find
        objectName: "onlineFind"
        visible: page.showCards
        x: profile.x + profile.width + 16; y: profile.y; width: page.width - x - 16; height: page.topH
        color: Theme.card; border.width: 1; border.color: Theme.border
        Caption { x: 12; y: 8; width: parent.width - 24; text: page.o.findTitle || ""; font.pixelSize: Theme.onlinePx(22); font.weight: Font.DemiBold; Accessible.role: Accessible.Heading }
        Row {
            id: findButtons; x: 12; y: 40; width: parent.width - 24; spacing: 12
            Repeater {
                model: [page.fnd.ranked || ({}), page.fnd.quick || ({})]
                Rectangle {
                    id: matchAction
                    required property var modelData
                    required property int index
                    readonly property var original: modelData
                    readonly property bool searching: !!page.o.arcade && !!page.o.arcade.search && (index === 0 ? !!page.o.arcade.search.ranked : !page.o.arcade.search.ranked)
                    readonly property var b: searching ? (page.o.arcade.search.buttons || [])[0] || ({}) : Object.assign({}, original, {disabled: !!original.disabled || !!(page.o.arcade || {}).search})
                    visible: !!original.present
                    objectName: index === 0 ? "onlineRankedAction" : "onlineCasualAction"
                    width: page.fnd.ranked && page.fnd.ranked.present ? (findButtons.width - 12) / 2 : findButtons.width; height: Math.max(80 / Math.max(.5, Theme.viewportScale), matchCaption.implicitHeight + matchNote.implicitHeight + (searching ? 14 : 16))
                    color: index === 0 ? page.acc : Theme.raised
                    border.width: b.focused ? Theme.focusWidth : 1; border.color: b.focused ? Theme.focus : Theme.border
                    opacity: b.disabled ? 0.55 : 1
                    Column {
                        x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 24 - (matchAction.searching ? searchCancel.width + 8 : 0); spacing: 2
                        Caption { id: matchCaption; objectName: "onlineMatchActionCaption"; width: parent.width; text: matchAction.searching ? (page.o.arcade.search.text || "") : (((page.o.arcade || {}).labels || {})[matchAction.index === 0 ? "ranked" : "quick"] || matchAction.original.label || ""); color: matchAction.index === 0 ? Theme.ground : Theme.text; font.pixelSize: Theme.onlinePx(matchAction.searching ? 18 : 24); font.weight: Font.Bold; wrapMode: matchAction.searching ? Text.Wrap : Text.NoWrap; maximumLineCount: matchAction.searching ? 2 : 1 }
                        Caption { id: matchNote; width: parent.width; text: matchAction.searching ? page.o.arcade.search.elapsed || "" : matchAction.original.disabled && matchAction.original.value ? page.prof.guest && page.o.arcade ? page.o.arcade.labels.needsAccount : matchAction.original.value : matchAction.index === 0 ? page.fnd.rankedNote || "" : page.fnd.quickNote || ""; color: matchAction.index === 0 ? Theme.ground : Theme.muted }
                    }
                    ArcadeAction { id: searchCancel; objectName: "searchCancelAction"; visible: matchAction.searching; root: page.root; b: matchAction.b; compact: true; height: Theme.target(44); width: Math.min(implicitWidth, parent.width * .42); anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; onActivated: page.click(b) }
                    TapHandler { id: matchTap; enabled: !matchAction.searching && !matchAction.b.disabled; onTapped: page.click(matchAction.b) }
                    Interaction { handler: matchTap; selected: !searching && !!b.focused; disabled: !searching && !!b.disabled; role: searching ? Accessible.StaticText : Accessible.Button; name: matchCaption.text + ". " + matchNote.text; onActivated: if (!matchAction.searching) page.click(matchAction.b) }
                }
            }
        }
        Flickable {
            id: findOptions
            objectName: "findOptionsViewport"
            x: 12; y: findButtons.y + findButtons.height + 8; width: find.width - 24
            height: Math.max(Theme.target(44), Theme.onlinePx(14) * 1.4 + 8)
            contentWidth: optionRow.width; clip: true; boundsBehavior: Flickable.StopAtBounds
            function revealOption() {
                for (var i = 0; i < optionChips.count; ++i) {
                    var chip = optionChips.itemAt(i)
                    if (chip && chip.b.focused) {
                        if (chip.x < contentX) contentX = chip.x
                        else if (chip.x + chip.width > contentX + width) contentX = chip.x + chip.width - width
                    }
                }
            }
            Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(findOptions.revealOption) } }
            Row {
                id: optionRow; spacing: 6
                Repeater {
                    id: optionChips
                    model: (page.fnd.delayOptions || (page.fnd.options || []).slice(0, 2)).concat([((page.o.arcade || {}).controls || {}).options || ({})])
                    ArcadeAction { objectName: "findOptionAction"; required property var modelData; root: page.root; b: modelData; visible: b.index !== undefined && (b.id !== "arcade_options" || page.arcadeFloor); compact: true; height: findOptions.height; label: [b.label || "", b.value || ""].filter(s => s).join(": "); onActivated: page.click(b) }
                }
            }
        }
    }
    Flickable {
        id: chapters
        objectName: "onlineChapters"
        x: 16; y: page.showCards ? profile.y + page.topH + 8 : 8; width: page.width - 32; height: Math.max(40, Theme.onlinePx(14) * 1.4 + 12)
        contentWidth: chapterRow.width; clip: true; boundsBehavior: Flickable.StopAtBounds
        function revealChapter() {
            for (var i = 0; i < tabs.count; ++i) {
                var tab = tabs.itemAt(i)
                if (tab && tab.modelData.active) {
                    if (tab.x < contentX) contentX = tab.x
                    else if (tab.x + tab.width > contentX + width) contentX = tab.x + tab.width - width
                }
            }
        }
        Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(chapters.revealChapter) } }
        Row {
            id: chapterRow; spacing: 4
            Repeater {
                id: tabs; model: page.o.chapters || []
                Rectangle {
                    required property var modelData
                    width: Math.max(chapterText.implicitWidth + 24, (chapters.width - 32) / 9); height: chapters.height
                    color: modelData.active ? Theme.raised : "transparent"
                    Caption { id: chapterText; anchors.centerIn: parent; text: parent.modelData.label || ""; color: parent.modelData.active ? page.acc : Theme.muted; font.weight: parent.modelData.active ? Font.Bold : Font.Normal }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: page.acc; visible: parent.modelData.active }
                    TapHandler { id: chapterTap; onTapped: page.root.backend.clickChapter(parent.modelData.id) }
                    Interaction { handler: chapterTap; selected: !!modelData.focused; name: modelData.label || ""; onActivated: page.root.backend.clickChapter(modelData.id) }
                }
            }
        }
    }
    PageLoader { x: 16; y: chapters.y + chapters.height + 8; width: page.width - 32; height: page.height - y - 8; active: page.arcadeFloor; page: "ArcadeFloor.qml"; pageName: "arcadeFloor"; root: page.root }
    OnlineBody { visible: !page.arcadeFloor; root: page.root; x: 16; y: chapters.y + chapters.height + 8; width: page.width - 32; height: page.height - y - 8 }
}
