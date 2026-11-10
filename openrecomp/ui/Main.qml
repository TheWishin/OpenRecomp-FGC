import QtQuick
import QtQuick.Window

Window {
    id: win
    required property var backend
    property bool wantFull: true
    property bool allowClose: false
    width: 1920
    height: 1080
    minimumWidth: 960
    minimumHeight: 540
    visible: false
    title: "OpenRecomp-FGC"
    color: "#000000"
    onClosing: (close) => {
        if (!allowClose) {
            close.accepted = false
            backend.requestQuit()
        }
    }

    readonly property var v: backend.view
    readonly property color ground: Theme.ground
    readonly property color panel: Theme.card
    readonly property color bar: "#08090A"
    readonly property color line: Theme.border
    readonly property color textC: Theme.text
    readonly property color muted: Theme.muted
    readonly property color bone: Theme.selected
    readonly property string display: "Big Shoulders"
    readonly property string sans: "IBM Plex Sans"
    readonly property string mono: "IBM Plex Mono"
    readonly property bool reducedMotion: !!v.reducedMotion
    readonly property bool motionActive: visible && active && visibility !== Window.Minimized && !(v.gameRunning || false)
    readonly property bool communityLobby: v.online.layout === "lobby" && v.online.chapter === "lobby"
    readonly property bool chatDocked: v.screen === "hub" && !!v.online.chatDocked
    readonly property real chatDockWidth: chatDocked ? ((v.online.chat || {}).open !== false ? 568 : 88) : 0
    readonly property real onlineContentWidth: chatDocked ? 1920 - chatDockWidth - 16 : 1920
    readonly property bool compactOnline: chatDocked || v.online.layout === "lobby"
    readonly property bool activityAtOrigin: !!(v.activity || {}).current && v.screen === "hub" && !v.mainMenu.show
        && ((v.online.chapter === "lobby" && !!(v.online.arcade || {}).search)
            || ["matched", "starting", "playing", "result", "result_sent"].indexOf(v.online.phase) >= 0)
    readonly property real activityHeight: (v.activity || {}).game && !activityAtOrigin ? Math.max(Theme.target(44) + 8, activityReturn.captionHeight + 28) : 0
    property string lastToast: ""
    readonly property real hintHeight: Math.ceil(Math.max((compactOnline ? 36 : 48) * Theme.textScale, focusHint.implicitHeight + (compactOnline ? 8 : 12)))
    readonly property real headerHeight: Math.max(compactOnline ? 56 : 72, Theme.target(44) + (compactOnline ? 8 : 12), topActions.implicitHeight + (compactOnline ? 8 : 12))
    readonly property var progressCard: v.progressCard || ({show: false, lines: []})
    readonly property real progressCardHeight: progressCard.show ? 20 + progressCard.lines.length * Math.ceil(Theme.px(19) * 1.3 + 22) : 0
    readonly property real progressReserve: progressCard.show ? progressCardHeight + 8 : 0
    readonly property real promptHeight: Math.max(compactOnline ? 48 : 60, promptRow.implicitHeight + (compactOnline ? 8 : 12))

    onVChanged: { Theme.textScale = v.textScale || 1; Theme.highContrast = !!v.highContrast; Theme.calm = v.colours !== "vivid"; Theme.gameKind = v.gameTheme || ""; Theme.reducedMotion = reducedMotion; if (v.toast) lastToast = v.toast }
    onReducedMotionChanged: Theme.reducedMotion = reducedMotion
    Component.onCompleted: { Theme.textScale = v.textScale || 1; Theme.highContrast = !!v.highContrast; Theme.calm = v.colours !== "vivid"; Theme.gameKind = v.gameTheme || ""; Theme.reducedMotion = reducedMotion; lastToast = v.toast || "" }

    function ok(a, i) { return (a && a[i]) || ({}) }
    function focusStage() { stage.forceActiveFocus() }

    Item {
        id: stage
        width: 1920
        height: 1080
        anchors.centerIn: parent
        scale: Math.min(win.width / 1920, win.height / 1080)
        Binding { target: Theme; property: "viewportScale"; value: stage.scale }
        focus: true
        clip: true
        Keys.onPressed: (e) => { if (!win.v.nativeEdit) win.backend.keyPress(e.key, e.text, e.isAutoRepeat, e.modifiers, e.nativeScanCode); e.accepted = true }
        Keys.onReleased: (e) => { win.backend.keyUp(e.key, e.isAutoRepeat); e.accepted = true }

        Rectangle { anchors.fill: parent; color: win.ground }

        Column {
            anchors.fill: parent
            // ---------------------------------------------------------------- top bar
            Rectangle {
                objectName: "topBar"
                width: 1920; height: win.headerHeight; color: win.bar
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: win.line }
                Row {
                    objectName: "topIdentity"
                    anchors.left: parent.left; anchors.leftMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 28
                    Image { visible: !!win.v.wordmark; source: win.v.wordmark || ""; asynchronous: true; cache: true; width: 300; height: 40; fillMode: Image.PreserveAspectFit; sourceSize.height: 80; smooth: true; anchors.verticalCenter: parent.verticalCenter }
                    Text { objectName: "brandFallback"; visible: !win.v.wordmark; width: implicitWidth; textFormat: Text.PlainText; text: "OpenRecomp-FGC"; color: win.textC; font.family: win.display; font.weight: Font.Black; font.pixelSize: Theme.px(34); anchors.verticalCenter: parent.verticalCenter }
                    Row {
                        visible: win.v.screen === "hub" && !win.v.mainMenu.show; spacing: 12; anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: 10; height: 10; radius: 2; color: Theme.readableAccent(win.v.accent); anchors.verticalCenter: parent.verticalCenter }
                        Text { textFormat: Text.PlainText; width: Math.min(implicitWidth, 250); elide: Text.ElideRight; text: win.v.gameShort; color: win.muted; font.family: win.sans; font.pixelSize: Theme.px(22)}
                        Rectangle {
                            visible: !!win.v.badge
                            anchors.verticalCenter: parent.verticalCenter
                            width: hubBadge.implicitWidth + 20; height: hubBadge.implicitHeight + 8; radius: 4
                            color: Theme.raised
                            Text { textFormat: Text.PlainText; id: hubBadge; anchors.centerIn: parent; width: Math.min(implicitWidth, parent.width - 20); elide: Text.ElideRight; text: win.v.badge || ""; color: Theme.readableAccent(win.v.accent); font.family: win.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(16)}
                        }
                    }
                }
                Row {
                    id: topActions
                    objectName: "topActions"
                    anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 24
                    Text { textFormat: Text.PlainText; visible: win.v.screen === "hub" && !win.v.mainMenu.show; width: implicitWidth; text: win.v.topline; color: win.muted; font.family: win.mono; font.pixelSize: Theme.px(19); anchors.verticalCenter: parent.verticalCenter }
                    // the players' Discord (one server for every game: community.py); pads reach it in the drawer (social)
                    Rectangle {
                        objectName: "discordButton"
                        visible: !!win.v.discord && !win.v.mainMenu.show
                        anchors.verticalCenter: parent.verticalCenter
                        width: discordLabel.implicitWidth + 28; height: Math.max(Theme.target(44), discordLabel.implicitHeight + 16); radius: 4
                        color: discordTap.pressed ? win.line : Theme.card; border.width: 1; border.color: win.line
                        Text { id: discordLabel; objectName: "discordLabel"; textFormat: Text.PlainText; anchors.centerIn: parent; text: win.v.discord || ""; color: win.textC; font.family: win.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(20)}
                        TapHandler { id: discordTap; onTapped: win.backend.press("discord") }
                        Interaction { handler: discordTap; selected: false; onActivated: win.backend.press("discord") }
                    }
                    Row {
                        objectName: "quickAccessButton"
                        height: Theme.target(44)
                        spacing: 12; anchors.verticalCenter: parent.verticalCenter
                        Glyph { g: win.v.social; size: 32; anchors.verticalCenter: parent.verticalCenter }
                        Text { objectName: "quickAccessLabel"; textFormat: Text.PlainText; width: implicitWidth; text: win.v.quickAccess; color: win.textC; font.family: win.sans; font.pixelSize: Theme.px(20); anchors.verticalCenter: parent.verticalCenter }
                        TapHandler { id: uiTap1; onTapped: win.backend.press("social") }
                        Interaction { handler: uiTap1; selected: false; onActivated: win.backend.press("social") }
                    }
                }
                Text {
                    objectName: "mainMenuStatus"
                    visible: !!win.v.mainMenu.show
                    x: 480; width: topActions.x - x - 32; height: parent.height - 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: [win.v.mainMenu.status || "", win.v.mainMenu.player || "", win.v.mainMenu.activity || ""].filter(s => s).join("  ·  ")
                    textFormat: Text.PlainText; wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter
                    color: win.textC; font.family: win.sans; font.pixelSize: Theme.px(20)
                    maximumLineCount: 2
                }
            }

            // ---------------------------------------------------------------- body
            Item {
                id: body
                width: 1920; height: 1080 - win.headerHeight - win.hintHeight - win.promptHeight
                LivingBackground {
                    anchors.fill: parent
                    visible: win.v.screen === "hub"
                    scene: win.v.livingBackground || ({})
                    reducedMotion: win.reducedMotion
                    motionActive: visible && win.motionActive
                }
                PageLoader { y: win.activityHeight; width: parent.width; height: parent.height - y - win.progressReserve; active: win.v.screen === "start"; page: "Shelf.qml"; root: win }
                PageLoader { y: win.activityHeight; width: win.onlineContentWidth; height: parent.height - y - win.progressReserve; active: win.v.screen === "hub" && !win.v.mainMenu.show; page: "Hub.qml"; root: win }
                PageLoader { y: win.activityHeight; width: win.onlineContentWidth; height: parent.height - y - win.progressReserve; active: win.v.screen === "hub" && !!win.v.mainMenu.show; page: "MainMenu.qml"; root: win }
                OnlineStyle.SecondaryButton {
                    id: activityReturn
                    objectName: "onlineActivityReturn"
                    visible: win.activityHeight > 0
                    x: 16; y: 4; width: win.onlineContentWidth - 32; maxW: width; height: win.activityHeight - 8
                    b: ({label: [(win.v.activity || {}).name, (win.v.activity || {}).label, (win.v.activity || {}).status].filter(s => s).join(" · ")})
                    onActivated: win.backend.press("returnActivity")
                }
                // ---------------------------------------------------------------- progress card: installs / updates in the background
                Rectangle {
                    id: progressCardBox
                    objectName: "progressCard"
                    visible: win.progressCard.show
                    width: 820; height: win.progressCardHeight
                    x: 1920 - width - 48; y: parent.height - height - 6; z: 400
                    color: Theme.raised; border.width: 1; border.color: win.line; radius: 4
                    Column {
                        x: 16; y: 10; width: parent.width - 32; spacing: 0
                        Repeater {
                            model: win.progressCard.lines.length
                            Item {
                                id: cardLine
                                objectName: "progressLine"
                                required property int index
                                readonly property var p: win.ok(win.progressCard.lines, index)
                                width: parent.width; height: Math.ceil(Theme.px(19) * 1.3 + 22)
                                Text {
                                    id: cardText
                                    objectName: "progressLineText"
                                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; maximumLineCount: 1
                                    text: cardLine.p.text || ""
                                    color: cardLine.p.state === "failed" ? Theme.error : win.textC
                                    font.family: win.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(19)
                                }
                                Rectangle {
                                    y: cardText.implicitHeight + 6; width: parent.width; height: 4; radius: 2; color: win.line
                                    Rectangle {
                                        width: parent.width * (cardLine.p.fraction < 0 ? 0.35 : Math.max(0, Math.min(1, cardLine.p.fraction || 0)))
                                        height: parent.height; radius: 2
                                        color: cardLine.p.state === "failed" ? Theme.error : cardLine.p.state === "done" ? Theme.success : Theme.readableAccent(win.v.accent)
                                        opacity: cardLine.p.fraction < 0 ? 0.7 : 1
                                    }
                                }
                                TapHandler { id: cardTap; onTapped: win.backend.openProgress(cardLine.p.id) }
                                Interaction { handler: cardTap; selected: false; onActivated: win.backend.openProgress(cardLine.p.id) }
                            }
                        }
                    }
                }
                LobbyChat {
                    objectName: "lobbyChatPane"
                    root: win; chat: win.v.online.chat || ({})
                    visible: win.chatDocked
                    x: win.onlineContentWidth + 8; y: 8
                    width: win.chatDockWidth; height: parent.height - 16
                }
            }

            // ---------------------------------------------------------------- focused hint and last input device
            Rectangle {
                width: 1920; height: win.hintHeight; color: win.bar
                Rectangle { width: parent.width; height: 1; color: win.line }
                Text {
                    id: focusHint
                    objectName: "focusHint"
                    anchors.left: parent.left; anchors.leftMargin: 48; anchors.right: deviceLabel.left; anchors.rightMargin: 32; anchors.verticalCenter: parent.verticalCenter
                    height: parent.height - (win.compactOnline ? 8 : 12); text: win.communityLobby && win.v.toast ? win.v.toast : win.v.hint; textFormat: Text.PlainText; color: win.textC; font.family: win.sans; font.pixelSize: Theme.px(win.compactOnline ? 16 : 23); wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter
                }
                Text { textFormat: Text.PlainText;
                    id: deviceLabel
                    anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter
                    width: implicitWidth; horizontalAlignment: Text.AlignRight
                    text: win.v.device; color: win.muted; font.family: win.mono; font.pixelSize: Theme.px(win.compactOnline ? 16 : 22)
                }
            }

            // ---------------------------------------------------------------- prompt bar
            Rectangle {
                width: 1920; height: win.promptHeight; color: win.bar
                Row {
                    id: promptRow
                    anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 48; anchors.verticalCenter: parent.verticalCenter; spacing: 20
                    Repeater {
                        model: win.v.prompts.length
                        Row {
                            objectName: "promptItem"
                            required property int index
                            readonly property var p: win.ok(win.v.prompts, index)
                            width: (1824 - Math.max(0, win.v.prompts.length - 1) * 20) / Math.max(1, win.v.prompts.length)
                            height: Math.max(Theme.target(44), promptLabel.implicitHeight + 8)
                            spacing: 12
                            Glyph { id: promptGlyph; g: parent.p.g || ({}); size: 32; anchors.verticalCenter: parent.verticalCenter }
                            Text { id: promptLabel; textFormat: Text.PlainText; objectName: "promptLabel"; width: parent.width - promptGlyph.width - 12; text: parent.p.label || ""; color: win.textC; font.family: win.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(win.compactOnline ? 16 : 21); wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter; anchors.verticalCenter: parent.verticalCenter }
                            TapHandler { id: uiTap2; onTapped: win.backend.press(parent.p.action) }
                            Interaction { handler: uiTap2; selected: false; onActivated: win.backend.press(parent.p.action) }
                        }
                    }
                }
            }
        }

        PageLoader { anchors.fill: parent; z: 1000; active: !!win.v.overlay || (win.v.globalOffers || []).length > 0; page: "Overlays.qml"; root: win }
        PromotionBanner {
            root: win
            anchors.right: parent.right; anchors.rightMargin: 24
            anchors.top: parent.top; anchors.topMargin: win.headerHeight + 12
            z: 500
        }

        // ---------------------------------------------------------------- one toast, never a stack of banners
        Rectangle {
            objectName: "resultToast"
            opacity: win.v.toast !== "" && !win.communityLobby ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { enabled: !win.reducedMotion; NumberAnimation { duration: 180 } }
            anchors.right: parent.right; anchors.rightMargin: 48; y: 88
            width: Math.min(toastText.implicitWidth + 56, 860); height: toastText.implicitHeight + 36
            radius: 4; color: Theme.raised; border.width: 1; border.color: win.line
            Rectangle { width: 4; height: parent.height; color: Theme.readableAccent(win.v.accent) }
            Text { textFormat: Text.PlainText; id: toastText; x: 28; y: 18; width: Math.min(implicitWidth, 804); text: win.lastToast; color: win.textC; wrapMode: Text.Wrap; font.family: win.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(23)}
        }
    }
}
