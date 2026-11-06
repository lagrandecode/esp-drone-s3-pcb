import 'package:flutter/material.dart';

import '../drone/drone_link.dart';

class SettingsSheet extends StatefulWidget {
  const SettingsSheet({super.key, required this.initial, required this.onChanged});

  final FlightLimits initial;
  final ValueChanged<FlightLimits> onChanged;

  @override
  State<SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<SettingsSheet> {
  late FlightLimits _l = widget.initial;

  void _set(FlightLimits l) {
    setState(() => _l = l);
    widget.onChanged(l);
  }

  Widget _slider(String label, double value, double min, double max, String unit, ValueChanged<double> onChanged,
      {int divisions = 40}) {
    return Row(
      children: [
        SizedBox(width: 150, child: Text(label)),
        Expanded(
          child: Slider(value: value.clamp(min, max), min: min, max: max, divisions: divisions, onChanged: onChanged),
        ),
        SizedBox(width: 70, child: Text('${value.toStringAsFixed(unit == '%' ? 0 : 1)} $unit')),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Flight settings', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            _slider('Max tilt angle', _l.maxAngleDeg, 5, 30, '°', (v) => _set(_l.copyWith(maxAngleDeg: v)),
                divisions: 25),
            _slider('Max yaw rate', _l.maxYawRateDeg, 30, 300, '°/s', (v) => _set(_l.copyWith(maxYawRateDeg: v)),
                divisions: 27),
            _slider('Max throttle', _l.maxThrustFraction * 100, 30, 100, '%',
                (v) => _set(_l.copyWith(maxThrustFraction: v / 100)),
                divisions: 14),
            _slider('Roll trim', _l.rollTrimDeg, -5, 5, '°', (v) => _set(_l.copyWith(rollTrimDeg: v))),
            _slider('Pitch trim', _l.pitchTrimDeg, -5, 5, '°', (v) => _set(_l.copyWith(pitchTrimDeg: v))),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Invert pitch'),
              subtitle: const Text('Use if pushing the right stick forward makes the drone fly backwards'),
              value: _l.invertPitch,
              onChanged: (v) => _set(_l.copyWith(invertPitch: v)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Invert roll'),
              subtitle: const Text('Use if pushing the right stick right makes the drone drift left'),
              value: _l.invertRoll,
              onChanged: (v) => _set(_l.copyWith(invertRoll: v)),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => _set(const FlightLimits()),
                child: const Text('Reset to defaults'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
