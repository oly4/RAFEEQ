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
  return;
}

Future<void> playMemoryAudioDataUrl(String dataUrl) async {
  return;
}

Future<RecordedMemoryAudio?> recordMemoryAudioAnswer() async {
  return null;
}

Future<MemoryVoiceAnswer> listenForMemoryAnswer() async {
  return const MemoryVoiceAnswer(
    transcript: '',
    supported: false,
    error: 'Voice recognition is not available on this platform.',
  );
}

class WakeWordListener {
  WakeWordListener({required this.onWake, this.onError});

  final void Function(String transcript) onWake;
  final void Function(String message)? onError;

  Future<void> start() async {}

  void stop() {}
}
