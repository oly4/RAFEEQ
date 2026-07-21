import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../../app/theme.dart';
import '../../../../l10n/app_localizations.dart';
import '../widgets/camera_stream_view.dart';

class CameraTestScreen extends StatefulWidget {
  const CameraTestScreen({super.key});

  @override
  State<CameraTestScreen> createState() => _CameraTestScreenState();
}

class _CameraTestScreenState extends State<CameraTestScreen>
    with WidgetsBindingObserver {
  static const _piCameraStreamUrl =
      String.fromEnvironment('RAFEEQ_CAMERA_STREAM_URL');

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

  bool get _hasPiCameraStream => _piCameraStreamUrl.trim().isNotEmpty;

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
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    return Scaffold(
      appBar: AppBar(
        title: Text(_hasPiCameraStream
            ? (isArabic ? 'كاميرا الرازبيري' : 'Raspberry Pi camera')
            : strings.cameraTest),
        leading: IconButton(
          onPressed: () => Navigator.pop(context),
          icon: const Icon(Icons.close),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          RafeeqGlowCard(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.privacy_tip_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(_hasPiCameraStream
                      ? (isArabic
                          ? 'بث مباشر من كاميرا الرازبيري. لا يتم حفظ الفيديو داخل التطبيق.'
                          : 'Live stream from the Raspberry Pi camera. The app does not save this video.')
                      : strings.cameraPrivacyNotice),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_hasPiCameraStream)
            _raspberryPiPreview(strings)
          else if (_ready)
            _cameraPreview(strings)
          else
            _cameraStartCard(strings),
        ],
      ),
    );
  }

  Widget _raspberryPiPreview(AppLocalizations strings) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    return RafeeqGlowCard(
      hero: true,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const CircleAvatar(
              backgroundColor: RafeeqColors.lavender,
              child: Icon(Icons.videocam_outlined, color: RafeeqColors.primary),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                isArabic ? 'بث غرفة المريض' : 'Patient room stream',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            const Chip(label: Text('LIVE')),
          ]),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: ColoredBox(
              color: Colors.black,
              child: AspectRatio(
                aspectRatio: 4 / 3,
                child: CameraStreamView(streamUrl: _piCameraStreamUrl),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            isArabic
                ? 'إذا لم يظهر البث، تأكد أن خدمة الكاميرا على الرازبيري والـ tunnel يعملان.'
                : 'If the stream does not appear, make sure the Raspberry Pi camera service and tunnel are running.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
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
