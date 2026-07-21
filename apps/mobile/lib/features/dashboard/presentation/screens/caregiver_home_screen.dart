import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../core/auth/providers.dart';
import '../../../../core/widgets/rafeeq_robot.dart';
import '../../../../l10n/app_localizations.dart';
import '../../../../l10n/localized_values.dart';
import '../../../activities/presentation/screens/activities_panel.dart';
import '../../../camera/presentation/screens/camera_test_screen.dart';
import '../../../doctor/presentation/screens/doctor_panel.dart';
import '../../../memories/presentation/screens/memories_panel.dart';
import '../../../memories/presentation/screens/memory_voice_assistant_stub.dart'
    if (dart.library.html) '../../../memories/presentation/screens/memory_voice_assistant_web.dart';

class CaregiverHomeScreen extends ConsumerStatefulWidget {
  const CaregiverHomeScreen({super.key});

  @override
  ConsumerState<CaregiverHomeScreen> createState() =>
      _CaregiverHomeScreenState();
}

class _CaregiverHomeScreenState extends ConsumerState<CaregiverHomeScreen> {
  int index = 0;
  int dashboardRefreshTick = 0;
  Timer? _voiceEventTimer;
  int _lastVoiceEventSequence = 0;
  bool _pollingVoiceEvents = false;

  @override
  void initState() {
    super.initState();
    _voiceEventTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => _pollVoiceCommandEvents(),
    );
    Future<void>.microtask(_pollVoiceCommandEvents);
  }

  @override
  void dispose() {
    _voiceEventTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    final pages = [
      DashboardTab(
          key: ValueKey(dashboardRefreshTick),
          session: session,
          onOpenRoutine: () => setState(() => index = 1),
          onOpenEmergencies: () => _openTabPanel(
                strings.emergencies,
                EmergencyTab(session: session),
              ),
          onOpenReports: () => _openTabPanel(
                strings.reports,
                ReportsTab(session: session),
              ),
          onOpenSentReports: () => _openTabPanel(
                strings.reportsSentToDoctor,
                SentReportsTab(session: session),
              ),
          onOpenActivities: () => _openPanel(ActivitiesPanel(session: session)),
          onOpenDoctor: () => _openPanel(DoctorPanel(session: session)),
          onOpenCamera: () => _openPanel(const CameraTestScreen())),
      RoutineTab(
        key: ValueKey('routine-$dashboardRefreshTick'),
        session: session,
        onRoutineChanged: () => setState(() => dashboardRefreshTick++),
      ),
      ActivitiesPanel(session: session, embedded: true),
      MemoriesPanel(session: session, embedded: true),
      SettingsTab(session: session),
    ];
    final titles = [
      strings.homePage,
      strings.routine,
      strings.activities,
      strings.album,
      strings.settings
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(titles[index]),
        leading: null,
        actions: index == 0
            ? [
                Padding(
                  padding: const EdgeInsetsDirectional.only(end: 10),
                  child: IconButton.filled(
                    tooltip: strings.activeAlerts,
                    style: IconButton.styleFrom(
                      backgroundColor: RafeeqColors.danger,
                      foregroundColor: Colors.white,
                    ),
                    onPressed: () => _openTabPanel(
                      strings.emergencies,
                      EmergencyTab(session: session),
                    ),
                    icon: const Icon(Icons.warning_amber_rounded, size: 20),
                  ),
                ),
              ]
            : null,
      ),
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RafeeqGradients.pageFor(Theme.of(context).brightness),
        ),
        child: IndexedStack(index: index, children: pages),
      ),
      floatingActionButton: index != 4
          ? FloatingActionButton.extended(
              onPressed: () => _runGlobalVoiceCommand(session),
              icon: const Icon(Icons.mic_none_rounded),
              label: Text(strings.appName),
              backgroundColor: Theme.of(context).brightness == Brightness.dark
                  ? const Color(0xFF35265F)
                  : const Color(0xFFF0E7FF),
              foregroundColor: Theme.of(context).brightness == Brightness.dark
                  ? const Color(0xFFF7F2FF)
                  : RafeeqColors.primary,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
            )
          : null,
      floatingActionButtonLocation: FloatingActionButtonLocation.endFloat,
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: [
          NavigationDestination(
              icon: const Icon(Icons.home_outlined),
              selectedIcon: const Icon(Icons.home),
              label: strings.dashboard),
          NavigationDestination(
              icon: const Icon(Icons.event_note_outlined),
              selectedIcon: const Icon(Icons.event_note),
              label: strings.routine),
          NavigationDestination(
              icon: const Icon(Icons.psychology_alt_outlined),
              selectedIcon: const Icon(Icons.psychology_alt),
              label: strings.activities),
          NavigationDestination(
              icon: const Icon(Icons.photo_library_outlined),
              selectedIcon: const Icon(Icons.photo_library_rounded),
              label: strings.album),
          NavigationDestination(
              icon: const Icon(Icons.settings_outlined),
              selectedIcon: const Icon(Icons.settings),
              label: strings.settings),
        ],
      ),
    );
  }

  void _openPanel(Widget panel) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => panel),
    );
  }

  void _openTabPanel(String title, Widget child) {
    _openPanel(Scaffold(
      appBar: AppBar(
        title: Text(title),
        leading: IconButton(
          onPressed: () => Navigator.pop(context),
          icon: const Icon(Icons.close_rounded),
        ),
      ),
      body: child,
    ));
  }

  Future<void> _runGlobalVoiceCommand(AppSession session) async {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(_homeCopy(
          context,
          'رفيق يسمعك الآن... قل أمرك بوضوح.',
          'Rafeeq is listening now... say your command clearly.',
        )),
      ),
    );
    try {
      final recorded = await recordMemoryAudioAnswer();
      if (!mounted) return;
      if (recorded == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_homeCopy(
              context,
              'ما وصل تسجيل واضح. حاول مرة ثانية.',
              'No clear recording was received. Try again.',
            )),
          ),
        );
        return;
      }
      final patientId = session.currentPatient!.id;
      final response = await session.api.dio.post<Map<String, dynamic>>(
        '/patients/$patientId/voice-command',
        data: {'audio_data_url': recorded.dataUrl, 'emit_event': false},
      );
      if (!mounted) return;
      final data = response.data ?? const <String, dynamic>{};
      final action = data['action']?.toString() ?? 'unknown';
      final audioDataUrl = data['audio_data_url']?.toString();
      await _applyVoiceAction(action, session);
      if (audioDataUrl != null && audioDataUrl.isNotEmpty) {
        await playMemoryAudioDataUrl(audioDataUrl);
      }
      if (!mounted) return;
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_homeCopy(
            context,
            'تعذر تنفيذ الأمر الصوتي. تأكد من المايك والاتصال.',
            'Could not run the voice command. Check microphone permission and connection.',
          )),
        ),
      );
    }
  }

  Future<void> _applyVoiceAction(String action, AppSession session) async {
    switch (action) {
      case 'open_dashboard':
        setState(() => index = 0);
        break;
      case 'open_routine':
      case 'add_routine':
      case 'edit_routine':
      case 'delete_routine':
      case 'complete_routine':
      case 'undo_complete_routine':
        setState(() {
          index = 1;
          dashboardRefreshTick++;
        });
        break;
      case 'open_activities':
        setState(() => index = 2);
        break;
      case 'open_album':
        setState(() => index = 3);
        break;
      case 'open_settings':
        setState(() => index = 4);
        break;
      case 'start_poem_test':
        _openPanel(ActivitiesPanel(
          session: session,
          startPoemImmediately: true,
        ));
        break;
      case 'start_photo_test':
        _openPanel(MemoriesPanel(
          session: session,
          startFirstPhotoTest: true,
        ));
        break;
      default:
        break;
    }
  }

  Future<void> _pollVoiceCommandEvents() async {
    if (_pollingVoiceEvents || !mounted) return;
    _pollingVoiceEvents = true;
    try {
      final session = ref.read(appSessionProvider);
      final patient = session.currentPatient;
      if (patient == null) return;
      final response = await session.api.dio.get<Map<String, dynamic>>(
        '/patients/${patient.id}/voice-command-events',
        queryParameters: {'since': _lastVoiceEventSequence},
      );
      if (!mounted) return;
      final data = response.data ?? const <String, dynamic>{};
      final rawItems = data['items'];
      final items = rawItems is List ? rawItems : const <Object?>[];
      for (final rawItem in items) {
        if (rawItem is! Map) continue;
        final event = Map<String, dynamic>.from(rawItem);
        final sequence = (event['sequence'] as num?)?.toInt();
        if (sequence != null && sequence > _lastVoiceEventSequence) {
          _lastVoiceEventSequence = sequence;
        }
        final action = event['action']?.toString() ?? 'unknown';
        await _applyVoiceAction(action, session);
      }
      final latestSequence = (data['latest_sequence'] as num?)?.toInt();
      if (latestSequence != null && latestSequence > _lastVoiceEventSequence) {
        _lastVoiceEventSequence = latestSequence;
      }
    } catch (_) {
      // The voice bridge is best-effort; the app can keep working while
      // the backend restarts or the wake-word script is disconnected.
    } finally {
      _pollingVoiceEvents = false;
    }
  }

  static String _homeCopy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;
}

