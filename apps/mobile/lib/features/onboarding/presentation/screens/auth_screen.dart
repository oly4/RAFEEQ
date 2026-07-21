import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/providers.dart';
import '../../../../core/widgets/rafeeq_robot.dart';
import '../../../../l10n/app_localizations.dart';
import '../widgets/onboarding_quick_settings.dart';

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({
    required this.registerMode,
    this.initialRole = 'caregiver',
    super.key,
  });

  final bool registerMode;
  final String initialRole;

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final formKey = GlobalKey<FormState>();
  final nameController = TextEditingController();
  final emailController = TextEditingController();
  final passwordController = TextEditingController();
  late String selectedRole;

  @override
  void initState() {
    super.initState();
    selectedRole = widget.initialRole == 'doctor' ? 'doctor' : 'caregiver';
  }

  @override
  void dispose() {
    nameController.dispose();
    emailController.dispose();
    passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    final accessLabel =
        selectedRole == 'doctor' ? strings.doctorAccess : strings.familyAccess;
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
          onPressed: () => context.go('/welcome'),
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
        ),
        title: Text(strings.appName),
      ),
      body: SafeArea(
        top: false,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: RafeeqGradients.pageFor(Theme.of(context).brightness),
          ),
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(22, 8, 22, 28),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 430),
                child: Form(
                  key: formKey,
                  child: Column(children: [
                    const Align(
                      alignment: AlignmentDirectional.centerEnd,
                      child: OnboardingQuickSettings(),
                    ),
                    const SizedBox(height: 12),
                    RafeeqRobot(
                      semanticLabel: strings.robotSemanticLabel,
                      size: 108,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      widget.registerMode
                          ? strings.createAccount
                          : strings.welcomeBack,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 7),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 7),
                      decoration: BoxDecoration(
                        color: RafeeqColors.lavender,
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        accessLabel,
                        style: const TextStyle(
                          color: RafeeqColors.primaryDark,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      strings.secureAccessSubtitle,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: RafeeqColors.muted),
                    ),
                    const SizedBox(height: 24),
                    RafeeqGlowCard(
                      hero: true,
                      child: Column(children: [
                        if (widget.registerMode) ...[
                          TextFormField(
                            controller: nameController,
                            textInputAction: TextInputAction.next,
                            decoration: InputDecoration(
                              labelText: strings.fullName,
                              prefixIcon: const Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                (value?.trim().length ?? 0) < 2
                                    ? strings.fullNameRequired
                                    : null,
                          ),
                          const SizedBox(height: 14),
                          SegmentedButton<String>(
                            showSelectedIcon: false,
                            segments: [
                              ButtonSegment(
                                value: 'caregiver',
                                icon: const Icon(Icons.family_restroom_rounded),
                                label: Text(strings.caregiver),
                              ),
                              ButtonSegment(
                                value: 'doctor',
                                icon:
                                    const Icon(Icons.medical_services_outlined),
                                label: Text(strings.doctor),
                              ),
                            ],
                            selected: {selectedRole},
                            onSelectionChanged: (value) =>
                                setState(() => selectedRole = value.first),
                          ),
                          const SizedBox(height: 14),
                        ],
                        TextFormField(
                          controller: emailController,
                          keyboardType: TextInputType.emailAddress,
                          textDirection: TextDirection.ltr,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.email],
                          decoration: InputDecoration(
                            labelText: strings.email,
                            prefixIcon: const Icon(Icons.email_outlined),
                          ),
                          validator: (value) => !(value?.contains('@') ?? false)
                              ? strings.validEmailRequired
                              : null,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: passwordController,
                          obscureText: true,
                          textDirection: TextDirection.ltr,
                          autofillHints: const [AutofillHints.password],
                          decoration: InputDecoration(
                            labelText: strings.password,
                            prefixIcon: const Icon(Icons.lock_outline),
                          ),
                          validator: (value) => (value?.length ?? 0) < 8
                              ? strings.passwordLengthRequired
                              : null,
                          onFieldSubmitted: (_) => _submit(),
                        ),
                        if (session.error != null) ...[
                          const SizedBox(height: 14),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color:
                                  Theme.of(context).colorScheme.errorContainer,
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: Semantics(
                              liveRegion: true,
                              child: Text(
                                session.error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onErrorContainer,
                                ),
                              ),
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: session.busy ? null : _submit,
                            child: session.busy
                                ? const SizedBox(
                                    width: 24,
                                    height: 24,
                                    child: CircularProgressIndicator(
                                      color: Colors.white,
                                      strokeWidth: 2,
                                    ),
                                  )
                                : Text(
                                    widget.registerMode
                                        ? strings.createAccount
                                        : strings.login,
                                  ),
                          ),
                        ),
                      ]),
                    ),
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () => context.go(
                        widget.registerMode
                            ? '/login?role=$selectedRole'
                            : '/register?role=$selectedRole',
                      ),
                      child: Text(
                        widget.registerMode
                            ? strings.login
                            : strings.createAccount,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      strings.byContinuing,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (!formKey.currentState!.validate()) return;
    final session = ref.read(appSessionProvider);
    if (widget.registerMode) {
      await session.register(
        name: nameController.text.trim(),
        email: emailController.text.trim(),
        password: passwordController.text,
        role: selectedRole,
      );
    } else {
      await session.login(emailController.text.trim(), passwordController.text);
    }
  }
}
