import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../core/auth/models.dart';
import '../../../../core/auth/providers.dart';
import '../../../../l10n/app_localizations.dart';
import '../../../../l10n/localized_values.dart';
import '../../data/repositories/doctor_dashboard_repository.dart';

class DoctorHomeScreen extends ConsumerStatefulWidget {
  const DoctorHomeScreen({super.key});

  @override
  ConsumerState<DoctorHomeScreen> createState() => _DoctorHomeScreenState();
}

class _DoctorHomeScreenState extends ConsumerState<DoctorHomeScreen> {
  late DoctorDashboardRepository repository;
  late Future<List<DoctorPatientData>> future;
  int index = 0;
  String query = '';
  String? reportPatientId;

  @override
  void initState() {
    super.initState();
    repository = DoctorDashboardRepository(ref.read(appSessionProvider));
    future = repository.loadAllPatients();
  }

  void refresh() => setState(() => future = repository.loadAllPatients());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    final titles = [
      strings.doctorDashboard,
      strings.medicalReports,
      strings.emergencyCases,
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(titles[index]),
        leading: IconButton.filledTonal(
          tooltip: strings.logout,
          onPressed: () => _confirmLogout(session),
          icon: Icon(
            Directionality.of(context) == TextDirection.rtl
                ? Icons.chevron_right_rounded
                : Icons.chevron_left_rounded,
          ),
        ),
        actions: [
          IconButton.filledTonal(
            tooltip: strings.emergencyCases,
            onPressed: () => setState(() => index = 2),
            icon: const Icon(Icons.notifications_none_rounded),
          ),
          const SizedBox(width: 10),
        ],
      ),
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: RafeeqGradients.page),
        child: FutureBuilder<List<DoctorPatientData>>(
          future: future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return _DoctorErrorState(
                message: session.api.errorMessage(snapshot.error!),
                retry: refresh,
              );
            }
            final patients = snapshot.data!;
            if (patients.isEmpty) return _EmptyDoctorState(strings: strings);
            return IndexedStack(
              index: index,
              children: [
                _DoctorDashboardView(
                  patients: patients,
                  query: query,
                  onQueryChanged: (value) => setState(() => query = value),
                  onOpenPatient: _openPatient,
                  onRefresh: refresh,
                ),
                _DoctorReportsView(
                  key: ValueKey(reportPatientId),
                  patients: patients,
                  repository: repository,
                  initialPatientId: reportPatientId,
                ),
                _DoctorEmergenciesView(
                  patients: patients,
                  onRefresh: refresh,
                ),
              ],
            );
          },
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.medical_services_outlined),
            selectedIcon: const Icon(Icons.medical_services_rounded),
            label: strings.homePage,
          ),
          NavigationDestination(
            icon: const Icon(Icons.description_outlined),
            selectedIcon: const Icon(Icons.description_rounded),
            label: strings.reports,
          ),
          NavigationDestination(
            icon: const Icon(Icons.warning_amber_outlined),
            selectedIcon: const Icon(Icons.warning_amber_rounded),
            label: strings.emergencies,
          ),
        ],
      ),
    );
  }

  Future<void> _openPatient(DoctorPatientData patient) async {
    final result = await Navigator.of(context).push<Map<String, String>>(
      MaterialPageRoute(
        builder: (_) => DoctorPatientDetailScreen(
          patient: patient.summary,
          repository: repository,
        ),
      ),
    );
    if (!mounted) return;
    if (result?['action'] == 'reports') {
      setState(() {
        reportPatientId = result?['patient_id'];
        index = 1;
      });
    } else if (result?['action'] == 'emergencies') {
      setState(() => index = 2);
    }
    refresh();
  }

  Future<void> _confirmLogout(AppSession session) async {
    final strings = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.logout),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(strings.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(strings.logout),
          ),
        ],
      ),
    );
    if (confirmed == true) await session.logout();
  }
}

class _DoctorDashboardView extends StatelessWidget {
  const _DoctorDashboardView({
    required this.patients,
    required this.query,
    required this.onQueryChanged,
    required this.onOpenPatient,
    required this.onRefresh,
  });