class DashboardTab extends StatefulWidget {
  const DashboardTab(
      {required this.session,
      required this.onOpenRoutine,
      required this.onOpenEmergencies,
      required this.onOpenReports,
      required this.onOpenSentReports,
      required this.onOpenActivities,
      required this.onOpenDoctor,
      required this.onOpenCamera,
      super.key});
  final AppSession session;
  final VoidCallback onOpenRoutine;
  final VoidCallback onOpenEmergencies;
  final VoidCallback onOpenReports;
  final VoidCallback onOpenSentReports;
  final VoidCallback onOpenActivities;
  final VoidCallback onOpenDoctor;
  final VoidCallback onOpenCamera;

  @override
  State<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends State<DashboardTab> {
  late Future<Map<String, dynamic>> future;

  @override
  void initState() {
    super.initState();
    future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final patient = widget.session.currentPatient!;
    final responses = await Future.wait<dynamic>([
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/${patient.id}/dashboard'),
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/${patient.id}/care-profile'),
    ]);
    final data = Map<String, dynamic>.from(responses[0].data!);
    data['care_profile'] = Map<String, dynamic>.from(responses[1].data!);
    return data;
  }

  void refresh() => setState(() => future = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return RefreshIndicator(
      onRefresh: () async => refresh(),
      child: FutureBuilder<Map<String, dynamic>>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return ListView(children: const [
              SizedBox(height: 240),
              Center(child: CircularProgressIndicator())
            ]);
          }
          if (snapshot.hasError) {
            return ListView(children: [
              const SizedBox(height: 160),
              const Icon(Icons.cloud_off, size: 64),
              Center(
                  child:
                      Text(widget.session.api.errorMessage(snapshot.error!))),
              Center(
                  child: FilledButton.tonal(
                      onPressed: refresh, child: Text(strings.retry))),
            ]);
          }
          final data = snapshot.data!;
          final progress =
              (data['daily_completion_percentage'] as num).toDouble();
          final deviceStatus = data['device_status'].toString();
          final alerts = data['active_emergencies'] as int;
          final careProfile = data['care_profile'] as Map<String, dynamic>;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 22),
            children: [
              _PatientSummaryCard(
                patientName: widget.session.currentPatient!.displayName,
                deviceStatus: deviceStatus,
                careProfile: careProfile,
                onEdit: () => _editCareProfile(careProfile),
              ),
              const SizedBox(height: 12),
              _CareProfileCard(
                profile: careProfile,
                onAddContact: _addEmergencyContact,
                onDeleteContact: _deleteEmergencyContact,
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.fromLTRB(16, 13, 16, 14),
                decoration: BoxDecoration(
                  gradient: RafeeqGradients.primary,
                  borderRadius: BorderRadius.circular(23),
                  boxShadow: [
                    BoxShadow(
                      color: RafeeqColors.primary.withValues(alpha: 0.34),
                      blurRadius: 26,
                      offset: const Offset(0, 14),
                    ),
                    BoxShadow(
                      color: Colors.white.withValues(alpha: 0.18),
                      blurRadius: 12,
                      offset: const Offset(-4, -5),
                    ),
                  ],
                ),
                child: Column(children: [
                  Row(children: [
                    RafeeqRobot(
                      semanticLabel: strings.robotSemanticLabel,
                      size: 70,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${strings.robotStatus} · ${localizedStatus(strings, deviceStatus)}',
                            style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 10,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            strings.talkingNow,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 17,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          const SizedBox(height: 5),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 9,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              strings.showingFamilyPhotos,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 9,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ]),
                  const SizedBox(height: 16),
                  Row(children: [
                    Expanded(
                      child: _QuickAction(
                        icon: Icons.medication_outlined,
                        label: strings.medication,
                        onTap: widget.onOpenRoutine,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _QuickAction(
                        icon: Icons.chat_bubble_outline_rounded,
                        label: strings.conversation,
                        onTap: widget.onOpenActivities,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _QuickAction(
                        icon: Icons.mic_none_rounded,
                        label: strings.poetry,
                        onTap: widget.onOpenActivities,
                      ),
                    ),
                  ]),
                ]),
              ),
              const SizedBox(height: 12),
              RafeeqGlowCard(
                onTap: widget.onOpenCamera,
                padding: const EdgeInsets.symmetric(
                  horizontal: 15,
                  vertical: 13,
                ),
                child: Row(children: [
                  Stack(clipBehavior: Clip.none, children: [
                    const CircleAvatar(
                      radius: 26,
                      backgroundColor: RafeeqColors.lavender,
                      child: Icon(
                        Icons.videocam_outlined,
                        color: RafeeqColors.primary,
                      ),
                    ),
                    PositionedDirectional(
                      top: -7,
                      end: -9,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: RafeeqColors.danger,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          strings.live,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 8,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                    ),
                  ]),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.liveRoomTitle,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          strings.liveRoomSubtitle,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right_rounded,
                    color: RafeeqColors.muted,
                  ),
                ]),
              ),
              const SizedBox(height: 12),
              RafeeqGlowCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(strings.dailyProgress,
                                style: Theme.of(context).textTheme.titleMedium),
                            Text('${progress.round()}%'),
                          ]),
                      const SizedBox(height: 12),
                      LinearProgressIndicator(
                          value: progress / 100,
                          minHeight: 10,
                          borderRadius: BorderRadius.circular(8)),
                    ]),
              ),
              const SizedBox(height: 12),
              _MedicationSummaryCard(
                data: data,
                onTap: widget.onOpenRoutine,
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: _DashboardTile(
                    icon: Icons.insights_outlined,
                    title: strings.reports,
                    subtitle: strings.dailyProgress,
                    onTap: widget.onOpenReports,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _DashboardTile(
                    icon: Icons.medical_services_outlined,
                    title: strings.doctorFollowUp,
                    subtitle: strings.doctorFollowUpSubtitle,
                    onTap: widget.onOpenDoctor,
                  ),
                ),
              ]),
              const SizedBox(height: 12),
              _DashboardActionCard(
                icon: Icons.send_outlined,
                iconColor: RafeeqColors.primary,
                title: strings.reportsSentToDoctor,
                subtitle: strings.browseReports,
                onTap: widget.onOpenSentReports,
              ),
              const SizedBox(height: 12),
              _DashboardActionCard(
                icon: alerts > 0
                    ? Icons.warning_amber_rounded
                    : Icons.verified_user_outlined,
                iconColor:
                    alerts > 0 ? RafeeqColors.danger : RafeeqColors.success,
                title: strings.latestAlert,
                subtitle: alerts > 0 ? '$alerts' : strings.noActiveEmergency,
                onTap: widget.onOpenEmergencies,
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _editCareProfile(Map<String, dynamic> profile) async {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final relationship = TextEditingController(
        text: profile['relationship_label']?.toString() ?? '');
    final likes =
        TextEditingController(text: profile['likes']?.toString() ?? '');
    final dislikes =
        TextEditingController(text: profile['dislikes']?.toString() ?? '');
    final stage =
        TextEditingController(text: profile['disease_stage']?.toString() ?? '');
    final description = TextEditingController(
        text: profile['care_description']?.toString() ?? '');
    final condition = TextEditingController(
        text: profile['condition_notes']?.toString() ?? '');
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(isArabic ? 'معلومات الرعاية' : 'Care information'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                controller: relationship,
                decoration: InputDecoration(
                  labelText: isArabic
                      ? 'وش علاقتك مع المريض؟'
                      : 'Relationship to patient',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: stage,
                decoration: InputDecoration(
                  labelText: isArabic ? 'درجة/مرحلة الحالة' : 'Condition stage',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: likes,
                decoration: InputDecoration(
                  labelText: isArabic ? 'وش يحب؟' : 'What do they like?',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: dislikes,
                decoration: InputDecoration(
                  labelText: isArabic ? 'وش ما يحب؟' : 'What do they dislike?',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: description,
                maxLines: 2,
                decoration: InputDecoration(
                  labelText: isArabic
                      ? 'وصف مختصر تحت الاسم'
                      : 'Short description under the name',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: condition,
                maxLines: 2,
                decoration: InputDecoration(
                  labelText: isArabic
                      ? 'ملاحظات الحالة للطبيب والعائلة'
                      : 'Care notes',
                ),
              ),
            ]),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AppLocalizations.of(context)!.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AppLocalizations.of(context)!.save),
          ),
        ],
      ),
    );
    if (accepted != true) return;
    try {
      await widget.session.api.dio.patch(
        '/patients/${widget.session.currentPatient!.id}/care-profile',
        data: {
          'relationship_label': relationship.text.trim(),
          'likes': likes.text.trim(),
          'dislikes': dislikes.text.trim(),
          'disease_stage': stage.text.trim(),
          'care_description': description.text.trim(),
          'condition_notes': condition.text.trim(),
        },
      );
      refresh();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _addEmergencyContact() async {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final name = TextEditingController();
    final relationship = TextEditingController();
    final phone = TextEditingController();
    final email = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(isArabic
            ? 'إضافة ولي أمر أو مسؤول'
            : 'Add guardian or responsible person'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                controller: name,
                decoration:
                    InputDecoration(labelText: isArabic ? 'الاسم' : 'Name'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: relationship,
                decoration: InputDecoration(
                  labelText: isArabic ? 'وش علاقته مع المريض؟' : 'Relationship',
                  hintText: isArabic
                      ? 'مثال: ولي أمر، بنت، أخ، حفيد، جار'
                      : 'Guardian, daughter, brother, neighbor',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: phone,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  labelText: isArabic ? 'الجوال اختياري' : 'Phone optional',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: email,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                    labelText: isArabic ? 'البريد اختياري' : 'Email optional'),
              ),
              const SizedBox(height: 10),
              Text(
                isArabic
                    ? 'سيظهر هذا الشخص للدكتور كمسؤول للتواصل، وضمن قائمة تنبيهات الخطر.'
                    : 'This person appears to the doctor as a contact and in danger alerts.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ]),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AppLocalizations.of(context)!.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AppLocalizations.of(context)!.save),
          ),
        ],
      ),
    );
    if (accepted != true ||
        name.text.trim().isEmpty ||
        relationship.text.trim().isEmpty) {
      return;
    }
    try {
      await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/emergency-contacts',
        data: {
          'name': name.text.trim(),
          'relationship': relationship.text.trim(),
          if (phone.text.trim().isNotEmpty) 'phone': phone.text.trim(),
          if (email.text.trim().isNotEmpty) 'email': email.text.trim(),
        },
      );
      refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content:
                Text(isArabic ? 'تمت إضافة الشخص للقائمة' : 'Person added'),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _deleteEmergencyContact(Map<String, dynamic> recipient) async {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    if (recipient['source'] != 'emergency_contact' || recipient['id'] == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(isArabic
            ? 'حسابات العائلة المرتبطة لا تُحذف من هنا'
            : 'Linked family accounts cannot be removed here'),
      ));
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.person_remove_alt_1_outlined,
            color: RafeeqColors.danger),
        title: Text(isArabic ? 'حذف من قائمة التنبيه؟' : 'Remove from alerts?'),
        content: Text(recipient['name']?.toString() ?? ''),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AppLocalizations.of(context)!.cancel),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: RafeeqColors.danger),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(isArabic ? 'حذف' : 'Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.session.api.dio
          .delete('/emergency-contacts/${recipient['id']}');
      refresh();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }
}

