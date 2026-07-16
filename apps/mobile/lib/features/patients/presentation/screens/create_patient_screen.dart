import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/auth/providers.dart';
import '../../../../l10n/app_localizations.dart';

class CreatePatientScreen extends ConsumerStatefulWidget {
  const CreatePatientScreen({super.key});

  @override
  ConsumerState<CreatePatientScreen> createState() =>
      _CreatePatientScreenState();
}

class _CreatePatientScreenState extends ConsumerState<CreatePatientScreen> {
  final controller = TextEditingController();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final session = ref.watch(appSessionProvider);
    return Scaffold(
      appBar: AppBar(title: Text(strings.createPatient)),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(children: [
              const Icon(Icons.elderly_outlined, size: 88),
              const SizedBox(height: 24),
              Text(strings.createPatient,
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 24),
              TextField(
                controller: controller,
                autofocus: true,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                    labelText: strings.patientName,
                    prefixIcon: const Icon(Icons.badge_outlined)),
              ),
              if (session.error != null) ...[
                const SizedBox(height: 12),
                Text(session.error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ],
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton.icon(
                  onPressed: session.busy || controller.text.trim().length < 2
                      ? null
                      : () => session.createPatient(controller.text.trim()),
                  icon: const Icon(Icons.person_add_alt_1),
                  label: Text(strings.continueLabel),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