  final List<DoctorPatientData> patients;
  final String query;
  final ValueChanged<String> onQueryChanged;
  final ValueChanged<DoctorPatientData> onOpenPatient;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final normalizedQuery = query.trim().toLowerCase();
    final visible = patients
        .where((item) =>
            normalizedQuery.isEmpty ||
            item.summary.displayName.toLowerCase().contains(normalizedQuery))
        .toList();
    final alerts = patients.fold<int>(
      0,
      (total, item) => total + item.activeEmergencyCount,
    );
    final appointments = patients.fold<int>(
      0,
      (total, item) => total + item.appointmentCount,
    );
    return RefreshIndicator(
      onRefresh: () async => onRefresh(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          GridView.count(
            crossAxisCount: 2,
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.8,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              _DoctorMetricCard(
                icon: Icons.people_alt_outlined,
                label: strings.doctorPatients,
                value: '${patients.length}',
              ),
              _DoctorMetricCard(
                icon: Icons.warning_amber_rounded,
                label: strings.alerts,
                value: '$alerts',
              ),
              _DoctorMetricCard(
                icon: Icons.calendar_month_outlined,
                label: strings.appointments,
                value: '$appointments',
              ),
              _DoctorMetricCard(
                icon: Icons.description_outlined,
                label: strings.newReports,
                value: '${patients.length}',
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            onChanged: onQueryChanged,
            decoration: InputDecoration(
              hintText: strings.searchPatients,
              prefixIcon: const Icon(Icons.search_rounded),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(strings.patientList,
                  style: Theme.of(context).textTheme.titleLarge),
              Text('${visible.length} ${strings.doctorPatients}',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          const SizedBox(height: 10),
          if (visible.isEmpty)
            RafeeqGlowCard(
              child: Text(strings.noData, textAlign: TextAlign.center),
            )
          else
            ...visible.map(
              (patient) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _DoctorPatientCard(
                  patient: patient,
                  onTap: () => onOpenPatient(patient),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _DoctorReportsView extends StatefulWidget {
  const _DoctorReportsView({
    required this.patients,
    required this.repository,
    this.initialPatientId,
    super.key,
  });

  final List<DoctorPatientData> patients;
  final DoctorDashboardRepository repository;
  final String? initialPatientId;

  @override
  State<_DoctorReportsView> createState() => _DoctorReportsViewState();
}

class _DoctorReportsViewState extends State<_DoctorReportsView> {
  late String selectedPatientId;
  String period = 'week';
  late Future<Map<String, dynamic>> future;

  @override
  void initState() {
    super.initState();
    selectedPatientId =
        widget.initialPatientId ?? widget.patients.first.summary.id;
    future = widget.repository.loadReport(selectedPatientId, period);
  }

  void reload() => setState(
        () => future = widget.repository.loadReport(selectedPatientId, period),
      );

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        DropdownButtonFormField<String>(
          initialValue: selectedPatientId,
          decoration: InputDecoration(labelText: strings.patientDetails),
          items: widget.patients
              .map((item) => DropdownMenuItem(
                    value: item.summary.id,
                    child: Text(item.summary.displayName),
                  ))
              .toList(),
          onChanged: (value) {
            if (value == null) return;
            selectedPatientId = value;
            reload();
          },
        ),
        const SizedBox(height: 12),
        SegmentedButton<String>(
          showSelectedIcon: false,
          segments: [
            ButtonSegment(value: 'week', label: Text(strings.weekly)),
            ButtonSegment(value: 'month', label: Text(strings.monthly)),
            ButtonSegment(value: 'quarter', label: Text(strings.quarterly)),
          ],
          selected: {period},
          onSelectionChanged: (value) {
            period = value.first;
            reload();
          },
        ),
        const SizedBox(height: 14),
        FutureBuilder<Map<String, dynamic>>(
          future: future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const SizedBox(
                height: 420,
                child: Center(child: CircularProgressIndicator()),
              );
            }
            if (snapshot.hasError) {
              return _DoctorErrorState(
                message:
                    widget.repository.session.api.errorMessage(snapshot.error!),
                retry: reload,
              );
            }
            final report = snapshot.data!;
            return Column(children: [
              RafeeqGlowCard(
                padding: EdgeInsets.zero,
                child: ListTile(
                  leading: const Icon(Icons.chevron_left_rounded),
                  title: Text(
                    _reportRange(context, report),
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                  trailing: const Icon(Icons.chevron_right_rounded),
                ),
              ),
              const SizedBox(height: 14),
              _ReportChartCard(
                title: strings.medicationAdherence,
                value: '${report['medication_adherence_rate']}%',
                values: _doubleList(report['medication_adherence_trend']),
                color: RafeeqColors.primary,
              ),
              const SizedBox(height: 14),
              _ReportChartCard(
                title: strings.memoryExercises,
                value: '${report['memory_activities_completed']}',
                values: _doubleList(report['memory_activity_trend']),
                color: RafeeqColors.danger,
              ),
              const SizedBox(height: 14),
              RafeeqGlowCard(
                child: Text(strings.clinicalDisclaimer),
              ),
            ]);
          },
        ),
      ],
    );
  }
}

class _DoctorEmergenciesView extends StatelessWidget {
  const _DoctorEmergenciesView({
    required this.patients,
    required this.onRefresh,
  });

  final List<DoctorPatientData> patients;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final items = <({DoctorPatientData patient, Map<String, dynamic> event})>[];
    for (final patient in patients) {
      for (final event in patient.emergencies) {
        items.add((patient: patient, event: event));
      }
    }
    items.sort((a, b) => b.event['detected_at']
        .toString()
        .compareTo(a.event['detected_at'].toString()));
    return RefreshIndicator(
      onRefresh: () async => onRefresh(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          if (items.isEmpty)
            RafeeqGlowCard(
              child: Column(children: [
                const Icon(Icons.health_and_safety_outlined, size: 54),
                const SizedBox(height: 12),
                Text(strings.noEmergencyHistory),
              ]),
            )
          else
            ...items.map(
              (item) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _DoctorEmergencyCard(
                  patient: item.patient,
                  event: item.event,
                ),
              ),
            ),
          if (items.isNotEmpty)
            FilledButton(
              onPressed: onRefresh,
              child: Text(strings.viewAllCases),
            ),
        ],
      ),
    );
  }
}

class DoctorPatientDetailScreen extends StatefulWidget {
  const DoctorPatientDetailScreen({
    required this.patient,
    required this.repository,
    super.key,
  });

  final PatientSummary patient;
  final DoctorDashboardRepository repository;

  @override
  State<DoctorPatientDetailScreen> createState() =>
      _DoctorPatientDetailScreenState();
}

class _DoctorPatientDetailScreenState extends State<DoctorPatientDetailScreen> {
  late Future<DoctorPatientData> future;
  final noteController = TextEditingController();
  bool saving = false;

  @override
  void initState() {
    super.initState();
    future = widget.repository.loadPatient(widget.patient);
  }

  @override
  void dispose() {
    noteController.dispose();
    super.dispose();
  }

  void refresh() => setState(
        () => future = widget.repository.loadPatient(widget.patient),
      );

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(strings.doctorDashboard),
        leading: IconButton.filledTonal(
          tooltip: strings.back,
          onPressed: () => Navigator.pop(context),
          icon: Icon(
            Directionality.of(context) == TextDirection.rtl
                ? Icons.chevron_right_rounded
                : Icons.chevron_left_rounded,
          ),
        ),
        actions: [
          IconButton.filledTonal(
            tooltip: strings.emergencyCases,
            onPressed: () => Navigator.pop(
              context,
              {'action': 'emergencies', 'patient_id': widget.patient.id},
            ),
            icon: const Icon(Icons.notifications_none_rounded),
          ),
          const SizedBox(width: 10),
        ],
      ),
      body: FutureBuilder<DoctorPatientData>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _DoctorErrorState(
              message:
                  widget.repository.session.api.errorMessage(snapshot.error!),
              retry: refresh,
            );
          }
          return _patientBody(snapshot.data!);
        },
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: 0,
        onDestinationSelected: (value) {
          if (value == 0) Navigator.pop(context);
          if (value == 1) {
            Navigator.pop(context, {
              'action': 'reports',
              'patient_id': widget.patient.id,
            });
          }
          if (value == 2) {
            Navigator.pop(context, {
              'action': 'emergencies',
              'patient_id': widget.patient.id,
            });
          }
        },
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.medical_services_outlined),
            selectedIcon: const Icon(Icons.medical_services_rounded),
            label: strings.homePage,
          ),
          NavigationDestination(
            icon: const Icon(Icons.description_outlined),
            label: strings.reports,
          ),
          NavigationDestination(
            icon: const Icon(Icons.warning_amber_outlined),
            label: strings.emergencies,
          ),
        ],
      ),
    );
  }

  Widget _patientBody(DoctorPatientData data) {
    final strings = AppLocalizations.of(context)!;
    final risk = _patientRisk(data);
    final medications =
        data.routines.where((item) => item['type'] == 'medication').toList();
    final appointments =
        data.routines.where((item) => item['type'] == 'appointment').toList();
    final guardian = _primaryGuardian(data);
    final occurrenceByRoutine = {
      for (final item in data.occurrences) item['routine_id'].toString(): item,
    };
    return RefreshIndicator(
      onRefresh: () async => refresh(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 2, 16, 24),
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton.icon(
              onPressed: () => Navigator.pop(context),
              icon: Icon(
                Directionality.of(context) == TextDirection.rtl
                    ? Icons.chevron_right_rounded
                    : Icons.chevron_left_rounded,
              ),
              label: Text(strings.backToPatients),
            ),
          ),
          RafeeqGlowCard(
            hero: true,
            padding: const EdgeInsets.all(17),
            child: Column(children: [
              Row(children: [
                CircleAvatar(
                  radius: 35,
                  backgroundColor: RafeeqColors.lavender,
                  child: Text(
                    data.summary.displayName.characters.first,
                    style: const TextStyle(
                      color: RafeeqColors.primary,
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Flexible(
                          child: Text(data.summary.displayName,
                              style: Theme.of(context).textTheme.titleLarge),
                        ),
                        const SizedBox(width: 7),
                        _RiskChip(risk: risk),
                      ]),
                      const SizedBox(height: 4),
                      Text(
                        '${_ageText(context, data.patient)} • ${data.patient['timezone']}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      Text(
                        '${strings.lastUpdated}: ${localizedDateTime(context, data.patient['updated_at'])}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ]),
              const SizedBox(height: 14),
              Row(children: [
                Expanded(
                  child: _PatientInfoTile(
                    label: _doctorCopy(context, 'ولي الأمر', 'Guardian'),
                    value: guardian == null
                        ? _doctorCopy(
                            context,
                            'لم يتم تحديد مسؤول',
                            'No guardian set',
                          )
                        : '${guardian['name']}'
                            '${guardian['relationship']?.toString().isNotEmpty == true ? ' (${guardian['relationship']})' : ''}',
                    subtitle: guardian == null
                        ? _doctorCopy(
                            context,
                            'تضيفه العائلة من الداشبورد',
                            'Family can add one from dashboard',
                          )
                        : [
                            guardian['phone']?.toString() ?? '',
                            guardian['email']?.toString() ?? '',
                          ].where((item) => item.isNotEmpty).join(' • '),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _PatientInfoTile(
                    label: strings.diagnosis,
                    value: data.patient['condition_notes']
                                ?.toString()
                                .isNotEmpty ==
                            true
                        ? data.patient['condition_notes'].toString()
                        : strings.noConditionNotes,
                  ),
                ),
              ]),
            ]),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: () => _showContact(data),
                icon: const Icon(Icons.call_outlined),
                label: Text(strings.contactFamily),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: RafeeqColors.success),
                onPressed: () => Navigator.pop(context, {
                  'action': 'reports',
                  'patient_id': data.summary.id,
                }),
                icon: const Icon(Icons.send_outlined),
                label: Text(strings.sendReport),
              ),
            ),
          ]),
          const SizedBox(height: 14),
          RafeeqGlowCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(strings.patientSummary,
                    style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 8,
                  crossAxisSpacing: 8,
                  childAspectRatio: 1.9,
                  children: [
                    _PatientSummaryMetric(
                      value: '${data.report['routine_completion_rate']}%',
                      label: strings.engagementLevel,
                    ),
                    _PatientSummaryMetric(
                      value: '${data.report['medication_adherence_rate']}%',
                      label: strings.medicationAdherence,
                    ),
                    _PatientSummaryMetric(
                      value: '${data.report['memory_activities_completed']}',
                      label: strings.memoryExercises,
                    ),
                    _PatientSummaryMetric(
                      value: '${data.emergencies.length}',
                      label: strings.fallCases,
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          _ReportChartCard(
            title: strings.weeklyEngagement,
            value: '${data.report['routine_completion_rate']}%',
            values: _flatTrend(data.report['routine_completion_rate']),
            color: RafeeqColors.primary,
          ),
          const SizedBox(height: 14),
          _ReportChartCard(
            title: strings.memoryExerciseResults,
            value: '${data.report['memory_activities_completed']}',
            values: _doubleList(data.report['memory_activity_trend']),
            color: RafeeqColors.primary,
          ),
          const SizedBox(height: 14),
          _DetailSectionCard(
            title: strings.medicationsAndAdherence,
            icon: Icons.medication_outlined,
            emptyText: strings.noMedications,
            action: TextButton.icon(
              onPressed: () => _addMedication(data),
              icon: const Icon(Icons.add_rounded),
              label: Text(_doctorCopy(context, 'إضافة دواء', 'Add medicine')),
            ),
            children: medications.map((routine) {
              final occurrence = occurrenceByRoutine[routine['id'].toString()];
              return _CompactDetailRow(
                title: routine['medication']?['medication_name']?.toString() ??
                    routine['title'].toString(),
                subtitle:
                    '${routine['medication']?['dosage_text'] ?? ''} • ${localizedClockTime(context, routine['scheduled_local_time'])}',
                status: occurrence?['status']?.toString(),
              );
            }).toList(),
          ),
          const SizedBox(height: 14),
          _DetailSectionCard(
            title: strings.upcomingAppointments,
            icon: Icons.calendar_month_outlined,
            emptyText: strings.noAppointments,
            children: appointments
                .map((routine) => _CompactDetailRow(
                      title: routine['title'].toString(),
                      subtitle: localizedClockTime(
                          context, routine['scheduled_local_time']),
                    ))
                .toList(),
          ),
          const SizedBox(height: 14),
          RafeeqGlowCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.note_alt_outlined,
                      color: RafeeqColors.primary),
                  const SizedBox(width: 8),
                  Text(strings.doctorNotes,
                      style: Theme.of(context).textTheme.titleLarge),
                ]),
                const SizedBox(height: 10),
                if (data.notes.isEmpty)
                  Text(strings.noNotes)
                else
                  ...data.notes.map(
                    (note) => _CompactDetailRow(
                      title: note['text'].toString(),
                      subtitle: localizedDateTime(context, note['created_at']),
                    ),
                  ),
                const SizedBox(height: 10),
                Row(children: [
                  Expanded(
                    child: TextField(
                      controller: noteController,
                      decoration: InputDecoration(hintText: strings.addNewNote),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: saving ? null : () => _saveNote(data),
                    child: saving
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : Text(strings.save),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _saveNote(DoctorPatientData data) async {
    final value = noteController.text.trim();
    if (value.length < 2) return;
    setState(() => saving = true);
    try {
      await widget.repository.addNote(data.summary.id, value);
      noteController.clear();
      refresh();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(widget.repository.session.api.errorMessage(error)),
        ));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _addMedication(DoctorPatientData data) async {
    final name = TextEditingController();
    final dosage = TextEditingController();
    final instructions = TextEditingController();
    TimeOfDay selectedTime = const TimeOfDay(hour: 8, minute: 0);
    var isSaving = false;
    final isArabic = Directionality.of(context) == TextDirection.rtl;
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_doctorCopy(
              context, 'إضافة دواء للمريض', 'Add patient medicine')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                controller: name,
                textInputAction: TextInputAction.next,
                decoration: InputDecoration(
                  labelText:
                      _doctorCopy(context, 'اسم الدواء', 'Medicine name'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: dosage,
                textInputAction: TextInputAction.next,
                decoration: InputDecoration(
                  labelText: _doctorCopy(context, 'الجرعة', 'Dose'),
                  hintText: _doctorCopy(
                      context, 'مثال: حبة واحدة', 'Example: one tablet'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: instructions,
                minLines: 1,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: _doctorCopy(
                      context, 'تعليمات اختيارية', 'Optional instructions'),
                ),
              ),
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.schedule_rounded),
                title:
                    Text(_doctorCopy(context, 'وقت التذكير', 'Reminder time')),
                subtitle: Text(selectedTime.format(context)),
                onTap: isSaving
                    ? null
                    : () async {
                        final picked = await showTimePicker(
                          context: context,
                          initialTime: selectedTime,
                        );
                        if (picked != null) {
                          setDialogState(() => selectedTime = picked);
                        }
                      },
              ),
              const SizedBox(height: 8),
              Text(
                isArabic
                    ? 'سيظهر الدواء في روتين المريض اليومي.'
                    : 'This medicine will appear in the patient daily routine.',
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ]),
          ),
          actions: [
            TextButton(
              onPressed:
                  isSaving ? null : () => Navigator.pop(dialogContext, false),
              child: Text(AppLocalizations.of(context)!.cancel),
            ),
            FilledButton(
              onPressed: isSaving
                  ? null
                  : () async {
                      if (name.text.trim().isEmpty ||
                          dosage.text.trim().isEmpty) {
                        return;
                      }
                      setDialogState(() => isSaving = true);
                      try {
                        await widget.repository.addMedicationRoutine(
                          patientId: data.summary.id,
                          timezone: data.patient['timezone']?.toString() ??
                              'Europe/London',
                          medicationName: name.text.trim(),
                          dosageText: dosage.text.trim(),
                          instructions: instructions.text.trim().isEmpty
                              ? null
                              : instructions.text.trim(),
                          time24h:
                              '${selectedTime.hour.toString().padLeft(2, '0')}:${selectedTime.minute.toString().padLeft(2, '0')}',
                        );
                        if (dialogContext.mounted) {
                          Navigator.pop(dialogContext, true);
                        }
                      } catch (error) {
                        if (dialogContext.mounted) {
                          setDialogState(() => isSaving = false);
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(
                              widget.repository.session.api.errorMessage(error),
                            ),
                          ));
                        }
                      }
                    },
              child: isSaving
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : Text(AppLocalizations.of(context)!.save),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    dosage.dispose();
    instructions.dispose();
    if (result == true) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(_doctorCopy(context, 'تمت إضافة الدواء للروتين',
              'Medicine added to routine')),
        ));
      }
      refresh();
    }
  }

  void _showContact(DoctorPatientData data) {
    final strings = AppLocalizations.of(context)!;
    final recipients =
        (data.careProfile['alert_recipients'] as List? ?? const [])
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
    final instructions = data.patient['emergency_instructions']?.toString();
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.contactFamily),
        content: SizedBox(
          width: 420,
          child: recipients.isEmpty
              ? SelectableText(
                  instructions?.isNotEmpty == true
                      ? instructions!
                      : strings.contactUnavailable,
                )
              : SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (final recipient in recipients)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: _DoctorContactTile(recipient: recipient),
                        ),
                      if (instructions?.isNotEmpty == true) ...[
                        const Divider(height: 18),
                        Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: Text(
                            _doctorCopy(
                              context,
                              'تعليمات الطوارئ',
                              'Emergency instructions',
                            ),
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                        ),
                        const SizedBox(height: 6),
                        SelectableText(instructions!),
                      ],
                    ],
                  ),
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(strings.ok),
          ),
        ],
      ),
    );
  }
}