class _DashboardActionCard extends StatelessWidget {
  const _DashboardActionCard({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        onTap: onTap,
        padding: EdgeInsets.zero,
        glowColor: iconColor,
        child: ListTile(
          contentPadding: const EdgeInsetsDirectional.fromSTEB(14, 9, 10, 9),
          leading: CircleAvatar(
            radius: 23,
            backgroundColor: iconColor.withValues(alpha: 0.11),
            child: Icon(icon, color: iconColor),
          ),
          title: Text(title),
          subtitle: Text(
            subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          trailing: Icon(
            Directionality.of(context) == TextDirection.rtl
                ? Icons.chevron_left_rounded
                : Icons.chevron_right_rounded,
            color: RafeeqColors.muted,
          ),
        ),
      );
}

class _MedicationSummaryCard extends StatelessWidget {
  const _MedicationSummaryCard({
    required this.data,
    required this.onTap,
  });

  final Map<String, dynamic> data;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final total = _asInt(data['medication_total']);
    final completed = _asInt(data['medication_completed']).clamp(0, total);
    final pending = _asInt(data['medication_pending'] ?? (total - completed))
        .clamp(0, total);
    final progress = total == 0 ? 0.0 : completed / total;
    final complete = total > 0 && completed >= total;
    final statusColor = total == 0
        ? RafeeqColors.muted
        : complete
            ? RafeeqColors.success
            : RafeeqColors.danger;
    final headline = total == 0
        ? (isArabic ? 'لا توجد جرعات اليوم' : 'No doses today')
        : complete
            ? (isArabic ? 'كل الجرعات مكتملة' : 'All doses completed')
            : isArabic
                ? 'المتبقي ${_arabicDoseCount(pending)}'
                : '$pending dose${pending == 1 ? '' : 's'} remaining';
    final detail = total == 0
        ? (isArabic
            ? 'اضغط لإضافة تذكير دواء'
            : 'Tap to add a medication reminder')
        : isArabic
            ? 'تم أخذ ${_arabicDoseCount(completed)} من ${_arabicDoseCount(total)}'
            : '$completed of $total taken today';

    return RafeeqGlowCard(
      onTap: onTap,
      glowColor: statusColor,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            CircleAvatar(
              radius: 25,
              backgroundColor: statusColor.withValues(alpha: 0.12),
              child: Icon(
                complete
                    ? Icons.check_circle_outline_rounded
                    : Icons.medication_outlined,
                color: statusColor,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    strings.todayMedication,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    headline,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: statusColor,
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                ],
              ),
            ),
            Icon(
              Directionality.of(context) == TextDirection.rtl
                  ? Icons.chevron_left_rounded
                  : Icons.chevron_right_rounded,
              color: RafeeqColors.muted,
            ),
          ]),
          const SizedBox(height: 12),
          Text(detail, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 9),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              backgroundColor: RafeeqColors.lavender,
              valueColor: AlwaysStoppedAnimation<Color>(statusColor),
            ),
          ),
        ],
      ),
    );
  }

  static int _asInt(Object? value) => value is num ? value.toInt() : 0;

  static String _arabicDoseCount(int count) {
    if (count <= 0) return '0';
    if (count == 1) return 'جرعة واحدة';
    if (count == 2) return 'جرعتين';
    return '$count جرعات';
  }
}

class _PatientSummaryCard extends StatefulWidget {
  const _PatientSummaryCard({
    required this.patientName,
    required this.deviceStatus,
    required this.careProfile,
    required this.onEdit,
  });

  final String patientName;
  final String deviceStatus;
  final Map<String, dynamic> careProfile;
  final VoidCallback onEdit;

  @override
  State<_PatientSummaryCard> createState() => _PatientSummaryCardState();
}

class _PatientSummaryCardState extends State<_PatientSummaryCard> {
  bool expanded = false;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final summary = _summaryLine(context, widget.careProfile);
    final items = <({IconData icon, String label, String? value})>[
      (
        icon: Icons.favorite_outline_rounded,
        label: isArabic ? 'علاقتك' : 'Relationship',
        value: widget.careProfile['relationship_label']?.toString(),
      ),
      (
        icon: Icons.monitor_heart_outlined,
        label: isArabic ? 'درجة الحالة' : 'Condition stage',
        value: widget.careProfile['disease_stage']?.toString(),
      ),
      (
        icon: Icons.thumb_up_alt_outlined,
        label: isArabic ? 'يحب' : 'Likes',
        value: widget.careProfile['likes']?.toString(),
      ),
      (
        icon: Icons.block_outlined,
        label: isArabic ? 'ما يحب' : 'Dislikes',
        value: widget.careProfile['dislikes']?.toString(),
      ),
      (
        icon: Icons.notes_outlined,
        label: isArabic ? 'وصف مختصر' : 'Description',
        value: widget.careProfile['care_description']?.toString(),
      ),
    ];
    final visibleItems = items
        .where((item) => item.value != null && item.value!.trim().isNotEmpty)
        .toList();

    return RafeeqGlowCard(
      hero: true,
      padding: const EdgeInsets.fromLTRB(16, 13, 12, 13),
      child: Column(children: [
        Row(children: [
          CircleAvatar(
            radius: 27,
            backgroundColor: RafeeqColors.lavender,
            child: Text(
              widget.patientName.characters.first,
              style: const TextStyle(
                color: RafeeqColors.primary,
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.patientName,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Row(children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: widget.deviceStatus == 'online'
                          ? RafeeqColors.success
                          : RafeeqColors.muted,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      localizedStatus(strings, widget.deviceStatus),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ]),
                const SizedBox(height: 3),
                Text(
                  summary,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: expanded
                ? (isArabic ? 'إخفاء المعلومات' : 'Hide info')
                : (isArabic ? 'عرض المعلومات' : 'Show info'),
            onPressed: () => setState(() => expanded = !expanded),
            icon: Icon(
              expanded
                  ? Icons.keyboard_arrow_up_rounded
                  : Icons.keyboard_arrow_down_rounded,
              color: RafeeqColors.primary,
            ),
          ),
        ]),
        AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
          child: expanded
              ? Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: RafeeqColors.lavenderSoft,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: RafeeqColors.outline),
                    ),
                    child: visibleItems.isEmpty
                        ? Row(children: [
                            Expanded(
                              child: Text(
                                isArabic
                                    ? 'أضف الأشياء التي يحبها ومعلومات الحالة هنا.'
                                    : 'Add preferences and care information here.',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                            TextButton.icon(
                              onPressed: widget.onEdit,
                              icon: const Icon(Icons.edit_outlined, size: 18),
                              label: Text(isArabic ? 'إضافة' : 'Add'),
                            ),
                          ])
                        : Column(children: [
                            ...visibleItems.map((item) => Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Icon(item.icon,
                                          color: RafeeqColors.primary,
                                          size: 18),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: Text.rich(TextSpan(children: [
                                          TextSpan(
                                            text: '${item.label}: ',
                                            style: const TextStyle(
                                                fontWeight: FontWeight.w900),
                                          ),
                                          TextSpan(text: item.value),
                                        ])),
                                      ),
                                    ],
                                  ),
                                )),
                            Align(
                              alignment: AlignmentDirectional.centerEnd,
                              child: TextButton.icon(
                                onPressed: widget.onEdit,
                                icon: const Icon(Icons.edit_outlined, size: 18),
                                label: Text(isArabic ? 'تعديل' : 'Edit'),
                              ),
                            ),
                          ]),
                  ),
                )
              : const SizedBox.shrink(),
        ),
      ]),
    );
  }

  static String _summaryLine(
      BuildContext context, Map<String, dynamic> profile) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final stage = profile['disease_stage']?.toString();
    final likes = profile['likes']?.toString();
    final description = profile['care_description']?.toString();
    final parts = [
      if (stage != null && stage.trim().isNotEmpty)
        isArabic ? 'الحالة: $stage' : 'Stage: $stage',
      if (likes != null && likes.trim().isNotEmpty)
        isArabic ? 'يحب: $likes' : 'Likes: $likes',
      if (description != null && description.trim().isNotEmpty) description,
    ];
    return parts.isEmpty
        ? (isArabic
            ? 'أضف التفضيلات ومعلومات الحالة'
            : 'Add preferences and care status')
        : parts.join(' · ');
  }
}

