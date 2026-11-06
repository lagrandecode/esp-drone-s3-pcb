import 'package:flutter/material.dart';

import '../drone/drone_link.dart';
import '../drone/settings_store.dart';
import 'joystick.dart';
import 'settings_sheet.dart';

class ControlScreen extends StatefulWidget {
  const ControlScreen({super.key});

  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen> with WidgetsBindingObserver {
  final DroneLink _link = DroneLink();
  double _yaw = 0, _throttle = 0, _roll = 0, _pitch = 0;
  int _resetCounter = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _link.addListener(_onLink);
    SettingsStore.load().then(_link.updateLimits);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _link.removeListener(_onLink);
    _link.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Never leave the drone armed while the app is not in the foreground.
    if (state != AppLifecycleState.resumed && _link.isOpen) {
      _stop();
    }
  }

  void _onLink() => setState(() {});

  void _push() => _link.updateSticks(Sticks(roll: _roll, pitch: _pitch, yaw: _yaw, throttle: _throttle));

  void _stop() {
    _link.emergencyStop();
    setState(() {
      _yaw = _throttle = _roll = _pitch = 0;
      _resetCounter++;
    });
  }

  void _toggleArm(bool value) {
    if (!_link.setArmed(value)) {
      final reason = _link.state != LinkState.connected
          ? 'Connect to the drone first.'
          : 'Lower the throttle to zero before arming.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(reason)));
    }
  }

  void _openSettings() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SettingsSheet(
        initial: _link.limits,
        onChanged: (l) {
          _link.updateLimits(l);
          SettingsStore.save(l);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final c = _link.command;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Column(
            children: [
              _topBar(scheme),
              const SizedBox(height: 4),
              Text(
                'roll ${c.roll.toStringAsFixed(1)}°   pitch ${c.pitch.toStringAsFixed(1)}°   '
                'yaw ${c.yawRate.toStringAsFixed(0)}°/s   thrust ${(c.thrust / 600).toStringAsFixed(0)}%',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(fontFeatures: const []),
              ),
              Expanded(
                child: LayoutBuilder(builder: (context, box) {
                  final size = (box.maxHeight - 30).clamp(120.0, 230.0);
                  return Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Joystick(
                        size: size,
                        springY: false,
                        initialY: -1,
                        resetSignal: _resetCounter,
                        label: 'Throttle / Yaw',
                        onChanged: (x, y) {
                          _yaw = x;
                          _throttle = (y + 1) / 2;
                          _push();
                        },
                      ),
                      _stopButton(scheme),
                      Joystick(
                        size: size,
                        resetSignal: _resetCounter,
                        label: 'Pitch / Roll',
                        onChanged: (x, y) {
                          _roll = x;
                          _pitch = y;
                          _push();
                        },
                      ),
                    ],
                  );
                }),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _topBar(ColorScheme scheme) {
    final (label, color) = switch (_link.state) {
      LinkState.disconnected => ('Disconnected', scheme.outline),
      LinkState.connecting => ('Waiting for drone…', Colors.orange),
      LinkState.connected => ('Connected${_link.latencyMs != null ? ' · ${_link.latencyMs} ms' : ''}', Colors.green),
      LinkState.lost => ('Link lost', scheme.error),
    };
    return Row(
      children: [
        Icon(Icons.circle, size: 12, color: color),
        const SizedBox(width: 8),
        Text(label),
        const Spacer(),
        if (_link.error != null)
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Text(_link.error!, style: TextStyle(color: scheme.error)),
          ),
        FilledButton.tonal(
          onPressed: () => _link.isOpen ? _link.disconnect() : _link.connect(),
          child: Text(_link.isOpen ? 'Disconnect' : 'Connect'),
        ),
        const SizedBox(width: 16),
        Text(_link.armed ? (_link.armConfirmed ? 'ARMED' : 'Arming…') : 'Disarmed',
            style: TextStyle(fontWeight: FontWeight.bold, color: _link.armed ? scheme.error : null)),
        Switch(value: _link.armed, onChanged: _toggleArm),
        IconButton(onPressed: _openSettings, icon: const Icon(Icons.tune), tooltip: 'Flight settings'),
      ],
    );
  }

  Widget _stopButton(ColorScheme scheme) {
    return SizedBox(
      width: 110,
      height: 110,
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: scheme.error,
          foregroundColor: scheme.onError,
          shape: const CircleBorder(),
        ),
        onPressed: _stop,
        child: const Text('STOP', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
      ),
    );
  }
}
