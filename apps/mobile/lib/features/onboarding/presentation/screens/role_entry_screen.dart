import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/providers.dart';
import '../../../../core/widgets/rafeeq_robot.dart';
import '../../../../l10n/app_localizations.dart';

class RoleEntryScreen extends ConsumerWidget {
  const RoleEntryScreen({required this.role, super.key});

  final String role;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    final isDoctor = role == 'doctor';
    final roleLabel = isDoctor ? strings.doctorAccess : strings.familyAccess;
    final brightness = Theme.of(context).brightness;
    return Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RafeeqGradients.pageFor(brightness),
        ),
        child: LayoutBuilder(
          builder: (context, constraints) => SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: IntrinsicHeight(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
                  child: Column(children: [
                    Row(children: [
                      TextButton.icon(
                        onPressed: () => context.go('/welcome'),
                        icon: Icon(
                          Directionality.of(context) == TextDirection.rtl
                              ? Icons.chevron_right_rounded
                              : Icons.chevron_left_rounded,
                          size: 18,
                        ),
                        label: Text(strings.back),
                      ),
                      const Spacer(),
                      IconButton.filledTonal(
                        tooltip: session.locale.languageCode == 'ar'
                            ? 'تغيير المظهر'
                            : 'Change appearance',
                        onPressed: () => session.changeThemeMode(
                          brightness == Brightness.dark
                              ? ThemeMode.light
                              : ThemeMode.dark,
                        ),
                        icon: Icon(
                          brightness == Brightness.dark
                              ? Icons.light_mode_rounded
                              : Icons.dark_mode_rounded,
                        ),
                      ),
                    ]),
                    const Spacer(),
                    RafeeqRobot(
                      semanticLabel: strings.robotSemanticLabel,
                      size: 176,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      strings.appName,
                      style: const TextStyle(
                        color: RafeeqColors.primary,
                        fontSize: 31,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          roleLabel,
                          style: const TextStyle(
                            color: RafeeqColors.primary,
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(width: 5),
                        Icon(
                          isDoctor
                              ? Icons.medical_services_outlined
                              : Icons.family_restroom_rounded,
                          size: 17,
                          color: RafeeqColors.primary,
                        ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    Text(
                      strings.dailyCareTagline,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          color: RafeeqColors.muted, fontSize: 12),
                    ),
                    const Spacer(flex: 2),
                    RafeeqGlowCard(
                      hero: true,
                      child: Column(children: [
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: () => context.go('/login?role=$role'),
                            child: Text(strings.login),
                          ),
                        ),
                        const SizedBox(height: 11),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton(
                            onPressed: () => context.go('/register?role=$role'),
                            child: Text(strings.createAccount),
                          ),
                        ),
                      ]),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      strings.byContinuing,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            fontSize: 10,
                          ),
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
