import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app_session.dart';

final appSessionProvider = ChangeNotifierProvider<AppSession>((ref) {
  final session = AppSession();
  session.initialize();
  return session;
});
