import 'package:flutter/material.dart';

import 'app_localizations.dart';

String localizedStatus(AppLocalizations strings, Object? value) {
  return switch (value?.toString()) {
    'متصل' => strings.statusOnline,
    'connected' => strings.statusOnline,
    'pairing' => strings.statusPairing,
    'online' => strings.statusOnline,
    'offline' => strings.statusOffline,
    'degraded' => strings.statusDegraded,
    'disabled' => strings.statusDisabled,
    'unpaired' => strings.statusUnpaired,
    'pending' => strings.statusPending,
    'reminded' => strings.statusReminded,
    'completed' => strings.statusCompleted,
    'snoozed' => strings.statusSnoozed,
    'missed' => strings.statusMissed,
    'skipped' => strings.statusSkipped,
    'cancelled' => strings.statusCancelled,
    'detected' => strings.statusDetected,
    'verifying' => strings.statusVerifying,
    'false_alarm' => strings.statusFalseAlarm,
    'confirmed' => strings.statusConfirmed,
    'notified' => strings.statusNotified,
    'acknowledged' => strings.statusAcknowledged,
    'resolved' => strings.statusResolved,
    final status => status ?? '',
  };
}

String localizedActivityType(AppLocalizations strings, Object? value) {
  return switch (value?.toString()) {
    'memory_exercise' => strings.activityMemoryExercise,
    'recognize_photos' => strings.activityRecognizePhotos,
    'complete_phrase' => strings.activityCompletePhrase,
    'reading' => strings.activityReading,
    'conversation' => strings.activityConversation,
    'calm_music' => strings.activityCalmMusic,
    'custom' => strings.activityCustom,
    final type => type ?? '',
  };
}

String localizedDateTime(BuildContext context, Object? value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (parsed == null) return value?.toString() ?? '';
  final material = MaterialLocalizations.of(context);
  final date = material.formatMediumDate(parsed);
  final time = material.formatTimeOfDay(TimeOfDay.fromDateTime(parsed));
  return '$date, $time';
}

String localizedClockTime(BuildContext context, Object? value) {
  final parts = value?.toString().split(':') ?? const [];
  if (parts.length < 2) return value?.toString() ?? '';
  final hour = int.tryParse(parts[0]);
  final minute = int.tryParse(parts[1]);
  if (hour == null || minute == null) return value?.toString() ?? '';
  return MaterialLocalizations.of(context)
      .formatTimeOfDay(TimeOfDay(hour: hour, minute: minute));
}
