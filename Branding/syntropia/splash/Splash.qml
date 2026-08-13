/*
    Syntropia splash — triangle mark first, then the Plasma logo, then boot.

    SPDX-License-Identifier: GPL-2.0-or-later

    Stage sequence (KSplash drives `stage` 1..5):
      1-3  triangle mark fades in
      4    triangle fades out, Plasma logo + spinner fade in
      5    everything fades out (session ready)
*/

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: "black"

    property int stage

    onStageChanged: {
        if (stage >= 1 && stage <= 3) {
            triangleFade.running = true
        } else if (stage == 4) {
            triangleFade.from = 1
            triangleFade.to = 0
            triangleFade.running = true
            plasmaFade.running = true
        } else if (stage == 5) {
            plasmaFade.from = 1
            plasmaFade.to = 0
            plasmaFade.running = true
        }
    }

    Item {
        id: content
        anchors.fill: parent

        // -- first: the Syntropia triangle mark --------------------------
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

        // -- second: the Plasma logo + spinner ---------------------------
        Image {
            id: plasma
            anchors.centerIn: parent
            asynchronous: true
            source: "images/plasma.svgz"
            readonly property real size: Kirigami.Units.gridUnit * 8
            sourceSize.width: size
            sourceSize.height: size
            opacity: 0
            OpacityAnimator {
                id: plasmaFade
                target: plasma
                from: 0
                to: 1
                duration: Kirigami.Units.longDuration
                running: false
            }
        }

        Image {
            id: busyIndicator
            y: parent.height - (parent.height - plasma.y) / 2 - height / 2
            anchors.horizontalCenter: parent.horizontalCenter
            asynchronous: true
            source: "images/busywidget.svgz"
            sourceSize.height: Kirigami.Units.gridUnit * 2
            sourceSize.width: Kirigami.Units.gridUnit * 2
            opacity: 0
            OpacityAnimator {
                id: busyFade
                target: busyIndicator
                from: 0
                to: 1
                duration: Kirigami.Units.longDuration
                running: false
            }
            RotationAnimator on rotation {
                id: rotationAnimator
                from: 0
                to: 360
                duration: 2000
                loops: Animation.Infinite
                running: false
            }
        }
    }

    // Keep the spinner's spin + fade tied to the plasma stage.
    Connections {
        target: root
        function onStageChanged() {
            if (root.stage == 4) {
                busyFade.running = true
                rotationAnimator.running = Kirigami.Units.longDuration > 1
            } else if (root.stage == 5) {
                busyFade.from = 1
                busyFade.to = 0
                busyFade.running = true
            }
        }
    }
}
