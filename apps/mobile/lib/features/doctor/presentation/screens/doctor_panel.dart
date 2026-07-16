import 'package:flutter/material.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../l10n/app_localizations.dart';
import '../../../../l10n/localized_values.dart';

class DoctorPanel extends StatefulWidget {
  const DoctorPanel({required this.session, super.key});
  final AppSession session;

  @override
  State<DoctorPanel> createState() => _DoctorPanelState();
}

class _DoctorPanelState extends State<DoctorPanel> {
  late Future<Map<String, List<dynamic>>> future;

  @override
  void initState() {
    super.initState();
    future = _load();
  }

  Future<Map<String, List<dynamic>>> _load() async {
    final id = widget.session.currentPatient!.id;
    final doctors = await widget.session.api.dio
        .get<List<dynamic>>('/patients/$id/doctors');
    final notes = await widget.session.api.dio
        .get<List<dynamic>>('/doctor/patients/$id/notes');
    return {'doctors': doctors.data!, 'notes': notes.data!};
  }

  void refresh() => setState(() => future = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(strings.doctorFollowUp),
        leading: IconButton(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close)),
      ),
      body: FutureBuilder<Map<String, List<dynamic>>>(
        future: future,
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final doctors = snapshot.data!['doctors']!;
          final notes = snapshot.data!['notes']!;
          return ListView(padding: const EdgeInsets.all(16), children: [
            if (doctors.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(children: [
                    const CircleAvatar(
                      radius: 40,
                      backgroundColor: RafeeqColors.lavender,
                      child: Icon(Icons.medical_services_outlined,
                          size: 38, color: RafeeqColors.primary),
                    ),
                    const SizedBox(height: 12),
                    Text(strings.noDoctorAssigned, textAlign: TextAlign.center),
                  ]),
                ),
              )
            else
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(children: [
                    CircleAvatar(
                      radius: 42,
                      backgroundColor: RafeeqColors.lavender,
                      child: Text(
                        doctors.first['full_name']
                            .toString()
                            .characters
                            .first
                            .toUpperCase(),
                        style: const TextStyle(
                          color: RafeeqColors.primary,
                          fontSize: 29,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(doctors.first['full_name'].toString(),
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 4),
                    Text(doctors.first['email'].toString(),
                        style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 13),
                    Row(children: [
                      Expanded(
                        child: FilledButton.tonalIcon(
                          onPressed: () =>
                              _showContact(doctors.first['email'].toString()),
                          icon: const Icon(Icons.call_outlined),
                          label: Text(strings.call),
                        ),
                      ),
                      const SizedBox(width: 9),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () =>
                              _showContact(doctors.first['email'].toString()),
                          icon: const Icon(Icons.mail_outline_rounded),
                          label: Text(strings.message),
                        ),
                      ),
                    ]),
                  ]),
                ),
              ),
            const SizedBox(height: 12),
            if (doctors.isEmpty)
              FilledButton.icon(
                  onPressed: _invite,
                  icon: const Icon(Icons.person_add_alt),
                  label: Text(strings.inviteRegisteredDoctor))
            else
              FilledButton.icon(
                onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(strings.reportReady)),
                ),
                icon: const Icon(Icons.send_outlined),
                label: Text(strings.sendLatestReport),
              ),
            const SizedBox(height: 20),
            Text(strings.followUpNotes,
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (notes.isEmpty)
              Text(strings.noSharedNotes)
            else
              ...notes.map((note) => Card(
                    child: ListTile(
                      leading: const Icon(Icons.note_outlined),
                      title: Text(note['text'].toString()),
                      subtitle:
                          Text(localizedDateTime(context, note['created_at'])),
                    ),
                  )),
          ]);
        },
      ),
    );
  }

  void _showContact(String value) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(value)));
  }

  Future<void> _invite() async {
    final strings = AppLocalizations.of(context)!;
    final controller = TextEditingController();
    final email = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.inviteDoctor),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.emailAddress,
          textDirection: TextDirection.ltr,
          decoration: InputDecoration(labelText: strings.doctorAccountEmail),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: Text(strings.cancel)),
          FilledButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, controller.text.trim()),
              child: Text(strings.invite)),
        ],
      ),
    );
    if (email == null || !email.contains('@')) return;
    try {
      await widget.session.api.dio.post(
          '/patients/${widget.session.currentPatient!.id}/doctors/invite',
          data: {'email': email});
      refresh();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(widget.session.api.errorMessage(error))));
      }
    }
  }
}
