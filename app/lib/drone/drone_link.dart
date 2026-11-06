import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'crtp.dart';

/// Pilot input, normalised: roll/pitch/yaw in -1..1, throttle in 0..1.
class Sticks {
  const Sticks({this.roll = 0, this.pitch = 0, this.yaw = 0, this.throttle = 0});
  final double roll;
  final double pitch;
  final double yaw;
  final double throttle;
}

class FlightLimits {
  const FlightLimits({
    this.maxAngleDeg = 15,
    this.maxYawRateDeg = 120,
    this.maxThrustFraction = 0.8,
    this.invertPitch = false,
    this.invertRoll = false,
    this.rollTrimDeg = 0,
    this.pitchTrimDeg = 0,
  });

  final double maxAngleDeg;
  final double maxYawRateDeg;
  final double maxThrustFraction;
  final bool invertPitch;
  final bool invertRoll;
  final double rollTrimDeg;
  final double pitchTrimDeg;

  FlightLimits copyWith({
    double? maxAngleDeg,
    double? maxYawRateDeg,
    double? maxThrustFraction,
    bool? invertPitch,
    bool? invertRoll,
    double? rollTrimDeg,
    double? pitchTrimDeg,
  }) =>
      FlightLimits(
        maxAngleDeg: maxAngleDeg ?? this.maxAngleDeg,
        maxYawRateDeg: maxYawRateDeg ?? this.maxYawRateDeg,
        maxThrustFraction: maxThrustFraction ?? this.maxThrustFraction,
        invertPitch: invertPitch ?? this.invertPitch,
        invertRoll: invertRoll ?? this.invertRoll,
        rollTrimDeg: rollTrimDeg ?? this.rollTrimDeg,
        pitchTrimDeg: pitchTrimDeg ?? this.pitchTrimDeg,
      );
}

enum LinkState { disconnected, connecting, connected, lost }

/// Streams setpoints to the drone at 50 Hz and tracks link health with echo pings.
///
/// The firmware stabilises after 500 ms without setpoints and cuts the motors
/// after 2 s, so simply stopping this loop is a safe failure mode.
class DroneLink extends ChangeNotifier {
  DroneLink({this.host = '192.168.43.42', this.port = 2390});

  final String host;
  final int port;

  static const _setpointPeriod = Duration(milliseconds: 20);
  static const _pingPeriod = Duration(milliseconds: 250);
  static const _linkTimeout = Duration(milliseconds: 1200);

  RawDatagramSocket? _socket;
  Timer? _setpointTimer;
  Timer? _pingTimer;
  InternetAddress? _target;

  Sticks sticks = const Sticks();
  FlightLimits limits = const FlightLimits();

  LinkState state = LinkState.disconnected;
  bool armed = false;
  bool armConfirmed = false;
  int? latencyMs;
  String? error;

  DateTime _lastRx = DateTime.fromMillisecondsSinceEpoch(0);
  final Map<int, DateTime> _pings = {};
  int _pingSeq = 0;

  bool get isOpen => _socket != null;

  Future<void> connect() async {
    if (_socket != null) return;
    state = LinkState.connecting;
    error = null;
    notifyListeners();
    try {
      _target = InternetAddress(host);
      // Bind to the Wi-Fi interface: the drone's access point has no internet,
      // so Android would otherwise route packets over mobile data.
      final local = await _wifiAddressFor(_target!);
      _socket = await RawDatagramSocket.bind(local ?? InternetAddress.anyIPv4, 0);
      _socket!.listen(_onSocketEvent, onError: (Object e) => _fail('$e'));
      _sendRaw(Crtp.setpoint(roll: 0, pitch: 0, yawRate: 0, thrust: 0)); // releases the thrust lock
      _setpointTimer = Timer.periodic(_setpointPeriod, (_) => _sendSetpoint());
      _pingTimer = Timer.periodic(_pingPeriod, (_) => _tick());
    } catch (e) {
      _fail('Could not open socket: $e');
    }
  }

  Future<void> disconnect() async {
    if (_socket != null) {
      _sendRaw(Crtp.setpoint(roll: 0, pitch: 0, yawRate: 0, thrust: 0));
      _sendRaw(Crtp.arm(false));
    }
    _setpointTimer?.cancel();
    _pingTimer?.cancel();
    _socket?.close();
    _socket = null;
    armed = false;
    armConfirmed = false;
    latencyMs = null;
    state = LinkState.disconnected;
    notifyListeners();
  }

