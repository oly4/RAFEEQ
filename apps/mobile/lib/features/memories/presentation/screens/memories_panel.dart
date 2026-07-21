import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/app_session.dart';
import '../../../../l10n/app_localizations.dart';
import 'memory_image_picker_stub.dart'
    if (dart.library.html) 'memory_image_picker_web.dart';
import 'memory_voice_assistant_stub.dart'
    if (dart.library.html) 'memory_voice_assistant_web.dart';

class MemoriesPanel extends StatefulWidget {
  const MemoriesPanel(
      {required this.session,
      this.embedded = false,
      this.startFirstPhotoTest = false,
      super.key});
  final AppSession session;
  final bool embedded;
  final bool startFirstPhotoTest;

  @override
  State<MemoriesPanel> createState() => _MemoriesPanelState();
}

class _MemoriesPanelState extends State<MemoriesPanel> {
  late Future<Map<String, List<Map<String, dynamic>>>> future;

  @override
  void initState() {
    super.initState();
    future = _load();
    if (widget.startFirstPhotoTest) {
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _startFirstPhotoTest());
    }
  }

  Future<Map<String, List<Map<String, dynamic>>>> _load() async {
    final id = widget.session.currentPatient!.id;
    final categories = await widget.session.api.dio
        .get<List<dynamic>>('/patients/$id/memory-categories');
    final memories = await widget.session.api.dio
        .get<Map<String, dynamic>>('/patients/$id/memories');
    return {
      'categories': categories.data!.cast<Map<String, dynamic>>(),
      'memories':
          (memories.data!['items'] as List).cast<Map<String, dynamic>>(),
    };
  }

  void refresh() => setState(() => future = _load());

  Future<void> _startFirstPhotoTest() async {
    final data = await future;
    if (!mounted) return;
    final memories = data['memories']!;
    final photo =
        memories.where((memory) => _imageUrl(memory) != null).firstOrNull;
    if (photo == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_copy(
              context,
              'ما فيه صور جاهزة للاختبار. ارفع صورة أولًا.',
              'No photos are ready for testing. Upload a photo first.')),
        ),
      );
      return;
    }
    await _openMemoryTest(photo);
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final content = FutureBuilder<Map<String, List<Map<String, dynamic>>>>(
      future: future,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final categories = snapshot.data!['categories']!;
        final memories = snapshot.data!['memories']!;
        final photoMemories =
            memories.where((memory) => _imageUrl(memory) != null).toList();
        final body = ListView(
          padding: widget.embedded
              ? const EdgeInsets.fromLTRB(16, 8, 16, 124)
              : const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            _HeroCard(
              title: strings.memorySupportSubtitle,
              subtitle: _copy(
                context,
                'ارفع صور العائلة والذكريات، ثم اختبر المريض بطريقة لطيفة مع تلميحات عند الحاجة.',
                'Upload family photos and memories, then test the patient gently with hints when needed.',
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Text(
                    _copy(context, 'ألبومات الذكريات', 'Memory albums'),
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                TextButton.icon(
                  onPressed: _addCategory,
                  icon: const Icon(Icons.add, size: 17),
                  label: Text(strings.addCategory),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (categories.isEmpty)
              RafeeqGlowCard(
                child: Text(strings.noMemoriesPrompt),
              )
            else
              _CategoryStrip(categories: categories, memories: memories),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: Text(
                    _copy(context, 'صور اختبار الذاكرة', 'Memory test photos'),
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: _addMemory,
              icon: const Icon(Icons.add_photo_alternate_outlined),
              label: Text(
                  _copy(context, 'رفع صورة للذاكرة', 'Upload memory photo')),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(52),
              ),
            ),
            const SizedBox(height: 12),
            if (photoMemories.isEmpty)
              RafeeqGlowCard(
                child: Column(
                  children: [
                    const Icon(Icons.photo_camera_back_outlined,
                        size: 42, color: RafeeqColors.primary),
                    const SizedBox(height: 10),
                    Text(
                      _copy(
                        context,
                        'ابدأ برفع صورة لشخص يعرفه المريض، واكتب الاسم والتلميح.',
                        'Start by uploading a photo of someone the patient knows, then add the name and hint.',
                      ),
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              )
            else
              ...photoMemories.map(
                (memory) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _MemoryPhotoCard(
                    memory: memory,
                    imageUrl: _imageUrl(memory)!,
                    labels: _labels(memory),
                    onTest: () => _openMemoryTest(memory),
                    onEdit: () => _editMemory(memory, categories),
                    onDelete: () => _deleteMemory(memory),
                  ),
                ),
              ),
            if (!widget.embedded) ...[
              const SizedBox(height: 8),
              Text(
                _copy(
                  context,
                  'كل الصور هنا تُستخدم كاختبار ذاكرة فقط. لاحقًا نربطها بصوت رفيق عشان يسأل المريض ويعطي تلميح بالصوت.',
                  'Photos here are used only for memory testing. Rafeeq can ask the patient and provide voice hints.',
                ),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        );
        return body;
      },
    );
    if (widget.embedded) return content;
    return Scaffold(
      appBar: AppBar(
        title: Text(strings.memorySupport),
        leading: IconButton(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close)),
      ),
      body: content,
    );
  }

  Future<void> _addCategory() async {
    final strings = AppLocalizations.of(context)!;
    final controller = TextEditingController();
    final value = await _textDialog(
        strings.newCategory, strings.categoryName, controller);
    if (value == null) return;
    await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/memory-categories',
        data: {'name': value});
    refresh();
  }

  Future<void> _addMemory() async {
    final strings = AppLocalizations.of(context)!;
    final data = await future;
    if (!mounted) return;
    var categories = data['categories']!;
    if (categories.isEmpty) {
      await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/memory-categories',
        data: {'name': _copy(context, 'العائلة', 'Family')},
      );
      final refreshed = await _load();
      if (!mounted) return;
      categories = refreshed['categories']!;
      setState(() => future = Future.value(refreshed));
    }

    final title = TextEditingController();
    final description = TextEditingController();
    final labels = TextEditingController();
    final hint = TextEditingController();
    var categoryId = categories.first['id'].toString();
    Uint8List? imageBytes;
    String? imageMimeType;

    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_copy(context, 'إضافة صورة للذاكرة', 'Add memory photo')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              InkWell(
                borderRadius: BorderRadius.circular(18),
                onTap: () async {
                  try {
                    final picked = await pickMemoryImage();
                    if (!dialogContext.mounted) return;
                    if (picked == null) {
                      ScaffoldMessenger.of(dialogContext).showSnackBar(
                        SnackBar(
                          content: Text(_copy(
                            context,
                            'ما تم اختيار صورة. حاول مرة ثانية.',
                            'No photo was selected. Try again.',
                          )),
                        ),
                      );
                      return;
                    }
                    if (picked.bytes.isEmpty) {
                      ScaffoldMessenger.of(dialogContext).showSnackBar(
                        SnackBar(
                          content: Text(_copy(
                            context,
                            'الصورة فاضية أو غير مدعومة.',
                            'The photo is empty or unsupported.',
                          )),
                        ),
                      );
                      return;
                    }
                    setDialogState(() {
                      imageBytes = picked.bytes;
                      imageMimeType = picked.mimeType;
                    });
                  } catch (error) {
                    if (!dialogContext.mounted) return;
                    ScaffoldMessenger.of(dialogContext).showSnackBar(
                      SnackBar(
                          content: Text(_copy(
                              context,
                              'تعذر اختيار الصورة: $error',
                              'Could not choose the photo: $error'))),
                    );
                  }
                },
                child: Container(
                  width: double.infinity,
                  height: 150,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF4EEFF),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: const Color(0xFFE4D7FA)),
                  ),
                  child: imageBytes == null
                      ? Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.add_photo_alternate_outlined,
                                color: RafeeqColors.primary, size: 42),
                            const SizedBox(height: 8),
                            Text(_copy(context, 'اضغط لاختيار صورة',
                                'Tap to choose a photo')),
                          ],
                        )
                      : ClipRRect(
                          borderRadius: BorderRadius.circular(18),
                          child: Image.memory(
                            imageBytes!,
                            fit: BoxFit.cover,
                            width: double.infinity,
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: title,
                decoration: InputDecoration(
                  labelText: _copy(context, 'عنوان الصورة', 'Photo title'),
                  hintText: _copy(context, 'مثال: صورة سارة بنت أحمد',
                      'Example: Sarah Ahmed photo'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: labels,
                decoration: InputDecoration(
                  labelText: _copy(context, 'الأسماء الموجودة بالصورة',
                      'Names in the photo'),
                  hintText: _copy(context, 'مثال: سارة، أم أحمد',
                      'Example: Sarah, Ahmed’s mother'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: hint,
                decoration: InputDecoration(
                  labelText:
                      _copy(context, 'تلميح للمريض', 'Hint for the patient'),
                  hintText: _copy(context, 'مثال: هذي بنتك اللي تزورك كل جمعة',
                      'Example: This is your daughter who visits every Friday'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: description,
                minLines: 2,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: _copy(context, 'وصف قصير', 'Short description'),
                  hintText: _copy(context, 'مثال: كانت الصورة في بيت العائلة.',
                      'Example: This photo was at the family house.'),
                ),
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                initialValue: categoryId,
                decoration: InputDecoration(labelText: strings.category),
                items: categories
                    .map((item) => DropdownMenuItem(
                        value: item['id'].toString(),
                        child: Text(item['name'].toString())))
                    .toList(),
                onChanged: (value) =>
                    setDialogState(() => categoryId = value ?? categoryId),
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
        ),
      ),
    );
    final cleanTitle = title.text.trim();
    if (accepted != true || cleanTitle.isEmpty || imageBytes == null) {
      if (accepted == true && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(_copy(context, 'اختر صورة واكتب عنوانها أولًا',
                  'Choose a photo and write its title first.'))),
        );
      }
      return;
    }

    final mimeType = imageMimeType ?? _mimeFromBytes(imageBytes!);
    final uploadDataUrl =
        'data:$mimeType;base64,${base64Encode(imageBytes!.toList())}';
    try {
      await widget.session.api.dio.post(
        '/patients/${widget.session.currentPatient!.id}/memories',
        data: {
          'category_id': categoryId,
          'title': cleanTitle,
          'description':
              description.text.trim().isEmpty ? null : description.text.trim(),
          'media_type': 'photo',
          'upload_data_url': uploadDataUrl,
          'people_labels': _splitLabels(labels.text),
          'spoken_prompt': hint.text.trim().isEmpty ? null : hint.text.trim(),
        },
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(_copy(
                context, 'تم رفع الصورة للألبوم', 'Photo uploaded to album'))),
      );
      refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(_copy(
                context,
                'فشل رفع الصورة: ${_friendlyUploadError(error)}',
                'Photo upload failed: ${_friendlyUploadError(error)}'))),
      );
    }
  }

  Future<void> _editMemory(
    Map<String, dynamic> memory,
    List<Map<String, dynamic>> categories,
  ) async {
    final strings = AppLocalizations.of(context)!;
    final title =
        TextEditingController(text: memory['title']?.toString() ?? '');
    final description =
        TextEditingController(text: memory['description']?.toString() ?? '');
    final labels = TextEditingController(text: _labels(memory).join('، '));
    final hint =
        TextEditingController(text: memory['spoken_prompt']?.toString() ?? '');
    var categoryId = memory['category_id']?.toString() ??
        (categories.isNotEmpty ? categories.first['id'].toString() : '');
    if (categories.isNotEmpty &&
        !categories.any((item) => item['id'].toString() == categoryId)) {
      categoryId = categories.first['id'].toString();
    }

    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_copy(context, 'تعديل الصورة', 'Edit photo')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                controller: title,
                decoration: InputDecoration(
                  labelText: _copy(context, 'عنوان الصورة', 'Photo title'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: labels,
                decoration: InputDecoration(
                  labelText: _copy(context, 'الأسماء الموجودة بالصورة',
                      'Names in the photo'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: hint,
                decoration: InputDecoration(
                  labelText:
                      _copy(context, 'تلميح للمريض', 'Hint for the patient'),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: description,
                minLines: 2,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: _copy(context, 'وصف قصير', 'Short description'),
                ),
              ),
              const SizedBox(height: 10),
              if (categories.isNotEmpty)
                DropdownButtonFormField<String>(
                  initialValue: categoryId,
                  decoration: InputDecoration(labelText: strings.category),
                  items: categories
                      .map((item) => DropdownMenuItem(
                            value: item['id'].toString(),
                            child: Text(item['name'].toString()),
                          ))
                      .toList(),
                  onChanged: (value) =>
                      setDialogState(() => categoryId = value ?? categoryId),
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
        ),
      ),
    );

    if (accepted != true || title.text.trim().isEmpty) return;
    try {
      await widget.session.api.dio.patch(
        '/memories/${memory['id']}',
        data: {
          if (categoryId.isNotEmpty) 'category_id': categoryId,
          'title': title.text.trim(),
          'description':
              description.text.trim().isEmpty ? null : description.text.trim(),
          'people_labels': _splitLabels(labels.text),
          'spoken_prompt': hint.text.trim().isEmpty ? null : hint.text.trim(),
        },
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(_copy(context, 'تم تحديث الصورة', 'Photo updated'))),
      );
      refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.session.api.errorMessage(error))),
      );
    }
  }

  Future<void> _deleteMemory(Map<String, dynamic> memory) async {
    final strings = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.delete_outline, color: RafeeqColors.danger),
        title: Text(_copy(context, 'حذف الصورة؟', 'Delete photo?')),
        content: Text(_copy(
          context,
          'سيتم حذف "${memory['title']}" من الألبوم.',
          'This will delete "${memory['title']}" from the album.',
        )),
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
      await widget.session.api.dio.delete('/memories/${memory['id']}');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(_copy(context, 'تم حذف الصورة', 'Photo deleted'))),
      );
      refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.session.api.errorMessage(error))),
      );
    }
  }

  Future<void> _openMemoryTest(Map<String, dynamic> memory) async {
    final answer = TextEditingController();
    var feedback = '';
    var hintShown = false;
    var lastTranscript = '';
    var isListening = false;
    final imageUrl = _imageUrl(memory)!;
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    String tr(String ar, String en) => isArabic ? ar : en;
    final hint = memory['spoken_prompt']?.toString().trim().isNotEmpty == true
        ? memory['spoken_prompt'].toString()
        : memory['description']?.toString() ??
            tr('حاول تتذكر متى شفت هالشخص.',
                'Try to remember when you saw this person.');
    final question =
        tr('وش اسم الشخص اللي في الصورة؟', 'Who is in this photo?');
    final introPrompt = tr('$question خذ وقتك، وإذا احتجت تلميح أنا معك.',
        '$question Take your time. If you need a hint, I am with you.');
    final noClearFeedback = tr('ما سمعت جواب واضح. خلنا نعيد السؤال بهدوء.',
        'I did not hear a clear answer. Let’s repeat the question calmly.');
    final noClearSpeech = tr('ما سمعت جواب واضح. $question',
        'I did not hear a clear answer. $question');
    final aiFailureFeedback = tr(
        'تعذر الاتصال بالذكاء الاصطناعي. خلنا نحاول مرة ثانية.',
        'Could not connect to AI. Let’s try again.');
    final aiFailureWithHint = tr(
        'تعذر الاتصال بالذكاء الاصطناعي. تلميح بسيط: $hint',
        'Could not connect to AI. Simple hint: $hint');

    Future<void>.delayed(const Duration(milliseconds: 500), () {
      _speakOpenAiMemory(memory, introPrompt);
    });

    Future<void> handleAnswer(
      void Function(void Function()) setDialogState, {
      required String value,
    }) async {
      final cleanValue = value.trim();
      if (cleanValue.isEmpty) {
        setDialogState(() {
          feedback = noClearFeedback;
        });
        await speakMemoryText(noClearSpeech);
        return;
      }
      try {
        final patientId = widget.session.currentPatient!.id;
        final response =
            await widget.session.api.dio.post<Map<String, dynamic>>(
          '/patients/$patientId/memories/${memory['id']}/ai-test',
          data: {'answer_text': cleanValue},
        );
        final data = response.data ?? const <String, dynamic>{};
        final matched = data['matched'] == true;
        final apiHint = data['hint_text']?.toString().trim();
        final effectiveHint =
            apiHint != null && apiHint.isNotEmpty ? apiHint : hint;
        final assistantText = matched
            ? tr('صح عليك، ممتاز. ذاكرتك جميلة.',
                'That’s right, excellent. Your memory is doing well.')
            : tr(
                'قريب. تلميح بسيط: $effectiveHint. خذ راحتك وحاول مرة ثانية.',
                'Close. A simple hint: $effectiveHint. Take your time and try again.',
              );
        setDialogState(() {
          feedback = assistantText;
          hintShown = !matched;
        });
        await _speakOpenAiMemory(memory, assistantText);
      } catch (_) {
        setDialogState(() {
          feedback = aiFailureFeedback;
          hintShown = true;
        });
        await _speakOpenAiMemory(memory, aiFailureWithHint);
      }
    }

    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_copy(context, 'اختبار الذاكرة', 'Memory test')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Image.network(
                  imageUrl,
                  height: 190,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    height: 160,
                    color: const Color(0xFFF4EEFF),
                    child: const Center(
                      child: Icon(Icons.broken_image_outlined,
                          color: RafeeqColors.primary, size: 42),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                _copy(context, 'مين في الصورة؟', 'Who is in the photo?'),
                style:
                    const TextStyle(fontWeight: FontWeight.w900, fontSize: 18),
              ),
              const SizedBox(height: 6),
              Text(
                _copy(
                  context,
                  'رفيق بيسأل بالصوت، ثم اضغط “اسمع الإجابة” وخلي المريض يجاوب.',
                  'Rafeeq asks by voice, then tap “Listen to answer” and let the patient respond.',
                ),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 10),
              TextField(
                controller: answer,
                textInputAction: TextInputAction.done,
                decoration: InputDecoration(
                  hintText: _copy(context, 'اكتب جواب المريض هنا',
                      'Write the patient answer here'),
                ),
              ),
              if (lastTranscript.isNotEmpty) ...[
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF4EEFF),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(
                    _copy(context, 'سمعت: $lastTranscript',
                        'Heard: $lastTranscript'),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: isListening
                      ? null
                      : () async {
                          setDialogState(() {
                            isListening = true;
                            feedback = _copy(
                              context,
                              'أنا أسجل جوابك الآن... تكلم بوضوح.',
                              'I am recording your answer now... speak clearly.',
                            );
                          });
                          try {
                            final recorded = await recordMemoryAudioAnswer();
                            if (!dialogContext.mounted) return;
                            if (recorded == null) {
                              setDialogState(() {
                                isListening = false;
                                feedback = _copy(
                                  context,
                                  'ما وصلني تسجيل واضح. خلنا نحاول مرة ثانية.',
                                  'I did not receive a clear recording. Let’s try again.',
                                );
                              });
                              await _speakOpenAiMemory(
                                memory,
                                _copy(
                                  context,
                                  'ما وصلني تسجيل واضح. خلنا نحاول مرة ثانية.',
                                  'I did not receive a clear recording. Let’s try again.',
                                ),
                              );
                              return;
                            }
                            final patientId = widget.session.currentPatient!.id;
                            final response = await widget.session.api.dio
                                .post<Map<String, dynamic>>(
                              '/patients/$patientId/memories/${memory['id']}/ai-voice-test',
                              data: {'audio_data_url': recorded.dataUrl},
                            );
                            if (!dialogContext.mounted) return;
                            final data = response.data ?? const {};
                            final transcript =
                                data['transcript']?.toString().trim() ?? '';
                            final matched = data['matched'] == true;
                            final apiHint =
                                data['hint_text']?.toString().trim();
                            final effectiveHint =
                                apiHint != null && apiHint.isNotEmpty
                                    ? apiHint
                                    : hint;
                            final assistantText = matched
                                ? _copy(
                                    context,
                                    'صح عليك، ممتاز. ذاكرتك جميلة.',
                                    'That’s right, excellent. Your memory is doing well.')
                                : _copy(
                                    context,
                                    'قريب. تلميح بسيط: $effectiveHint. خذ راحتك وحاول مرة ثانية.',
                                    'Close. A simple hint: $effectiveHint. Take your time and try again.',
                                  );
                            setDialogState(() {
                              isListening = false;
                              lastTranscript = transcript;
                              answer.text = transcript;
                              feedback = assistantText;
                              hintShown = !matched;
                            });
                            final audioDataUrl =
                                data['audio_data_url']?.toString();
                            if (matched &&
                                audioDataUrl != null &&
                                audioDataUrl.isNotEmpty) {
                              await playMemoryAudioDataUrl(audioDataUrl);
                            } else {
                              await _speakOpenAiMemory(memory, assistantText);
                            }
                          } catch (_) {
                            if (!dialogContext.mounted) return;
                            setDialogState(() {
                              isListening = false;
                              feedback = _copy(
                                context,
                                'تعذر اختبار الجواب بالصوت. تأكد من إذن المايك والاتصال.',
                                'Could not test the answer by voice. Check microphone permission and connection.',
                              );
                              hintShown = true;
                            });
                            await _speakOpenAiMemory(
                              memory,
                              _copy(
                                context,
                                'تعذر اختبار الجواب بالصوت. تأكد من إذن المايك والاتصال.',
                                'Could not test the answer by voice. Check microphone permission and connection.',
                              ),
                            );
                          }
                        },
                  icon: Icon(isListening
                      ? Icons.hearing_disabled_outlined
                      : Icons.mic_none_outlined),
                  label: Text(isListening
                      ? _copy(context, 'أسمع الآن...', 'Listening...')
                      : _copy(context, 'اسمع الإجابة', 'Listen to answer')),
                ),
              ),
              if (feedback.isNotEmpty) ...[
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color:
                        feedback.startsWith('صح') || feedback.startsWith('That')
                            ? const Color(0xFFE7F8EF)
                            : const Color(0xFFFFF4DD),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(feedback, textAlign: TextAlign.center),
                ),
              ],
              if (hintShown) ...[
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF2EBFF),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(_copy(context, 'تلميح: $hint', 'Hint: $hint'),
                      textAlign: TextAlign.center),
                ),
              ],
            ]),
          ),
          actions: [
            TextButton(
              onPressed: () async {
                setDialogState(() {
                  hintShown = true;
                  feedback = _copy(
                      context,
                      'خلنا نعطيه تلميح بسيط ونحاول مرة ثانية.',
                      'Let’s give a simple hint and try again.');
                });
                await _speakOpenAiMemory(
                    memory, _copy(context, 'تلميح: $hint', 'Hint: $hint'));
              },
              child: Text(_copy(context, 'اعطِ تلميح', 'Give hint')),
            ),
            TextButton(
              onPressed: () => _speakOpenAiMemory(memory, question),
              child: Text(_copy(context, 'إعادة السؤال', 'Repeat question')),
            ),
            FilledButton(
              onPressed: () => handleAnswer(
                setDialogState,
                value: answer.text,
              ),
              child: Text(_copy(context, 'تحقق', 'Check')),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _speakOpenAiMemory(
      Map<String, dynamic> memory, String text) async {
    try {
      final patientId = widget.session.currentPatient!.id;
      final response = await widget.session.api.dio.post<Map<String, dynamic>>(
        '/patients/$patientId/memories/${memory['id']}/ai-speech',
        data: {'text': text},
      );
      final audioDataUrl = response.data?['audio_data_url']?.toString();
      if (audioDataUrl != null && audioDataUrl.isNotEmpty) {
        await playMemoryAudioDataUrl(audioDataUrl);
        return;
      }
    } catch (_) {
      // Browser speech is a soft fallback when OpenAI audio is unavailable.
    }
    await speakMemoryText(text);
  }

  Future<String?> _textDialog(
      String title, String label, TextEditingController controller) async {
    final strings = AppLocalizations.of(context)!;
    final value = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(title),
        content: TextField(
            controller: controller,
            decoration: InputDecoration(labelText: label)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: Text(strings.cancel)),
          FilledButton(
              onPressed: () =>
                  Navigator.pop(dialogContext, controller.text.trim()),
              child: Text(strings.save)),
        ],
      ),
    );
    return value == null || value.isEmpty ? null : value;
  }

  String? _imageUrl(Map<String, dynamic> memory) {
    final raw = memory['object_key_or_url']?.toString();
    if (raw == null || raw.isEmpty) return null;
    if (raw.startsWith('http://') ||
        raw.startsWith('https://') ||
        raw.startsWith('data:')) {
      return raw;
    }
    final apiBase = Uri.parse(widget.session.api.dio.options.baseUrl);
    final origin = apiBase.replace(path: '', query: '', fragment: '');
    return origin.resolve(raw).toString();
  }

  List<String> _labels(Map<String, dynamic> memory) {
    final raw = memory['people_labels_json'];
    if (raw is! List) return const [];
    return raw
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
  }

  List<String> _splitLabels(String value) => value
      .split(RegExp(r'[,،\n]'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList();

  String _mimeFromBytes(Uint8List bytes) {
    if (bytes.length >= 12 &&
        bytes[0] == 0x52 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x46 &&
        bytes[8] == 0x57 &&
        bytes[9] == 0x45 &&
        bytes[10] == 0x42 &&
        bytes[11] == 0x50) {
      return 'image/webp';
    }
    if (bytes.length >= 8 &&
        bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4E &&
        bytes[3] == 0x47) {
      return 'image/png';
    }
    return 'image/jpeg';
  }

  String _friendlyUploadError(Object error) {
    final text = error.toString();
    if (text.contains('413')) {
      return _copy(context, 'الصورة كبيرة جدًا. اختر صورة أصغر أو لقطة شاشة.',
          'The photo is too large. Choose a smaller photo or screenshot.');
    }
    if (text.contains('422')) {
      return _copy(context, 'صيغة الصورة غير مدعومة. جرّب JPG أو PNG.',
          'This photo format is unsupported. Try JPG or PNG.');
    }
    if (text.contains('401')) {
      return _copy(context, 'انتهت الجلسة. سجّل دخول مرة ثانية.',
          'Session expired. Please sign in again.');
    }
    return _copy(context, 'تأكد من الاتصال ثم حاول مرة ثانية.',
        'Check the connection and try again.');
  }

  static String _copy(BuildContext context, String ar, String en) =>
      Localizations.localeOf(context).languageCode == 'ar' ? ar : en;
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return RafeeqGlowCard(
      hero: true,
      gradient: const LinearGradient(
        begin: AlignmentDirectional.topStart,
        end: AlignmentDirectional.bottomEnd,
        colors: [
          RafeeqColors.primary,
          Color(0xFFB27CFA),
        ],
      ),
      child: Row(
        children: [
          const CircleAvatar(
            backgroundColor: Colors.white24,
            child: Icon(Icons.psychology_alt_outlined, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  subtitle,
                  style: const TextStyle(color: Colors.white70, height: 1.4),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CategoryStrip extends StatelessWidget {
  const _CategoryStrip({required this.categories, required this.memories});

  final List<Map<String, dynamic>> categories;
  final List<Map<String, dynamic>> memories;

  @override
  Widget build(BuildContext context) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    return SizedBox(
      height: 92,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: categories.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final category = categories[index];
          final count = memories
              .where((memory) =>
                  memory['category_id'].toString() == category['id'].toString())
              .length;
          return RafeeqGlowCard(
            width: 150,
            padding: const EdgeInsets.all(14),
            radius: 22,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.photo_library_outlined,
                    color: RafeeqColors.primary),
                const Spacer(),
                Text(
                  category['name'].toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
                Text(isArabic ? '$count صورة' : '$count photos',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _MemoryPhotoCard extends StatelessWidget {
  const _MemoryPhotoCard({
    required this.memory,
    required this.imageUrl,
    required this.labels,
    required this.onTest,
    required this.onEdit,
    required this.onDelete,
  });

  final Map<String, dynamic> memory;
  final String imageUrl;
  final List<String> labels;
  final VoidCallback onTest;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final prompt = memory['spoken_prompt']?.toString();
    return RafeeqGlowCard(
      padding: EdgeInsets.zero,
      hero: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 16 / 9,
            child: Image.network(
              imageUrl,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                color: const Color(0xFFF4EEFF),
                child: const Center(
                  child: Icon(Icons.broken_image_outlined,
                      color: RafeeqColors.primary, size: 42),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  memory['title'].toString(),
                  style: const TextStyle(
                    fontWeight: FontWeight.w900,
                    fontSize: 17,
                  ),
                ),
                if (labels.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: labels
                        .map((label) => Chip(
                              visualDensity: VisualDensity.compact,
                              label: Text(label),
                              avatar:
                                  const Icon(Icons.person_outline, size: 16),
                            ))
                        .toList(),
                  ),
                ],
                if (prompt != null && prompt.trim().isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    isArabic ? 'التلميح: $prompt' : 'Hint: $prompt',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: onTest,
                    icon: const Icon(Icons.quiz_outlined),
                    label: Text(
                        isArabic ? 'ابدأ اختبار الذاكرة' : 'Start memory test'),
                  ),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onEdit,
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      label: Text(isArabic ? 'تعديل' : 'Edit'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onDelete,
                      icon: const Icon(Icons.delete_outline,
                          size: 18, color: RafeeqColors.danger),
                      label: Text(
                        isArabic ? 'حذف' : 'Delete',
                        style: const TextStyle(color: RafeeqColors.danger),
                      ),
                    ),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