class _PatientInfoTile extends StatelessWidget {
  const _PatientInfoTile({
    required this.label,
    required this.value,
    this.subtitle,
  });

  final String label;
  final String value;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final cleanSubtitle = subtitle?.trim() ?? '';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: RafeeqColors.lavenderSoft,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 2),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          if (cleanSubtitle.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(
              cleanSubtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}

class _DoctorContactTile extends StatelessWidget {
  const _DoctorContactTile({required this.recipient});

  final Map<String, dynamic> recipient;

  @override
  Widget build(BuildContext context) {
    final relationship = recipient['relationship']?.toString() ?? '';
    final phone = recipient['phone']?.toString() ?? '';
    final email = recipient['email']?.toString() ?? '';
    final details = [
      if (relationship.isNotEmpty) relationship,
      if (phone.isNotEmpty) phone,
      if (email.isNotEmpty) email,
    ].join(' • ');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: RafeeqColors.lavenderSoft,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: RafeeqColors.outline),
      ),
      child: Row(children: [
        const CircleAvatar(
          backgroundColor: RafeeqColors.lavender,
          child:
              Icon(Icons.person_outline_rounded, color: RafeeqColors.primary),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(
                recipient['name']?.toString() ?? '',
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
              if (details.isNotEmpty)
                SelectableText(
                  details,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
        ),
      ]),
    );
  }
}

