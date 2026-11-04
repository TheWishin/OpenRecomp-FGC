import QtQuick

// Keep only the visible page alive. Initial properties are set before its bindings run.
Loader {
    id: loader
    objectName: "pageLoader"
    required property var root
    required property string page
    property string pageName: ""
    asynchronous: true
    visible: active
    function loadPage() {
        if (active && page) setSource(page, {root: root, objectName: pageName})
    }
    onActiveChanged: loadPage()
    onLoaded: if (!root.reducedMotion) reveal.restart()
    Component.onCompleted: loadPage()
    NumberAnimation { id: reveal; target: loader.item; property: "opacity"; from: 0.6; to: 1; duration: 130; easing.type: Easing.OutCubic }
    Connections {
        target: loader.root
        function onReducedMotionChanged() {
            if (loader.root.reducedMotion) {
                reveal.stop()
                if (loader.item) loader.item.opacity = 1
            }
        }
    }
    Rectangle {
        objectName: "pageLoadState"
        visible: loader.active && (loader.status === Loader.Loading || loader.status === Loader.Error)
        x: 24; y: 18; width: parent.width - 48; height: 150
        color: Theme.card; border.width: 1; border.color: loader.root.line
        Rectangle { x: 0; y: 24; width: 5; height: parent.height - 48; color: Theme.readableAccent(loader.root.v.accent) }
        Text {
            objectName: "pageLoadMessage"
            x: 36; y: 28; width: parent.width - 72; height: parent.height - 56
            textFormat: Text.PlainText
            text: loader.status === Loader.Error ? loader.root.v.loadError : loader.root.v.loading
            color: loader.root.muted; font.family: loader.root.sans; font.pixelSize: Theme.px(24)
            wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter
        }
    }
}
