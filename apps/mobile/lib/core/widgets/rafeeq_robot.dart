import 'package:flutter/material.dart';

class RafeeqRobot extends StatelessWidget {
  const RafeeqRobot({
    required this.semanticLabel,
    this.size = 150,
    super.key,
  });

  final String semanticLabel;
  final double size;

  @override
  Widget build(BuildContext context) => Image.asset(
        'assets/images/rafeeq_robot.png',
        width: size,
        height: size,
        fit: BoxFit.contain,
        semanticLabel: semanticLabel,
      );
}
