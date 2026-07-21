import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/providers.dart';
import '../../../../core/widgets/rafeeq_robot.dart';
import '../../../../l10n/app_localizations.dart';

class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
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
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
                  child: Column(children: [
                    _Brand(title: strings.appName),
                    const SizedBox(height: 12),
                    RafeeqRobot(
                      semanticLabel: strings.robotSemanticLabel,
                      size: 144,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      strings.chooseLoginRole,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            fontSize: 21,
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 7),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: Text(
                        strings.platformDescription,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: RafeeqColors.muted,
                              height: 1.55,
                            ),
                      ),
                    ),
                    const Spacer(),
                    _RoleCard(
                      icon: Icons.family_restroom_rounded,
                      title: strings.caregiverLogin,
                      description: strings.caregiverRoleDescription,
                      onTap: () => context.go('/access?role=caregiver'),
                    ),
                    const SizedBox(height: 12),
                    _RoleCard(
                      icon: Icons.medical_services_outlined,
                      title: strings.doctorLogin,
                      description: strings.doctorRoleDescription,
                      emphasized: true,
                      onTap: () => context.go('/access?role=doctor'),
                    ),
                    const Spacer(),
                    Wrap(
                      alignment: WrapAlignment.center,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 2,
                      children: [
                        TextButton(
                          onPressed: () => _showInformation(
                            context,
                            strings.privacyTitle,
                            strings.privacy,
                          ),
                          child: Text(strings.privacyTitle),
                        ),
                        const Text('•',
                            style: TextStyle(color: RafeeqColors.muted)),
                        TextButton(
                          onPressed: () => _showInformation(
                            context,
                            strings.termsOfUse,
                            strings.byContinuing,
                          ),
                          child: Text(strings.termsOfUse),
                        ),
                        IconButton(
                          tooltip: strings.language,
                          visualDensity: VisualDensity.compact,
                          onPressed: () => session.changeLocale(
                            session.locale.languageCode == 'ar' ? 'en' : 'ar',
                          ),
                          icon: const Icon(Icons.language_rounded, size: 17),
                        ),
                      ],
                    ),
                    Text(
                      '${strings.appName} © 2026',
                      style: const TextStyle(
                        color: RafeeqColors.primary,
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
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

  void _showInformation(BuildContext context, String title, String content) {
    final strings = AppLocalizations.of(context)!;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(content),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(strings.ok),
          ),
        ],
      ),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: RafeeqColors.primary,
              fontSize: 25,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(width: 9),
          const CircleAvatar(
            radius: 20,
            backgroundColor: RafeeqColors.primary,
            child: Icon(Icons.favorite_rounded, color: Colors.white, size: 21),
          ),
        ],
      );
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.icon,
    required this.title,
    required this.description,
    required this.onTap,
    this.emphasized = false,
  });

  final IconData icon;
  final String title;
  final String description;
  final VoidCallback onTap;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    final isDark = brightness == Brightness.dark;
    final textColor =
        emphasized || isDark ? Colors.white : RafeeqColors.primary;
    final subtitleColor = emphasized
        ? Colors.white.withValues(alpha: 0.86)
        : isDark
            ? RafeeqColors.mutedDark
            : RafeeqColors.muted;
    return RafeeqGlowCard(
      onTap: onTap,
      hero: emphasized,
      radius: 28,
      glowColor: emphasized ? RafeeqColors.primary : RafeeqColors.primaryDark,
      gradient: emphasized
          ? RafeeqGradients.primary
          : RafeeqGradients.aliveCardFor(brightness),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 102),
        child: Row(children: [
          CircleAvatar(
            radius: 24,
            backgroundColor: emphasized
                ? Colors.white.withValues(alpha: 0.15)
                : isDark
                    ? const Color(0xFF35265F)
                    : RafeeqColors.lavender,
            child: Icon(icon, color: textColor),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: textColor,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: subtitleColor,
                    fontSize: 11,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          Icon(
            Directionality.of(context) == TextDirection.rtl
                ? Icons.chevron_left_rounded
                : Icons.chevron_right_rounded,
            color: textColor,
            size: 20,
          ),
        ]),
      ),
    );
  }
}
