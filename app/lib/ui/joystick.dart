import 'dart:math';

import 'package:flutter/material.dart';

/// Touch joystick reporting x/y in -1..1 (up is +y).
///
/// An axis with `springY: false` keeps its position when released, which is
/// how the throttle stick works; otherwise the axis returns to centre.
class Joystick extends StatefulWidget {
  const Joystick({
    super.key,
    required this.onChanged,
    this.springX = true,
    this.springY = true,
    this.initialY = 0,
    this.label,
    this.size = 190,
    this.resetSignal,
  });

  final void Function(double x, double y) onChanged;
  final bool springX;
  final bool springY;
  final double initialY;
  final String? label;
  final double size;

  /// Changing this value snaps the stick back to its initial position.
  final Object? resetSignal;

  @override
  State<Joystick> createState() => _JoystickState();
}

class _JoystickState extends State<Joystick> {
  late Offset _knob = Offset(0, -widget.initialY);
  bool _active = false;

  @override
  void didUpdateWidget(Joystick old) {
    super.didUpdateWidget(old);
    if (old.resetSignal != widget.resetSignal) {
      setState(() => _knob = Offset(0, -widget.initialY));
    }
  }

  void _update(Offset local) {
    final r = widget.size / 2;
    var v = (local - Offset(r, r)) / r;
    if (v.distance > 1) v = v / v.distance;
    setState(() => _knob = v);
    widget.onChanged(v.dx, -v.dy);
  }

  void _release() {
    final v = Offset(widget.springX ? 0 : _knob.dx, widget.springY ? 0 : _knob.dy);
    setState(() {
      _knob = v;
      _active = false;
    });
    widget.onChanged(v.dx, -v.dy);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanStart: (d) {
            _active = true;
            _update(d.localPosition);
          },
          onPanUpdate: (d) => _update(d.localPosition),
          onPanEnd: (_) => _release(),
          onPanCancel: _release,
          child: CustomPaint(
            size: Size.square(widget.size),
            painter: _StickPainter(_knob, _active, scheme),
          ),
        ),
        if (widget.label != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(widget.label!, style: Theme.of(context).textTheme.labelMedium),
          ),
      ],
    );
  }
}

class _StickPainter extends CustomPainter {
  _StickPainter(this.knob, this.active, this.scheme);

  final Offset knob;
  final bool active;
  final ColorScheme scheme;

  @override
  void paint(Canvas canvas, Size size) {
    final r = size.width / 2;
    final c = Offset(r, r);
    canvas.drawCircle(c, r, Paint()..color = scheme.surfaceContainerHighest);
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = scheme.outline,
    );
    final guide = Paint()
      ..color = scheme.outlineVariant
      ..strokeWidth = 1;
    canvas.drawLine(Offset(r, 8), Offset(r, size.height - 8), guide);
    canvas.drawLine(Offset(8, r), Offset(size.width - 8, r), guide);
    final knobR = max(22.0, r * 0.28);
    canvas.drawCircle(
      c + knob * (r - knobR),
      knobR,
      Paint()..color = active ? scheme.primary : scheme.secondary,
    );
  }

  @override
  bool shouldRepaint(_StickPainter old) => old.knob != knob || old.active != active;
}
