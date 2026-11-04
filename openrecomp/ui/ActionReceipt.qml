import QtQuick

OnlineHelp {
    property var receipt: ({})
    visible: !!receipt.text
    text: (receipt.kind === "error" || receipt.kind === "declined" || receipt.kind === "expired" ? "! " : receipt.kind === "success" ? "+ " : "… ") + (receipt.text || "")
    readonly property color statusColour: receipt.kind === "error" || receipt.kind === "declined" || receipt.kind === "expired" ? Theme.error : receipt.kind === "success" ? Theme.success : Theme.value
    color: statusColour
    font.weight: Font.DemiBold

}
