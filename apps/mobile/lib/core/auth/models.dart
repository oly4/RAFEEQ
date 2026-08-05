class AppUser {
  const AppUser(
      {required this.id,
      required this.role,
      required this.fullName,
      required this.email});
  final String id;
  final String role;
  final String fullName;
  final String email;

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        id: json['id'] as String,
        role: json['role'] as String,
        fullName: json['full_name'] as String,
        email: json['email'] as String,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role,
        'full_name': fullName,
        'email': email,
      };
}

class PatientSummary {
  const PatientSummary(
      {required this.id, required this.displayName, required this.timezone});
  final String id;
  final String displayName;
  final String timezone;

  factory PatientSummary.fromJson(Map<String, dynamic> json) => PatientSummary(
        id: json['id'] as String,
        displayName: json['display_name'] as String,
        timezone: json['timezone'] as String,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'display_name': displayName,
        'timezone': timezone,
      };
}
