import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../core/auth/providers.dart';
import '../../../../features/dashboard/presentation/screens/caregiver_home_screen.dart';
import '../../../../features/doctor/presentation/screens/doctor_home_screen.dart';
import '../../../../l10n/app_localizations.dart';

class DualDashboardScreen extends StatefulWidget {
  const DualDashboardScreen({super.key});

  @override
  State<DualDashboardScreen> createState() => _DualDashboardScreenState();
}

class _DualDashboardScreenState extends State<DualDashboardScreen> {
  late final AppSession _familySession;
  late final AppSession _doctorSession;

  @override
  void initState() {
    super.initState();
    _familySession = AppSession(storagePrefix: 'dual_family_');
    _doctorSession = AppSession(storagePrefix: 'dual_doctor_');
    _familySession.initialize();
    _doctorSession.initialize();
  }

  @override
  void dispose() {
    _familySession.dispose();
    _doctorSession.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    return DecoratedBox(
      decoration:
          BoxDecoration(gradient: RafeeqGradients.viewportFor(brightness)),
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 900;
            final phoneHeight = compact
                ? (constraints.maxHeight * 0.82).clamp(560.0, 760.0)
                : (constraints.maxHeight - 92).clamp(620.0, 820.0);
            return SingleChildScrollView(
              padding: const EdgeInsets.all(18),
              child: Column(
                children: [
                  Wrap(
                    alignment: WrapAlignment.center,
                    runAlignment: WrapAlignment.center,
                    spacing: 22,
                    runSpacing: 22,
                    children: [
                      _DemoPhone(
                        title:
                            _copy(context, 'لوحة العائلة', 'Family dashboard'),
                        subtitle: _copy(
                          context,
                          'مراقبة الروتين والتنبيهات والذاكرة',
                          'Routine, alerts, and memory support',
                        ),
                        height: phoneHeight,
                        child: ProviderScope(
                          overrides: [
                            appSessionProvider
                                .overrideWith((ref) => _familySession),
                          ],
                          child: const _DemoAutoLogin(
                            email: 'caregiver@demo.rafeeq.app',
                            password: 'Rafeeq-Test-2026!',
                            expectedRole: 'caregiver',
                            child: CaregiverHomeScreen(),
                          ),
                        ),
                      ),
                      _DemoPhone(
                        title:
                            _copy(context, 'لوحة الطبيب', 'Doctor dashboard'),
                        subtitle: _copy(
                          context,
                          'متابعة المرضى والتقارير والطوارئ',
                          'Patients, reports, and emergency review',
                        ),
                        height: phoneHeight,
                        child: ProviderScope(
                          overrides: [
                            appSessionProvider
                                .overrideWith((ref) => _doctorSession),
                          ],
                          child: const _DemoAutoLogin(
                            email: 'doctor@demo.rafeeq.app',
                            password: 'Rafeeq-Test-2026!',
                            expectedRole: 'doctor',
                            child: DoctorHomeScreen(),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  static String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;
}

class _DemoPhone extends StatelessWidget {
  const _DemoPhone({
    required this.title,
    required this.subtitle,
    required this.height,
    required this.child,
  });

  final String title;
  final String subtitle;
  final double height;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    return SizedBox(
      width: 390,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ],
            ),
          ),
          Container(
            height: height,
            decoration: BoxDecoration(
              color: RafeeqColors.ink,
              borderRadius: BorderRadius.circular(44),
              boxShadow: [
                BoxShadow(
                  color: RafeeqColors.primary.withValues(alpha: 0.18),
                  blurRadius: 34,
                  offset: const Offset(0, 18),
                ),
              ],
            ),
            padding: const EdgeInsets.all(10),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(34),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RafeeqGradients.pageFor(brightness),
                ),
                child: child,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DemoAutoLogin extends ConsumerStatefulWidget {
  const _DemoAutoLogin({
    required this.email,
    required this.password,
    required this.expectedRole,
    required this.child,
  });

  final String email;
  final String password;
  final String expectedRole;
  final Widget child;

  @override
  ConsumerState<_DemoAutoLogin> createState() => _DemoAutoLoginState();
}

class _DemoAutoLoginState extends ConsumerState<_DemoAutoLogin> {
  bool _loginStarted = false;

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    if (session.status == SessionStatus.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final wrongRole =
        session.user != null && session.user!.role != widget.expectedRole;
    if ((session.status == SessionStatus.unauthenticated || wrongRole) &&
        !_loginStarted) {
      _loginStarted = true;
      Future<void>.microtask(() async {
        if (wrongRole) {
          await session.logout();
        }
        await session.login(widget.email, widget.password);
        if (mounted) setState(() => _loginStarted = false);
      });
    }
    if (session.status != SessionStatus.authenticated ||
        session.user?.role != widget.expectedRole) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              const SizedBox(height: 14),
              Text(
                _copy(context, 'جاري تجهيز الحساب...',
                    'Preparing demo account...'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
              ),
              if (session.error != null) ...[
                const SizedBox(height: 12),
                Text(
                  session.error ?? strings.networkUnavailable,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.error,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ],
          ),
        ),
      );
    }
    return widget.child;
  }

  static String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;
}