class _CareProfileCard extends StatefulWidget {
  const _CareProfileCard({
    required this.profile,
    required this.onAddContact,
    required this.onDeleteContact,
  });

  final Map<String, dynamic> profile;
  final VoidCallback onAddContact;
  final void Function(Map<String, dynamic> recipient) onDeleteContact;

  @override
  State<_CareProfileCard> createState() => _CareProfileCardState();
}

class _CareProfileCardState extends State<_CareProfileCard> {
  bool expanded = false;

  @override
  Widget build(BuildContext context) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final recipients = (widget.profile['alert_recipients'] as List? ?? const [])
        .cast<dynamic>();
    return RafeeqGlowCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const CircleAvatar(
            radius: 22,
            backgroundColor: RafeeqColors.lavender,
            child: Icon(Icons.family_restroom_rounded,
                color: RafeeqColors.primary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                isArabic ? 'ولي الأمر والمسؤولون' : 'Guardians and contacts',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 2),
              Text(
                isArabic
                    ? 'أشخاص يقدر الدكتور يتواصل معهم ويصلهم التنبيه عند الخطر'
                    : 'People doctors can contact and notify during danger',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ]),
          ),
        ]),
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            color: RafeeqColors.lavenderSoft,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: RafeeqColors.outline),
          ),
          child: Column(children: [
            InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: () => setState(() => expanded = !expanded),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Row(children: [
                  Icon(
                    expanded
                        ? Icons.keyboard_arrow_up_rounded
                        : Icons.keyboard_arrow_down_rounded,
                    color: RafeeqColors.primary,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      isArabic ? 'قائمة المسؤولين' : 'Contact list',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      '${recipients.length}',
                      style: const TextStyle(
                        color: RafeeqColors.primary,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  IconButton.filledTonal(
                    onPressed: widget.onAddContact,
                    tooltip: isArabic ? 'إضافة' : 'Add',
                    icon: const Icon(Icons.person_add_alt_1_rounded, size: 18),
                  ),
                ]),
              ),
            ),
            AnimatedSize(
              duration: const Duration(milliseconds: 220),
              curve: Curves.easeOut,
              child: expanded
                  ? Padding(
                      padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                      child: recipients.isEmpty
                          ? Align(
                              alignment: AlignmentDirectional.centerStart,
                              child: Text(
                                isArabic
                                    ? 'أضف ولي أمر أو شخص مسؤول عن المريض هنا.'
                                    : 'Add a guardian or responsible contact here.',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            )
                          : Column(
                              children: recipients.take(8).map((item) {
                                final recipient =
                                    Map<String, dynamic>.from(item as Map);
                                final removable =
                                    recipient['source'] == 'emergency_contact';
                                final relationship =
                                    recipient['relationship']?.toString() ?? '';
                                final phone =
                                    recipient['phone']?.toString() ?? '';
                                final email =
                                    recipient['email']?.toString() ?? '';
                                final details = [
                                  if (relationship.isNotEmpty) relationship,
                                  if (phone.isNotEmpty) phone,
                                  if (email.isNotEmpty) email,
                                ].join(' • ');
                                return Container(
                                  margin: const EdgeInsets.only(top: 8),
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 10, vertical: 8),
                                  decoration: BoxDecoration(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(15),
                                  ),
                                  child: Row(children: [
                                    const Icon(Icons.person_outline_rounded,
                                        color: RafeeqColors.primary, size: 19),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            recipient['name']?.toString() ?? '',
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(
                                                fontWeight: FontWeight.w800),
                                          ),
                                          if (details.isNotEmpty) ...[
                                            const SizedBox(height: 2),
                                            Text(
                                              details,
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .bodySmall,
                                            ),
                                          ],
                                        ],
                                      ),
                                    ),
                                    if (removable)
                                      IconButton(
                                        tooltip: isArabic ? 'حذف' : 'Delete',
                                        visualDensity: VisualDensity.compact,
                                        onPressed: () =>
                                            widget.onDeleteContact(recipient),
                                        icon: const Icon(
                                            Icons.delete_outline_rounded,
                                            color: RafeeqColors.danger,
                                            size: 20),
                                      )
                                    else
                                      Icon(
                                        Icons.lock_outline_rounded,
                                        color: RafeeqColors.muted
                                            .withValues(alpha: 0.65),
                                        size: 18,
                                      ),
                                  ]),
                                );
                              }).toList(),
                            ),
                    )
                  : const SizedBox.shrink(),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _DashboardTile extends StatelessWidget {
  const _DashboardTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        onTap: onTap,
        padding: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 13),
          child: Row(children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                gradient:
                    RafeeqGradients.softCardFor(Theme.of(context).brightness),
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: RafeeqColors.primary.withValues(alpha: 0.14),
                    blurRadius: 14,
                    offset: const Offset(0, 7),
                  ),
                ],
              ),
              child: Icon(icon, color: RafeeqColors.primary, size: 21),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ]),
        ),
      );
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(18),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
            child: Column(children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.18),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.22),
                  ),
                ),
                child: Icon(icon, color: Colors.white, size: 20),
              ),
              const SizedBox(height: 5),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ]),
          ),
        ),
      );
}

class RoutineTab extends StatefulWidget {
  const RoutineTab({
    required this.session,
    required this.onRoutineChanged,
    super.key,
  });

  final AppSession session;
  final VoidCallback onRoutineChanged;

  @override
  State<RoutineTab> createState() => _RoutineTabState();
}

class _RoutineTabState extends State<RoutineTab> {
  late Future<List<Map<String, dynamic>>> future;

  @override
  void initState() {
    super.initState();
    future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final patientId = widget.session.currentPatient!.id;
    final routines = await widget.session.api.dio
        .get<Map<String, dynamic>>('/patients/$patientId/routines');
    final occurrences = await widget.session.api.dio
        .get<Map<String, dynamic>>('/patients/$patientId/routine-occurrences');
    final routineItems =
        (routines.data!['items'] as List).cast<Map<String, dynamic>>();
    final occurrenceItems =
        (occurrences.data!['items'] as List).cast<Map<String, dynamic>>();
    return routineItems.map((routine) {
      final occurrence = occurrenceItems
          .where((item) => item['routine_id'] == routine['id'])
          .firstOrNull;
      return {...routine, 'occurrence': occurrence};
    }).toList();
  }

