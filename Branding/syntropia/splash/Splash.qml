/*
    Syntropia splash — pure triangle mark.

    SPDX-License-Identifier: GPL-2.0-or-later

    Stage sequence (KSplash drives `stage` 1..5):
      1-4  triangle mark fades in / remains visible
      5    triangle fades out (session ready)
*/

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: "black"

    property int stage

    onStageChanged: {
        if (stage >= 1 && stage <= 4) {
            triangleFade.from = triangle.opacity
            triangleFade.to = 1
            triangleFade.running = true
        } else if (stage >= 5) {
            triangleFade.from = triangle.opacity
            triangleFade.to = 0
            triangleFade.running = true
        }
    }

    Item {
        id: content
        anchors.fill: parent

        Image {
            id: triangle
            anchors.centerIn: parent
            asynchronous: true
            source: "images/logo.png"
            readonly property real size: Kirigami.Units.gridUnit * 12
            sourceSize.width: size
            sourceSize.height: size
            opacity: 0
            OpacityAnimator {
                id: triangleFade
                target: triangle
                from: 0
                to: 1
                duration: Kirigami.Units.longDuration
                running: false
            }
        }
    }
}