enum _PatientRisk { stable, followUp, critical }

String _doctorCopy(BuildContext context, String ar, String en) =>
    Directionality.of(context) == TextDirection.rtl ? ar : en;

Map<String, dynamic>? _primaryGuardian(DoctorPatientData data) {
  final recipients = (data.careProfile['alert_recipients'] as List? ?? const [])
      .map((item) => Map<String, dynamic>.from(item as Map))
      .toList();
  if (recipients.isEmpty) return null;
  final emergencyContacts =
      recipients.where((item) => item['source'] == 'emergency_contact');
  return emergencyContacts.isNotEmpty
      ? emergencyContacts.first
      : recipients.first;
}

_PatientRisk _patientRisk(DoctorPatientData patient) {
  if (patient.activeEmergencyCount > 0) return _PatientRisk.critical;
  final adherence =
      (patient.report['medication_adherence_rate'] as num?)?.toDouble() ?? 0;
  final completion =
      (patient.report['routine_completion_rate'] as num?)?.toDouble() ?? 0;
  if ((patient.medicationCount > 0 && adherence < 70) || completion < 50) {
    return _PatientRisk.followUp;
  }
  return _PatientRisk.stable;
}

class _DoctorPatientCard extends StatelessWidget {
  const _DoctorPatientCard({required this.patient, required this.onTap});