  void refresh() => setState(() => future = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _ErrorState(
                message: widget.session.api.errorMessage(snapshot.error!),
                retry: refresh);
          }
          final items = snapshot.data!;
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 124),
            itemCount: items.length + 2,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              if (index == 0) {
                return RafeeqGlowCard(
                  padding: EdgeInsets.zero,
                  child: ListTile(
                    leading: const Icon(Icons.chevron_left_rounded),
                    title: Text(
                      MaterialLocalizations.of(context)
                          .formatFullDate(DateTime.now()),
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontWeight: FontWeight.w900),
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                  ),
                );
              }
              if (index == 1) {
                return FilledButton.icon(
                  onPressed: _addRoutine,
                  icon: const Icon(Icons.add_rounded),
                  label: Text(_copy(context, 'إضافة للروتين', 'Add routine')),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                  ),
                );
              }
              if (items.isEmpty) {
                return Padding(
                  padding: const EdgeInsets.only(top: 28),
                  child: Center(child: Text(strings.noData)),
                );
              }
              final item = items[index - 2];
              final occurrence = item['occurrence'] as Map<String, dynamic>?;
              final complete = occurrence?['status'] == 'completed';
              return RafeeqGlowCard(
                padding: EdgeInsets.zero,
                glowColor:
                    complete ? RafeeqColors.success : RafeeqColors.primary,
                child: ListTile(
                  contentPadding:
                      const EdgeInsetsDirectional.fromSTEB(12, 7, 10, 7),
                  leading: Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      gradient: complete
                          ? const LinearGradient(
                              colors: [Color(0xFFE1F7EC), Colors.white],
                            )
                          : RafeeqGradients.softCardFor(
                              Theme.of(context).brightness,
                            ),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: (complete
                                  ? RafeeqColors.success
                                  : RafeeqColors.primary)
                              .withValues(alpha: 0.16),
                          blurRadius: 14,
                          offset: const Offset(0, 7),
                        ),
                      ],
                    ),
                    child: Icon(
                      item['type'] == 'medication'
                          ? Icons.medication_outlined
                          : Icons.event_note_outlined,
                      color: complete
                          ? RafeeqColors.success
                          : RafeeqColors.primary,
                    ),
                  ),
                  title: Text(item['title'].toString()),
                  subtitle: Text(
                      '${localizedClockTime(context, item['scheduled_local_time'])} • '
                      '${localizedStatus(strings, occurrence?['status'] ?? 'pending')}'),
                  trailing: Wrap(
                    spacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      if (complete)
                        IconButton(
                          tooltip:
                              _copy(context, 'إزالة علامة تم', 'Mark not done'),
                          onPressed: occurrence == null
                              ? null
                              : () =>
                                  _undoComplete(occurrence['id'].toString()),
                          icon: const Icon(Icons.check_circle_outline_rounded,
                              color: RafeeqColors.success, size: 29),
                        )
                      else if (occurrence == null)
                        const Icon(Icons.circle_outlined,
                            color: RafeeqColors.outline, size: 29)
                      else
                        FilledButton.tonal(
                          onPressed: () =>
                              _complete(occurrence['id'].toString()),
                          child: Text(strings.complete),
                        ),
                      PopupMenuButton<String>(
                        tooltip: _copy(context, 'خيارات', 'Options'),
                        onSelected: (value) {
                          if (value == 'edit') {
                            _editRoutine(item);
                          } else if (value == 'delete') {
                            _deleteRoutine(item);
                          }
                        },
                        itemBuilder: (context) => [
                          PopupMenuItem(
                            value: 'edit',
                            child: ListTile(
                              leading: const Icon(Icons.edit_outlined),
                              title: Text(_copy(context, 'تعديل', 'Edit')),
                            ),
                          ),
                          PopupMenuItem(
                            value: 'delete',
                            child: ListTile(
                              leading: const Icon(Icons.delete_outline,
                                  color: RafeeqColors.danger),
                              title: Text(
                                _copy(context, 'حذف', 'Delete'),
                                style:
                                    const TextStyle(color: RafeeqColors.danger),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Future<void> _complete(String occurrenceId) async {
    try {
      await widget.session.api.dio.post(
          '/routine-occurrences/$occurrenceId/complete',
          data: {'confirmation_source': 'caregiver'});
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _undoComplete(String occurrenceId) async {
    try {
      await widget.session.api.dio
          .post('/routine-occurrences/$occurrenceId/undo-complete');
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _editRoutine(Map<String, dynamic> item) async {
    final isMedication = item['type'] == 'medication';
    final title = TextEditingController(text: item['title']?.toString() ?? '');
    final description =
        TextEditingController(text: item['description']?.toString() ?? '');
    final medication = item['medication'] is Map
        ? Map<String, dynamic>.from(item['medication'] as Map)
        : <String, dynamic>{};
    final dosage = TextEditingController(
      text: medication['dosage_text']?.toString() ?? '',
    );
    var selectedTime = _timeFromApi(item['scheduled_local_time']?.toString()) ??
        TimeOfDay.now();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) =>
          StatefulBuilder(builder: (context, setDialogState) {
        final strings = AppLocalizations.of(context)!;
        return AlertDialog(
          title: Text(_copy(context, 'تعديل الروتين', 'Edit routine')),
          content: SizedBox(
            width: 420,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                controller: title,
                decoration: InputDecoration(
                  labelText: isMedication
                      ? strings.medicationName
                      : _copy(context, 'العنوان', 'Title'),
                ),
              ),
              const SizedBox(height: 12),
              if (isMedication) ...[
                TextField(
                  controller: dosage,
                  decoration: InputDecoration(labelText: strings.dosage),
                ),
                const SizedBox(height: 12),
              ] else ...[
                TextField(
                  controller: description,
                  decoration: InputDecoration(
                    labelText:
                        _copy(context, 'ملاحظة اختيارية', 'Optional note'),
                  ),
                ),
                const SizedBox(height: 12),
              ],
              ListTile(
                leading: const Icon(Icons.schedule),
                title: Text(strings.time),
                subtitle: Text(selectedTime.format(context)),
                onTap: () async {
                  final value = await showTimePicker(
                    context: context,
                    initialTime: selectedTime,
                  );
                  if (value != null) setDialogState(() => selectedTime = value);
                },
              ),
            ]),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: Text(strings.cancel),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(strings.save),
            ),
          ],
        );
      }),
    );
    if (accepted != true || title.text.trim().isEmpty) return;
    if (isMedication && dosage.text.trim().isEmpty) return;
    final time =
        '${selectedTime.hour.toString().padLeft(2, '0')}:${selectedTime.minute.toString().padLeft(2, '0')}:00';
    try {
      await widget.session.api.dio.patch(
        '/routines/${item['id']}',
        data: {
          'title': title.text.trim(),
          'description':
              description.text.trim().isEmpty ? null : description.text.trim(),
          'scheduled_local_time': time,
          if (isMedication)
            'medication': {
              'medication_name': title.text.trim(),
              'dosage_text': dosage.text.trim(),
            },
        },
      );
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _deleteRoutine(Map<String, dynamic> item) async {
    final strings = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.delete_outline, color: RafeeqColors.danger),
        title: Text(_copy(context, 'حذف من الروتين؟', 'Delete routine?')),
        content: Text(
          _copy(
            context,
            'سيتم حذف "${item['title']}" وإلغاء التذكيرات القادمة له.',
            'This will delete "${item['title']}" and cancel upcoming reminders.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(strings.cancel),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: RafeeqColors.danger),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(_copy(context, 'حذف', 'Delete')),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.session.api.dio.delete('/routines/${item['id']}');
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _addRoutine() async {
    final type = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _copy(
                    context, 'ماذا تريد أن تضيف؟', 'What do you want to add?'),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 14),
              _RoutineChoiceTile(
                icon: Icons.medication_outlined,
                title: _copy(context, 'تذكير دواء', 'Medicine reminder'),
                subtitle: _copy(
                  context,
                  'اسم الدواء، الجرعة، ووقت التذكير',
                  'Medicine name, dose, and reminder time',
                ),
                onTap: () => Navigator.pop(sheetContext, 'medication'),
              ),
              const SizedBox(height: 10),
              _RoutineChoiceTile(
                icon: Icons.event_note_outlined,
                title: _copy(context, 'موعد أو مهمة', 'Appointment or task'),
                subtitle: _copy(
                  context,
                  'موعد، غداء، زيارة، قراءة، أو أي شيء تريد تذكيره به',
                  'Appointment, meal, visit, reading, or any reminder',
                ),
                onTap: () => Navigator.pop(sheetContext, 'task'),
              ),
            ],
          ),
        ),
      ),
    );
    if (type == 'medication') {
      await _addMedicationReminder();
    } else if (type == 'task') {
      await _addTaskRoutine();
    }
  }

  Future<void> _addMedicationReminder() async {
    final name = TextEditingController();
    final dosage = TextEditingController();
    var selectedTime = TimeOfDay.now();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) =>
          StatefulBuilder(builder: (context, setDialogState) {
        final strings = AppLocalizations.of(context)!;
        return AlertDialog(
          title: Text(strings.addReminder),
          content: SizedBox(
            width: 420,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                  controller: name,
                  decoration:
                      InputDecoration(labelText: strings.medicationName)),
              const SizedBox(height: 12),
              TextField(
                  controller: dosage,
                  decoration: InputDecoration(labelText: strings.dosage)),
              const SizedBox(height: 12),
              ListTile(
                leading: const Icon(Icons.schedule),
                title: Text(strings.time),
                subtitle: Text(selectedTime.format(context)),
                onTap: () async {
                  final value = await showTimePicker(
                      context: context, initialTime: selectedTime);
                  if (value != null) setDialogState(() => selectedTime = value);
                },
              ),
            ]),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: Text(strings.cancel)),
            FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: Text(strings.save)),
          ],
        );
      }),
    );
    if (accepted != true ||
        name.text.trim().isEmpty ||
        dosage.text.trim().isEmpty) {
      return;
    }
    final now = DateTime.now();
    final date =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    final time =
        '${selectedTime.hour.toString().padLeft(2, '0')}:${selectedTime.minute.toString().padLeft(2, '0')}:00';
    try {
      await widget.session.api.dio.post(
          '/patients/${widget.session.currentPatient!.id}/routines',
          data: {
            'type': 'medication',
            'title': name.text.trim(),
            'start_date': date,
            'scheduled_local_time': time,
            'timezone': widget.session.currentPatient!.timezone,
            'medication': {
              'medication_name': name.text.trim(),
              'dosage_text': dosage.text.trim()
            },
          });
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  Future<void> _addTaskRoutine() async {
    final title = TextEditingController();
    final description = TextEditingController();
    var selectedTime = TimeOfDay.now();
    var selectedType = 'appointment';
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) =>
          StatefulBuilder(builder: (context, setDialogState) {
        final strings = AppLocalizations.of(context)!;
        return AlertDialog(
          title: Text(
              _copy(context, 'إضافة موعد أو مهمة', 'Add appointment or task')),
          content: SizedBox(
            width: 420,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              SegmentedButton<String>(
                segments: [
                  ButtonSegment(
                    value: 'appointment',
                    icon: const Icon(Icons.event_note_outlined),
                    label: Text(_copy(context, 'موعد', 'Appointment')),
                  ),
                  ButtonSegment(
                    value: 'custom',
                    icon: const Icon(Icons.task_alt_outlined),
                    label: Text(_copy(context, 'مهمة', 'Task')),
                  ),
                ],
                selected: {selectedType},
                showSelectedIcon: false,
                onSelectionChanged: (value) =>
                    setDialogState(() => selectedType = value.first),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: title,
                decoration: InputDecoration(
                  labelText: _copy(context, 'العنوان', 'Title'),
                  hintText: _copy(
                    context,
                    'مثال: موعد لقاء مع أحفادي',
                    'Example: Meeting with my grandchildren',
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: description,
                decoration: InputDecoration(
                  labelText: _copy(context, 'ملاحظة اختيارية', 'Optional note'),
                ),
              ),
              const SizedBox(height: 12),
              ListTile(
                leading: const Icon(Icons.schedule),
                title: Text(strings.time),
                subtitle: Text(selectedTime.format(context)),
                onTap: () async {
                  final value = await showTimePicker(
                    context: context,
                    initialTime: selectedTime,
                  );
                  if (value != null) setDialogState(() => selectedTime = value);
                },
              ),
            ]),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: Text(strings.cancel),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(strings.save),
            ),
          ],
        );
      }),
    );
    if (accepted != true || title.text.trim().isEmpty) {
      return;
    }
    await _createRoutine(
      type: selectedType,
      title: title.text.trim(),
      description:
          description.text.trim().isEmpty ? null : description.text.trim(),
      selectedTime: selectedTime,
    );
  }

  Future<void> _createRoutine({
    required String type,
    required String title,
    required TimeOfDay selectedTime,
    String? description,
    Map<String, dynamic>? medication,
  }) async {
    final now = DateTime.now();
    final date =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    final time =
        '${selectedTime.hour.toString().padLeft(2, '0')}:${selectedTime.minute.toString().padLeft(2, '0')}:00';
    try {
      await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/routines',
        data: {
          'type': type,
          'title': title,
          if (description != null) 'description': description,
          'start_date': date,
          'scheduled_local_time': time,
          'timezone': widget.session.currentPatient!.timezone,
          if (medication != null) 'medication': medication,
        },
      );
      refresh();
      widget.onRoutineChanged();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }

  static String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;

  static TimeOfDay? _timeFromApi(String? value) {
    if (value == null || value.isEmpty) return null;
    final parts = value.split(':');
    if (parts.length < 2) return null;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null || minute == null) return null;
    return TimeOfDay(hour: hour, minute: minute);
  }
}

