import 'package:dio/dio.dart';

class ApiFailure implements Exception {
  ApiFailure(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient()
      : dio = Dio(BaseOptions(
            baseUrl: _baseUrl(),
            connectTimeout: const Duration(seconds: 8),
            receiveTimeout: const Duration(seconds: 8))) {
    dio.interceptors
        .add(QueuedInterceptorsWrapper(onError: (error, handler) async {
      final canRefresh = error.response?.statusCode == 401 &&
          error.requestOptions.extra['retried_after_refresh'] != true &&
          !error.requestOptions.path.contains('/auth/refresh') &&
          refreshAccessToken != null;
      if (canRefresh) {
        final token = await refreshAccessToken!();
        if (token != null) {
          final request = error.requestOptions;
          request.extra['retried_after_refresh'] = true;
          request.headers['Authorization'] = 'Bearer $token';
          try {
            return handler.resolve(await dio.fetch(request));
          } catch (_) {}
        }
      }
      final data = error.response?.data;
      var message = networkUnavailableMessage;
      if (data is Map && data['error'] is Map) {
        message = data['error']['message']?.toString() ?? message;
      }
      handler.reject(DioException(
        requestOptions: error.requestOptions,
        response: error.response,
        type: error.type,
        error: ApiFailure(message, statusCode: error.response?.statusCode),
      ));
    }));
  }

  final Dio dio;
  Future<String?> Function()? refreshAccessToken;
  String networkUnavailableMessage = 'Unable to connect to the RAFEEQ service';
  String unexpectedErrorMessage = 'An unexpected error occurred';

  void configureErrorMessages({
    required String networkUnavailable,
    required String unexpectedError,
  }) {
    networkUnavailableMessage = networkUnavailable;
    unexpectedErrorMessage = unexpectedError;
  }

  static String _baseUrl() {
    const configured = String.fromEnvironment('API_BASE_URL');
    if (configured.isNotEmpty) return configured;
    final host = Uri.base.host.isEmpty ? '127.0.0.1' : Uri.base.host;
    final secure = Uri.base.scheme == 'https';
    final scheme = secure ? 'https' : 'http';
    final port = secure ? 8444 : 8000;
    return '$scheme://$host:$port/api/v1';
  }

  void setAccessToken(String? token) {
    if (token == null) {
      dio.options.headers.remove('Authorization');
    } else {
      dio.options.headers['Authorization'] = 'Bearer $token';
    }
  }

  String errorMessage(Object error) {
    if (error is DioException && error.error is ApiFailure) {
      return (error.error! as ApiFailure).message;
    }
    return unexpectedErrorMessage;
  }
}
