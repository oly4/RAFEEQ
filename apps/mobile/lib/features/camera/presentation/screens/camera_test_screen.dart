import 'package:camera/camera.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme.dart';
import '../../../../core/auth/providers.dart';
import '../../../../l10n/app_localizations.dart';
import '../widgets/camera_stream_view.dart';

class CameraTestScreen extends ConsumerStatefulWidget {
  const CameraTestScreen({super.key});

  @override
  ConsumerState<CameraTestScreen> createState() => _CameraTestScreenState();
}

class _CameraTestScreenState extends ConsumerState<CameraTestScreen>
    with WidgetsBindingObserver {
  static const _piCameraStreamUrl =
      String.fromEnvironment('RAFEEQ_CAMERA_STREAM_URL');
  static const _cameraControlBaseUrl =
      String.fromEnvironment('RAFEEQ_CAMERA_CONTROL_BASE_URL');

  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  bool _loading = false;
  String? _errorCode;
  bool _fallDetectionRunning = false;
  bool _fallDetectionBusy = false;
  bool _fallDetectionStatusLoaded = false;
  String? _fallDetectionError;
  int _streamRefreshKey = 0;

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
    if (_hasPiCameraStream) {
      Future.microtask(_refreshFallDetectionStatus);
    }
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
        title: Text(isArabic ? 'كاميرا الرازبيري' : 'Raspberry Pi camera'),
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
                  child: Text(isArabic
                      ? 'الكاميرا مغلقة حتى تبدأ اكتشاف السقوط. لا يتم حفظ الفيديو داخل التطبيق.'
                      : 'The camera stays off until you start fall detection. The app does not save this video.'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _raspberryPiPreview(strings),
        ],
      ),
    );
  }

  Widget _raspberryPiPreview(AppLocalizations strings) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    final statusText = _fallDetectionRunning
        ? (isArabic ? 'اكتشاف السقوط يعمل الآن' : 'Fall detection is running')
        : (isArabic
            ? 'الكاميرا مغلقة حتى تبدأ اكتشاف السقوط'
            : 'The camera is off until you start fall detection');
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
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isArabic ? 'بث غرفة المريض' : 'Patient room stream',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    statusText,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            Chip(label: Text(_fallDetectionRunning ? 'LIVE' : 'OFF')),
          ]),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: ColoredBox(
              color: Colors.black,
              child: AspectRatio(
                aspectRatio: 4 / 3,
                child: _fallDetectionRunning && _hasPiCameraStream
                    ? CameraStreamView(
                        key: ValueKey(_streamRefreshKey),
                        streamUrl: _streamUrlWithRefreshKey(),
                      )
                    : Center(
                        child: Icon(
                          Icons.videocam_off_outlined,
                          color: Colors.white.withValues(alpha: 0.82),
                          size: 64,
                        ),
                      ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (_fallDetectionError != null) ...[
            Semantics(
              liveRegion: true,
              child: Text(
                _fallDetectionError!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
            const SizedBox(height: 12),
          ],
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _fallDetectionBusy ? null : _toggleFallDetection,
              icon: _fallDetectionBusy
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(_fallDetectionRunning
                      ? Icons.stop_circle_outlined
                      : Icons.play_arrow_outlined),
              label: Text(_fallDetectionRunning
                  ? (isArabic ? 'إيقاف اكتشاف السقوط' : 'Stop fall detection')
                  : (isArabic ? 'بدء اكتشاف السقوط' : 'Start fall detection')),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            _fallDetectionStatusLoaded
                ? (isArabic
                    ? 'عند البدء، تعمل الكاميرا واكتشاف السقوط على الرازبيري.'
                    : 'When started, the Raspberry Pi camera and fall detection run together.')
                : (isArabic
                    ? 'جاري فحص حالة كاميرا الرازبيري.'
                    : 'Checking the Raspberry Pi camera status.'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Future<void> _refreshFallDetectionStatus() async {
    if (!_hasPiCameraStream) return;
    try {
      final data = await _cameraControlRequest();
      if (!mounted) return;
      setState(() {
        _fallDetectionRunning = data['active'] == true;
        _fallDetectionStatusLoaded = true;
        _fallDetectionError = null;
        if (_fallDetectionRunning) _streamRefreshKey++;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _fallDetectionStatusLoaded = true;
        _fallDetectionError = _cameraControlError(error);
      });
    }
  }

  Future<void> _toggleFallDetection() async {
    final action = _fallDetectionRunning ? 'stop' : 'start';
    final wasRunning = _fallDetectionRunning;
    final expectedRunning = action == 'start';
    setState(() {
      _fallDetectionBusy = true;
      _fallDetectionError = null;
      if (wasRunning) {
        _fallDetectionRunning = false;
        _fallDetectionStatusLoaded = true;
        _streamRefreshKey++;
      }
    });
    try {
      await _cameraControlRequest(action);
      final data = await _waitForFallDetectionState(expectedRunning);
      if (!mounted) return;
      setState(() {
        _fallDetectionRunning = data['active'] == true;
        _fallDetectionStatusLoaded = true;
        if (_fallDetectionRunning) _streamRefreshKey++;
      });
      if (_fallDetectionRunning) {
        Future.delayed(const Duration(seconds: 2), () {
          if (!mounted || !_fallDetectionRunning) return;
          setState(() => _streamRefreshKey++);
        });
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _fallDetectionRunning = wasRunning;
        if (wasRunning) _streamRefreshKey++;
        _fallDetectionError = _cameraControlError(error);
      });
    } finally {
      if (mounted) setState(() => _fallDetectionBusy = false);
    }
  }

  Future<Map<String, dynamic>> _waitForFallDetectionState(bool expected) async {
    Map<String, dynamic> latest = const <String, dynamic>{};
    for (var attempt = 0; attempt < 8; attempt++) {
      latest = await _cameraControlRequest();
      if (latest['active'] == expected) return latest;
      await Future<void>.delayed(const Duration(milliseconds: 800));
    }
    return latest;
  }

  Future<Map<String, dynamic>> _cameraControlRequest([String? action]) async {
    final session = ref.read(appSessionProvider);
    final path = action == null
        ? '/devices/camera/fall-detection'
        : '/devices/camera/fall-detection/$action';
    if (_cameraControlBaseUrl.trim().isEmpty) {
      final response = action == null
          ? await session.api.dio.get<Map<String, dynamic>>(path)
          : await session.api.dio.post<Map<String, dynamic>>(path);
      return response.data ?? const <String, dynamic>{};
    }

    final client = Dio(BaseOptions(
      baseUrl: _normalizedCameraControlBaseUrl(),
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 20),
      headers: {
        if (session.accessToken != null)
          'Authorization': 'Bearer ${session.accessToken}',
      },
    ));
    final response = action == null
        ? await client.get<Map<String, dynamic>>(path)
        : await client.post<Map<String, dynamic>>(path);
    return response.data ?? const <String, dynamic>{};
  }

  String _normalizedCameraControlBaseUrl() {
    final trimmed = _cameraControlBaseUrl.trim();
    if (trimmed.endsWith('/api/v1')) return trimmed;
    return '${trimmed.replaceAll(RegExp(r'/+$'), '')}/api/v1';
  }

  String _streamUrlWithRefreshKey() {
    final separator = _piCameraStreamUrl.contains('?') ? '&' : '?';
    return '$_piCameraStreamUrl${separator}restart=$_streamRefreshKey';
  }

  String _cameraControlError(Object error) {
    final isArabic = Localizations.localeOf(context).languageCode == 'ar';
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
    }
    return isArabic
        ? 'تعذر التحكم بكاميرا الرازبيري الآن.'
        : 'Could not control the Raspberry Pi camera right now.';
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
