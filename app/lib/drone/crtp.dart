import 'dart:convert';
import 'dart:typed_data';

/// CRTP packets for the ESP-Drone firmware's Wi-Fi link
/// (espressif/esp-drone components/drivers/general/wifi/wifi_esp32.c).
///
/// Each UDP datagram is `[header, payload..., checksum]` where the checksum
/// is the 8-bit sum of every preceding byte.
class Crtp {
  static const int portParam = 0x02;
  static const int portSetpoint = 0x03;
  static const int portLink = 0x0F;

  static const int paramChannelMisc = 3;
  static const int paramMiscSetByName = 0;
  static const int paramTypeInt8 = 0x00;

  static const int maxThrust = 60000;

  static int header(int port, int channel) => ((port & 0x0F) << 4) | (channel & 0x03);

  static Uint8List frame(int header, List<int> payload) {
    final out = Uint8List(payload.length + 2);
    out[0] = header;
    out.setRange(1, payload.length + 1, payload);
    out[out.length - 1] = checksum(out.sublist(0, out.length - 1));
    return out;
  }

  static int checksum(List<int> bytes) => bytes.fold<int>(0, (a, b) => (a + b) & 0xFF);

  /// Legacy roll/pitch/yaw-rate/thrust setpoint (crtp_commander_rpyt.c).
  /// Roll and pitch are angles in degrees, yaw is a rate in degrees/second.
  static Uint8List setpoint({
    required double roll,
    required double pitch,
    required double yawRate,
    required int thrust,
  }) {
    final data = ByteData(14)
      ..setFloat32(0, roll, Endian.little)
      ..setFloat32(4, pitch, Endian.little)
      ..setFloat32(8, yawRate, Endian.little)
      ..setUint16(12, thrust.clamp(0, maxThrust), Endian.little);
    return frame(header(portSetpoint, 0), data.buffer.asUint8List());
  }

  /// Sets an int8 parameter by "group.name" without downloading the TOC.
  static Uint8List setInt8Param(String group, String name, int value) {
    final payload = <int>[
      paramMiscSetByName,
      ...ascii.encode(group),
      0,
      ...ascii.encode(name),
      0,
      paramTypeInt8,
      value & 0xFF,
    ];
    return frame(header(portParam, paramChannelMisc), payload);
  }

  /// The firmware arms the motors only while `system.forceArm` is non-zero.
  static Uint8List arm(bool armed) => setInt8Param('system', 'forceArm', armed ? 1 : 0);

  static Uint8List echo(int sequence) => frame(header(portLink, 0), [sequence & 0xFF]);

  /// Returns the CRTP packet (header + payload) if the datagram's checksum is valid.
  static Uint8List? parse(Uint8List datagram) {
    if (datagram.length < 2) return null;
    final body = datagram.sublist(0, datagram.length - 1);
    return checksum(body) == datagram.last ? body : null;
  }

  static int portOf(int header) => (header >> 4) & 0x0F;
  static int channelOf(int header) => header & 0x03;
}
