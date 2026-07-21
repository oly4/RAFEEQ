import 'package:flutter/material.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../l10n/app_localizations.dart';
import '../../../../l10n/localized_values.dart';
import '../../../memories/presentation/screens/memory_voice_assistant_stub.dart'
    if (dart.library.html) '../../../memories/presentation/screens/memory_voice_assistant_web.dart';

class ActivitiesPanel extends StatefulWidget {
  const ActivitiesPanel(
      {required this.session,
      this.embedded = false,
      this.startPoemImmediately = false,
      super.key});
  final AppSession session;
  final bool embedded;
  final bool startPoemImmediately;

  @override
  State<ActivitiesPanel> createState() => _ActivitiesPanelState();
}

class _ActivitiesPanelState extends State<ActivitiesPanel> {
  late Future<List<Map<String, dynamic>>> future;

  @override
  void initState() {
    super.initState();
    future = _load();
    if (widget.startPoemImmediately) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _startPoemExercise();
      });
    }
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final response = await widget.session.api.dio.get<Map<String, dynamic>>(
        '/patients/${widget.session.currentPatient!.id}/activities');
    return (response.data!['items'] as List).cast<Map<String, dynamic>>();
  }

  void refresh() => setState(() => future = _load());

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: widget.embedded
          ? null
          : AppBar(
              title: Text(strings.activities),
              leading: IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close)),
            ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: future,
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.data!.isEmpty) {
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
              children: [
                _PoemExerciseCard(onPressed: _startPoemExercise),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _add,
                  icon: const Icon(Icons.add),
                  label: Text(strings.addActivity),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                  ),
                ),
                const SizedBox(height: 12),
                Center(child: Text(strings.addActivityPrompt)),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
            itemCount: snapshot.data!.length + 2,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              if (index == 0) {
                return _PoemExerciseCard(onPressed: _startPoemExercise);
              }
              if (index == 1) {
                return FilledButton.icon(
                  onPressed: _add,
                  icon: const Icon(Icons.add),
                  label: Text(strings.addActivity),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                  ),
                );
              }
              final activityIndex = index - 2;
              final activity = snapshot.data![activityIndex];
              final duration =
                  (activity['duration_minutes'] as num?)?.toInt() ?? 0;
              return RafeeqGlowCard(
                padding: EdgeInsets.zero,
                child: ListTile(
                  leading: Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      gradient: RafeeqGradients.softCardFor(
                        Theme.of(context).brightness,
                      ),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.psychology_alt_outlined),
                  ),
                  title: Text(activity['title'].toString()),
                  subtitle: Text(
                      '${localizedActivityType(strings, activity['type'])} '
                      '• ${strings.activityDuration(duration)}'),
                  trailing: FilledButton.tonal(
                    onPressed: () => _start(activity),
                    child: Text(strings.start),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Future<void> _add() async {
    final strings = AppLocalizations.of(context)!;
    final title = TextEditingController();
    var type = 'memory_exercise';
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(strings.newActivity),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: title,
                decoration: InputDecoration(labelText: strings.activityTitle)),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: type,
              decoration: InputDecoration(labelText: strings.activityType),
              items: [
                DropdownMenuItem(
                    value: 'memory_exercise',
                    child: Text(strings.activityMemoryExercise)),
                DropdownMenuItem(
                    value: 'recognize_photos',
                    child: Text(strings.activityRecognizePhotos)),
                DropdownMenuItem(
                    value: 'reading', child: Text(strings.activityReading)),
                DropdownMenuItem(
                    value: 'conversation',
                    child: Text(strings.activityConversation)),
                DropdownMenuItem(
                    value: 'calm_music',
                    child: Text(strings.activityCalmMusic)),
              ],
              onChanged: (value) => setDialogState(() => type = value ?? type),
            ),
          ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: Text(strings.cancel)),
            FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: Text(strings.save)),
          ],
        ),
      ),
    );
    if (accepted != true || title.text.trim().isEmpty) return;
    await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/activities',
        data: {
          'type': type,
          'title': title.text.trim(),
          'duration_minutes': 10,
        });
    refresh();
  }

  Future<void> _start(Map<String, dynamic> activity) async {
    final strings = AppLocalizations.of(context)!;
    final response = await widget.session.api.dio
        .post<Map<String, dynamic>>('/activities/${activity['id']}/start');
    if (!mounted) return;
    final completed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.play_circle_outline),
        title: Text(activity['title'].toString()),
        content: Text(activity['instructions']?.toString() ??
            strings.activityInstructions),
        actions: [
          FilledButton.icon(
            onPressed: () => Navigator.pop(dialogContext, true),
            icon: const Icon(Icons.check),
            label: Text(strings.activityDone),
          ),
        ],
      ),
    );
    if (completed == true) {
      await widget.session.api.dio
          .post('/activity-logs/${response.data!['id']}/complete');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(strings.activityCompletionRecorded)));
      }
    }
  }

  Future<void> _startPoemExercise() async {
    final patientId = widget.session.currentPatient!.id;
    var savedPoems = await _loadSavedPoems();
    if (!mounted) return;
    String? selectedPoemId;
    final poemStart = TextEditingController();
    final completion = TextEditingController();
    final poemTitle = TextEditingController();
    var isWorking = false;
    var transcript = '';
    var feedback = '';

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title:
              Text(_copy(context, 'تمرين إكمال القصيدة', 'Complete the poem')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(
                _copy(
                  context,
                  'اكتب الجزء اللي يقراه رفيق، واكتب التكملة الصحيحة. رفيق ما بيكملها بالبداية؛ بيخلي المريض يحاول.',
                  'Write the part Rafeeq should read, then write the correct completion. Rafeeq will let the patient try first.',
                ),
              ),
              const SizedBox(height: 12),
              if (savedPoems.isNotEmpty) ...[
                DropdownButtonFormField<String>(
                  initialValue: selectedPoemId,
                  decoration: InputDecoration(
                    labelText: _copy(
                        context, 'اختر قصيدة محفوظة', 'Choose saved poem'),
                  ),
                  items: savedPoems
                      .map(
                        (poem) => DropdownMenuItem<String>(
                          value: poem['id']?.toString(),
                          child: Text(poem['title']?.toString() ??
                              _copy(context, 'قصيدة', 'Poem')),
                        ),
                      )
                      .toList(),
                  onChanged: isWorking
                      ? null
                      : (value) {
                          final poem = savedPoems
                              .where((item) => item['id']?.toString() == value)
                              .firstOrNull;
                          if (poem == null) return;
                          setDialogState(() {
                            selectedPoemId = value;
                            poemTitle.text = poem['title']?.toString() ?? '';
                            poemStart.text =
                                poem['poem_start']?.toString() ?? '';
                            completion.text =
                                poem['expected_completion']?.toString() ?? '';
                            transcript = '';
                            feedback = _copy(
                              context,
                              'تم اختيار القصيدة. خل رفيق يقرأها أو ابدأ الاختبار.',
                              'Poem selected. Let Rafeeq read it, or start the test.',
                            );
                          });
                        },
                ),
                const SizedBox(height: 10),
              ],
              TextField(
                controller: poemTitle,
                decoration: InputDecoration(
                  labelText:
                      _copy(context, 'اسم القصيدة للحفظ', 'Poem name to save'),
                  hintText:
                      _copy(context, 'مثال: قصيدة المطر', 'Example: Rain poem'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: poemStart,
                minLines: 2,
                maxLines: 4,
                decoration: InputDecoration(
                  labelText: _copy(context, 'بداية القصيدة', 'Poem beginning'),
                  hintText: _copy(
                    context,
                    'مثال: قفا نبك من ذكرى حبيب ومنزل',
                    'Example: write the opening line',
                  ),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: completion,
                minLines: 2,
                maxLines: 4,
                decoration: InputDecoration(
                  labelText:
                      _copy(context, 'التكملة الصحيحة', 'Correct completion'),
                  hintText: _copy(
                    context,
                    'اكتب الجملة أو البيت اللي تبغى المريض يكمله',
                    'Write the phrase or verse you want the patient to complete',
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: [
                  OutlinedButton.icon(
                    onPressed: isWorking
                        ? null
                        : () async {
                            final title = poemTitle.text.trim().isEmpty
                                ? '${_copy(context, 'قصيدة', 'Poem')} ${savedPoems.length + 1}'
                                : poemTitle.text.trim();
                            final start = poemStart.text.trim();
                            final expected = completion.text.trim();
                            if (start.isEmpty || expected.isEmpty) {
                              setDialogState(() {
                                feedback = _copy(
                                  context,
                                  'اكتب بداية القصيدة والتكملة قبل الحفظ.',
                                  'Write the poem beginning and completion before saving.',
                                );
                              });
                              return;
                            }
                            setDialogState(() {
                              isWorking = true;
                              feedback = _copy(context, 'جاري حفظ القصيدة...',
                                  'Saving poem...');
                            });
                            try {
                              final saved = await _savePoem(
                                title: title,
                                poemStart: start,
                                expectedCompletion: expected,
                              );
                              savedPoems = await _loadSavedPoems();
                              if (!dialogContext.mounted) return;
                              setDialogState(() {
                                selectedPoemId = saved?['id']?.toString();
                                poemTitle.text = title;
                                feedback = _copy(
                                  context,
                                  'تم حفظ القصيدة. رفيق يقدر يستخدمها الآن.',
                                  'Poem saved. Rafeeq can use it now.',
                                );
                              });
                            } catch (_) {
                              if (!dialogContext.mounted) return;
                              setDialogState(() {
                                feedback = _copy(
                                  context,
                                  'تعذر حفظ القصيدة. حاول مرة ثانية.',
                                  'Could not save the poem. Try again.',
                                );
                              });
                            } finally {
                              if (dialogContext.mounted) {
                                setDialogState(() => isWorking = false);
                              }
                            }
                          },
                    icon: const Icon(Icons.bookmark_add_outlined),
                    label: Text(_copy(context, 'حفظ القصيدة', 'Save poem')),
                  ),
                  if (selectedPoemId != null)
                    OutlinedButton.icon(
                      onPressed: isWorking
                          ? null
                          : () async {
                              final id = selectedPoemId;
                              if (id == null) return;
                              setDialogState(() {
                                isWorking = true;
                                feedback = _copy(
                                  context,
                                  'جاري حذف القصيدة...',
                                  'Deleting poem...',
                                );
                              });
                              try {
                                await _deletePoem(id);
                                savedPoems = await _loadSavedPoems();
                                if (!dialogContext.mounted) return;
                                setDialogState(() {
                                  selectedPoemId = null;
                                  poemTitle.clear();
                                  poemStart.clear();
                                  completion.clear();
                                  feedback = _copy(context, 'تم حذف القصيدة.',
                                      'Poem deleted.');
                                });
                              } catch (_) {
                                if (!dialogContext.mounted) return;
                                setDialogState(() {
                                  feedback = _copy(context, 'تعذر حذف القصيدة.',
                                      'Could not delete poem.');
                                });
                              } finally {
                                if (dialogContext.mounted) {
                                  setDialogState(() => isWorking = false);
                                }
                              }
                            },
                      icon: const Icon(Icons.delete_outline),
                      label: Text(
                          _copy(context, 'حذف المختارة', 'Delete selected')),
                    ),
                ],
              ),
              if (transcript.isNotEmpty) ...[
                const SizedBox(height: 12),
                _SoftInfoBox(
                    text: _copy(context, 'سمعت من المريض: $transcript',
                        'Patient said: $transcript')),
              ],
              if (feedback.isNotEmpty) ...[
                const SizedBox(height: 12),
                _SoftInfoBox(text: feedback),
              ],
            ]),
          ),
          actions: [
            TextButton(
              onPressed: isWorking ? null : () => Navigator.pop(dialogContext),
              child: Text(_copy(context, 'إغلاق', 'Close')),
            ),
            TextButton.icon(
              onPressed: isWorking
                  ? null
                  : () async {
                      final start = poemStart.text.trim();
                      if (start.isEmpty) {
                        setDialogState(() {
                          feedback = _copy(context, 'اكتب بداية القصيدة أولًا.',
                              'Write the poem beginning first.');
                        });
                        return;
                      }
                      setDialogState(() {
                        isWorking = true;
                        feedback = _copy(
                          context,
                          'رفيق يجهز الصوت من OpenAI...',
                          'Rafeeq is preparing the OpenAI voice...',
                        );
                      });
                      try {
                        final response = await widget.session.api.dio
                            .post<Map<String, dynamic>>(
                          '/patients/$patientId/activities/poem-speech',
                          data: {'poem_start': start},
                        );
                        final audio =
                            response.data?['audio_data_url']?.toString();
                        if (audio == null || audio.isEmpty) {
                          throw StateError('OpenAI audio is unavailable');
                        }
                        await playMemoryAudioDataUrl(audio);
                        if (!dialogContext.mounted) return;
                        setDialogState(() {
                          feedback = _copy(
                            context,
                            'رفيق قرأ البداية. الآن اضغط “اسمع تكملة المريض”.',
                            'Rafeeq read the beginning. Now tap “Listen to patient completion”.',
                          );
                        });
                      } catch (_) {
                        if (!dialogContext.mounted) return;
                        setDialogState(() {
                          feedback = _copy(
                            context,
                            'تعذر تشغيل صوت OpenAI. تأكد من مفتاح OpenAI والاتصال.',
                            'Could not play the OpenAI voice. Check the OpenAI key and connection.',
                          );
                        });
                      } finally {
                        if (dialogContext.mounted) {
                          setDialogState(() => isWorking = false);
                        }
                      }
                    },
              icon: const Icon(Icons.volume_up_outlined),
              label: Text(_copy(context, 'خل رفيق يقرأ', 'Let Rafeeq read')),
            ),
            FilledButton.icon(
              onPressed: isWorking
                  ? null
                  : () async {
                      final start = poemStart.text.trim();
                      final expected = completion.text.trim();
                      if (start.isEmpty || expected.isEmpty) {
                        setDialogState(() {
                          feedback = _copy(
                            context,
                            'اكتب بداية القصيدة والتكملة الصحيحة أولًا.',
                            'Write the poem beginning and correct completion first.',
                          );
                        });
                        return;
                      }
                      setDialogState(() {
                        isWorking = true;
                        feedback = _copy(context, 'سجل جواب المريض الآن...',
                            'Record the patient answer now...');
                      });
                      try {
                        final recorded = await recordMemoryAudioAnswer();
                        if (!dialogContext.mounted) return;
                        if (recorded == null) {
                          setDialogState(() {
                            feedback = _copy(
                              context,
                              'ما وصل تسجيل واضح. حاول مرة ثانية.',
                              'No clear recording was received. Try again.',
                            );
                          });
                          return;
                        }
                        final response = await widget.session.api.dio
                            .post<Map<String, dynamic>>(
                          '/patients/$patientId/activities/poem-voice-test',
                          data: {
                            'poem_start': start,
                            'expected_completion': expected,
                            'audio_data_url': recorded.dataUrl,
                          },
                        );
                        final data = response.data ?? const {};
                        final audio = data['audio_data_url']?.toString() ?? '';
                        setDialogState(() {
                          transcript =
                              data['transcript']?.toString().trim() ?? '';
                          feedback =
                              data['assistant_text']?.toString().trim() ??
                                  _copy(context, 'تم اختبار الإجابة.',
                                      'Answer checked.');
                        });
                        if (audio.isNotEmpty) {
                          await playMemoryAudioDataUrl(audio);
                        }
                      } catch (_) {
                        if (!dialogContext.mounted) return;
                        setDialogState(() {
                          feedback = _copy(
                            context,
                            'تعذر اختبار القصيدة بالصوت. تأكد من إذن المايك والاتصال.',
                            'Could not test the poem by voice. Check microphone permission and connection.',
                          );
                        });
                      } finally {
                        if (dialogContext.mounted) {
                          setDialogState(() => isWorking = false);
                        }
                      }
                    },
              icon: const Icon(Icons.mic_none_outlined),
              label: Text(isWorking
                  ? _copy(context, 'انتظر...', 'Wait...')
                  : _copy(context, 'اسمع تكملة المريض',
                      'Listen to patient completion')),
            ),
          ],
        ),
      ),
    );
  }

  Future<List<Map<String, dynamic>>> _loadSavedPoems() async {
    final patientId = widget.session.currentPatient!.id;
    final response = await widget.session.api.dio.get<List<dynamic>>(
      '/patients/$patientId/activities/poems',
    );
    return (response.data ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>?> _savePoem({
    required String title,
    required String poemStart,
    required String expectedCompletion,
  }) async {
    final patientId = widget.session.currentPatient!.id;
    final response = await widget.session.api.dio.post<Map<String, dynamic>>(
      '/patients/$patientId/activities/poems',
      data: {
        'title': title,
        'poem_start': poemStart,
        'expected_completion': expectedCompletion,
      },
    );
    refresh();
    return response.data;
  }

  Future<void> _deletePoem(String poemId) async {
    await widget.session.api.dio.delete('/activities/poems/$poemId');
    refresh();
  }

  static String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;
}

class _PoemExerciseCard extends StatelessWidget {
  const _PoemExerciseCard({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? const Color(0xFFF7F2FF) : RafeeqColors.ink;
    final subtitleColor = isDark ? RafeeqColors.mutedDark : RafeeqColors.muted;
    return RafeeqGlowCard(
      hero: true,
      gradient: LinearGradient(
        begin: AlignmentDirectional.topStart,
        end: AlignmentDirectional.bottomEnd,
        colors: isDark
            ? const [
                Color(0xFF2B224A),
                Color(0xFF1D1733),
                Color(0xFF171229),
              ]
            : const [RafeeqColors.lavender, Colors.white],
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              gradient: RafeeqGradients.primary,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: RafeeqColors.primary.withValues(alpha: 0.24),
                  blurRadius: 16,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: const Icon(
              Icons.auto_stories_outlined,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isArabic ? 'تمرين إكمال القصيدة' : 'Complete the poem',
                  style: TextStyle(
                    color: textColor,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  isArabic
                      ? 'رفيق يقرأ البداية بصوت OpenAI، والمريض يكملها من الذاكرة.'
                      : 'Rafeeq reads the beginning with OpenAI voice, and the patient completes it from memory.',
                  style: TextStyle(color: subtitleColor),
                ),
              ],
            ),
          ),
          FilledButton.tonal(
            onPressed: onPressed,
            child: Text(isArabic ? 'ابدأ' : 'Start'),
          ),
        ],
      ),
    );
  }
}

class _SoftInfoBox extends StatelessWidget {
  const _SoftInfoBox({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2148) : const Color(0xFFF4EEFF),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(text, textAlign: TextAlign.center),
    );
  }
}
