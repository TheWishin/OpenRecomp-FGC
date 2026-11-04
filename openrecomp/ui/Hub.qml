import QtQuick

// One game: fixed section tabs, the list on the left, the live detail panel on the right.
Column {
    id: hub
    required property var root
    readonly property var v: root.v
    readonly property var d: v.detail
    readonly property bool hasImages: (d.images || []).length > 0 || !!d.image
    property string lastSection: ""
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
        width: 1920; height: 64; color: hub.root.bar
        Rectangle { width: parent.width; height: 1; color: hub.root.line }
        Row {
            anchors.fill: parent
            Item {
                width: 120; height: 64
                Glyph { anchors.centerIn: parent; g: hub.v.prevG; size: 36 }
                TapHandler { onTapped: hub.root.backend.press("prev") }
            }
            Repeater {
                model: hub.v.tabs.length
                Rectangle {
                    required property int index
                    readonly property var t: hub.root.ok(hub.v.tabs, index)
                    width: (1920 - 240) / Math.max(1, hub.v.tabs.length); height: 64
                    color: t.active ? hub.root.panel : "transparent"
                    Behavior on color { enabled: !hub.root.reducedMotion; ColorAnimation { duration: 100 } }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: hub.v.accent; visible: !!parent.t.active }
                    Text { textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width - 28; height: 48; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: parent.t.label || ""; color: parent.t.active ? hub.root.textC : hub.root.muted; font.family: hub.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 28; minimumPixelSize: 20; fontSizeMode: Text.Fit; elide: Text.ElideRight }
                    TapHandler { onTapped: hub.root.backend.clickTab(parent.t.id) }
                }
            }
            Item {
                width: 120; height: 64
                Glyph { anchors.centerIn: parent; g: hub.v.nextG; size: 36 }
                TapHandler { onTapped: hub.root.backend.press("next") }
            }
        }
    }

    PageLoader {
        page: "OnlineHub.qml"; pageName: "onlineHub"
        active: hub.v.online.layout === "lobby"
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    PageLoader {
        page: "OnlineCard.qml"; pageName: "onlineCardPage"
        active: hub.v.online.layout === "card"
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    PageLoader {
        page: "OnlineLogin.qml"; pageName: "onlineLoginPage"
        active: hub.v.online.layout === "login"
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    PageLoader {
        page: "SettingsHub.qml"; pageName: "settingsHub"
        active: hub.v.settingsPage.layout === "groups"
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    PageLoader {
        page: "BindingsPage.qml"; pageName: "bindingsPage"
        active: hub.v.bindingsPage.layout === "bindings"
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    PageLoader {
        page: "BuildPage.qml"; pageName: "buildPage"
        active: !!(hub.v.build && hub.v.build.show)
        width: 1920; height: parent.height - 64
        root: hub.root
    }

    Row {
        visible: !(hub.v.build && hub.v.build.show) && ["lobby", "card", "login"].indexOf(hub.v.online.layout) < 0 && hub.v.settingsPage.layout !== "groups" && hub.v.bindingsPage.layout !== "bindings"
        width: 1920; height: parent.height - 64
        // ---------------------------------------------------------------- the list
        Item {
            id: listArea
            objectName: "hubList"
            width: 760; height: parent.height
            clip: true
            Column {
                y: 16; width: parent.width
                Repeater {
                    model: hub.v.rows.length
                    Item {
                        id: row
                        objectName: "hubRow"
                        required property int index
                        readonly property var r: hub.root.ok(hub.v.rows, index)
                        width: 760
                        height: r.heading ? 44 + (r.mt || 0) : Math.min(r.focused ? 100 : 84, (listArea.height - 32) / Math.max(1, hub.v.rows.length))
                        Text {
                            visible: !!row.r.heading
                            x: 48; width: parent.width - 96; height: 40; anchors.bottom: parent.bottom
                            textFormat: Text.PlainText; text: row.r.label || ""; color: hub.root.muted; font.family: hub.root.mono; font.pixelSize: 22
                            minimumPixelSize: 18; fontSizeMode: Text.Fit; verticalAlignment: Text.AlignVCenter
                        }
                        Rectangle {
                            visible: !row.r.heading
                            anchors.fill: parent
                            color: row.r.focused ? hub.root.bone : "transparent"
                            Behavior on color { enabled: !hub.root.reducedMotion; ColorAnimation { duration: 90 } }
                            clip: true
                            Rectangle { height: parent.height; width: parent.width * (row.r.holdPct || 0); color: hub.v.accent }
                            Text {
                                objectName: "hubRowLabel"
                                x: 48; width: rowAction.x - x - 20; height: parent.height - 12; anchors.verticalCenter: parent.verticalCenter
                                textFormat: Text.PlainText; text: row.r.label || ""
                                color: row.r.focused ? "#0E0F11" : (row.r.hold ? hub.v.accent : (row.r.disabled ? "#8A8D94" : hub.root.textC))
                                font.family: hub.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: row.r.focused ? 52 : 42
                                minimumPixelSize: 22; fontSizeMode: Text.Fit; wrapMode: Text.Wrap; maximumLineCount: 2; verticalAlignment: Text.AlignVCenter
                            }
                            Row {
                                id: rowAction
                                anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 16
                                Text {
                                    visible: !!row.r.value; anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, 240); elide: Text.ElideMiddle
                                    textFormat: Text.PlainText; text: row.r.value || ""; color: row.r.focused ? "#0E0F11" : (row.r.missing ? hub.v.accent : hub.root.muted); font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 26
                                }
                                Text { textFormat: Text.PlainText; visible: !!row.r.verb; width: Math.min(implicitWidth, 200); elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: row.r.verb || ""; color: "#0E0F11"; font.family: hub.root.sans; font.weight: Font.DemiBold; font.pixelSize: 26 }
                                Glyph { visible: !!row.r.verb; g: hub.v.confirmInk; anchors.verticalCenter: parent.verticalCenter }
                            }
                            TapHandler { onTapped: hub.root.backend.clickRow(row.r.index) }
                        }
                    }
                }
            }
            Text { textFormat: Text.PlainText; visible: hub.v.more.up; x: 720; y: 2; text: "▲"; color: hub.root.muted; font.pixelSize: 18 }
            Text { textFormat: Text.PlainText; visible: hub.v.more.down; x: 720; anchors.bottom: parent.bottom; anchors.bottomMargin: 2; text: "▼"; color: hub.root.muted; font.pixelSize: 18 }
        }

        // ---------------------------------------------------------------- the detail panel
        Rectangle {
            width: 1160; height: parent.height
            color: hub.root.panel
            clip: true
            Text { textFormat: Text.PlainText; x: 1160 - implicitWidth - 8; y: -90; text: hub.v.numeral; color: "#1A1C20"; font.family: hub.root.display; font.weight: Font.Black; font.pixelSize: 980 }
            Image {
                visible: !!hub.v.hero && hub.v.tabs.length > 0 && (hub.d.images || []).length === 0 && !hub.d.image
                source: hub.v.hero || ""
                width: 760; height: 760; x: 1160 - 640; y: 30
                opacity: 0.22; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit
            }
            Item {
                objectName: "detailContent"
                x: 72; y: 32; width: 1016
                height: Math.min(detailContent.implicitHeight, parent.height - y - (hub.d.primary ? 160 : 32))
                Column {
                    id: detailContent
                    width: parent.width; spacing: 0
                    transformOrigin: Item.TopLeft
                    scale: Math.min(1, parent.height / Math.max(1, implicitHeight))
                    Text { textFormat: Text.PlainText; width: parent.width; text: hub.d.kicker || ""; elide: Text.ElideRight; color: hub.v.accent; font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 24 }
                    Text { objectName: "detailTitle"; width: parent.width; topPadding: 8; textFormat: Text.PlainText; text: hub.d.title || ""; wrapMode: Text.Wrap; lineHeight: 0.95; color: hub.root.textC; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: hub.hasImages ? 64 : 72 }
                    Text { objectName: "detailLead"; width: parent.width; topPadding: 12; visible: !!hub.d.lead; textFormat: Text.PlainText; text: hub.d.lead || ""; wrapMode: Text.Wrap; lineHeight: 1.1; color: hub.root.textC; font.family: hub.root.sans; font.pixelSize: 28 }
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
                        Rectangle { height: parent.height; width: parent.width * Math.max(0, hub.d.progress === undefined ? 0 : hub.d.progress); color: hub.v.accent }
                    }
                    Repeater {
                        model: (hub.d.rows || []).length
                        Rectangle {
                            required property int index
                            readonly property var r: hub.root.ok(hub.d.rows, index)
                            width: detailContent.width; height: Math.max((hub.d.rows || []).length > 5 ? 38 : (hub.hasImages ? 44 : 48), Math.max(detailKey.implicitHeight, detailValue.implicitHeight) + 12); color: "transparent"
                            Rectangle { width: parent.width; height: 1; color: hub.root.line }
                            Text { id: detailKey; objectName: "detailKey"; width: parent.width * 0.45; wrapMode: Text.Wrap; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: parent.r.k || ""; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: 26 }
                            Image { objectName: "detailPlate"; visible: !!parent.r.plate; source: parent.r.plate || ""; height: 34; width: 68; fillMode: Image.PreserveAspectFit; asynchronous: true; sourceSize.height: 68; anchors.verticalCenter: parent.verticalCenter; x: detailValue.x + detailValue.width - detailValue.contentWidth - width - 10 }
                            Text { id: detailValue; objectName: "detailValue"; width: parent.width * 0.53; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap; anchors.verticalCenter: parent.verticalCenter; anchors.right: parent.right; textFormat: Text.PlainText; text: parent.r.v || ""; color: parent.r.accent ? hub.v.accent : hub.root.textC; font.family: hub.root.mono; font.weight: Font.Medium; font.pixelSize: 26 }
                        }
                    }
                    Row {
                        visible: (hub.d.results || []).length > 0
                        spacing: 8
                        topPadding: 16
                        Text { textFormat: Text.PlainText; text: hub.v.recentSets; width: 260; elide: Text.ElideRight; color: hub.root.muted; font.family: hub.root.sans; font.pixelSize: 26; anchors.verticalCenter: parent.verticalCenter }
                        Repeater {
                            model: (hub.d.results || []).length
                            ResultCell { required property int index; c: hub.root.ok(hub.d.results, index); accent: hub.v.accent; root: hub.root }
                        }
                    }
                    }
            }
            Rectangle {
                objectName: "primaryAction"
                visible: !!hub.d.primary
                x: 72; y: parent.height - 112 - 32
                width: 860; height: 112
                color: hub.root.bone
                Rectangle { width: 6; height: parent.height; color: hub.v.accent }
                Text { textFormat: Text.PlainText; x: 40; width: parent.width - 152; height: parent.height - 24; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; minimumPixelSize: 36; fontSizeMode: Text.Fit; anchors.verticalCenter: parent.verticalCenter; text: hub.d.primary || ""; color: "#0E0F11"; font.family: hub.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 60 }
                Glyph { anchors.right: parent.right; anchors.rightMargin: 40; anchors.verticalCenter: parent.verticalCenter; size: 56; g: hub.d.primaryG || ({}) }
                TapHandler { onTapped: hub.root.backend.clickPrimary() }
            }
        }
    }
}
