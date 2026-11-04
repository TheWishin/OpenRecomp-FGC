import QtQuick

// One game: fixed section tabs, the list on the left, the live detail panel on the right.
Column {
    id: hub
    required property var root
    readonly property var v: root.v
    readonly property var d: v.detail
    readonly property bool hasImages: (d.images || []).length > 0 || !!d.image
    property string lastSection: ""
    readonly property bool communityLobby: v.online.layout === "lobby" && v.online.chapter === "lobby"
    readonly property real navHeight: communityLobby || (v.mainMenu.available && root.chatDocked) ? 0 : Math.max(64, Theme.target(44) + 14)
    Connections {
        target: hub.root.backend
        function onViewChanged() {
            var active = hub.v.tabs.filter(t => t.active).map(t => t.id).join("")
            if (active !== hub.lastSection) {
                hub.lastSection = active
                if (!hub.root.reducedMotion) sectionReveal.restart()
            }
        }
    }
    Connections {
        target: hub.root
        function onReducedMotionChanged() {
            if (hub.root.reducedMotion) {
                sectionReveal.stop()
                detailContent.opacity = 1
            }
        }
    }
    NumberAnimation { id: sectionReveal; target: detailContent; property: "opacity"; from: 0.6; to: 1; duration: 120; easing.type: Easing.OutCubic }

    Rectangle {
        objectName: "sectionTabs"
        visible: !hub.v.mainMenu.available && !hub.communityLobby
        width: hub.width; height: hub.navHeight; color: hub.root.bar
        Rectangle { width: parent.width; height: 1; color: hub.root.line }
        Row {
            anchors.fill: parent
            Item {
                width: 120; height: 64
                Glyph { anchors.centerIn: parent; g: hub.v.prevG; size: 36 }
                TapHandler { id: uiTap0; onTapped: hub.root.backend.press("prev") }
                Interaction { handler: uiTap0; selected: false; onActivated: hub.root.backend.press("prev") }
            }
            Repeater {
                model: hub.v.tabs.length
                Rectangle {
                    required property int index
                    readonly property var t: hub.root.ok(hub.v.tabs, index)
                    width: (hub.width - 240) / Math.max(1, hub.v.tabs.length); height: 64
                    color: t.active ? hub.root.panel : "transparent"
                    Behavior on color { enabled: !hub.root.reducedMotion; ColorAnimation { duration: 100 } }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: Theme.readableAccent(hub.v.accent); visible: !!parent.t.active }
                    Text { objectName: "sectionTabLabel"; textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width - 28; height: 60; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: parent.t.label || ""; color: parent.t.active ? hub.root.textC : hub.root.muted; font.family: hub.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(28); minimumPixelSize: Theme.px(16); fontSizeMode: Text.Fit; wrapMode: Text.Wrap; maximumLineCount: 2 }
                    TapHandler { id: uiTap1; onTapped: hub.root.backend.clickTab(parent.t.id) }
                    Interaction { handler: uiTap1; selected: !!parent.t.active; onActivated: hub.root.backend.clickTab(parent.t.id) }
                }
            }
            Item {
                width: 120; height: 64
                Glyph { anchors.centerIn: parent; g: hub.v.nextG; size: 36 }
                TapHandler { id: uiTap2; onTapped: hub.root.backend.press("next") }
                Interaction { handler: uiTap2; selected: false; onActivated: hub.root.backend.press("next") }
            }
        }
    }

    Rectangle {
        visible: !!hub.v.mainMenu.available && !hub.communityLobby && !hub.root.chatDocked
        width: hub.width; height: hub.navHeight; color: hub.root.bar
        Row {
            x: 24; y: 7; spacing: 24
            OnlineStyle.SecondaryButton {
                b: ({label: hub.v.mainMenu.homeLabel || ""})
                maxW: 500
                onActivated: hub.root.backend.press("home")
            }
            OnlineStyle.HelpText { anchors.verticalCenter: parent.verticalCenter; text: hub.v.tabs.filter(t => t.active).map(t => t.label).join(""); color: Theme.value }
        }
    }

    PageLoader {
        page: "OnlineHub.qml"; pageName: "onlineHub"
        active: hub.v.online.layout === "lobby"
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    PageLoader {
        page: "OnlineCard.qml"; pageName: "onlineCardPage"
        active: hub.v.online.layout === "card"
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    PageLoader {
        page: "OnlineLogin.qml"; pageName: "onlineLoginPage"
        active: hub.v.online.layout === "login"
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    PageLoader {
        page: "SettingsHub.qml"; pageName: "settingsHub"
        active: hub.v.settingsPage.layout === "groups"
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    PageLoader {
        page: "BuildPage.qml"; pageName: "buildPage"
        active: !!(hub.v.build && hub.v.build.show)
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    PageLoader {
        page: "SessionPage.qml"; pageName: "sessionPage"
        active: !!(hub.v.sessionPage && hub.v.sessionPage.show)
        width: hub.width; height: parent.height - hub.navHeight
        root: hub.root
    }

    Row {
        visible: !(hub.v.sessionPage && hub.v.sessionPage.show) && !(hub.v.build && hub.v.build.show) && ["lobby", "card", "login"].indexOf(hub.v.online.layout) < 0 && hub.v.settingsPage.layout !== "groups"
        width: hub.width; height: parent.height - hub.navHeight
        // ---------------------------------------------------------------- the list
        Item {
            id: listArea
            objectName: "hubList"
            width: 760; height: parent.height
            clip: true
            Rectangle { x: 24; y: 16; width: parent.width - 40; height: parent.height - 32; color: Theme.card; border.width: 1; border.color: hub.root.line }
            Column {
                y: 24; width: parent.width
                Repeater {
                    model: hub.v.rows.length
                    Item {
                        id: row
                        objectName: "hubRow"
                        required property int index
                        readonly property var r: hub.root.ok(hub.v.rows, index)
                        width: 760
                        height: r.heading ? 44 + (r.mt || 0) : Math.min(68, (listArea.height - 64) / Math.max(1, hub.v.rows.length))
                        Text {
                            visible: !!row.r.heading
                            x: 48; width: parent.width - 96; height: 40; anchors.bottom: parent.bottom
                            textFormat: Text.PlainText; text: row.r.label || ""; color: hub.root.muted; font.family: hub.root.mono; font.pixelSize: Theme.px(22)
                            minimumPixelSize: Theme.px(18); fontSizeMode: Text.Fit; verticalAlignment: Text.AlignVCenter
                        }
                        Rectangle {
                            visible: !row.r.heading
                            anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 24; anchors.topMargin: 3; anchors.bottomMargin: 3
                            radius: 4
                            color: row.r.focused ? hub.root.bone : Theme.raised
                            Behavior on color { enabled: !hub.root.reducedMotion; ColorAnimation { duration: 90 } }
                            clip: true
                            Rectangle { height: parent.height; width: parent.width * (row.r.holdPct || 0); color: Theme.readableAccent(hub.v.accent) }
                            Text {
                                objectName: "hubRowLabel"
                                x: 16; width: rowAction.x - x - 16; height: parent.height - 12; anchors.verticalCenter: parent.verticalCenter
                                textFormat: Text.PlainText; text: row.r.label || ""
                                color: row.r.focused ? Theme.ground : (row.r.hold ? Theme.readableAccent(hub.v.accent) : (row.r.disabled ? Theme.muted : hub.root.textC))
                                font.family: hub.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(25)
                                minimumPixelSize: Theme.px(22); fontSizeMode: Text.Fit; wrapMode: Text.Wrap; maximumLineCount: 2; verticalAlignment: Text.AlignVCenter
                            }
                            Row {
                                id: rowAction
                                anchors.right: parent.right; anchors.rightMargin: 32; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                                Text {
                                    visible: !!row.r.value; anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, 210); elide: Text.ElideMiddle
                                    textFormat: Text.PlainText; text: row.r.value || ""; color: row.r.focused ? Theme.ground : (row.r.missing ? Theme.readableAccent(hub.v.accent) : hub.root.muted); font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: Theme.px(20)
                                }
                                Text { textFormat: Text.PlainText; visible: !!row.r.verb; width: Math.min(implicitWidth, 160); elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: row.r.verb || ""; color: Theme.ground; font.family: hub.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(20)}
                                Glyph { visible: !!row.r.verb; size: 32; g: hub.v.confirmInk; anchors.verticalCenter: parent.verticalCenter }
                            }
                            TapHandler { id: uiTap3; onTapped: hub.root.backend.clickRow(row.r.index) }
                            Interaction { handler: uiTap3; selected: !!row.r.focused; onActivated: hub.root.backend.clickRow(row.r.index) }
                        }
                    }
                }
            }
            Text { textFormat: Text.PlainText; visible: hub.v.more.up; x: 720; y: 2; text: "▲"; color: hub.root.muted; font.pixelSize: Theme.px(18)}
            Text { textFormat: Text.PlainText; visible: hub.v.more.down; x: 720; anchors.bottom: parent.bottom; anchors.bottomMargin: 2; text: "▼"; color: hub.root.muted; font.pixelSize: Theme.px(18)}
        }

        // ---------------------------------------------------------------- the detail panel
        Rectangle {
            width: 1160; height: parent.height
            color: hub.root.ground
            clip: true
            Rectangle { x: 0; y: 16; width: parent.width - 24; height: parent.height - 32; color: Theme.card; border.width: 1; border.color: hub.root.line }
            Image {
                visible: !!hub.v.hero && hub.v.tabs.length > 0 && (hub.d.images || []).length === 0 && !hub.d.image
                source: hub.v.hero || ""
                width: 760; height: 760; x: 1160 - 640; y: 30
                opacity: 0.22; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit
            }
            Item {
                objectName: "detailContent"
                x: 32; y: 40; width: 1072
                height: Math.min(detailContent.implicitHeight, parent.height - y - (hub.d.primary ? 160 : 32))
                Column {
                    id: detailContent
                    width: parent.width; spacing: 0
                    transformOrigin: Item.TopLeft
                    scale: Math.min(1, parent.height / Math.max(1, implicitHeight))
                    Text { textFormat: Text.PlainText; width: parent.width; text: hub.d.kicker || ""; elide: Text.ElideRight; color: Theme.readableAccent(hub.v.accent); font.family: hub.root.mono; font.weight: Font.Medium; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(18)}
                    Text { objectName: "detailTitle"; width: parent.width; topPadding: 8; textFormat: Text.PlainText; text: hub.d.title || ""; wrapMode: Text.Wrap; lineHeight: 0.95; color: hub.root.textC; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(50)}
                    Text { objectName: "detailLead"; width: parent.width; topPadding: 12; visible: !!hub.d.lead; textFormat: Text.PlainText; text: hub.d.lead || ""; wrapMode: Text.Wrap; lineHeight: 1.1; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: Theme.px(23)}
                    Item { width: 1; height: 16 }
                    Row {
                        visible: hub.hasImages
                        spacing: 12
                        bottomPadding: 16
                        Repeater {
                            model: (hub.d.images || []).length
                            Rectangle {
                                required property int index
                                width: 96; height: 96; color: "#1B1D21"
                                Image { anchors.fill: parent; source: (hub.d.images || [])[parent.index] || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit }
                            }
                        }
                        Rectangle {
                            visible: !!hub.d.image
                            width: 96; height: 96; color: "#1B1D21"
                            Image { anchors.fill: parent; source: hub.d.image || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit }
                        }
                    }
                    Rectangle {
                        visible: (hub.d.progress === undefined ? -1 : hub.d.progress) >= 0
                        objectName: "buildProgress"
                        width: parent.width; height: 16; color: "#24272C"
                        Rectangle { height: parent.height; width: parent.width * Math.max(0, hub.d.progress === undefined ? 0 : hub.d.progress); color: Theme.readableAccent(hub.v.accent) }
                    }
                    Repeater {
                        model: (hub.d.rows || []).length
                        Rectangle {
                            required property int index
                            readonly property var r: hub.root.ok(hub.d.rows, index)
                            width: detailContent.width; height: Math.max((hub.d.rows || []).length > 5 ? 38 : (hub.hasImages ? 44 : 48), Math.max(detailKey.implicitHeight, detailValue.implicitHeight) + 12); color: "transparent"
                            Rectangle { width: parent.width; height: 1; color: hub.root.line }
                            Text { id: detailKey; objectName: "detailKey"; width: parent.width * 0.45; wrapMode: Text.Wrap; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: parent.r.k || ""; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: Theme.px(26)}
                            Text { id: detailValue; objectName: "detailValue"; width: parent.width * 0.53; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; textFormat: Text.PlainText; text: parent.r.v || ""; color: parent.r.accent ? Theme.readableAccent(hub.v.accent) : hub.root.textC; font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: Theme.px(26)}
                        }
                    }
                    Row {
                        visible: (hub.d.results || []).length > 0
                        spacing: 8
                        topPadding: 16
                        Text { textFormat: Text.PlainText; text: hub.v.recentSets; width: 260; elide: Text.ElideRight; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: Theme.px(26); anchors.verticalCenter: parent.verticalCenter }
                        Repeater {
                            model: (hub.d.results || []).length
                            ResultCell { required property int index; c: hub.root.ok(hub.d.results, index); accent: Theme.readableAccent(hub.v.accent); root: hub.root }
                        }
                    }
                    }
            }
            Rectangle {
                objectName: "primaryAction"
                visible: !!hub.d.primary
                x: 32; y: parent.height - 112 - 32
                width: 1072; height: 80; radius: 4
                color: hub.root.bone
                Rectangle { width: 6; height: parent.height; color: Theme.readableAccent(hub.v.accent) }
                Text { textFormat: Text.PlainText; x: 24; width: parent.width - 112; height: parent.height - 24; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; minimumPixelSize: Theme.px(28); fontSizeMode: Text.Fit; anchors.verticalCenter: parent.verticalCenter; text: hub.d.primary || ""; color: Theme.ground; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(40)}
                Glyph { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; size: 40; g: hub.d.primaryG || ({}) }
                TapHandler { id: uiTap4; onTapped: hub.root.backend.clickPrimary() }
                Interaction { handler: uiTap4; selected: !!hub.d.focused; onActivated: hub.root.backend.clickPrimary() }
            }
        }
    }
}
