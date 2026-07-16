import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../../l10n/app_localizations.dart';

class CameraTestScreen extends StatefulWidget {
  const CameraTestScreen({super.key});

  @override
  State<CameraTestScreen> createState() => _CameraTestScreenState();
}

class _CameraTestScreenState extends State<CameraTestScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  bool _loading = false;
  String? _errorCode;

  bool get _hasSecureContext {
    if (!kIsWeb) return true;
    final uri = Uri.base;
    return uri.scheme == 'https' ||
        uri.host == 'localhost' ||
        uri.host == '127.0.0.1';
  }

  bool get _ready => _controller?.value.isInitialized ?? false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _stopCamera(updateUi: false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(strings.cameraTest),
        leading: IconButton(
          onPressed: () => Navigator.pop(context),
          icon: const Icon(Icons.close),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.primaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.privacy_tip_outlined),
                  const SizedBox(width: 12),
                  Expanded(child: Text(strings.cameraPrivacyNotice)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          if (_ready) _cameraPreview(strings) else _cameraStartCard(strings),
        ],
      ),
    );
  }

  Widget _cameraStartCard(AppLocalizations strings) {
    final error = _localizedError(strings);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(
              _hasSecureContext ? Icons.videocam_outlined : Icons.lock_outline,
              size: 72,
            ),
            const SizedBox(height: 16),
            Text(
              _hasSecureContext
                  ? strings.cameraPermissionPrompt
                  : strings.cameraSecureContextRequired,
              textAlign: TextAlign.center,
            ),
            if (error != null) ...[
              const SizedBox(height: 12),
              Semantics(
                liveRegion: true,
                child: Text(
                  error,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            ],
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _loading || !_hasSecureContext ? null : _startCamera,
                icon: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.videocam_outlined),
                label: Text(strings.startCameraTest),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cameraPreview(AppLocalizations strings) {
    final controller = _controller!;
    return Column(
      children: [
        Semantics(
          label: strings.liveCameraPreview,
          image: true,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: ColoredBox(
              color: Colors.black,
              child: AspectRatio(
                aspectRatio: controller.value.aspectRatio,
                child: CameraPreview(controller),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        if (_cameras.length > 1) ...[
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _loading ? null : _switchCamera,
              icon: const Icon(Icons.cameraswitch_outlined),
              label: Text(strings.switchCamera),
            ),
          ),
          const SizedBox(height: 8),
        ],
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: () => _stopCamera(),
            icon: const Icon(Icons.videocam_off_outlined),
            label: Text(strings.stopCamera),
          ),
        ),
      ],
    );
  }

  Future<void> _startCamera() async {
    if (!_hasSecureContext) return;
    setState(() {
      _loading = true;
      _errorCode = null;
    });
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        _errorCode = 'not_found';
        return;
      }
      final selected = _cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
        orElse: () => _cameras.first,
      );
      await _initialize(selected);
    } on CameraException catch (error) {
      _errorCode = error.code;
    } catch (_) {
      _errorCode = 'unavailable';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _initialize(CameraDescription description) async {
    await _controller?.dispose();
    final controller = CameraController(
      description,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    _controller = controller;
    await controller.initialize();
  }

  Future<void> _switchCamera() async {
    final current = _controller?.description;
    if (current == null || _cameras.length < 2) return;
    final index = _cameras.indexWhere((camera) => camera.name == current.name);
    final next = _cameras[(index + 1) % _cameras.length];
    setState(() => _loading = true);
    try {
      await _initialize(next);
      _errorCode = null;
    } on CameraException catch (error) {
      _errorCode = error.code;
    } catch (_) {
      _errorCode = 'unavailable';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _stopCamera({bool updateUi = true}) async {
    final controller = _controller;
    _controller = null;
    await controller?.dispose();
    if (updateUi && mounted) setState(() {});
  }

  String? _localizedError(AppLocalizations strings) {
    return switch (_errorCode) {
      null => null,
      'not_found' || 'NotFoundError' => strings.noCameraFound,
      'CameraAccessDenied' ||
      'CameraAccessDeniedWithoutPrompt' ||
      'permissionDenied' ||
      'NotAllowedError' =>
        strings.cameraPermissionDenied,
      'CameraAccessRestricted' => strings.cameraAccessRestricted,
      _ => strings.cameraUnavailable,
    };
  }
}
