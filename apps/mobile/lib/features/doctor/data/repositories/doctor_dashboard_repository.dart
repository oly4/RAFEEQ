import '../../../../core/auth/app_session.dart';
import '../../../../core/auth/models.dart';

class DoctorPatientData {
  const DoctorPatientData({
    required this.summary,
    required this.patient,
    required this.report,
    required this.emergencies,
    required this.notes,
    required this.routines,
    required this.occurrences,
    required this.careProfile,
  });

  final PatientSummary summary;
  final Map<String, dynamic> patient;
  final Map<String, dynamic> report;
  final List<Map<String, dynamic>> emergencies;
  final List<Map<String, dynamic>> notes;
  final List<Map<String, dynamic>> routines;
  final List<Map<String, dynamic>> occurrences;
  final Map<String, dynamic> careProfile;

  int get activeEmergencyCount => emergencies
      .where((item) =>
          item['status'] != 'resolved' && item['status'] != 'false_alarm')
      .length;

  int get appointmentCount =>
      routines.where((item) => item['type'] == 'appointment').length;

  int get medicationCount =>
      routines.where((item) => item['type'] == 'medication').length;
}

class DoctorDashboardRepository {
  const DoctorDashboardRepository(this.session);

  final AppSession session;

  Future<List<DoctorPatientData>> loadAllPatients() => Future.wait(
        session.patients.map(loadPatient),
      );

  Future<DoctorPatientData> loadPatient(PatientSummary patient) async {
    final id = patient.id;
    final responses = await Future.wait<dynamic>([
      session.api.dio.get<Map<String, dynamic>>('/patients/$id'),
      session.api.dio
          .get<Map<String, dynamic>>('/patients/$id/reports/summary'),
      session.api.dio.get<Map<String, dynamic>>('/patients/$id/emergencies'),
      session.api.dio.get<List<dynamic>>('/doctor/patients/$id/notes'),
      session.api.dio.get<Map<String, dynamic>>('/patients/$id/routines'),
      session.api.dio
          .get<Map<String, dynamic>>('/patients/$id/routine-occurrences'),
      session.api.dio.get<Map<String, dynamic>>('/patients/$id/care-profile'),
    ]);
    return DoctorPatientData(
      summary: patient,
      patient: Map<String, dynamic>.from(responses[0].data!),
      report: Map<String, dynamic>.from(responses[1].data!),
      emergencies: (responses[2].data!['items'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList(),
      notes: (responses[3].data! as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList(),
      routines: (responses[4].data!['items'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList(),
      occurrences: (responses[5].data!['items'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList(),
      careProfile: Map<String, dynamic>.from(responses[6].data!),
    );
  }

  Future<Map<String, dynamic>> loadReport(
    String patientId,
    String period,
  ) async {
    final response = await session.api.dio.get<Map<String, dynamic>>(
      '/patients/$patientId/reports/summary',
      queryParameters: {'period': period},
    );
    return response.data!;
  }

  Future<void> addNote(String patientId, String text) async {
    await session.api.dio.post(
      '/doctor/patients/$patientId/notes',
      data: {'text': text, 'is_shared_with_caregiver': true},
    );
  }

  Future<void> addMedicationRoutine({
    required String patientId,
    required String timezone,
    required String medicationName,
    required String dosageText,
    required String time24h,
    String? instructions,
  }) async {
    final now = DateTime.now();
    final today =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    await session.api.dio.post(
      '/patients/$patientId/routines',
      data: {
        'type': 'medication',
        'title': medicationName,
        'description': instructions,
        'timezone': timezone,
        'start_date': today,
        'recurrence_rule': 'FREQ=DAILY',
        'scheduled_local_time': time24h,
        'requires_confirmation': true,
        'snooze_minutes': 10,
        'max_snoozes': 2,
        'medication': {
          'medication_name': medicationName,
          'dosage_text': dosageText,
          'instructions': instructions,
        },
      },
    );
  }
}
