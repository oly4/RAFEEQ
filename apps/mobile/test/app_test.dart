import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rafeeq_mobile/app/app.dart';
import 'package:rafeeq_mobile/core/auth/app_session.dart';
import 'package:rafeeq_mobile/core/auth/models.dart';
import 'package:rafeeq_mobile/core/auth/providers.dart';
import 'package:rafeeq_mobile/core/widgets/rafeeq_robot.dart';
import 'package:rafeeq_mobile/features/camera/presentation/screens/camera_test_screen.dart';
import 'package:rafeeq_mobile/l10n/app_localizations.dart';
import 'package:rafeeq_mobile/l10n/localized_values.dart';

void main() {
  Future<void> pumpApp(WidgetTester tester, AppSession session) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [appSessionProvider.overrideWith((ref) => session)],
      child: const RafeeqApp(),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('language selector changes the welcome page to English LTR',
      (tester) async {
    final session = AppSession()..status = SessionStatus.unauthenticated;
    await pumpApp(tester, session);

    expect(find.byType(RafeeqRobot), findsOneWidget);
    final arabic = lookupAppLocalizations(const Locale('ar'));
    expect(Directionality.of(tester.element(find.text(arabic.caregiverLogin))),
        TextDirection.rtl);

    await tester.ensureVisible(find.byIcon(Icons.language_rounded));
    await tester.tap(find.byIcon(Icons.language_rounded));
    await tester.pumpAndSettle();

    expect(find.byType(RafeeqRobot), findsOneWidget);
    expect(find.text('Continue as family'), findsOneWidget);
    expect(find.text('Continue as doctor'), findsOneWidget);
    expect(find.text(arabic.caregiverLogin), findsNothing);
    expect(Directionality.of(tester.element(find.text('Continue as family'))),
        TextDirection.ltr);
  });

  testWidgets('English registration labels and validation are complete',
      (tester) async {
    final session = AppSession()
      ..status = SessionStatus.unauthenticated
      ..changeLocale('en');
    await pumpApp(tester, session);

    await tester.tap(find.text('Continue as family'));
    await tester.pumpAndSettle();

    final createAccount = find.widgetWithText(OutlinedButton, 'Create account');
    await tester.ensureVisible(createAccount);
    await tester.tap(createAccount);
    await tester.pumpAndSettle();

    expect(find.text('Full name'), findsOneWidget);
    expect(find.text('Caregiver'), findsOneWidget);
    expect(find.text('Doctor'), findsOneWidget);
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);

    final submit = find.widgetWithText(FilledButton, 'Create account');
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pump();

    expect(find.text('Enter your full name'), findsOneWidget);
    expect(find.text('Enter a valid email address'), findsOneWidget);
    expect(find.text('Use at least 8 characters'), findsOneWidget);
  });

  testWidgets('English patient creation page is LTR', (tester) async {
    final session = AppSession()
      ..status = SessionStatus.authenticated
      ..user = const AppUser(
          id: 'caregiver-1',
          role: 'caregiver',
          fullName: 'Care Giver',
          email: 'caregiver@example.com')
      ..changeLocale('en');
    await pumpApp(tester, session);

    expect(find.text('Add patient profile'), findsWidgets);
    expect(find.text('Name of the person you care for'), findsOneWidget);
    expect(
        Directionality.of(
            tester.element(find.text('Name of the person you care for'))),
        TextDirection.ltr);
  });

  testWidgets('English doctor empty state is translated', (tester) async {
    final session = AppSession()
      ..status = SessionStatus.authenticated
      ..user = const AppUser(
          id: 'doctor-1',
          role: 'doctor',
          fullName: 'Doctor One',
          email: 'doctor@example.com')
      ..changeLocale('en');
    await pumpApp(tester, session);

    expect(find.text('Doctor dashboard'), findsOneWidget);
    expect(find.text('No patients are assigned to this account yet'),
        findsOneWidget);
    expect(
        find.text(
            'A caregiver can invite the doctor using their email address.'),
        findsOneWidget);
  });

  testWidgets('camera test explains local-only privacy before permission',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      locale: const Locale('en'),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      home: const CameraTestScreen(),
    ));

    expect(find.text('Camera test'), findsOneWidget);
    expect(
        find.text(
            'Live preview only. RAFEEQ does not record, save, or upload this video.'),
        findsOneWidget);
    expect(find.text('Start camera test'), findsOneWidget);
  });

  test('Arabic and English catalogs have exactly the same messages', () {
    final arabic = jsonDecode(File('lib/l10n/app_ar.arb').readAsStringSync())
        as Map<String, dynamic>;
    final english = jsonDecode(File('lib/l10n/app_en.arb').readAsStringSync())
        as Map<String, dynamic>;
    final arabicKeys = arabic.keys.where((key) => !key.startsWith('@')).toSet();
    final englishKeys =
        english.keys.where((key) => !key.startsWith('@')).toSet();

    expect(englishKeys, arabicKeys);

    final arabicCharacters = RegExp(r'[\u0600-\u06FF]');
    for (final entry in english.entries) {
      if (entry.key.startsWith('@') || entry.key == 'arabic') continue;
      if (entry.value is String) {
        expect((entry.value as String).trim(), isNotEmpty,
            reason: 'Empty English message: ${entry.key}');
        expect(arabicCharacters.hasMatch(entry.value as String), isFalse,
            reason: 'Arabic text in English message: ${entry.key}');
      }
    }
  });

  test('backend statuses and activity types have English display values', () {
    final strings = lookupAppLocalizations(const Locale('en'));

    expect(localizedStatus(strings, 'online'), 'Online');
    expect(localizedStatus(strings, 'false_alarm'), 'False alarm');
    expect(localizedStatus(strings, 'acknowledged'), 'Acknowledged');
    expect(localizedActivityType(strings, 'complete_phrase'),
        'Complete a familiar phrase');
    expect(localizedActivityType(strings, 'custom'), 'Custom activity');
  });

  test('UI source has no hard-coded Arabic outside localization files', () {
    final arabicCharacters = RegExp(r'[\u0600-\u06FF]');
    final files = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((file) =>
            file.path.endsWith('.dart') &&
            !file.path.contains(
                '${Platform.pathSeparator}l10n${Platform.pathSeparator}'));

    for (final file in files) {
      expect(arabicCharacters.hasMatch(file.readAsStringSync()), isFalse,
          reason: 'Hard-coded Arabic found in ${file.path}');
    }
  });
}