  final DoctorPatientData patient;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return RafeeqGlowCard(
      onTap: onTap,
      padding: EdgeInsets.zero,
      child: ListTile(
        contentPadding: const EdgeInsetsDirectional.fromSTEB(14, 10, 10, 10),
        leading: CircleAvatar(
          radius: 28,
          backgroundColor: RafeeqColors.lavender,
          child: Text(
            patient.summary.displayName.characters.first,
            style: const TextStyle(
              color: RafeeqColors.primary,
              fontSize: 20,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
        title: Row(children: [
          Flexible(child: Text(patient.summary.displayName)),
          const SizedBox(width: 7),
          _RiskChip(risk: _patientRisk(patient)),
        ]),
        subtitle: Text(
          '${_ageText(context, patient.patient)} • '
          '${strings.lastUpdated}: ${localizedDateTime(context, patient.patient['updated_at'])}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: Icon(
          Directionality.of(context) == TextDirection.rtl
              ? Icons.chevron_left_rounded
              : Icons.chevron_right_rounded,
        ),
      ),
    );
  }
}

class _RiskChip extends StatelessWidget {
  const _RiskChip({required this.risk});

  final _PatientRisk risk;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final (label, color, background) = switch (risk) {
      _PatientRisk.stable => (
          strings.stable,
          RafeeqColors.success,
          const Color(0xFFE1F7EC),
        ),
      _PatientRisk.followUp => (
          strings.needsFollowUp,
          const Color(0xFFB66D00),
          const Color(0xFFFFF0CF),
        ),
      _PatientRisk.critical => (
          strings.criticalCondition,
          RafeeqColors.danger,
          const Color(0xFFFFE4E9),
        ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style:
            TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _DoctorMetricCard extends StatelessWidget {
  const _DoctorMetricCard({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: SizedBox(
          height: double.infinity,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: RafeeqColors.lavender,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: RafeeqColors.primary.withValues(alpha: 0.13),
                        blurRadius: 12,
                        offset: const Offset(0, 7),
                      ),
                    ],
                  ),
                  child: Icon(icon, color: RafeeqColors.primary, size: 22),
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(label, style: Theme.of(context).textTheme.bodySmall),
                  Text(
                    value,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(color: RafeeqColors.primary),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
}

class _DoctorEmergencyCard extends StatelessWidget {
  const _DoctorEmergencyCard({
    required this.patient,
    required this.event,
  });

  final DoctorPatientData patient;
  final Map<String, dynamic> event;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final active =
        event['status'] != 'resolved' && event['status'] != 'false_alarm';
    return RafeeqGlowCard(
      padding: EdgeInsets.zero,
      glowColor: active ? RafeeqColors.danger : RafeeqColors.primary,
      gradient: active
          ? const LinearGradient(
              begin: AlignmentDirectional.topStart,
              end: AlignmentDirectional.bottomEnd,
              colors: [Color(0xFFFFE8ED), Colors.white],
            )
          : RafeeqGradients.aliveCard,
      child: ListTile(
        onTap: () => showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(event['type'] == 'sos'
                ? strings.sosHelpRequest
                : strings.fallDetected),
            content: Text(
              '${patient.summary.displayName}\n'
              '${localizedDateTime(context, event['detected_at'])}\n'
              '${localizedStatus(strings, event['status'].toString())}',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: Text(strings.ok),
              ),
            ],
          ),
        ),
        contentPadding: const EdgeInsetsDirectional.fromSTEB(14, 12, 10, 12),
        leading: CircleAvatar(
          radius: 27,
          backgroundColor: active ? RafeeqColors.danger : RafeeqColors.lavender,
          child: Icon(
            active ? Icons.warning_amber_rounded : Icons.history_rounded,
            color: active ? Colors.white : RafeeqColors.primary,
          ),
        ),
        title: Text(
          event['type'] == 'sos'
              ? strings.sosHelpRequest
              : strings.fallDetected,
          style: TextStyle(
            color: active ? RafeeqColors.danger : RafeeqColors.ink,
            fontWeight: FontWeight.w900,
          ),
        ),
        subtitle: Text(
          '${patient.summary.displayName} • '
          '${localizedDateTime(context, event['detected_at'])}',
        ),
        trailing: Icon(
          Directionality.of(context) == TextDirection.rtl
              ? Icons.chevron_left_rounded
              : Icons.chevron_right_rounded,
        ),
      ),
    );
  }
}

class _ReportChartCard extends StatelessWidget {
  const _ReportChartCard({
    required this.title,
    required this.value,
    required this.values,
    required this.color,
  });

  final String title;
  final String value;
  final List<double> values;
  final Color color;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        glowColor: color,
        padding: const EdgeInsets.all(17),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleLarge),
                Text(
                  value,
                  style: TextStyle(
                    color: color,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              height: 145,
              width: double.infinity,
              child: CustomPaint(
                painter: _TrendPainter(values: values, color: color),
              ),
            ),
          ],
        ),
      );
}

