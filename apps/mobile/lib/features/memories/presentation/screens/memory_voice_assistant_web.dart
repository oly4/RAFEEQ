// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:async';
import 'dart:html' as html;
import 'dart:js' as js;

class MemoryVoiceAnswer {
  const MemoryVoiceAnswer({
    required this.transcript,
    required this.supported,
    this.error,
  });

  final String transcript;
  final bool supported;
  final String? error;
}

class RecordedMemoryAudio {
  const RecordedMemoryAudio({required this.dataUrl});

  final String dataUrl;
}

Future<void> speakMemoryText(String text) async {
  final utteranceConstructor = js.context['SpeechSynthesisUtterance'];
  final synthesis = js.context['speechSynthesis'];
  if (utteranceConstructor == null ||
      synthesis == null ||
      text.trim().isEmpty) {
    return;
  }

  final completer = Completer<void>();
  final utterance = js.JsObject(utteranceConstructor, [text]);
  utterance['lang'] = 'ar-SA';
  utterance['rate'] = 0.86;
  utterance['pitch'] = 1.0;
  utterance['volume'] = 1.0;
  utterance.callMethod('addEventListener', [
    'end',
    js.JsFunction.withThis((_, __) {
      if (!completer.isCompleted) completer.complete();
    }),
  ]);
  utterance.callMethod('addEventListener', [
    'error',
    js.JsFunction.withThis((_, __) {
      if (!completer.isCompleted) completer.complete();
    }),
  ]);

  final synthesisObject = synthesis as js.JsObject;
  synthesisObject.callMethod('cancel', []);
  synthesisObject.callMethod('speak', [utterance]);

  final timeoutSeconds = (text.length / 8).ceil().clamp(4, 18);
  return completer.future.timeout(
    Duration(seconds: timeoutSeconds),
    onTimeout: () {},
  );
}

Future<void> playMemoryAudioDataUrl(String dataUrl) async {
  if (dataUrl.trim().isEmpty) return;
  final audio = html.AudioElement(dataUrl);
  await audio.play();
}

Future<RecordedMemoryAudio?> recordMemoryAudioAnswer() async {
  final mediaDevices = html.window.navigator.mediaDevices;
  if (mediaDevices == null) {
    throw Exception('متصفحك لا يدعم التسجيل الصوتي. جرّب Chrome.');
  }
  final stream = await mediaDevices.getUserMedia({'audio': true});
  final mimeType = html.MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : 'audio/ogg';
  final recorder = html.MediaRecorder(stream, {'mimeType': mimeType});
  final chunks = <html.Blob>[];
  final completer = Completer<RecordedMemoryAudio?>();
  StreamSubscription<html.Event>? dataSub;
  StreamSubscription<html.Event>? stopSub;

  dataSub = recorder.on['dataavailable'].listen((event) {
    final dataEvent = event as html.BlobEvent;
    final data = dataEvent.data;
    if (data != null && data.size > 0) chunks.add(data);
  });
  stopSub = recorder.on['stop'].listen((_) async {
    await dataSub?.cancel();
    await stopSub?.cancel();
    for (final track in stream.getTracks()) {
      track.stop();
    }
    if (chunks.isEmpty) {
      completer.complete(null);
      return;
    }
    final blob = html.Blob(chunks, mimeType);
    final reader = html.FileReader();
    reader.onLoad.first.then((_) {
      final result = reader.result?.toString();
      completer.complete(
        result == null ? null : RecordedMemoryAudio(dataUrl: result),
      );
    });
    reader.onError.first.then((_) {
      if (!completer.isCompleted) {
        completer.completeError(Exception('تعذر قراءة التسجيل الصوتي.'));
      }
    });
    reader.readAsDataUrl(blob);
  });

  recorder.start();
  await Future<void>.delayed(const Duration(seconds: 6));
  if (recorder.state == 'recording') {
    recorder.stop();
  }
  return completer.future.timeout(
    const Duration(seconds: 10),
    onTimeout: () => null,
  );
}

Future<MemoryVoiceAnswer> listenForMemoryAnswer() async {
  final recognitionConstructor =
      js.context['SpeechRecognition'] ?? js.context['webkitSpeechRecognition'];
  if (recognitionConstructor == null) {
    return const MemoryVoiceAnswer(
      transcript: '',
      supported: false,
      error: 'متصفحك لا يدعم التعرف على الصوت. جرّب Chrome.',
    );
  }

  final completer = Completer<MemoryVoiceAnswer>();
  final recognition = js.JsObject(recognitionConstructor, []);
  recognition['lang'] = 'ar-SA';
  recognition['continuous'] = false;
  recognition['interimResults'] = false;
  recognition['maxAlternatives'] = 1;

  Timer? timer;
  void finish(MemoryVoiceAnswer answer) {
    timer?.cancel();
    if (!completer.isCompleted) completer.complete(answer);
  }

  recognition.callMethod('addEventListener', [
    'result',
    js.JsFunction.withThis((_, event) {
      final eventObject = js.JsObject.fromBrowserObject(event);
      final results = eventObject['results'];
      final firstResult = results[0];
      final firstAlternative = firstResult[0];
      final transcript = firstAlternative['transcript']?.toString() ?? '';
      finish(MemoryVoiceAnswer(
        transcript: transcript.trim(),
        supported: true,
      ));
    }),
  ]);
  recognition.callMethod('addEventListener', [
    'error',
    js.JsFunction.withThis((_, event) {
      final eventObject = js.JsObject.fromBrowserObject(event);
      final error = eventObject['error']?.toString();
      finish(MemoryVoiceAnswer(
        transcript: '',
        supported: true,
        error: error == 'not-allowed'
            ? 'اسمح للمتصفح باستخدام المايكروفون.'
            : 'ما قدرت أسمع الجواب بوضوح.',
      ));
    }),
  ]);
  recognition.callMethod('addEventListener', [
    'end',
    js.JsFunction.withThis((_, __) {
      finish(const MemoryVoiceAnswer(transcript: '', supported: true));
    }),
  ]);

  try {
    recognition.callMethod('start', []);
  } catch (_) {
    return const MemoryVoiceAnswer(
      transcript: '',
      supported: true,
      error: 'الصوت شغال الآن، انتظر لحظة ثم جرّب مرة ثانية.',
    );
  }

  timer = Timer(const Duration(seconds: 8), () {
    try {
      recognition.callMethod('stop', []);
    } catch (_) {
      finish(const MemoryVoiceAnswer(transcript: '', supported: true));
    }
  });

  return completer.future;
}
