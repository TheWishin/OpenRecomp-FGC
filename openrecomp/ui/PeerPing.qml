import QtQuick

Row {
    id: ping
    objectName: "peerPing"
    property var connection: ({})
    property color ink: "#E8E4DD"
    property color dim: "#696B70"
    property bool compact: false
    spacing: compact ? 4 : 10
    height: compact ? 18 : 24
    Row {
        visible: (ping.connection.bars || 0) > 0
        spacing: 2; height: ping.compact ? 14 : 20; anchors.verticalCenter: parent.verticalCenter
        Repeater {
            model: 4
            Rectangle {
                required property int index
                objectName: "peerPingBar"
                width: ping.compact ? 3 : 4; height: ping.compact ? 4 + index * 3 : 6 + index * 4
                anchors.bottom: parent.bottom
                color: index < (ping.connection.bars || 0) ? ping.ink : ping.dim
            }
        }
    }
    Text {
        objectName: "peerPingText"
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText; text: ping.connection.text || ""
        color: ping.ink; font.pixelSize: ping.compact ? Theme.onlinePx(14) : Theme.px(20)
    }
    Text {
        objectName: "peerPingPath"
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText; text: ping.connection.path || ""
        color: ping.ink; font.pixelSize: ping.compact ? Theme.onlinePx(14) : Theme.px(18)
    }
}