class _TrendPainter extends CustomPainter {
  const _TrendPainter({required this.values, required this.color});

  final List<double> values;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = RafeeqColors.outline
      ..strokeWidth = 1;
    for (var index = 1; index < 4; index++) {
      final y = size.height * index / 4;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    if (values.isEmpty) return;
    final maximum = math.max(1.0, values.reduce(math.max));
    final path = Path();
    for (var index = 0; index < values.length; index++) {
      final x = values.length == 1
          ? size.width / 2
          : size.width * index / (values.length - 1);
      final y =
          size.height - (values[index] / maximum) * (size.height - 14) - 7;
      if (index == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(covariant _TrendPainter oldDelegate) =>
      oldDelegate.values != values || oldDelegate.color != color;
}

class _PatientSummaryMetric extends StatelessWidget {
  const _PatientSummaryMetric({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: RafeeqColors.lavenderSoft,
          borderRadius: BorderRadius.circular(17),
        ),
        padding: const EdgeInsets.all(10),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              value,
              style: const TextStyle(
                color: RafeeqColors.primary,
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      );
}

class _DetailSectionCard extends StatelessWidget {
  const _DetailSectionCard({
    required this.title,
    required this.icon,
    required this.emptyText,
    required this.children,
    this.action,
  });

  final String title;
  final IconData icon;
  final String emptyText;
  final List<Widget> children;
  final Widget? action;

  @override
  Widget build(BuildContext context) => RafeeqGlowCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, color: RafeeqColors.primary),
              const SizedBox(width: 8),
              Expanded(
                child:
                    Text(title, style: Theme.of(context).textTheme.titleLarge),
              ),
              if (action != null) action!,
            ]),
            const SizedBox(height: 10),
            if (children.isEmpty) Text(emptyText) else ...children,
          ],
        ),
      );
}