class _RoutineChoiceTile extends StatelessWidget {
  const _RoutineChoiceTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        onTap: onTap,
        padding: const EdgeInsets.all(14),
        child: Row(children: [
          CircleAvatar(
            radius: 24,
            backgroundColor: RafeeqColors.lavender,
            child: Icon(icon, color: RafeeqColors.primary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 3),
                Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          Icon(
            Directionality.of(context) == TextDirection.rtl
                ? Icons.chevron_left_rounded
                : Icons.chevron_right_rounded,
            color: RafeeqColors.muted,
          ),
        ]),
      );
}

class _EmergencyRecipientsSlide extends StatefulWidget {
  const _EmergencyRecipientsSlide({
    required this.recipients,
    this.initiallyExpanded = false,
  });

  final List<Map<String, dynamic>> recipients;
  final bool initiallyExpanded;

  @override
  State<_EmergencyRecipientsSlide> createState() =>
      _EmergencyRecipientsSlideState();
}

class _EmergencyRecipientsSlideState extends State<_EmergencyRecipientsSlide> {
  late bool expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final count = widget.recipients.length;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.76),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: RafeeqColors.outline),
      ),
      child: Column(children: [
        InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: () => setState(() => expanded = !expanded),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            child: Row(children: [
              Icon(
                expanded
                    ? Icons.keyboard_arrow_up_rounded
                    : Icons.keyboard_arrow_down_rounded,
                color: RafeeqColors.primary,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  isArabic ? 'الأشخاص الذين وصلهم التنبيه' : 'People notified',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: RafeeqColors.lavender,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '$count',
                  style: const TextStyle(
                    color: RafeeqColors.primary,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ]),
          ),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          child: expanded
              ? Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  child: count == 0
                      ? Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: Text(
                            isArabic
                                ? 'ما فيه أشخاص في قائمة التنبيه حالياً. أضفهم من الداشبورد.'
                                : 'No recipients yet. Add them from the dashboard.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        )
                      : Column(
                          children: widget.recipients.map((recipient) {
                            final name = recipient['name']?.toString() ?? '';
                            final relationship =
                                recipient['relationship']?.toString() ?? '';
                            final phone = recipient['phone']?.toString() ?? '';
                            final email = recipient['email']?.toString() ?? '';
                            final details = [
                              if (relationship.isNotEmpty) relationship,
                              if (phone.isNotEmpty) phone,
                              if (email.isNotEmpty) email,
                            ].join(' • ');
                            return Container(
                              margin: const EdgeInsets.only(top: 8),
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 8),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: Row(children: [
                                const Icon(
                                  Icons.notifications_active_outlined,
                                  color: RafeeqColors.danger,
                                  size: 19,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800),
                                      ),
                                      if (details.isNotEmpty)
                                        Text(
                                          details,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall,
                                        ),
                                    ],
                                  ),
                                ),
                              ]),
                            );
                          }).toList(),
                        ),
                )
              : const SizedBox.shrink(),
        ),
      ]),
    );
  }
}

class EmergencyTab extends StatefulWidget {
  const EmergencyTab({required this.session, super.key});
  final AppSession session;

  @override
  State<EmergencyTab> createState() => _EmergencyTabState();
}

class _EmergencyTabState extends State<EmergencyTab> {
  late Future<Map<String, dynamic>> future;
  WebSocketChannel? channel;
  StreamSubscription<dynamic>? channelSubscription;

  @override
  void initState() {
    super.initState();
    future = _load();
    _connectLiveUpdates();
  }

  void _connectLiveUpdates() {
    final token = widget.session.accessToken;
    if (token == null) return;
    const configured = String.fromEnvironment('WS_BASE_URL');
    final base = configured.isEmpty ? Uri.base : Uri.parse(configured);
    final secure = base.scheme == 'https' || base.scheme == 'wss';
    final uri = Uri(
      scheme: secure ? 'wss' : 'ws',
      host: base.host,
      port: configured.isNotEmpty ? base.port : (secure ? 8444 : 8000),
      path: '/ws/patients/${widget.session.currentPatient!.id}',
    );
    channel = WebSocketChannel.connect(uri);
    channel!.sink.add(jsonEncode({'type': 'authenticate', 'token': token}));
    channelSubscription = channel!.stream.listen((message) {
      try {
        final event = jsonDecode(message.toString()) as Map<String, dynamic>;
        if (event['type'] == 'emergency.updated' && mounted) refresh();
      } catch (_) {}
    }, onError: (_) {});
  }

  @override
  void dispose() {
    channelSubscription?.cancel();
    channel?.sink.close();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final patientId = widget.session.currentPatient!.id;
    final responses = await Future.wait<dynamic>([
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/$patientId/devices'),
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/$patientId/emergencies'),
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/$patientId/care-profile'),
    ]);
    final devices = responses[0] as dynamic;
    final emergencies = responses[1] as dynamic;
    final careProfile = responses[2] as dynamic;
    return {
      'devices': (devices.data!['items'] as List).cast<Map<String, dynamic>>(),
      'emergencies':
          (emergencies.data!['items'] as List).cast<Map<String, dynamic>>(),
      'recipients': (careProfile.data!['alert_recipients'] as List? ?? const [])
          .cast<dynamic>()
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList(),
    };
  }

