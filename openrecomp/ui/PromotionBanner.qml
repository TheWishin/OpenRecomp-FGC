import QtQuick

// A passive cue leaves controller focus and every modal's input ownership intact.
Rectangle {
    id: banner
    objectName: "promotionBanner"
    required property var root
    readonly property var cue: root.v.promotion || ({})
    visible: !!cue.label
    width: Math.min(520, parent.width - 48); height: content.height + 32
    color: Theme.card; radius: 4; border.width: 2; border.color: Theme.rankGold
    property real entryOffset: 0
    transform: Translate { x: banner.entryOffset }
    Rectangle { width: 5; height: parent.height; color: Theme.rankGold }
    Column {
        id: content; x: 24; y: 16; width: parent.width - 48; spacing: 4
        OnlineStyle.SectionHeader { width: parent.width; text: banner.cue.label || ""; color: Theme.rankGold }
        OnlineStyle.Value { width: parent.width; text: banner.cue.rank || ""; visible: !!text }
    }
    onVisibleChanged: if (visible && !root.reducedMotion) reveal.restart()
    Component.onCompleted: if (visible && !root.reducedMotion) reveal.restart()
    ParallelAnimation {
        id: reveal
        NumberAnimation { target: banner; property: "entryOffset"; from: 24; to: 0; duration: 160; easing.type: Easing.OutCubic }
        NumberAnimation { target: banner; property: "opacity"; from: .5; to: 1; duration: 160; easing.type: Easing.OutCubic }
    }
    Connections {
        target: banner.root
        function onReducedMotionChanged() {
            if (banner.root.reducedMotion) { reveal.stop(); banner.entryOffset = 0; banner.opacity = 1 }
        }
    }
    Accessible.role: Accessible.StaticText
    Accessible.name: [cue.label || "", cue.rank || ""].join(". ")
}
