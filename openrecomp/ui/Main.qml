import QtQuick
import QtQuick.Window

Window {
    id: win
    required property var backend
    property bool wantFull: true
    width: 1920
    height: 1080
    minimumWidth: 960
    minimumHeight: 540
    visible: false
    title: "OpenRecomp-FGC"
    color: "#000000"

    readonly property var v: backend.view
    readonly property color ground: "#0E0F11"
    readonly property color panel: "#141619"
    readonly property color bar: "#08090A"
    readonly property color line: "#2A2D32"
    readonly property color textC: "#ECE9E1"
    readonly property color muted: "#A3A5AB"
    readonly property color bone: "#F2EFE6"
    readonly property string display: "Big Shoulders"
    readonly property string sans: "IBM Plex Sans"
    readonly property string mono: "IBM Plex Mono"

    function ok(a, i) { return (a && a[i]) || ({}) }

    Item {
        id: stage
        width: 1920
        height: 1080
        anchors.centerIn: parent
        scale: Math.min(win.width / 1920, win.height / 1080)
        focus: true
        clip: true
        Keys.onPressed: (e) => { win.backend.keyDown(e.key, e.text, e.isAutoRepeat); e.accepted = true }
        Keys.onReleased: (e) => { win.backend.keyUp(e.key, e.isAutoRepeat); e.accepted = true }

        Rectangle { anchors.fill: parent; color: win.ground }

        Column {
            anchors.fill: parent
            // ---------------------------------------------------------------- top bar
            Rectangle {
                width: 1920; height: 72; color: win.bar
                Row {
                    anchors.left: parent.left; anchors.leftMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 28
                    Image { source: "assets/logo-wordmark.svg"; height: 44; fillMode: Image.PreserveAspectFit; sourceSize.height: 88; smooth: true; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        visible: win.v.screen === "hub"; spacing: 12; anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 14; height: 14; color: win.v.accent; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: win.v.gameShort; color: win.muted; font.family: win.sans; font.pixelSize: 26 }
                        Rectangle {
                            visible: !!win.v.badge
                            anchors.verticalCenter: parent.verticalCenter
                            width: hubBadge.implicitWidth + 16; height: 30
                            color: "transparent"; border.width: 2; border.color: win.v.accent
                            Text { id: hubBadge; anchors.centerIn: parent; text: win.v.badge || ""; color: win.v.accent; font.family: win.mono; font.weight: Font.DemiBold; font.pixelSize: 18 }
                        }
                    }
                }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 36
                    Text { visible: win.v.screen === "hub"; text: win.v.topline; color: win.muted; font.family: win.mono; font.pixelSize: 24; anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        spacing: 12; anchors.verticalCenter: parent.verticalCenter
                        Glyph { g: win.v.social; size: 40 }
                        Text { text: "Quick access"; color: win.textC; font.family: win.sans; font.pixelSize: 24; anchors.verticalCenter: parent.verticalCenter }
                        TapHandler { onTapped: win.backend.press("social") }
                    }
                }
            }

            // ---------------------------------------------------------------- body
            Item {
                id: body
                width: 1920; height: 1080 - 72 - 60 - 76
                Shelf { anchors.fill: parent; visible: win.v.screen === "start"; root: win }
                Hub { anchors.fill: parent; visible: win.v.screen === "hub"; root: win }
            }

            // ---------------------------------------------------------------- hint line and input trail
            Rectangle {
                width: 1920; height: 60; color: win.bar
                Rectangle { width: parent.width; height: 1; color: win.line }
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 48; anchors.right: trailRow.left; anchors.rightMargin: 32; anchors.verticalCenter: parent.verticalCenter
                    text: win.v.hint; color: win.textC; font.family: win.sans; font.pixelSize: 28; elide: Text.ElideRight
                }
                Row {
                    id: trailRow
                    anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                    Repeater {
                        model: 16
                        Rectangle {
                            required property int index
                            readonly property var c: win.ok(win.v.trail, index)
                            width: 38; height: 38
                            color: c.newest ? (win.v.accent === "#ECE9E1" ? win.bone : win.v.accent) : (c.text ? "#24272C" : win.panel)
                            Text { anchors.centerIn: parent; text: parent.c.text || ""; color: parent.c.newest ? "#0E0F11" : win.textC; font.family: win.mono; font.weight: Font.DemiBold; font.pixelSize: 18 }
                        }
                    }
                }
            }

            // ---------------------------------------------------------------- prompt bar
            Rectangle {
                width: 1920; height: 76; color: win.bar
                Row {
                    anchors.left: parent.left; anchors.leftMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 36
                    Repeater {
                        model: win.v.prompts.length
                        Row {
                            required property int index
                            readonly property var p: win.ok(win.v.prompts, index)
                            spacing: 12
                            Glyph { g: parent.p.g || ({}); anchors.verticalCenter: parent.verticalCenter }
                            Text { text: parent.p.label || ""; color: win.textC; font.family: win.sans; font.weight: Font.Medium; font.pixelSize: 26; anchors.verticalCenter: parent.verticalCenter }
                            TapHandler { onTapped: win.backend.press(parent.p.action) }
                        }
                    }
                }
                Text { anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; text: win.v.device; color: win.muted; font.family: win.mono; font.pixelSize: 22 }
            }
        }

        Overlays { anchors.fill: parent; root: win }

        // ---------------------------------------------------------------- one toast, never a stack of banners
        Rectangle {
            visible: win.v.toast !== ""
            anchors.right: parent.right; anchors.rightMargin: 48; y: 88
            width: Math.min(toastText.implicitWidth + 56, 860); height: toastText.implicitHeight + 36
            color: win.textC
            Text { id: toastText; x: 28; y: 18; width: Math.min(implicitWidth, 804); text: win.v.toast; color: "#0E0F11"; wrapMode: Text.Wrap; font.family: win.sans; font.weight: Font.Medium; font.pixelSize: 26 }
        }
    }
}
