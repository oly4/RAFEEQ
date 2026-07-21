import 'package:web/web.dart' as web;

class BrowserSessionStorage {
  static const _prefix = 'rafeeq.';

  String? read(String key) => web.window.localStorage.getItem('$_prefix$key');

  void write(String key, String value) {
    web.window.localStorage.setItem('$_prefix$key', value);
  }

  void delete(String key) {
    web.window.localStorage.removeItem('$_prefix$key');
  }
}
