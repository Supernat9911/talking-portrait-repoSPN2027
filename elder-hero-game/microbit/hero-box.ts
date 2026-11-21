// กล่องไฟฉุกเฉินฮีโร่จิ๋ว · micro:bit V2 · MakeCode JavaScript
// ปุ่ม: P0 แดง, P1 เหลือง, P2 เขียว, P8 SOS · แผ่นรองนั่ง: P12 · LED: P13 แดง, P14 เหลือง, P15 เขียว
// ทุกปุ่มต่อระหว่างขากับ GND (กด = 0)

const IN_PINS = [DigitalPin.P0, DigitalPin.P1, DigitalPin.P2, DigitalPin.P8, DigitalPin.P12]
const IN_MSG = ["BTN:R", "BTN:Y", "BTN:G", "SOS", "SEAT"]
const LED_PINS = [DigitalPin.P13, DigitalPin.P14, DigitalPin.P15]
let last = [1, 1, 1, 1, 1]
let sosOn = false

function lampsOff() {
    for (let i = 0; i < 3; i++) pins.digitalWritePin(LED_PINS[i], 0)
}
function lamp(i: number) {
    lampsOff()
    pins.digitalWritePin(LED_PINS[i], 1)
}

function startSos() {
    if (sosOn) return
    sosOn = true
    control.inBackground(function () {
        while (sosOn) {
            lamp(0)
            basic.showLeds(`
                . . # . .
                . . # . .
                . . # . .
                . . . . .
                . . # . .
                `, 0)
            music.playTone(988, 250)
            lampsOff()
            basic.clearScreen()
            music.playTone(659, 250)
        }
        basic.showIcon(IconNames.Heart)
    })
}

serial.redirectToUSB()
serial.setBaudRate(BaudRate.BaudRate115200)
for (let i = 0; i < IN_PINS.length; i++) pins.setPull(IN_PINS[i], PinPullMode.PullUp)
lampsOff()
basic.showIcon(IconNames.Heart)

// อ่านปุ่มและแผ่นรองนั่ง ส่งให้แอปเมื่อมีการเปลี่ยนแปลง
basic.forever(function () {
    for (let i = 0; i < IN_PINS.length; i++) {
        const v = pins.digitalReadPin(IN_PINS[i])
        if (v != last[i]) {
            last[i] = v
            if (i == 4) {
                serial.writeLine(v == 0 ? "SEAT:1" : "SEAT:0")
            } else if (v == 0) {
                serial.writeLine(IN_MSG[i])
                if (i == 3) startSos()
                else music.playTone(523, 60)
            }
        }
    }
    basic.pause(20)
})

// รับคำสั่งจากแอป
serial.onDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    const cmd = serial.readUntil(serial.delimiters(Delimiters.NewLine))
    if (cmd == "OK") {
        basic.showIcon(IconNames.Yes)
        music.playTone(1046, 120)
        music.playTone(1568, 160)
    } else if (cmd == "NO") {
        basic.showIcon(IconNames.No)
        music.playTone(196, 300)
    } else if (cmd == "LED:R") lamp(0)
    else if (cmd == "LED:Y") lamp(1)
    else if (cmd == "LED:G") lamp(2)
    else if (cmd == "LED:OFF") {
        lampsOff()
        if (!sosOn) basic.showIcon(IconNames.Heart)
    } else if (cmd == "GO") {
        basic.showArrow(ArrowNames.North)
        music.playTone(784, 200)
    } else if (cmd.substr(0, 4) == "NUM:") {
        basic.showNumber(parseInt(cmd.substr(4)))
    } else if (cmd == "CLEAR") {
        sosOn = false
        lampsOff()
    }
})
