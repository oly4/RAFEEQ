import 'package:flutter/material.dart';

class CameraStreamView extends StatelessWidget {
  const CameraStreamView({required this.streamUrl, super.key});

  final String streamUrl;

  @override
  Widget build(BuildContext context) => Image.network(
        streamUrl,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => const Center(
          child: Icon(Icons.videocam_off_outlined, size: 64),
        ),
      );
}
