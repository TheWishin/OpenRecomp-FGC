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
    Component.onCompleted: loadPage()
}
