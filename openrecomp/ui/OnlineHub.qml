import QtQuick

// The Online section's lobby page: profile card + find-opponent card on top, chapters below, the chat panel at the
// right on every chapter. Sub-pages give their section cards the full height. Actions come from v.online.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online
    readonly property var prof: o.profile || ({})
    readonly property var fnd: o.find || ({})
    readonly property var acc: Theme.readableAccent(root.v.accent)
    readonly property bool chatOpen: !!o.chatOpen
    readonly property bool arcadeFloor: o.chapter === "lobby" && !!o.arcade
    readonly property int gap: 16
    readonly property bool showCards: !arcadeFloor && o.chapter !== "ranked" && (o.chapter === "lobby" || o.focusRegion === "find")
    readonly property int topH: Math.max(226, findOptions.y + findOptions.height + 18,
                                       fnd.incoming || fnd.outgoing || fnd.notice ? findOptions.y + 180 : 0)
    readonly property int chatW: chatOpen ? 520 : 76
    readonly property color card: Theme.card
    readonly property color raised: Theme.raised
    readonly property color ink: Theme.ground

    function click(i) { if (i !== undefined && i >= 0) root.backend.clickRow(i) }
    function list(a) { return a || [] }

    component Option: OnlineStyle.Chip {
        onActivated: i => page.click(i)
    }

    PageLoader { anchors.fill: parent; active: page.arcadeFloor; page: "ArcadeFloor.qml"; pageName: "arcadeFloor"; root: page.root }

    // ================================================================ profile card: who you are, your ranked standing
    Rectangle {
        id: profile
        objectName: "onlineProfile"
        visible: page.showCards
        x: 24; y: 14; width: 640; height: page.topH
        color: page.card; border.width: 1; border.color: page.prof.focused ? page.acc : page.root.line
        Rectangle {
            id: face
            x: 16; y: 16; width: 112; height: 144; color: "#24272C"; clip: true
            Image { anchors.fill: parent; source: page.prof.face || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectCrop; visible: !!page.prof.face }
            Text {
                visible: !page.prof.face
                anchors.centerIn: parent; textFormat: Text.PlainText
                text: (page.prof.name || "?").substring(0, 1).toUpperCase()
                color: page.root.muted; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(72)
            }
            Rectangle {
                visible: !!page.prof.main
                anchors.bottom: parent.bottom; width: parent.width; height: 24; color: "#CC0E0F11"
                Text { anchors.centerIn: parent; width: parent.width - 8; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.main || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(Theme.helpSize)}
            }
        }
        Column {
            x: 144; y: 10; width: parent.width - 160; spacing: 3
            OnlineStyle.PageTitle { objectName: "profileName"; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.name || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: Theme.px(Theme.titleSize)}
            Row {
                spacing: 10; height: 28
                Image { visible: !!page.prof.plate; source: page.prof.plate || ""; height: 26; width: 52; fillMode: Image.PreserveAspectFit; asynchronous: true; anchors.verticalCenter: parent.verticalCenter }
                Text { textFormat: Text.PlainText; text: page.prof.rank || ""; color: page.acc; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(Theme.labelSize); anchors.verticalCenter: parent.verticalCenter }
                Text { textFormat: Text.PlainText; text: page.list(page.prof.rows).join("  ·  "); color: page.root.textC; font.family: page.root.mono; font.pixelSize: Theme.px(Theme.helpSize); anchors.verticalCenter: parent.verticalCenter }
            }
            // progress to the next rank (or through the placement matches)
            Item {
                visible: (page.prof.progress === undefined ? -1 : page.prof.progress) >= 0
                width: parent.width; height: 26
                Rectangle {
                    y: 9; width: parent.width * 0.55; height: 8; radius: 4; color: Theme.border
                    Rectangle { height: parent.height; radius: 4; width: parent.width * Math.max(0, page.prof.progress || 0); color: page.acc }
                }
                Text { x: parent.width * 0.55 + 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.45 - 12; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.prof.progressText || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize)}
            }
            Row {
                visible: page.list(page.prof.recent).length > 0
                spacing: 4; height: 26
                Text { textFormat: Text.PlainText; text: page.prof.recentLabel || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize); anchors.verticalCenter: parent.verticalCenter; rightPadding: 6 }
                Repeater {
                    model: page.list(page.prof.recent).length
                    Rectangle {
                        id: result
                        required property int index
                        readonly property var c: page.root.ok(page.prof.recent, index)
                        width: 24; height: 24; color: c.win ? page.acc : "transparent"; border.width: 1; border.color: c.win ? page.acc : Theme.muted
                        Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: result.c.text || ""; color: result.c.win ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: Theme.px(Theme.helpSize)}
                    }
                }
            }
            OnlineStyle.HelpText { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.list(page.prof.conn).join("  ·  "); color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize)}
            OnlineStyle.HelpText { objectName: "profileBuild"; visible: text !== ""; width: parent.width - 230; elide: Text.ElideMiddle; textFormat: Text.PlainText; text: page.list(page.prof.build).join("  ·  "); color: page.root.muted; font.family: page.root.mono; font.pixelSize: Theme.px(Theme.helpSize)}
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 12; spacing: 8
            Repeater {
                model: page.list(page.prof.buttons).length
                Option { required property int index; b: page.root.ok(page.prof.buttons, index); maxW: 170 }
            }
        }
        TapHandler { id: uiTap0; onTapped: page.click(page.prof.index) }
        Interaction { handler: uiTap0; selected: !!page.prof.focused; onActivated: page.click(page.prof.index) }
    }

    // ================================================================ find an opponent
    Rectangle {
        id: find
        objectName: "onlineFind"
        visible: page.showCards
        x: profile.x + profile.width + 16; y: 14; width: 1920 - 24 - x; height: page.topH
        color: page.card; border.width: 1; border.color: page.root.line
        OnlineStyle.SectionHeader { x: 20; y: 12; width: parent.width - 40; text: page.o.findTitle || "" }
        Row {
            id: findButtons
            x: 20; y: 54; spacing: 12
            Repeater {
                model: [page.fnd.ranked || ({}), page.fnd.quick || ({})]
                Column {
                    id: big
                    required property var modelData
                    required property int index
                    readonly property var b: modelData || ({})
                    visible: !!b.present
                    width: (find.width - 52) / (page.fnd.ranked && page.fnd.ranked.present ? 2 : 1)
                    spacing: 5
                    OnlineStyle.PrimaryButton {
                        width: big.width; maxW: width
                        b: ({label: big.b.label, index: big.b.index, focused: big.b.focused, disabled: big.b.disabled})
                        primary: big.index === 0
                        accent: page.acc; fontSize: Theme.sectionSize
                        onActivated: i => page.click(i)
                    }
                    OnlineStyle.HelpText {
                        width: parent.width
                        text: big.index === 0 ? (big.b.disabled && big.b.value ? big.b.value : page.fnd.rankedNote || "") : page.fnd.quickNote || ""
                    }
                }
            }
        }
        Column {
            id: findOptions
            x: 20; y: findButtons.y + findButtons.height + 14; width: find.width - 40; spacing: 8
            Repeater {
                model: page.fnd.groups || []
                Column {
                    required property var modelData
                    width: findOptions.width; spacing: 5
                    OnlineStyle.HelpText { width: parent.width; text: parent.modelData.label || "" }
                    Flow {
                        width: parent.width; spacing: 6
                        Repeater {
                            model: parent.parent.modelData.options || []
                            Option { required property var modelData; b: modelData; maxW: findOptions.width }
                        }
                    }
                }
            }
            Flow {
                width: parent.width; spacing: 6
                Repeater {
                    model: page.fnd.extra || []
                    Option { required property var modelData; b: modelData; maxW: findOptions.width }
                }
            }
        }
        // another launcher of this game is open: the note sits over the options until the player chose
        Rectangle {
            objectName: "otherLauncherNote"
            visible: !!(page.fnd.notice && page.fnd.notice.text) && !page.fnd.incoming
            x: 20; y: findOptions.y; width: find.width - 40; height: page.topH - y - 10; color: page.raised
            border.width: 1; border.color: page.acc
            Text { x: 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width - noticeRow.width - 50; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.fnd.notice ? (page.fnd.notice.text || "") : ""; color: page.root.textC; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize)}
            Row {
                id: noticeRow
                anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                Repeater {
                    model: page.fnd.notice ? page.list(page.fnd.notice.buttons).length : 0
                    Option { required property int index; b: page.root.ok(page.fnd.notice.buttons, index); strong: true; maxW: 260 }
                }
            }
        }
        // A challenge sits over the options until it is answered or cancelled.
        Rectangle {
            id: challengeBanner
            readonly property var offer: page.fnd.incoming || page.fnd.outgoing || ({})
            visible: !!page.fnd.incoming || !!page.fnd.outgoing
            x: 20; y: findOptions.y; width: find.width - 40; height: page.topH - y - 10; color: page.acc
            Column {
                x: 18; anchors.verticalCenter: parent.verticalCenter; width: parent.width - incomingRow.width - 50; spacing: 3
                Text { objectName: "challengeBannerTitle"; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: challengeBanner.offer.text || ""; color: page.ink; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(Theme.sectionSize)}
                PeerPing { connection: challengeBanner.offer.connection || ({}); ink: page.ink; dim: "#8A3838" }
                Text {
                    objectName: "challengeBannerTerms"
                    width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText
                    text: page.list(challengeBanner.offer.details).map(function(r) { return r.k + ": " + r.v }).join(" · ")
                    color: page.ink; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize)
                }
            }
            Row {
                id: incomingRow
                anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                Repeater {
                    model: page.list(challengeBanner.offer.buttons).length
                    Option { required property int index; b: page.root.ok(challengeBanner.offer.buttons, index); strong: true; maxW: 240 }
                }
            }
        }
    }

    // ================================================================ chapters
    Item {
        id: chapters
        objectName: "onlineChapters"
        visible: !page.arcadeFloor && !page.root.v.mainMenu.available
        x: 24; y: page.showCards ? 14 + page.topH + 10 : 14; width: 1920 - 48; height: visible ? 58 : 0
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 4
            Glyph { g: page.o.prevG || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
            Item { width: 8; height: 1 }
            Repeater {
                model: page.list(page.o.chapters).length
                Rectangle {
                    id: tab
                    required property int index
                    readonly property var c: page.root.ok(page.o.chapters, index)
                    width: (chapters.width - 136) / Math.max(1, page.list(page.o.chapters).length); height: 58
                    color: "transparent"
                    Row {
                        id: tabRow
                        anchors.centerIn: parent; width: parent.width - 12; spacing: 6
                        OnlineStyle.FieldLabel { text: tab.c.label || ""; width: parent.width - (chapterBadge.visible ? chapterBadge.width + 6 : 0); horizontalAlignment: Text.AlignHCenter; color: tab.c.active ? page.root.textC : page.root.muted; anchors.verticalCenter: parent.verticalCenter }
                        Rectangle {
                            id: chapterBadge
                            visible: !!tab.c.badge
                            width: Math.max(28, badgeText.implicitWidth + 12); height: 26; radius: 13; color: tab.c.active ? page.acc : Theme.border
                            anchors.verticalCenter: parent.verticalCenter
                            Text { id: badgeText; anchors.centerIn: parent; textFormat: Text.PlainText; text: tab.c.badge || ""; color: tab.c.active ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: Theme.px(Theme.helpSize)}
                        }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: page.acc; visible: !!tab.c.active }
                    TapHandler { id: uiTap1; onTapped: page.root.backend.clickChapter(tab.c.id) }
                    Interaction { handler: uiTap1; selected: !!tab.c.focused; onActivated: page.root.backend.clickChapter(tab.c.id) }
                }
            }
            Item { width: 8; height: 1 }
            Glyph { g: page.o.nextG || ({}); size: 30; anchors.verticalCenter: parent.verticalCenter }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: page.root.line }
    }

    OnlineBody {
        visible: !page.arcadeFloor
        root: page.root
        x: 24; y: chapters.y + chapters.height + 12
        width: 1920 - 48 - page.chatW - page.gap; height: page.height - y - 16
    }

    // ================================================================ the chat panel (every chapter)
    Rectangle {
        id: chat
        objectName: "onlineChat"
        visible: !page.arcadeFloor || page.o.focusRegion === "chat"
        readonly property var c: page.o.chat || ({})
        x: 1920 - 24 - page.chatW; y: page.arcadeFloor ? 86 : chapters.y + chapters.height + 12; width: page.chatW; height: page.height - y - 16
        color: page.card; border.width: 1; border.color: page.o.focusRegion === "chat" ? page.acc : page.root.line
        clip: true
        // closed: a slim strip with the unread count
        Item {
            visible: !page.chatOpen
            anchors.fill: parent
            Rectangle {
                visible: (chat.c.unread || 0) > 0
                anchors.horizontalCenter: parent.horizontalCenter; y: 16; width: 44; height: 44; radius: 22; color: page.acc
                Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: String(chat.c.unread || 0); color: page.ink; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(Theme.helpSize)}
            }
            Item {
                x: 0; y: 76; width: parent.width; height: parent.height - 76 - 76
                Text {
                    anchors.centerIn: parent; rotation: 90; width: parent.height; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                    textFormat: Text.PlainText; text: chat.c.title || ""; color: page.root.textC
                    font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(Theme.sectionSize)
                }
            }
            Glyph { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; g: page.o.chatG || ({}); size: 40 }
            TapHandler { id: uiTap2; onTapped: page.click(chat.c.toggle ? chat.c.toggle.index : -1) }
            Interaction { handler: uiTap2; selected: !!(chat.c.toggle || {}).focused; onActivated: page.click(chat.c.toggle ? chat.c.toggle.index : -1) }
        }
        Item {
            visible: page.chatOpen
            anchors.fill: parent
            Row {
                id: chatHead
                x: 18; y: 12; spacing: 12; width: chat.width - chatToggle.width - 48
                OnlineStyle.SectionHeader { width: chatHead.width - 36; text: chat.c.title || ""; anchors.verticalCenter: parent.verticalCenter }
                Rectangle {
                    visible: (chat.c.unread || 0) > 0; width: 30; height: 26; radius: 13; color: page.acc; anchors.verticalCenter: parent.verticalCenter
                    Text { anchors.centerIn: parent; textFormat: Text.PlainText; text: String(chat.c.unread || 0); color: page.ink; font.family: page.root.mono; font.pixelSize: Theme.px(Theme.helpSize)}
                }
            }
            Option { id: chatToggle; anchors.right: parent.right; anchors.rightMargin: 14; y: 10; b: chat.c.toggle || ({}); maxW: 200 }
            // tabs: lobby chat and private conversations
            Flow {
                id: chatTabs
                x: 14; y: Math.max(chatHead.y + chatHead.height, chatToggle.y + chatToggle.height) + 10; width: parent.width - 28; spacing: 6
                Repeater {
                    model: page.list(chat.c.tabs).length
                    Option {
                        required property int index
                        b: page.root.ok(chat.c.tabs, index); maxW: 220
                        strong: !!b.active
                        Rectangle { visible: !!parent.b.active && !parent.b.focused; anchors.bottom: parent.bottom; width: parent.width; height: 3; color: page.acc }
                    }
                }
            }
            // the conversation, newest at the bottom
            Item {
                id: lines
                x: 14; y: chatTabs.y + chatTabs.height + 10; width: parent.width - 28
                height: compose.y - y - 10 - (otherRow.visible ? otherRow.height + 8 : 0)
                clip: true
                Column {
                    width: parent.width; anchors.bottom: parent.bottom; spacing: 6
                    Repeater {
                        model: page.list(chat.c.lines).length
                        Rectangle {
                            required property int index
                            readonly property var m: page.root.ok(chat.c.lines, index)
                            width: lines.width; height: msg.implicitHeight + 8
                            color: m.focused ? "#2A2E35" : "transparent"
                            Rectangle { visible: !!parent.m.focused; width: 3; height: parent.height; color: page.acc }
                            Column {
                                id: msg
                                x: 8; y: 4; width: parent.width - 16
                                OnlineStyle.FieldLabel { visible: !!parent.parent.m.name; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.m.name || ""; color: parent.parent.m.own ? page.root.textC : page.acc; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(Theme.helpSize)}
                                OnlineStyle.HelpText { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.m.text || ""; color: parent.parent.m.system ? page.root.muted : page.root.textC; font.family: page.root.sans; font.pixelSize: Theme.px(Theme.helpSize)}
                            }
                            TapHandler { id: uiTap3; onTapped: page.click(parent.m.index) }
                            Interaction { handler: uiTap3; selected: !!parent.m.focused; onActivated: page.click(parent.m.index) }
                        }
                    }
                }
            }
            Flow {
                id: otherRow
                visible: page.list(chat.c.other).length > 0
                x: 14; anchors.bottom: compose.top; anchors.bottomMargin: 8; width: parent.width - 28; spacing: 6
                Repeater {
                    model: page.list(chat.c.other).length
                    Option { required property int index; b: page.root.ok(chat.c.other, index); maxW: 230 }
                }
            }
            // text field + Send
            Row {
                id: compose
                x: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 14; spacing: 8
                Rectangle {
                    readonly property var f: chat.c.compose || ({})
                    width: chat.width - 28 - sendChip.width - 8; height: 48
                    color: f.focused ? page.root.bone : Theme.ground; border.width: 1; border.color: page.root.line
                    Text {
                        x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 24; elide: Text.ElideLeft; textFormat: Text.PlainText
                        text: parent.f.value || parent.f.label || ""
                        color: parent.f.focused ? page.ink : (parent.f.value ? page.root.textC : page.root.muted)
                        font.family: page.root.sans; font.pixelSize: Theme.px(Theme.labelSize)
                    }
                    TapHandler { id: uiTap4; onTapped: page.click(parent.f.index) }
                    Interaction { handler: uiTap4; selected: !!parent.f.focused; onActivated: page.click(parent.f.index) }
                }
                Option { id: sendChip; b: chat.c.send || ({}); strong: true; maxW: 230 }
            }
        }
    }
}