class _CompactDetailRow extends StatelessWidget {
  const _CompactDetailRow({
    required this.title,
    required this.subtitle,
    this.status,
  });

  final String title;
  final String subtitle;
  final String? status;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: RafeeqColors.lavenderSoft,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
              Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
        if (status != null)
          Text(
            localizedStatus(strings, status!),
            style: TextStyle(
              color: status == 'completed'
                  ? RafeeqColors.success
                  : RafeeqColors.danger,
              fontSize: 10,
              fontWeight: FontWeight.w800,
            ),
          ),
      ]),
    );
  }
}

class _EmptyDoctorState extends StatelessWidget {
  const _EmptyDoctorState({required this.strings});

  final AppLocalizations strings;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(children: [
            const CircleAvatar(
              radius: 42,
              backgroundColor: RafeeqColors.lavender,
              child: Icon(Icons.assignment_ind_outlined,
                  size: 44, color: RafeeqColors.primary),
            ),
            const SizedBox(height: 18),
            Text(strings.noAssignedPatients,
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(strings.caregiverInviteDoctorHint,
                textAlign: TextAlign.center,
                style: const TextStyle(color: RafeeqColors.muted)),
          ]),
        ),
      );
}

class _DoctorErrorState extends StatelessWidget {
  const _DoctorErrorState({required this.message, required this.retry});

