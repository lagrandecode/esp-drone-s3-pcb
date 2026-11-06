import 'package:shared_preferences/shared_preferences.dart';

import 'drone_link.dart';

class SettingsStore {
  static const _prefix = 'limits.';

  static Future<FlightLimits> load() async {
    final p = await SharedPreferences.getInstance();
    const d = FlightLimits();
    return FlightLimits(
      maxAngleDeg: p.getDouble('${_prefix}maxAngle') ?? d.maxAngleDeg,
      maxYawRateDeg: p.getDouble('${_prefix}maxYawRate') ?? d.maxYawRateDeg,
      maxThrustFraction: p.getDouble('${_prefix}maxThrust') ?? d.maxThrustFraction,
      invertPitch: p.getBool('${_prefix}invertPitch') ?? d.invertPitch,
      invertRoll: p.getBool('${_prefix}invertRoll') ?? d.invertRoll,
      rollTrimDeg: p.getDouble('${_prefix}rollTrim') ?? d.rollTrimDeg,
      pitchTrimDeg: p.getDouble('${_prefix}pitchTrim') ?? d.pitchTrimDeg,
    );
  }

  static Future<void> save(FlightLimits l) async {
    final p = await SharedPreferences.getInstance();
    await p.setDouble('${_prefix}maxAngle', l.maxAngleDeg);
    await p.setDouble('${_prefix}maxYawRate', l.maxYawRateDeg);
    await p.setDouble('${_prefix}maxThrust', l.maxThrustFraction);
    await p.setBool('${_prefix}invertPitch', l.invertPitch);
    await p.setBool('${_prefix}invertRoll', l.invertRoll);
    await p.setDouble('${_prefix}rollTrim', l.rollTrimDeg);
    await p.setDouble('${_prefix}pitchTrim', l.pitchTrimDeg);
  }
}
