import 'package:flutter/material.dart';

class RafeeqLogo extends StatelessWidget {
  const RafeeqLogo({
    required this.semanticLabel,
    this.size = 260,
    super.key,
  });

  final String semanticLabel;
  final double size;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(size * 0.12),
        child: Image.asset(
          'assets/images/rafeeq_logo.jpg',
          width: size,
          height: size,
          fit: BoxFit.contain,
          semanticLabel: semanticLabel,
        ),
      );
}
