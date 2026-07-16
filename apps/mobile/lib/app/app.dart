import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/auth/app_session.dart';
import '../core/auth/providers.dart';
import '../l10n/app_localizations.dart';
import 'router.dart';
import 'theme.dart';

class RafeeqApp extends ConsumerWidget {
  const RafeeqApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(appSessionProvider);
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'RAFEEQ',
      debugShowCheckedModeBanner: false,
      locale: session.locale,
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      builder: (context, child) {
        final strings = AppLocalizations.of(context)!;
        session.api.configureErrorMessages(
          networkUnavailable: strings.networkUnavailable,
          unexpectedError: strings.unexpectedError,
        );
        return RafeeqAppViewport(
          authenticated: session.status == SessionStatus.authenticated,
          footer: strings.platformFooter,
          child: child!,
        );
      },
      routerConfig: router,
      theme: buildRafeeqTheme(),
    );
  }
}
