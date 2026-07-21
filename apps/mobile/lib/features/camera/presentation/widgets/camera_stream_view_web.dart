import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

class CameraStreamView extends StatefulWidget {
  const CameraStreamView({required this.streamUrl, super.key});

  final String streamUrl;

  @override
  State<CameraStreamView> createState() => _CameraStreamViewState();
}

class _CameraStreamViewState extends State<CameraStreamView> {
  late final String _viewType;

  @override
  void initState() {
    super.initState();
    _viewType = 'rafeeq-camera-stream-${DateTime.now().microsecondsSinceEpoch}';
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (viewId) {
      final image = web.HTMLImageElement()
        ..src = widget.streamUrl
        ..alt = 'RAFEEQ Raspberry Pi camera stream';
      image.style
        ..width = '100%'
        ..height = '100%'
        ..objectFit = 'contain'
        ..backgroundColor = '#000'
        ..borderRadius = '20px';
      return image;
    });
  }

  @override
  Widget build(BuildContext context) => HtmlElementView(viewType: _viewType);
}
