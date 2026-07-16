import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/auth/app_session.dart';
import '../core/auth/providers.dart';
import '../features/dashboard/presentation/screens/caregiver_home_screen.dart';
import '../features/camera/presentation/screens/camera_test_screen.dart';
import '../features/doctor/presentation/screens/doctor_home_screen.dart';
import '../features/onboarding/presentation/screens/auth_screen.dart';
import '../features/onboarding/presentation/screens/role_entry_screen.dart';
import '../features/onboarding/presentation/screens/splash_screen.dart';
import '../features/onboarding/presentation/screens/welcome_screen.dart';
import '../features/patients/presentation/screens/create_patient_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final session = ref.read(appSessionProvider);
  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: session,
    redirect: (context, state) {
      final location = state.matchedLocation;
      if (session.status == SessionStatus.loading) {
        return location == '/splash' ? null : '/splash';
      }
      if (session.status == SessionStatus.unauthenticated) {
        return {'/welcome', '/access', '/login', '/register', '/camera-test'}
                .contains(location)
            ? null
            : '/welcome';
      }
      if (session.user?.role == 'doctor') {
        return location == '/doctor' ? null : '/doctor';
      }
      if (session.patients.isEmpty) {
        return location == '/patient/new' ? null : '/patient/new';
      }
      return location == '/home' ? null : '/home';
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      GoRoute(path: '/welcome', builder: (_, __) => const WelcomeScreen()),
      GoRoute(
        path: '/access',
        builder: (_, state) => RoleEntryScreen(
          role: state.uri.queryParameters['role'] == 'doctor'
              ? 'doctor'
              : 'caregiver',
        ),
      ),
      GoRoute(
          path: '/login',
          builder: (_, state) => AuthScreen(
                registerMode: false,
                initialRole: state.uri.queryParameters['role'] ?? 'caregiver',
              )),
      GoRoute(
          path: '/register',
          builder: (_, state) => AuthScreen(
                registerMode: true,
                initialRole: state.uri.queryParameters['role'] ?? 'caregiver',
              )),
      GoRoute(
          path: '/camera-test', builder: (_, __) => const CameraTestScreen()),
      GoRoute(
          path: '/patient/new',
          builder: (_, __) => const CreatePatientScreen()),
      GoRoute(path: '/home', builder: (_, __) => const CaregiverHomeScreen()),
      GoRoute(path: '/doctor', builder: (_, __) => const DoctorHomeScreen()),
    ],
  );
});