  final String message;
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.cloud_off_outlined, size: 56),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(
              onPressed: retry,
              child: Text(AppLocalizations.of(context)!.retry),
            ),
          ]),
        ),
      );
}

String _ageText(BuildContext context, Map<String, dynamic> patient) {
  final strings = AppLocalizations.of(context)!;
  final birth = DateTime.tryParse(patient['date_of_birth']?.toString() ?? '');
  if (birth == null) return strings.unknownAge;
  final now = DateTime.now();
  var age = now.year - birth.year;
  if (now.month < birth.month ||
      (now.month == birth.month && now.day < birth.day)) {
    age--;
  }
  return '$age ${strings.yearsOld}';
}

String _reportRange(BuildContext context, Map<String, dynamic> report) {
  final start = DateTime.tryParse(report['range_start']?.toString() ?? '');
  final end = DateTime.tryParse(report['range_end']?.toString() ?? '');
  if (start == null || end == null) return AppLocalizations.of(context)!.noData;
  final localizations = MaterialLocalizations.of(context);
  return '${localizations.formatShortDate(start)} - '
      '${localizations.formatShortDate(end)}';
}

List<double> _doubleList(dynamic value) => value is List
    ? value.map((item) => (item as num).toDouble()).toList()
    : const [];

List<double> _flatTrend(dynamic value) {
  final point = (value as num?)?.toDouble() ?? 0;
  return List<double>.filled(7, point);
}
