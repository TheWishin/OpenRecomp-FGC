import QtQuick

// Runtime adapter pictures stay on the player's PC. Missing pictures get a geometric silhouette.
Rectangle {
    id: portrait
    property url source: ""
    property string name: ""
    property bool mirrored: false
    color: Theme.raised; clip: true
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: Theme.gameAccent }
    Item {
        visible: picture.status !== Image.Ready
        anchors.fill: parent
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * .18; width: Math.min(parent.width * .33, parent.height * .23); height: width; radius: width / 2; color: Theme.border }
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * .45; width: parent.width * .78; height: parent.height * .65; radius: width * .30; color: Theme.border; rotation: portrait.mirrored ? -9 : 9 }
    }
    Image { id: picture; anchors.fill: parent; source: portrait.source; fillMode: Image.PreserveAspectFit; mirror: portrait.mirrored; asynchronous: true; visible: status === Image.Ready }
    Rectangle { visible: !!portrait.name; anchors.bottom: parent.bottom; width: parent.width; height: caption.height + 12; color: Theme.ground; opacity: .94 }
    Text { id: caption; visible: !!portrait.name; x: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 6; width: parent.width - 16; text: portrait.name; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.text; font.family: "IBM Plex Sans"; font.pixelSize: Theme.onlinePx(14); Accessible.name: text }
}