  void refresh() => setState(() => future = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorState(
              message: widget.session.api.errorMessage(snapshot.error!),
              retry: refresh);
        }
        final devices =
            (snapshot.data!['devices'] as List).cast<Map<String, dynamic>>();
        final emergencies = (snapshot.data!['emergencies'] as List)
            .cast<Map<String, dynamic>>();
        final recipients =
            (snapshot.data!['recipients'] as List).cast<Map<String, dynamic>>();
        final activeEmergency = emergencies
            .where((item) =>
                item['status'] != 'resolved' && item['status'] != 'false_alarm')
            .firstOrNull;
        return RefreshIndicator(
          onRefresh: () async => refresh(),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (activeEmergency != null) ...[
                Container(
                  padding: const EdgeInsets.all(22),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFE7EA),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: const Color(0xFFFFA5B4)),
                  ),
                  child: Column(children: [
                    const Icon(Icons.warning_amber_rounded,
                        color: RafeeqColors.danger, size: 45),
                    const SizedBox(height: 8),
                    Text(
                      activeEmergency['type'] == 'sos'
                          ? strings.sosHelpRequest
                          : strings.fallDetected,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: RafeeqColors.danger,
                          ),
                    ),
                    const SizedBox(height: 6),
                    Text(widget.session.currentPatient!.displayName),
                    Text(
                      localizedDateTime(
                          context, activeEmergency['detected_at']),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 14),
                    _EmergencyRecipientsSlide(
                      recipients: recipients,
                      initiallyExpanded: true,
                    ),
                  ]),
                ),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => ScaffoldMessenger.of(context)
                          .showSnackBar(SnackBar(
                              content: Text(
                                  widget.session.currentPatient!.displayName))),
                      icon: const Icon(Icons.call_outlined),
                      label: Text(strings.call),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const CameraTestScreen(),
                        ),
                      ),
                      icon: const Icon(Icons.videocam_outlined),
                      label: Text(strings.live),
                    ),
                  ),
                ]),
                const SizedBox(height: 12),
              ],
              if (devices.isEmpty)
                RafeeqGlowCard(
                  child: Column(children: [
                    const Icon(Icons.smart_toy_outlined, size: 64),
                    const SizedBox(height: 12),
                    Text(strings.deviceNotPaired),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: _provisionSimulator,
                      icon: const Icon(Icons.link),
                      label: Text(strings.pairSimulator),
                    ),
                  ]),
                )
              else ...[
                RafeeqGlowCard(
                  padding: EdgeInsets.zero,
                  child: ListTile(
                    leading: const Icon(Icons.smart_toy, color: Colors.green),
                    title: Text(devices.first['display_name'].toString()),
                    subtitle: Text('${strings.status}: '
                        '${localizedStatus(strings, devices.first['status'])}'),
                    trailing: const Icon(Icons.cloud_done),
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.error),
                  onPressed: () =>
                      _confirmSimulatedSos(devices.first['id'].toString()),
                  icon: const Icon(Icons.sos),
                  label: Text(strings.simulateSos),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () =>
                      _simulateFall(devices.first['id'].toString()),
                  icon: const Icon(Icons.personal_injury_outlined),
                  label: Text(strings.simulateFall),
                ),
              ],
              const SizedBox(height: 20),
              Text(strings.emergencyHistory,
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              if (emergencies.isEmpty)
                RafeeqGlowCard(
                  child: Column(children: [
                    const Icon(Icons.health_and_safety_outlined, size: 56),
                    const SizedBox(height: 12),
                    Text(strings.noEmergencyHistory),
                  ]),
                )
              else
                ...emergencies
                    .map((emergency) => _emergencyCard(emergency, recipients)),
            ],
          ),
        );
      },
    );
  }

  Widget _emergencyCard(
    Map<String, dynamic> emergency,
    List<Map<String, dynamic>> recipients,
  ) {
    final strings = AppLocalizations.of(context)!;
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final status = emergency['status'].toString();
    final type = emergency['type'].toString();
    final active = status != 'resolved' && status != 'false_alarm';
    final recipientNames = recipients
        .map((item) => item['name']?.toString() ?? '')
        .where((name) => name.trim().isNotEmpty)
        .take(4)
        .join('، ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: RafeeqGlowCard(
        glowColor: active ? RafeeqColors.danger : RafeeqColors.primary,
        gradient: active
            ? const LinearGradient(
                begin: AlignmentDirectional.topStart,
                end: AlignmentDirectional.bottomEnd,
                colors: [Color(0xFFFFE8ED), Colors.white],
              )
            : RafeeqGradients.aliveCardFor(Theme.of(context).brightness),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(active ? Icons.warning_amber : Icons.check_circle_outline),
            const SizedBox(width: 10),
            Expanded(
                child: Text(
                    type == 'sos'
                        ? strings.sosHelpRequest
                        : strings.fallDetected,
                    style: Theme.of(context).textTheme.titleMedium)),
            Chip(label: Text(localizedStatus(strings, status))),
          ]),
          const SizedBox(height: 8),
          Text('${strings.time}: '
              '${localizedDateTime(context, emergency['detected_at'])}'),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: active
                  ? Colors.white.withValues(alpha: 0.64)
                  : RafeeqColors.lavenderSoft,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: RafeeqColors.outline),
            ),
            child: Row(children: [
              const Icon(
                Icons.notifications_active_outlined,
                color: RafeeqColors.primary,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  recipientNames.isEmpty
                      ? (isArabic
                          ? 'لم تتم إضافة أشخاص لقائمة التنبيه بعد'
                          : 'No alert recipients added yet')
                      : (isArabic
                          ? 'وصل التنبيه إلى: $recipientNames'
                          : 'Notified: $recipientNames'),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
            ]),
          ),
          if (emergency['resolution_note'] != null)
            Text('${strings.result}: ${emergency['resolution_note']}'),
          const SizedBox(height: 10),
          _EmergencyRecipientsSlide(
            recipients: recipients,
            initiallyExpanded: true,
          ),
          const SizedBox(height: 12),
          if (status == 'notified')
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () => _acknowledge(emergency['id'].toString()),
                icon: const Icon(Icons.front_hand),
                label: Text(strings.acknowledgeAlert),
              ),
            ),
          if (status == 'verifying') ...[
            Text(strings.fallVerificationQuestion),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: () =>
                      _verifyFall(emergency['id'].toString(), 'safe'),
                  icon: const Icon(Icons.sentiment_satisfied_alt),
                  label: Text(strings.patientIsOkay),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton.icon(
                  onPressed: () =>
                      _verifyFall(emergency['id'].toString(), 'timeout'),
                  icon: const Icon(Icons.timer_off_outlined),
                  label: Text(strings.simulateNoResponse),
                ),
              ),
            ]),
          ],
          if (status == 'acknowledged')
            SizedBox(
              width: double.infinity,
              child: FilledButton.tonalIcon(
                onPressed: () => _resolve(emergency['id'].toString()),
                icon: const Icon(Icons.task_alt),
                label: Text(strings.resolveEmergency),
              ),
            ),
        ]),
      ),
    );
  }

  Future<void> _provisionSimulator() async {
    try {
      await widget.session.api.dio.post(
          '/patients/${widget.session.currentPatient!.id}/devices/simulated');
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _confirmSimulatedSos(String deviceId) async {
    final strings = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.sos, color: Colors.red),
        title: Text(strings.simulateSosTitle),
        content: Text(strings.simulateSosConfirmation),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: Text(strings.cancel)),
          FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(strings.runSimulation)),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.session.api.dio.post('/devices/$deviceId/simulate-sos');
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _acknowledge(String emergencyId) async {
    try {
      await widget.session.api.dio
          .post('/emergencies/$emergencyId/acknowledge');
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _simulateFall(String deviceId) async {
    try {
      await widget.session.api.dio.post('/devices/$deviceId/simulate-fall');
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _verifyFall(String emergencyId, String outcome) async {
    try {
      await widget.session.api.dio.post(
          '/emergencies/$emergencyId/simulate-verification',
          data: {'outcome': outcome});
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _resolve(String emergencyId) async {
    final strings = AppLocalizations.of(context)!;
    final controller = TextEditingController();
    final note = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.resolveEmergencyTitle),
        content: TextField(
          controller: controller,
          maxLines: 3,
          decoration: InputDecoration(
              labelText: strings.resolutionNote,
              hintText: strings.resolutionHint),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: Text(strings.cancel)),
          FilledButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, controller.text.trim()),
              child: Text(strings.saveAndResolve)),
        ],
      ),
    );
    if (note == null || note.length < 2) return;
    try {
      await widget.session.api.dio.post('/emergencies/$emergencyId/resolve',
          data: {'resolution_note': note});
      refresh();
    } catch (error) {
      _showError(error);
    }
  }

  void _showError(Object error) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.session.api.errorMessage(error))));
  }
}

class ReportsTab extends StatefulWidget {
  const ReportsTab({required this.session, super.key});
  final AppSession session;

  @override
  State<ReportsTab> createState() => _ReportsTabState();
}

class _ReportsTabState extends State<ReportsTab> {
  late Future<Map<String, dynamic>> future;
  int selectedPeriod = 0;

