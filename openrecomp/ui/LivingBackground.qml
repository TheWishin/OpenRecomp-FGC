import QtQuick

// All images come from the adapter at runtime. The fallback is original geometry.
Item {
    id: backdrop
    objectName: "livingBackground"
    property var scene: ({})
    property bool reducedMotion: false
    property bool motionActive: true
    readonly property bool animated: visible && motionActive && !reducedMotion && !Theme.highContrast
    readonly property bool softwareRenderer: GraphicsInfo.api === GraphicsInfo.Software
    readonly property bool blue: scene.theme === "t4"
    readonly property color atmosphere: Theme.quiet ? "#2A2D33" : blue ? "#244C69" : "#60152B"
    property real drift: 0
    property real direction: 1
    clip: true

    // Software compositing costs more: retain the same slow drift at 2 Hz.
    // Input transitions remain independent of this idle update budget.
    Timer {
        objectName: "backgroundDriftTimer"
        interval: backdrop.softwareRenderer ? 500 : 100; repeat: true; running: backdrop.animated
        onTriggered: {
            backdrop.drift += backdrop.direction * (backdrop.softwareRenderer ? 0.015 : 0.003)
            if (backdrop.drift >= 1 || backdrop.drift <= 0) backdrop.direction *= -1
        }
    }
    onReducedMotionChanged: { if (reducedMotion) drift = 0 }

    Rectangle { anchors.fill: parent; color: Theme.ground }
    Rectangle {
        objectName: "backgroundAtmosphere"
        x: parent.width * 0.36 + backdrop.drift * 16; y: -parent.height * .15
        width: parent.width * .82; height: parent.height * 1.3
        rotation: -12
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: .55; color: backdrop.atmosphere }
            GradientStop { position: 1; color: "transparent" }
        }
        opacity: Theme.highContrast ? 0 : Theme.atmosphereStrength
    }
    Repeater {
        model: 7
        Rectangle {
            required property int index
            x: backdrop.width * (.48 + index * .075) + backdrop.drift * (index % 2 ? 14 : -10)
            y: backdrop.height * (.04 + (index * .137) % .85)
            width: index % 3 ? 1 : 2; height: backdrop.height * (.12 + index * .017)
            rotation: 22
            color: Theme.quiet ? Theme.border : backdrop.blue ? "#71CBE5" : "#D11F3F"
            opacity: Theme.highContrast ? 0 : Theme.quiet ? .05 : .09 + index * .012
        }
    }
    Image {
        id: art
        objectName: "backgroundRuntimeArt"
        x: parent.width * .37 + backdrop.drift * 12
        y: -parent.height * .035 - backdrop.drift * 6
        width: parent.width * .69; height: parent.height * 1.10
        source: backdrop.scene.source || ""
        asynchronous: true; cache: true
        sourceSize.width: 1100; sourceSize.height: 900
        fillMode: Image.PreserveAspectCrop; verticalAlignment: Image.AlignTop
        opacity: status === Image.Ready && !Theme.highContrast ? Theme.artStrength : 0
        Behavior on opacity { NumberAnimation { duration: backdrop.reducedMotion ? 0 : 160; easing.type: Easing.OutCubic } }
    }
    // Even a white source is capped below 0.10 relative luminance behind text.
    Rectangle {
        objectName: "backgroundReadabilityVeil"
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .97) }
            GradientStop { position: .42; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .88) }
            GradientStop { position: 1; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .76) }
        }
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .05) }
            GradientStop { position: .78; color: Qt.rgba(Theme.ground.r, Theme.ground.g, Theme.ground.b, .12) }
            GradientStop { position: 1; color: Theme.ground }
        }
    }
}
