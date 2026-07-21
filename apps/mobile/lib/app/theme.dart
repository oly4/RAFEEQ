import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

abstract final class RafeeqColors {
  static const primary = Color(0xFF9364F7);
  static const primaryDark = Color(0xFF6F42D9);
  static const lavender = Color(0xFFF0E8FF);
  static const lavenderSoft = Color(0xFFF9F6FF);
  static const ink = Color(0xFF17152D);
  static const muted = Color(0xFF77718D);
  static const success = Color(0xFF21B876);
  static const danger = Color(0xFFFF3154);
  static const outline = Color(0xFFE6DDF5);
}

abstract final class RafeeqGradients {
  static const page = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [
      Color(0xFFF0E8FF),
      RafeeqColors.lavenderSoft,
      Colors.white,
    ],
    stops: [0, 0.42, 1],
  );

  static const primary = LinearGradient(
    begin: AlignmentDirectional.topStart,
    end: AlignmentDirectional.bottomEnd,
    colors: [
      RafeeqColors.primary,
      RafeeqColors.primaryDark,
    ],
  );

  static const softCard = LinearGradient(
    begin: AlignmentDirectional.topStart,
    end: AlignmentDirectional.bottomEnd,
    colors: [
      Colors.white,
      RafeeqColors.lavenderSoft,
    ],
  );
}

const _rafeeqFontFamily = 'Roboto';
const _rafeeqFontFallback = ['RafeeqNaskh'];

ThemeData buildRafeeqTheme() {
  const scheme = ColorScheme.light(
    primary: RafeeqColors.primary,
    onPrimary: Colors.white,
    primaryContainer: RafeeqColors.lavender,
    onPrimaryContainer: RafeeqColors.primaryDark,
    secondary: RafeeqColors.primaryDark,
    onSecondary: Colors.white,
    secondaryContainer: Color(0xFFE8DBFF),
    onSecondaryContainer: RafeeqColors.ink,
    error: RafeeqColors.danger,
    onError: Colors.white,
    errorContainer: Color(0xFFFFE8ED),
    onErrorContainer: Color(0xFF97152F),
    surface: Colors.white,
    onSurface: RafeeqColors.ink,
    outline: RafeeqColors.outline,
  );

  final baseText = ThemeData.light(useMaterial3: true).textTheme.apply(
        fontFamily: _rafeeqFontFamily,
        fontFamilyFallback: _rafeeqFontFallback,
        bodyColor: RafeeqColors.ink,
        displayColor: RafeeqColors.ink,
      );

  return ThemeData(
    useMaterial3: true,
    fontFamily: _rafeeqFontFamily,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xFFFCFAFF),
    textTheme: baseText.copyWith(
      headlineSmall: baseText.headlineSmall?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.3,
      ),
      titleLarge: baseText.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      titleMedium: baseText.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      labelLarge: baseText.labelLarge?.copyWith(fontWeight: FontWeight.w800),
      bodySmall: baseText.bodySmall?.copyWith(color: RafeeqColors.muted),
    ),
    appBarTheme: const AppBarTheme(
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      backgroundColor: Color(0xFFFCFAFF),
      foregroundColor: RafeeqColors.ink,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TextStyle(
        fontFamily: _rafeeqFontFamily,
        fontFamilyFallback: _rafeeqFontFallback,
        color: RafeeqColors.ink,
        fontSize: 22,
        fontWeight: FontWeight.w800,
      ),
    ),
    cardTheme: CardThemeData(
      margin: EdgeInsets.zero,
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 5,
      shadowColor: RafeeqColors.primary.withValues(alpha: 0.16),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(26),
        side: BorderSide(color: RafeeqColors.outline.withValues(alpha: 0.82)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 54),
        elevation: 5,
        shadowColor: RafeeqColors.primary.withValues(alpha: 0.28),
        backgroundColor: RafeeqColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        textStyle: const TextStyle(
          fontFamily: _rafeeqFontFamily,
          fontFamilyFallback: _rafeeqFontFallback,
          fontSize: 16,
          fontWeight: FontWeight.w800,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 54),
        side: const BorderSide(color: RafeeqColors.outline, width: 1.5),
        backgroundColor: Colors.white,
        foregroundColor: RafeeqColors.primary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        textStyle: const TextStyle(
          fontFamily: _rafeeqFontFamily,
          fontFamilyFallback: _rafeeqFontFallback,
          fontSize: 16,
          fontWeight: FontWeight.w800,
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 17),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: RafeeqColors.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: RafeeqColors.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(20),
        borderSide: const BorderSide(color: RafeeqColors.primary, width: 2),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        backgroundColor: Colors.white,
        foregroundColor: RafeeqColors.ink,
        highlightColor: RafeeqColors.lavender,
        shadowColor: RafeeqColors.primary.withValues(alpha: 0.14),
        elevation: 2,
      ),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      elevation: 10,
      highlightElevation: 4,
      backgroundColor: RafeeqColors.lavender,
      foregroundColor: RafeeqColors.primary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: RafeeqColors.primary,
      linearTrackColor: RafeeqColors.lavender,
      circularTrackColor: RafeeqColors.lavender,
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 72,
      elevation: 12,
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: RafeeqColors.lavender,
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            fontFamily: _rafeeqFontFamily,
            fontFamilyFallback: _rafeeqFontFallback,
            color: states.contains(WidgetState.selected)
                ? RafeeqColors.primaryDark
                : RafeeqColors.muted,
            fontSize: 11,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w800
                : FontWeight.w600,
          )),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected)
                ? RafeeqColors.primary
                : RafeeqColors.muted,
          )),
    ),
    listTileTheme: ListTileThemeData(
      iconColor: RafeeqColors.primary,
      textColor: RafeeqColors.ink,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? RafeeqColors.primary
              : Colors.white,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? Colors.white
              : RafeeqColors.ink,
        ),
        side: WidgetStateProperty.all(
          BorderSide(color: RafeeqColors.outline.withValues(alpha: 0.95)),
        ),
        shape: WidgetStateProperty.all(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: RafeeqColors.ink,
      contentTextStyle: const TextStyle(
        color: Colors.white,
        fontFamily: _rafeeqFontFamily,
        fontFamilyFallback: _rafeeqFontFallback,
        fontWeight: FontWeight.w700,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    dividerTheme: const DividerThemeData(color: RafeeqColors.outline),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.windows: CupertinoPageTransitionsBuilder(),
      TargetPlatform.linux: CupertinoPageTransitionsBuilder(),
    }),
  );
}

