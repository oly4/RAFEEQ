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
      this.startMemoryTourImmediately = false,
      this.startFirstPhotoTest = false,
      super.key});
  final AppSession session;
  final bool embedded;
  final bool startMemoryTourImmediately;
  final bool startFirstPhotoTest;

  @override
  State<MemoriesPanel> createState() => _MemoriesPanelState();
}

class _MemoriesPanelState extends State<MemoriesPanel> {
  late Future<Map<String, List<Map<String, dynamic>>>> future;
  Map<String, List<Map<String, dynamic>>>? _cachedData;
  bool _memoryTourAutoStarted = false;

  @override
  void initState() {
    super.initState();
    future = _load();
    _queuePhotoTestIfRequested();
  }

  @override
  void didUpdateWidget(covariant MemoriesPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if ((widget.startMemoryTourImmediately &&
            !oldWidget.startMemoryTourImmediately) ||
        (widget.startFirstPhotoTest && !oldWidget.startFirstPhotoTest)) {
      _queuePhotoTestIfRequested();
    }
  }

  void _queuePhotoTestIfRequested() {
    if ((!widget.startMemoryTourImmediately && !widget.startFirstPhotoTest) ||
        _memoryTourAutoStarted) {
      return;
    }
    _memoryTourAutoStarted = true;
    future.then((_) {
      if (!mounted) return;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _startMemoryTourFromVoice();
      });
    });
  }

  Future<Map<String, List<Map<String, dynamic>>>> _load() async {
    final id = widget.session.currentPatient!.id;
    final responses = await Future.wait<dynamic>([
      widget.session.api.dio
          .get<List<dynamic>>('/patients/$id/memory-categories'),
      widget.session.api.dio
          .get<Map<String, dynamic>>('/patients/$id/memories'),
    ]);
    final categories = responses[0] as dynamic;
    final memories = responses[1] as dynamic;
    final data = <String, List<Map<String, dynamic>>>{
      'categories': categories.data!.cast<Map<String, dynamic>>(),
      'memories':
          (memories.data!['items'] as List).cast<Map<String, dynamic>>(),
    };
    _cachedData = data;
    return data;
  }

  void refresh() => setState(() => future = _load());

  Future<void> _startMemoryTourFromVoice() async {
    final data = await future;
    if (!mounted) return;
    final memories = data['memories']!;
    final photoMemories =
        memories.where((memory) => _imageUrl(memory) != null).toList();
    if (photoMemories.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_copy(
              context,
              'ما فيه صور جاهزة للعرض. ارفع صورة أولًا.',
              'No photos are ready to show. Upload a photo first.')),
        ),
      );
      return;
    }
    await _openMemorySlideshow(photoMemories, autoPlay: true);
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    final content = FutureBuilder<Map<String, List<Map<String, dynamic>>>>(
      future: future,
      builder: (context, snapshot) {
        final data = snapshot.data ?? _cachedData;
        if (data == null) {
          return const Center(child: CircularProgressIndicator());
        }
        final categories = data['categories']!;
        final memories = data['memories']!;
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
                'ارفع صور العائلة والذكريات، وخل رفيق يعرضها للمريض ويقرأ وصفها بهدوء بدون اختبار.',
                'Upload family photos and memories, then let Rafeeq show them gently without testing or scoring.',
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
                    _copy(context, 'صور الذكريات', 'Memory photos'),
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
                        'ابدأ برفع صورة لشخص أو مكان يعرفه المريض، واكتب الوصف اللي يقرأه رفيق.',
                        'Start by uploading a photo of someone or somewhere the patient knows, then add what Rafeeq should read.',
                      ),
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              )
            else
              Column(
                children: [
                  FilledButton.icon(
                    onPressed: () => _openMemorySlideshow(photoMemories),
                    icon: const Icon(Icons.play_circle_outline_rounded),
                    label: Text(
                      _copy(context, 'ابدأ جولة الذكريات', 'Start memory tour'),
                    ),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                    ),
                  ),
                  const SizedBox(height: 12),
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: photoMemories.length,
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 2,
                      crossAxisSpacing: 10,
                      mainAxisSpacing: 10,
                      childAspectRatio: 0.78,
                    ),
                    itemBuilder: (context, index) {
                      final memory = photoMemories[index];
                      return _MemoryPhotoCard(
                        memory: memory,
                        imageUrl: _imageUrl(memory)!,
                        labels: _labels(memory),
                        onTest: () => _openMemorySlideshow(
                          photoMemories,
                          initialIndex: index,
                        ),
                        onEdit: () => _editMemory(memory, categories),
                        onDelete: () => _deleteMemory(memory),
                      );
                    },
                  ),
                ],
              ),
            if (!widget.embedded) ...[
              const SizedBox(height: 8),
              Text(
                _copy(
                  context,
                  'كل الصور هنا تُستخدم لعرض ذكريات لطيفة بدون اختبار. رفيق يقرأ الوصف بصوت هادئ حسب الكلام المكتوب للصورة.',
                  'Photos here are used for gentle memory viewing, not testing. Rafeeq reads the written description calmly.',
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
                  labelText: _copy(
                      context, 'وصف رفيق للصورة', 'Rafeeq photo description'),
                  hintText: _copy(
                      context,
                      'مثال: هذا ابنك أحمد، كان يزورك كل جمعة.',
                      'Example: This is your son Ahmed. He used to visit every Friday.'),
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
                  labelText: _copy(
                      context, 'وصف رفيق للصورة', 'Rafeeq photo description'),
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

  // Legacy quiz mode is kept for reference, but the app now uses the gentle
  // memory-tour flow so patients are not scored or corrected.
  // ignore: unused_element
  Future<void> _openMemoryTest(Map<String, dynamic> memory) async {
    if (_useGentleMemoryStoryMode()) {
      await _openMemoryStory(memory);
      return;
    }
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

  Future<void> _openMemorySlideshow(
    List<Map<String, dynamic>> memories, {
    int initialIndex = 0,
    bool autoPlay = false,
  }) async {
    if (memories.isEmpty) return;
    var currentIndex = initialIndex.clamp(0, memories.length - 1).toInt();
    var dialogOpen = true;
    var autoPlayRunning = false;
    StateSetter? setSlideState;

    Future<void> speakCurrent() async {
      final memory = memories[currentIndex];
      await _speakOpenAiMemory(memory, _memoryNarration(memory));
    }

    Future<void> playTour() async {
      if (autoPlayRunning) return;
      autoPlayRunning = true;
      try {
        var visited = 0;
        while (dialogOpen && mounted && visited < memories.length) {
          await speakCurrent();
          visited++;
          if (!autoPlay || memories.length <= 1 || visited >= memories.length) {
            break;
          }
          await Future<void>.delayed(const Duration(seconds: 2));
          if (!dialogOpen || !mounted) break;
          setSlideState?.call(() {
            currentIndex = (currentIndex + 1) % memories.length;
          });
          await Future<void>.delayed(const Duration(milliseconds: 350));
        }
      } finally {
        autoPlayRunning = false;
      }
    }

    Future<void>.delayed(const Duration(milliseconds: 450), () {
      if (mounted) {
        if (autoPlay) {
          playTour();
        } else {
          speakCurrent();
        }
      }
    });

    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          setSlideState = setDialogState;
          final memory = memories[currentIndex];
          final imageUrl = _imageUrl(memory)!;
          final narration = _memoryNarration(memory);
          final labels = _labels(memory);
          final currentNumber = currentIndex + 1;
          return AlertDialog(
            title: Text(_copy(context, 'جولة الذكريات', 'Memory tour')),
            content: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: Image.network(
                    imageUrl,
                    height: 230,
                    width: double.infinity,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                      height: 180,
                      color: const Color(0xFFF4EEFF),
                      child: const Center(
                        child: Icon(Icons.broken_image_outlined,
                            color: RafeeqColors.primary, size: 42),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '${memory['title']}',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                if (labels.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Wrap(
                    alignment: WrapAlignment.center,
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
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Theme.of(context).brightness == Brightness.dark
                        ? const Color(0xFF2A2148)
                        : const Color(0xFFF4EEFF),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Text(
                    narration,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  _copy(
                    context,
                    'صورة $currentNumber من ${memories.length}',
                    'Photo $currentNumber of ${memories.length}',
                  ),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ]),
            ),
            actions: [
              TextButton(
                onPressed: () {
                  dialogOpen = false;
                  Navigator.pop(dialogContext);
                },
                child: Text(_copy(context, 'إغلاق', 'Close')),
              ),
              IconButton.filledTonal(
                tooltip: _copy(context, 'السابق', 'Previous'),
                onPressed: memories.length <= 1
                    ? null
                    : () {
                        setDialogState(() {
                          currentIndex = (currentIndex - 1 + memories.length) %
                              memories.length;
                        });
                        speakCurrent();
                      },
                icon: const Icon(Icons.chevron_left_rounded),
              ),
              IconButton.filledTonal(
                tooltip: _copy(context, 'خل رفيق يقرأ', 'Let Rafeeq read'),
                onPressed: speakCurrent,
                icon: const Icon(Icons.volume_up_outlined),
              ),
              FilledButton.icon(
                onPressed: memories.length <= 1
                    ? null
                    : () {
                        setDialogState(() {
                          currentIndex = (currentIndex + 1) % memories.length;
                        });
                        speakCurrent();
                      },
                icon: const Icon(Icons.chevron_right_rounded),
                label: Text(_copy(context, 'التالي', 'Next')),
              ),
            ],
          );
        },
      ),
    ).whenComplete(() => dialogOpen = false);
  }

  bool _useGentleMemoryStoryMode() => true;

  Future<void> _openMemoryStory(Map<String, dynamic> memory) async {
    final imageUrl = _imageUrl(memory)!;
    final narration = _memoryNarration(memory);
    Future<void>.delayed(const Duration(milliseconds: 450), () {
      if (mounted) _speakOpenAiMemory(memory, narration);
    });
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(_copy(context, 'عرض الذكرى', 'Memory story')),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: Image.network(
                imageUrl,
                height: 220,
                width: double.infinity,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  height: 170,
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
              _copy(
                context,
                'رفيق يعرض الذكرى ويقرأ الوصف بهدوء بدون اختبار أو تقييم.',
                'Rafeeq shows the memory and reads it gently with no test or scoring.',
              ),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Theme.of(context).brightness == Brightness.dark
                    ? const Color(0xFF2A2148)
                    : const Color(0xFFF4EEFF),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Text(
                narration,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
              ),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(_copy(context, 'إغلاق', 'Close')),
          ),
          FilledButton.icon(
            onPressed: () => _speakOpenAiMemory(memory, narration),
            icon: const Icon(Icons.volume_up_outlined),
            label: Text(_copy(context, 'خل رفيق يقرأ', 'Let Rafeeq read')),
          ),
        ],
      ),
    );
  }

  String _memoryNarration(Map<String, dynamic> memory) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    String clean(Object? value) => value?.toString().trim() ?? '';
    final prompt = clean(memory['spoken_prompt']);
    if (prompt.isNotEmpty) return prompt;
    final description = clean(memory['description']);
    if (description.isNotEmpty) return description;
    final labels = _labels(memory);
    if (labels.isNotEmpty) {
      final joined = labels.join(isArabic ? ' و ' : ' and ');
      return isArabic
          ? 'هذه ذكرى جميلة مع $joined.'
          : 'This is a warm memory with $joined.';
    }
    final title = clean(memory['title']);
    if (title.isNotEmpty) {
      return isArabic ? 'هذه ذكرى عن $title.' : 'This memory is about $title.';
    }
    return isArabic
        ? 'هذه صورة من الذكريات الجميلة.'
        : 'This is a gentle memory photo.';
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
                  _localizedCategoryName(context, category['name']),
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

  String _localizedCategoryName(BuildContext context, Object? value) {
    final raw = value?.toString().trim() ?? '';
    final normalized = raw.toLowerCase();
    final arabicNormalized = raw
        .replaceAll('أ', 'ا')
        .replaceAll('إ', 'ا')
        .replaceAll('آ', 'ا')
        .replaceAll('ة', 'ه')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    if (normalized == 'family' ||
        arabicNormalized == 'العائله' ||
        arabicNormalized.contains('عائله')) {
      return isArabic ? 'العائلة' : 'Family';
    }
    if (normalized == 'friends' ||
        arabicNormalized == 'الاصدقاء' ||
        arabicNormalized.contains('اصدقاء')) {
      return isArabic ? 'الأصدقاء' : 'Friends';
    }
    if (normalized == 'events' ||
        arabicNormalized == 'الاحداث' ||
        arabicNormalized.contains('احداث')) {
      return isArabic ? 'الأحداث' : 'Events';
    }
    if (normalized == 'new memories' || arabicNormalized == 'ذكريات جديده') {
      return isArabic ? 'ذكريات جديدة' : 'New memories';
    }
    return raw;
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
    final labelText = labels.take(2).join(' • ');
    return RafeeqGlowCard(
      padding: EdgeInsets.zero,
      hero: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(28),
        onTap: onTest,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(28)),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.network(
                      imageUrl,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(
                        color: const Color(0xFFF4EEFF),
                        child: const Center(
                          child: Icon(Icons.broken_image_outlined,
                              color: RafeeqColors.primary, size: 34),
                        ),
                      ),
                    ),
                    PositionedDirectional(
                      top: 8,
                      end: 8,
                      child: PopupMenuButton<String>(
                        tooltip: isArabic ? 'خيارات' : 'Options',
                        icon: const Icon(Icons.more_vert_rounded,
                            color: Colors.white),
                        color: Theme.of(context).cardColor,
                        onSelected: (value) {
                          if (value == 'edit') onEdit();
                          if (value == 'delete') onDelete();
                        },
                        itemBuilder: (context) => [
                          PopupMenuItem(
                            value: 'edit',
                            child: Text(isArabic ? 'تعديل' : 'Edit'),
                          ),
                          PopupMenuItem(
                            value: 'delete',
                            child: Text(isArabic ? 'حذف' : 'Delete'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    memory['title'].toString(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w900,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    labelText.isEmpty
                        ? (isArabic ? 'اضغط للعرض' : 'Tap to show')
                        : labelText,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
