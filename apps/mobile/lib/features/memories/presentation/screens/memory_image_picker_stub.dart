import 'dart:typed_data';

class PickedMemoryImage {
  const PickedMemoryImage({required this.bytes, required this.mimeType});

  final Uint8List bytes;
  final String mimeType;
}

Future<PickedMemoryImage?> pickMemoryImage() {
  throw UnsupportedError('Image upload is only available in the web demo.');
}