  @override
  void initState() {
    super.initState();
    future = widget.session.api.dio
        .get<Map<String, dynamic>>(
            '/patients/${widget.session.currentPatient!.id}/reports/summary')
        .then((value) => value.data!);
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final data = snapshot.data!;
        final completion = (data['routine_completion_rate'] as num).toDouble();
        final periodLabels = [strings.today, strings.week, strings.month];
        return ListView(padding: const EdgeInsets.all(16), children: [
          SegmentedButton<int>(
            segments: List.generate(
              periodLabels.length,
              (index) => ButtonSegment(
                value: index,
                label: Text(periodLabels[index]),
              ),
            ),
            selected: {selectedPeriod},
            showSelectedIcon: false,
            onSelectionChanged: (value) =>
                setState(() => selectedPeriod = value.first),
          ),
          const SizedBox(height: 14),
          RafeeqGlowCard(
            hero: true,
            padding: const EdgeInsets.all(18),
            child: Row(children: [
              SizedBox.square(
                dimension: 104,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    CircularProgressIndicator(
                      value: completion / 100,
                      strokeWidth: 15,
                      backgroundColor: RafeeqColors.lavender,
                    ),
                    Center(
                      child: Text(
                        '${completion.round()}%',
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(color: RafeeqColors.primary),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(strings.dailyProgress,
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 6),
                    Text(
                      '${strings.completedActivitySessions}: ${data['total_activity_sessions']}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    Text(
                      '${strings.totalEmergencies}: ${data['emergency_count']}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ]),
          ),
          const SizedBox(height: 14),
          _ReportCard(
              label: strings.routineCompletion,
              value: '${data['routine_completion_rate']}%',
              icon: Icons.check_circle_outline),
          _ReportCard(
              label: strings.medicationAdherence,
              value: '${data['medication_adherence_rate']}%',
              icon: Icons.medication_outlined),
          _ReportCard(
              label: strings.totalEmergencies,
              value: '${data['emergency_count']}',
              icon: Icons.warning_amber_outlined),
          _ReportCard(
              label: strings.completedActivitySessions,
              value: '${data['total_activity_sessions']}',
              icon: Icons.psychology_alt_outlined),
          _ReportCard(
              label: strings.memoryExercises,
              value: '${data['memory_activities_completed']}',
              icon: Icons.memory_outlined),
          _ReportCard(
              label: strings.conversation,
              value: '${data['conversation_interactions']}',
              icon: Icons.chat_bubble_outline_rounded),
          RafeeqGlowCard(child: Text(strings.medicalDisclaimer)),
        ]);
      },
    );
  }
}

class _ReportCard extends StatelessWidget {
  const _ReportCard(
      {required this.label, required this.value, required this.icon});
  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: RafeeqGlowCard(
          padding: EdgeInsets.zero,
          child: ListTile(
              leading: CircleAvatar(
                backgroundColor: RafeeqColors.lavender,
                child: Icon(icon, color: RafeeqColors.primary),
              ),
              title: Text(label),
              trailing:
                  Text(value, style: Theme.of(context).textTheme.titleLarge)),
        ),
      );
}

class SentReportsTab extends StatefulWidget {
  const SentReportsTab({required this.session, super.key});

  final AppSession session;

  @override
  State<SentReportsTab> createState() => _SentReportsTabState();
}

class _SentReportsTabState extends State<SentReportsTab> {
  late Future<Map<String, dynamic>> report;

  @override
  void initState() {
    super.initState();
    report = _load();
  }

  Future<Map<String, dynamic>> _load() => widget.session.api.dio
      .get<Map<String, dynamic>>(
          '/patients/${widget.session.currentPatient!.id}/reports/summary')
      .then((response) => response.data!);

  void refresh() => setState(() => report = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return FutureBuilder<Map<String, dynamic>>(
      future: report,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorState(
            message: widget.session.api.errorMessage(snapshot.error!),
            retry: refresh,
          );
        }
        final data = snapshot.data!;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              readOnly: true,
              decoration: InputDecoration(
                hintText: strings.searchReports,
                prefixIcon: const Icon(Icons.search_rounded),
              ),
            ),
            const SizedBox(height: 16),
            RafeeqGlowCard(
              padding: EdgeInsets.zero,
              child: ListTile(
                contentPadding: const EdgeInsets.all(14),
                leading: const CircleAvatar(
                  backgroundColor: RafeeqColors.lavender,
                  child: Icon(Icons.description_outlined,
                      color: RafeeqColors.primary),
                ),
                title: Text(strings.latestReport),
                subtitle: Text(
                  '${strings.routineCompletion}: ${data['routine_completion_rate']}%\n'
                  '${strings.medicationAdherence}: ${data['medication_adherence_rate']}%',
                ),
                isThreeLine: true,
                trailing: const Icon(Icons.verified_rounded,
                    color: RafeeqColors.success),
              ),
            ),
            const SizedBox(height: 12),
            RafeeqGlowCard(child: Text(strings.medicalDisclaimer)),
          ],
        );
      },
    );
  }
}

class SettingsTab extends StatelessWidget {
  const SettingsTab({required this.session, super.key});
  final AppSession session;

  String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final patient = session.currentPatient!;
    return ListView(padding: const EdgeInsets.all(16), children: [
      RafeeqGlowCard(
        padding: EdgeInsets.zero,
        hero: true,
        child: ListTile(
          contentPadding: const EdgeInsets.all(14),
          leading: CircleAvatar(
            radius: 30,
            backgroundColor: RafeeqColors.lavender,
            child: Text(
              patient.displayName.characters.first.toUpperCase(),
              style: const TextStyle(
                color: RafeeqColors.primary,
                fontSize: 22,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          title: Text(patient.displayName),
          subtitle: Text(patient.timezone),
        ),
      ),
      const SizedBox(height: 12),
      _settingsCard(
        context,
        icon: Icons.person_outline_rounded,
        title: strings.patientData,
        subtitle: patient.displayName,
        onTap: () => _showInformation(
          context,
          strings.patientData,
          '${patient.displayName}\n${patient.timezone}',
        ),
      ),
      _settingsCard(
        context,
        icon: Icons.family_restroom_rounded,
        title: strings.familyMembers,
        subtitle: session.user?.fullName ?? '',
        onTap: () => _showInformation(
          context,
          strings.familyMembers,
          '${session.user?.fullName ?? ''}\n${session.user?.email ?? ''}',
        ),
      ),
      _settingsCard(
        context,
        icon: Icons.medical_services_outlined,
        title: strings.doctorFollowUp,
        subtitle: strings.doctorFollowUpSubtitle,
        onTap: () => _openPanel(context, DoctorPanel(session: session)),
      ),
      _settingsCard(
        context,
        icon: Icons.smart_toy_outlined,
        title: strings.robotSettings,
        subtitle: strings.cameraTestSubtitle,
        onTap: () => _openPanel(context, const CameraTestScreen()),
      ),
      _settingsCard(
        context,
        icon: Icons.privacy_tip_outlined,
        title: strings.privacyAndSafety,
        subtitle: strings.privacy,
        onTap: () =>
            _showInformation(context, strings.privacyTitle, strings.privacy),
      ),
      RafeeqGlowCard(
        padding: EdgeInsets.zero,
        child: Column(children: [
          ListTile(
            leading: const CircleAvatar(
              backgroundColor: RafeeqColors.lavender,
              child: Icon(Icons.language, color: RafeeqColors.primary),
            ),
            title: Text(strings.language),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'ar', label: Text(strings.arabic)),
                ButtonSegment(value: 'en', label: Text(strings.english)),
              ],
              selected: {session.locale.languageCode},
              onSelectionChanged: (value) => session.changeLocale(value.first),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 12),
      RafeeqGlowCard(
        padding: EdgeInsets.zero,
        child: Column(children: [
          ListTile(
            leading: const CircleAvatar(
              backgroundColor: RafeeqColors.lavender,
              child:
                  Icon(Icons.dark_mode_outlined, color: RafeeqColors.primary),
            ),
            title: Text(_copy(context, 'المظهر', 'Appearance')),
            subtitle: Text(_copy(
              context,
              'اختر الوضع المناسب لعينك',
              'Choose the look that feels comfortable',
            )),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: SegmentedButton<ThemeMode>(
              segments: [
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text(_copy(context, 'النظام', 'System')),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text(_copy(context, 'فاتح', 'Light')),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text(_copy(context, 'داكن', 'Dark')),
                ),
              ],
              selected: {session.themeMode},
              onSelectionChanged: (value) =>
                  session.changeThemeMode(value.first),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        style: OutlinedButton.styleFrom(
          foregroundColor: RafeeqColors.danger,
          side: const BorderSide(color: Color(0xFFFFA9B8)),
          backgroundColor: Theme.of(context).brightness == Brightness.dark
              ? const Color(0xFF351825)
              : const Color(0xFFFFECEF),
        ),
        onPressed: session.logout,
        icon: const Icon(Icons.logout),
        label: Text(strings.logout),
      ),
    ]);
  }

  Widget _settingsCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: RafeeqGlowCard(
          padding: EdgeInsets.zero,
          child: ListTile(
            contentPadding: const EdgeInsetsDirectional.fromSTEB(12, 6, 10, 6),
            leading: CircleAvatar(
              backgroundColor: RafeeqColors.lavender,
              child: Icon(icon, color: RafeeqColors.primary),
            ),
            title: Text(title),
            subtitle:
                Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
            trailing: Icon(
              Directionality.of(context) == TextDirection.rtl
                  ? Icons.chevron_left_rounded
                  : Icons.chevron_right_rounded,
            ),
            onTap: onTap,
          ),
        ),
      );

  void _showInformation(BuildContext context, String title, String content) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(title),
        content: Text(content),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(AppLocalizations.of(context)!.ok),
          ),
        ],
      ),
    );
  }

  void _openPanel(BuildContext context, Widget panel) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => panel),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.retry});
  final String message;
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.error_outline, size: 64),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(
                onPressed: retry,
                child: Text(AppLocalizations.of(context)!.retry)),
          ]),
        ),
      );
}
