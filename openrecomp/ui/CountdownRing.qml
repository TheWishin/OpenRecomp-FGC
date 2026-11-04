import QtQuick

// Only real deadline updates animate; no timer or perpetual scene repaint.
Canvas {
    id: ring
    objectName: "countdownArc"
    property var seconds: null
    property bool reducedMotion: Theme.reducedMotion
    property bool paused: false
    property real initialSeconds: 0
    readonly property bool hasDeadline: typeof seconds === "number" && isFinite(seconds) && seconds >= 0
    readonly property real progress: hasDeadline && initialSeconds > 0 ? Math.max(0, Math.min(1, seconds / initialSeconds)) : 0
    property real displayProgress: progress
    property color ink: Theme.gameAccent
    property real lineWidth: 4
    onSecondsChanged: if (hasDeadline && seconds > initialSeconds) initialSeconds = seconds
    onDisplayProgressChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onReducedMotionChanged: if (reducedMotion) countdownTween.complete()
    onPausedChanged: if (paused) countdownTween.complete()
    Behavior on displayProgress {
        enabled: !ring.reducedMotion && !ring.paused && ring.visible
        NumberAnimation { id: countdownTween; duration: 1000; easing.type: Easing.Linear }
    }
    onPaint: {
        var context = getContext("2d")
        context.reset()
        if (!hasDeadline || displayProgress <= 0) return
        context.lineWidth = lineWidth
        context.strokeStyle = ink
        context.lineCap = "round"
        context.beginPath()
        context.arc(width / 2, height / 2, Math.max(1, Math.min(width, height) / 2 - lineWidth), -Math.PI / 2,
                    -Math.PI / 2 + Math.PI * 2 * displayProgress, false)
        context.stroke()
    }
}
