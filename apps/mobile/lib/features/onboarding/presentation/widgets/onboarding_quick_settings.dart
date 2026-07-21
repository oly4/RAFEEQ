import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/providers.dart';

class OnboardingQuickSettings extends ConsumerWidget {
  const OnboardingQuickSettings({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(appSessionProvider);
    final brightness = Theme.of(context).brightness;
    final isDark = brightness == Brightness.dark;
    final languageLabel = session.locale.languageCode == 'ar' ? 'EN' : 'عربي';
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isDark
            ? const Color(0xFF211A38).withValues(alpha: 0.88)
            : Colors.white.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: isDark ? RafeeqColors.outlineDark : RafeeqColors.outline,
        ),
        boxShadow: [
          BoxShadow(
            color: RafeeqColors.primary.withValues(alpha: isDark ? 0.22 : 0.12),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextButton.icon(
              style: TextButton.styleFrom(
                visualDensity: VisualDensity.compact,
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              onPressed: () => session.changeLocale(
                session.locale.languageCode == 'ar' ? 'en' : 'ar',
              ),
              icon: const Icon(Icons.language_rounded, size: 16),
              label: Text(
                languageLabel,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
            Container(
              width: 1,
              height: 22,
              color: isDark ? RafeeqColors.outlineDark : RafeeqColors.outline,
            ),
            IconButton(
              tooltip: session.locale.languageCode == 'ar'
                  ? 'تغيير المظهر'
                  : 'Change appearance',
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.all(7),
              constraints: const BoxConstraints(),
              onPressed: () => session.changeThemeMode(
                isDark ? ThemeMode.light : ThemeMode.dark,
              ),
              icon: Icon(
                isDark ? Icons.light_mode_rounded : Icons.dark_mode_rounded,
                size: 18,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
