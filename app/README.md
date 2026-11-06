# ESP-Drone Controller (Flutter)

Phone controller for the ESP-Drone S3 board, talking to the stock
[esp-drone](https://github.com/espressif/esp-drone) firmware over its Wi-Fi access point.

## Use

1. Power the drone (switch ON) and join its Wi-Fi network, `ESP-DRONE_<mac>`, with password `12345678`.
2. Open the app (it runs in landscape) and tap **Connect**. The status dot turns green and shows the round-trip time.
3. Throttle all the way down, then flip **Arm**. The label changes to **ARMED** once the drone confirms.
4. Fly:
   - **Left stick:** throttle (stays where you leave it) and yaw.
   - **Right stick:** pitch and roll (springs back to centre).
5. **STOP** cuts thrust and disarms immediately. The app also disarms if it goes to the background. If the phone disconnects, the firmware levels the drone after 0.5 s and stops the motors after 2 s.

Before the first flight, check the stick directions with the **props off**:

- Arm, raise the throttle a little, and push the right stick **forward**. The **rear** motors (M2, M3) should speed up.
- Push the right stick **right**. The **left** motors (M3, M4) should speed up.

If either direction is backwards, turn on **Invert pitch** or **Invert roll** in the settings (the tune icon).

## Protocol

Every UDP packet goes to `192.168.43.42:2390` and has the form `[CRTP header, payload…, checksum]`, where the checksum is the 8-bit sum of all preceding bytes.

| Purpose | Header | Payload |
| --- | --- | --- |
| Setpoint, sent at 50 Hz | `0x30` | roll float32 (°), pitch float32 (°), yaw rate float32 (°/s), thrust uint16 (0–60000) |
| Arm / disarm | `0x23` | `00 "system" 00 "forceArm" 00 00 <0 or 1>` (set parameter by name) |
| Link ping | `0xF0` | sequence byte, which the firmware echoes back |

The firmware ignores thrust until it has received one setpoint with thrust 0. The app sends that automatically on connect.

## Develop

```sh
flutter test          # packet encoding + an end-to-end test against a fake drone
flutter run           # on a phone connected to the drone's Wi-Fi
```