/// Shows the web build in a phone-sized canvas on larger screens while using
/// the full display on an actual phone.
class RafeeqAppViewport extends StatelessWidget {
  const RafeeqAppViewport({
    required this.child,
    required this.authenticated,
    required this.footer,
    super.key,
  });

  final Widget child;
  final bool authenticated;
  final String footer;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final phoneWidth = math.min(366.0, constraints.maxWidth - 24);
          const phoneHeight = 772.0;
          final footerHeight = authenticated ? 0.0 : 34.0;
          const gap = 8.0;
          final availablePhoneHeight =
              constraints.maxHeight - footerHeight - 12;
          final resolvedPhoneHeight =
              math.min(phoneHeight, math.max(520.0, availablePhoneHeight));
          return DecoratedBox(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFFF0E8FF),
                  Color(0xFFF9F6FF),
                  Colors.white,
                ],
              ),
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: phoneWidth,
                    height: resolvedPhoneHeight,
                    decoration: BoxDecoration(
                      color: RafeeqColors.ink,
                      borderRadius: BorderRadius.circular(42),
                      boxShadow: [
                        BoxShadow(
                          color: RafeeqColors.ink.withValues(alpha: 0.16),
                          blurRadius: 32,
                          offset: const Offset(0, 16),
                        ),
                      ],
                    ),
                    padding: const EdgeInsets.all(10),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(32),
                      child: DecoratedBox(
                        decoration: const BoxDecoration(
                          gradient: RafeeqGradients.page,
                        ),
                        child: child,
                      ),
                    ),
                  ),
                  if (!authenticated) const SizedBox(height: gap),
                  if (!authenticated)
                    SizedBox(
                      width: phoneWidth,
                      height: footerHeight,
                      child: Center(
                        child: Text(
                          footer,
                          style: const TextStyle(
                            fontFamily: _rafeeqFontFamily,
                            fontFamilyFallback: _rafeeqFontFallback,
                            color: RafeeqColors.muted,
                            fontSize: 11,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      );
}