  /// Arming is refused unless the throttle is at zero.
  bool setArmed(bool value) {
    if (value && sticks.throttle > 0.02) return false;
    if (value && state != LinkState.connected) return false;
    armed = value;
    armConfirmed = false;
    _sendRaw(Crtp.arm(value));
    notifyListeners();
    return true;
  }

  /// Immediate stop: zero thrust and disarm, repeated to survive packet loss.
  void emergencyStop() {
    sticks = const Sticks();
    armed = false;
    armConfirmed = false;
    for (var i = 0; i < 3; i++) {
      _sendRaw(Crtp.setpoint(roll: 0, pitch: 0, yawRate: 0, thrust: 0));
      _sendRaw(Crtp.arm(false));
    }
    notifyListeners();
  }

  void updateSticks(Sticks s) => sticks = s;

  void updateLimits(FlightLimits l) {
    limits = l;
    notifyListeners();
  }

  /// The setpoint actually sent, for display.
  ({double roll, double pitch, double yawRate, int thrust}) get command {
    final l = limits;
    final roll = sticks.roll * l.maxAngleDeg * (l.invertRoll ? -1 : 1) + l.rollTrimDeg;
    final pitch = sticks.pitch * l.maxAngleDeg * (l.invertPitch ? -1 : 1) + l.pitchTrimDeg;
    final yaw = sticks.yaw * l.maxYawRateDeg;
    final thrust = armed ? (sticks.throttle * l.maxThrustFraction * Crtp.maxThrust).round() : 0;
    return (roll: roll, pitch: pitch, yawRate: yaw, thrust: thrust);
  }

  void _sendSetpoint() {
    final c = command;
    _sendRaw(Crtp.setpoint(roll: c.roll, pitch: c.pitch, yawRate: c.yawRate, thrust: c.thrust));
  }

  void _tick() {
    final seq = _pingSeq = (_pingSeq + 1) & 0xFF;
    _pings[seq] = DateTime.now();
    _pings.removeWhere((_, t) => DateTime.now().difference(t) > const Duration(seconds: 3));
    _sendRaw(Crtp.echo(seq));
    // Re-send the arm state until the firmware acknowledges it.
    if (!armConfirmed && state == LinkState.connected) _sendRaw(Crtp.arm(armed));

    final alive = DateTime.now().difference(_lastRx) < _linkTimeout;
    final next = alive
        ? LinkState.connected
        : (state == LinkState.connected || state == LinkState.lost ? LinkState.lost : LinkState.connecting);
    if (next != state) {
      state = next;
      if (state == LinkState.lost) {
        armed = false;
        armConfirmed = false;
      }
      notifyListeners();
    }
  }

  void _onSocketEvent(RawSocketEvent event) {
    if (event != RawSocketEvent.read) return;
    Datagram? d;
    while ((d = _socket?.receive()) != null) {
      final pkt = Crtp.parse(d!.data);
      if (pkt == null) continue;
      _lastRx = DateTime.now();
      final port = Crtp.portOf(pkt[0]);
      final channel = Crtp.channelOf(pkt[0]);
      if (port == Crtp.portLink && channel == 0 && pkt.length >= 2) {
        final sent = _pings.remove(pkt[1]);
        if (sent != null) latencyMs = DateTime.now().difference(sent).inMilliseconds;
      } else if (port == Crtp.portParam && channel == Crtp.paramChannelMisc && pkt.length > 1) {
        // Set-by-name reply ends with an error byte; 0 means the value was written.
        if (_isForceArmReply(pkt) && pkt.last == 0) armConfirmed = true;
      }
      if (state != LinkState.connected) {
        state = LinkState.connected;
      }
      notifyListeners();
    }
  }

  static bool _isForceArmReply(Uint8List pkt) {
    final text = String.fromCharCodes(pkt.sublist(2, pkt.length - 1).where((b) => b != 0));
    return text.contains('systemforceArm');
  }

  void _sendRaw(Uint8List bytes) {
    final s = _socket;
    final t = _target;
    if (s == null || t == null) return;
    try {
      s.send(bytes, t, port);
    } catch (e) {
      _fail('Send failed: $e');
    }
  }

  void _fail(String message) {
    error = message;
    disconnect();
  }

  static Future<InternetAddress?> _wifiAddressFor(InternetAddress target) async {
    final prefix = target.address.substring(0, target.address.lastIndexOf('.') + 1);
    try {
      for (final iface in await NetworkInterface.list(type: InternetAddressType.IPv4)) {
        for (final addr in iface.addresses) {
          if (addr.address.startsWith(prefix)) return addr;
        }
      }
    } catch (_) {}
    return null;
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
