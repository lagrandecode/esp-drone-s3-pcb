import 'dart:typed_data';

import 'package:esp_drone_controller/drone/crtp.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('setpoint packet matches CommanderCrtpLegacyValues layout', () {
    final p = Crtp.setpoint(roll: 1.5, pitch: -2, yawRate: 30, thrust: 12345);
    expect(p.length, 16); // header + 14 payload bytes + checksum
    expect(p[0], 0x30);
    final d = ByteData.sublistView(p, 1, 15);
    expect(d.getFloat32(0, Endian.little), 1.5);
    expect(d.getFloat32(4, Endian.little), -2);
    expect(d.getFloat32(8, Endian.little), 30);
    expect(d.getUint16(12, Endian.little), 12345);
    expect(p.last, Crtp.checksum(p.sublist(0, 15)));
  });

  test('thrust is clamped to the firmware maximum', () {
    final p = Crtp.setpoint(roll: 0, pitch: 0, yawRate: 0, thrust: 99999);
    expect(ByteData.sublistView(p, 1, 15).getUint16(12, Endian.little), Crtp.maxThrust);
  });

  test('arm packet sets system.forceArm by name', () {
    final p = Crtp.arm(true);
    expect(p[0], 0x23);
    expect(p.sublist(1, p.length - 1), [0, ...'system'.codeUnits, 0, ...'forceArm'.codeUnits, 0, 0x00, 1]);
  });

  test('parse rejects a bad checksum and accepts a good one', () {
    final good = Crtp.echo(7);
    expect(Crtp.parse(good), [0xF0, 7]);
    final bad = Uint8List.fromList(good)..[good.length - 1] ^= 0xFF;
    expect(Crtp.parse(bad), isNull);
  });
}
