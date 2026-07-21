import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../networking/api_client.dart';
import 'models.dart';

enum SessionStatus { loading, unauthenticated, authenticated }

class AppSession extends ChangeNotifier {
  AppSession({ApiClient? apiClient}) : api = apiClient ?? ApiClient() {
    api.refreshAccessToken = _refreshAccessToken;
  }

  final ApiClient api;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  SessionStatus status = SessionStatus.loading;
  Locale locale = const Locale('ar');
  ThemeMode themeMode = ThemeMode.system;
  AppUser? user;
  List<PatientSummary> patients = const [];
  String? accessToken;
  String? refreshToken;
  String? error;
  bool busy = false;
  bool _initialized = false;

  PatientSummary? get currentPatient =>
      patients.isEmpty ? null : patients.first;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    try {
      final savedLocale = await _safeRead('preferred_locale');
      if (savedLocale == 'ar' || savedLocale == 'en') {
        locale = Locale(savedLocale!);
      }
      final savedThemeMode = await _safeRead('preferred_theme_mode');
      themeMode = _themeModeFromStorage(savedThemeMode);
      accessToken = await _safeRead('access_token');
      refreshToken = await _safeRead('refresh_token');
      if (accessToken == null) {
        status = SessionStatus.unauthenticated;
      } else {
        api.setAccessToken(accessToken);
        final response = await api.dio.get<Map<String, dynamic>>('/auth/me');
        user = AppUser.fromJson(response.data!);
        if (savedLocale == null) {
          locale = Locale(response.data!['locale']?.toString() ?? 'ar');
        }
        await loadPatients();
        status = SessionStatus.authenticated;
      }
    } catch (_) {
      final restored = await _refreshAccessToken();
      if (restored != null) {
        try {
          final response = await api.dio.get<Map<String, dynamic>>('/auth/me');
          user = AppUser.fromJson(response.data!);
          await loadPatients();
          status = SessionStatus.authenticated;
        } catch (_) {
          await _clearTokens();
          status = SessionStatus.unauthenticated;
        }
      } else {
        await _clearTokens();
        status = SessionStatus.unauthenticated;
      }
    }
    notifyListeners();
  }

  Future<bool> register({
    required String name,
    required String email,
    required String password,
    String role = 'caregiver',
  }) async {
    return _run(() async {
      await api.dio.post('/auth/register', data: {
        'full_name': name,
        'email': email,
        'password': password,
        'role': role,
        'locale': locale.languageCode,
      });
      await _loginRequest(email, password);
    });
  }

  Future<bool> login(String email, String password) =>
      _run(() => _loginRequest(email, password));

  Future<void> _loginRequest(String email, String password) async {
    final response =
        await api.dio.post<Map<String, dynamic>>('/auth/login', data: {
      'email': email,
      'password': password,
    });
    final data = response.data!;
    accessToken = data['access_token'] as String;
    refreshToken = data['refresh_token'] as String;
    api.setAccessToken(accessToken);
    user = AppUser.fromJson(data['user'] as Map<String, dynamic>);
    await _safeWrite('access_token', accessToken!);
    await _safeWrite('refresh_token', refreshToken!);
    await loadPatients();
    status = SessionStatus.authenticated;
  }

  Future<String?> _refreshAccessToken() async {
    if (refreshToken == null) return null;
    try {
      final raw = Dio(BaseOptions(
        baseUrl: api.dio.options.baseUrl,
        connectTimeout: const Duration(seconds: 8),
        receiveTimeout: const Duration(seconds: 8),
      ));
      final response = await raw.post<Map<String, dynamic>>('/auth/refresh',
          data: {'refresh_token': refreshToken});
      final data = response.data!;
      accessToken = data['access_token'] as String;
      refreshToken = data['refresh_token'] as String;
      api.setAccessToken(accessToken);
      await _safeWrite('access_token', accessToken!);
      await _safeWrite('refresh_token', refreshToken!);
      return accessToken;
    } catch (_) {
      return null;
    }
  }

  Future<void> loadPatients() async {
    final response = await api.dio.get<Map<String, dynamic>>('/patients');
    final items = response.data?['items'] as List<dynamic>? ?? const [];
    patients = items
        .map((item) => PatientSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<bool> createPatient(String name) => _run(() async {
        await api.dio.post('/patients', data: {
          'display_name': name,
          'preferred_language': locale.languageCode
        });
        await loadPatients();
      });

  Future<void> logout() async {
    if (refreshToken != null) {
      try {
        await api.dio
            .post('/auth/logout', data: {'refresh_token': refreshToken});
      } catch (_) {}
    }
    await _clearTokens();
    patients = const [];
    user = null;
    status = SessionStatus.unauthenticated;
    notifyListeners();
  }

  void changeLocale(String languageCode) {
    if (languageCode != 'ar' && languageCode != 'en') return;
    locale = Locale(languageCode);
    unawaited(_safeWrite('preferred_locale', languageCode));
    notifyListeners();
  }

  void changeThemeMode(ThemeMode mode) {
    themeMode = mode;
    unawaited(_safeWrite('preferred_theme_mode', mode.name));
    notifyListeners();
  }

  ThemeMode _themeModeFromStorage(String? value) {
    switch (value) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  Future<bool> _run(Future<void> Function() action) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      await action();
      return true;
    } catch (exception) {
      error = api.errorMessage(exception);
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<String?> _safeRead(String key) async {
    try {
      return await _storage.read(key: key);
    } catch (_) {
      return null;
    }
  }

  Future<void> _safeWrite(String key, String value) async {
    try {
      await _storage.write(key: key, value: value);
    } catch (error) {
      if (kDebugMode) {
        debugPrint(
            'Secure storage unavailable for this browser session: $error');
      }
    }
  }

  Future<void> _clearTokens() async {
    accessToken = null;
    refreshToken = null;
    api.setAccessToken(null);
    try {
      await _storage.delete(key: 'access_token');
      await _storage.delete(key: 'refresh_token');
    } catch (_) {}
  }
}
