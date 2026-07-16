// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:async';
import 'dart:html' as html;
import 'dart:typed_data';

class PickedMemoryImage {
  const PickedMemoryImage({required this.bytes, required this.mimeType});

  final Uint8List bytes;
  final String mimeType;
}

Future<PickedMemoryImage?> pickMemoryImage() async {
  final completer = Completer<PickedMemoryImage?>();
  final input = html.FileUploadInputElement()
    ..accept = 'image/jpeg,image/png,image/webp'
    ..multiple = false;

  input.onChange.first.then((_) {
    final file = input.files?.isNotEmpty == true ? input.files!.first : null;
    if (file == null) {
      if (!completer.isCompleted) completer.complete(null);
      return;
    }

    final reader = html.FileReader();
    reader.onError.first.then((_) {
      if (!completer.isCompleted) {
        completer.completeError(Exception('تعذر قراءة الصورة من الجهاز'));
      }
    });
    reader.onLoad.first.then((_) {
      final result = reader.result;
      if (result is! Uint8List) {
        if (!completer.isCompleted) {
          completer.completeError(Exception('صيغة الصورة غير مدعومة'));
        }
        return;
      }
      if (!completer.isCompleted) {
        completer.complete(
          PickedMemoryImage(
            bytes: result,
            mimeType: file.type.isEmpty ? 'image/jpeg' : file.type,
          ),
        );
      }
    });
    reader.readAsArrayBuffer(file);
  });

  input.click();
  return completer.future.timeout(
    const Duration(minutes: 2),
    onTimeout: () => null,
  );
}
