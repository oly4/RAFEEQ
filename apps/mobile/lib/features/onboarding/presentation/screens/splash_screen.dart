import 'package:flutter/material.dart';

import '../../../../core/widgets/rafeeq_robot.dart';
import '../../../../l10n/app_localizations.dart';

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            RafeeqRobot(semanticLabel: strings.robotSemanticLabel, size: 190),
            const SizedBox(height: 24),
            CircularProgressIndicator(semanticsLabel: strings.loading),
          ],
        ),
      ),
    );
  }
}
