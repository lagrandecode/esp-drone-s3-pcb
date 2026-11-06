import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:esp_drone_controller/drone/crtp.dart';
import 'package:esp_drone_controller/drone/drone_link.dart';
import 'package:flutter_test/flutter_test.dart';

/// Minimal stand-in for the firmware's UDP link: echoes link packets, answers
/// parameter set-by-name, and records the latest setpoint.
class FakeDrone {
  late RawDatagramSocket socket;
  int forceArm = 0;
  int lastThrust = -1;
  int setpoints = 0;

  Future<int> start() async {
    socket = await RawDatagramSocket.bind(InternetAddress.loopbackIPv4, 0);
    socket.listen((e) {
      if (e != RawSocketEvent.read) return;
      final d = socket.receive();
      if (d == null) return;
      final pkt = Crtp.parse(d.data);
      if (pkt == null) return;
      final port = Crtp.portOf(pkt[0]);
      if (port == Crtp.portLink) {
        socket.send(Crtp.frame(pkt[0], pkt.sublist(1)), d.address, d.port);
      } else if (port == Crtp.portSetpoint) {
        setpoints++;
        lastThrust = ByteData.sublistView(pkt, 1).getUint16(12, Endian.little);
      } else if (port == Crtp.portParam) {
        forceArm = pkt.last;
        final reply = [...pkt.sublist(1, pkt.length - 2), 0]; // type byte replaced by error 0
        socket.send(Crtp.frame(pkt[0], reply), d.address, d.port);
      }
    });
    return socket.port;
  }
}

Future<void> waitFor(bool Function() cond, {Duration timeout = const Duration(seconds: 3)}) async {
  final end = DateTime.now().add(timeout);
  while (!cond()) {
    if (DateTime.now().isAfter(end)) throw TimeoutException('condition not met');
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

void main() {
  test('connects, arms with acknowledgement, streams thrust, and stops', () async {
    final drone = FakeDrone();
    final port = await drone.start();
    final link = DroneLink(host: '127.0.0.1', port: port);

    await link.connect();
    await waitFor(() => link.state == LinkState.connected && link.latencyMs != null);
    expect(drone.lastThrust, 0);

    link.updateSticks(const Sticks(throttle: 0.5));
    expect(link.setArmed(true), isFalse, reason: 'arming with throttle up must be refused');

    link.updateSticks(const Sticks());
    expect(link.setArmed(true), isTrue);
    await waitFor(() => link.armConfirmed);
    expect(drone.forceArm, 1);

    link.updateSticks(const Sticks(throttle: 0.5));
    await waitFor(() => drone.lastThrust == (0.5 * 0.8 * Crtp.maxThrust).round());

    link.emergencyStop();
    await waitFor(() => drone.forceArm == 0 && drone.lastThrust == 0);
    expect(link.armed, isFalse);

    await link.disconnect();
    drone.socket.close();
  });
}
