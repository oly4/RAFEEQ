import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('ar'),
    Locale('en')
  ];

  /// No description provided for @appName.
  ///
  /// In ar, this message translates to:
  /// **'رفيق'**
  String get appName;

  /// No description provided for @robotSemanticLabel.
  ///
  /// In ar, this message translates to:
  /// **'روبوت رفيق'**
  String get robotSemanticLabel;

  /// No description provided for @welcome.
  ///
  /// In ar, this message translates to:
  /// **'رعاية ومساندة يومية لكبار السن'**
  String get welcome;

  /// No description provided for @chooseLoginRole.
  ///
  /// In ar, this message translates to:
  /// **'اختر طريقة تسجيل الدخول'**
  String get chooseLoginRole;

  /// No description provided for @platformDescription.
  ///
  /// In ar, this message translates to:
  /// **'منصة رفيق تربط بين العائلة والطبيب لمتابعة ورعاية مرضى الزهايمر.'**
  String get platformDescription;

  /// No description provided for @caregiverLogin.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الدخول كعائلة'**
  String get caregiverLogin;

  /// No description provided for @doctorLogin.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الدخول كطبيب'**
  String get doctorLogin;

  /// No description provided for @caregiverRoleDescription.
  ///
  /// In ar, this message translates to:
  /// **'إدارة الروتين اليومي، الذكريات، الأنشطة، متابعة التقارير واستقبال تنبيهات الطوارئ.'**
  String get caregiverRoleDescription;

  /// No description provided for @doctorRoleDescription.
  ///
  /// In ar, this message translates to:
  /// **'متابعة الحالة الطبية، مراجعة التقارير، إضافة الملاحظات، ومراقبة تقدم المريض.'**
  String get doctorRoleDescription;

  /// No description provided for @termsOfUse.
  ///
  /// In ar, this message translates to:
  /// **'شروط الاستخدام'**
  String get termsOfUse;

  /// No description provided for @byContinuing.
  ///
  /// In ar, this message translates to:
  /// **'بالمتابعة فأنت توافق على الشروط وسياسة الخصوصية.'**
  String get byContinuing;

  /// No description provided for @familyAccess.
  ///
  /// In ar, this message translates to:
  /// **'دخول العائلة'**
  String get familyAccess;

  /// No description provided for @doctorAccess.
  ///
  /// In ar, this message translates to:
  /// **'دخول الطبيب'**
  String get doctorAccess;

  /// No description provided for @secureAccessSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'دخول آمن إلى منصة رفيق للرعاية'**
  String get secureAccessSubtitle;

  /// No description provided for @welcomeBack.
  ///
  /// In ar, this message translates to:
  /// **'مرحباً بعودتك'**
  String get welcomeBack;

  /// No description provided for @family.
  ///
  /// In ar, this message translates to:
  /// **'العائلة'**
  String get family;

  /// No description provided for @familyApp.
  ///
  /// In ar, this message translates to:
  /// **'تطبيق العائلة'**
  String get familyApp;

  /// No description provided for @doctorApp.
  ///
  /// In ar, this message translates to:
  /// **'تطبيق الطبيب'**
  String get doctorApp;

  /// No description provided for @platformFooter.
  ///
  /// In ar, this message translates to:
  /// **'تطبيق رفيق · رعاية مرضى الزهايمر'**
  String get platformFooter;

  /// No description provided for @dailyCareTagline.
  ///
  /// In ar, this message translates to:
  /// **'رفيق يومك… اهتمام يسهّل الحياة'**
  String get dailyCareTagline;

  /// No description provided for @back.
  ///
  /// In ar, this message translates to:
  /// **'رجوع'**
  String get back;

  /// No description provided for @homePage.
  ///
  /// In ar, this message translates to:
  /// **'الصفحة الرئيسية'**
  String get homePage;

  /// No description provided for @robotStatus.
  ///
  /// In ar, this message translates to:
  /// **'حالة الروبوت'**
  String get robotStatus;

  /// No description provided for @talkingNow.
  ///
  /// In ar, this message translates to:
  /// **'يتحدث مع المريض الآن'**
  String get talkingNow;

  /// No description provided for @showingFamilyPhotos.
  ///
  /// In ar, this message translates to:
  /// **'يعرض صور العائلة'**
  String get showingFamilyPhotos;

  /// No description provided for @conversation.
  ///
  /// In ar, this message translates to:
  /// **'محادثة'**
  String get conversation;

  /// No description provided for @poetry.
  ///
  /// In ar, this message translates to:
  /// **'شعر'**
  String get poetry;

  /// No description provided for @live.
  ///
  /// In ar, this message translates to:
  /// **'مباشر'**
  String get live;

  /// No description provided for @liveRoomTitle.
  ///
  /// In ar, this message translates to:
  /// **'بث مباشر من غرفة المريض'**
  String get liveRoomTitle;

  /// No description provided for @liveRoomSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'شاهد المريض في الوقت الحالي'**
  String get liveRoomSubtitle;

  /// No description provided for @todayMedication.
  ///
  /// In ar, this message translates to:
  /// **'الدواء اليوم'**
  String get todayMedication;

  /// No description provided for @reportsSentToDoctor.
  ///
  /// In ar, this message translates to:
  /// **'التقارير المُرسلة للطبيب'**
  String get reportsSentToDoctor;

  /// No description provided for @browseReports.
  ///
  /// In ar, this message translates to:
  /// **'تصفح، ابحث، وافتح أي تقرير سابق'**
  String get browseReports;

  /// No description provided for @latestAlert.
  ///
  /// In ar, this message translates to:
  /// **'آخر تنبيه'**
  String get latestAlert;

  /// No description provided for @album.
  ///
  /// In ar, this message translates to:
  /// **'الألبوم'**
  String get album;

  /// No description provided for @today.
  ///
  /// In ar, this message translates to:
  /// **'اليوم'**
  String get today;

  /// No description provided for @week.
  ///
  /// In ar, this message translates to:
  /// **'الأسبوع'**
  String get week;

  /// No description provided for @month.
  ///
  /// In ar, this message translates to:
  /// **'الشهر'**
  String get month;

  /// No description provided for @latestReport.
  ///
  /// In ar, this message translates to:
  /// **'أحدث تقرير'**
  String get latestReport;

  /// No description provided for @reportReady.
  ///
  /// In ar, this message translates to:
  /// **'ملخص الرعاية الحالي جاهز'**
  String get reportReady;

  /// No description provided for @searchReports.
  ///
  /// In ar, this message translates to:
  /// **'ابحث في التقارير'**
  String get searchReports;

  /// No description provided for @patientData.
  ///
  /// In ar, this message translates to:
  /// **'بيانات المريض'**
  String get patientData;

  /// No description provided for @familyMembers.
  ///
  /// In ar, this message translates to:
  /// **'أفراد العائلة'**
  String get familyMembers;

  /// No description provided for @robotSettings.
  ///
  /// In ar, this message translates to:
  /// **'إعدادات الروبوت'**
  String get robotSettings;

  /// No description provided for @notifications.
  ///
  /// In ar, this message translates to:
  /// **'الإشعارات'**
  String get notifications;

  /// No description provided for @privacyAndSafety.
  ///
  /// In ar, this message translates to:
  /// **'الخصوصية والأمان'**
  String get privacyAndSafety;

  /// No description provided for @aboutApp.
  ///
  /// In ar, this message translates to:
  /// **'حول تطبيق رفيق'**
  String get aboutApp;

  /// No description provided for @call.
  ///
  /// In ar, this message translates to:
  /// **'اتصال'**
  String get call;

  /// No description provided for @message.
  ///
  /// In ar, this message translates to:
  /// **'مراسلة'**
  String get message;

  /// No description provided for @sendLatestReport.
  ///
  /// In ar, this message translates to:
  /// **'إرسال أحدث تقرير'**
  String get sendLatestReport;

  /// No description provided for @login.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الدخول'**
  String get login;

  /// No description provided for @createAccount.
  ///
  /// In ar, this message translates to:
  /// **'إنشاء حساب'**
  String get createAccount;

  /// No description provided for @email.
  ///
  /// In ar, this message translates to:
  /// **'البريد الإلكتروني'**
  String get email;

  /// No description provided for @password.
  ///
  /// In ar, this message translates to:
  /// **'كلمة المرور'**
  String get password;

  /// No description provided for @fullName.
  ///
  /// In ar, this message translates to:
  /// **'الاسم الكامل'**
  String get fullName;

  /// No description provided for @continueLabel.
  ///
  /// In ar, this message translates to:
  /// **'متابعة'**
  String get continueLabel;

  /// No description provided for @logout.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الخروج'**
  String get logout;

  /// No description provided for @patientName.
  ///
  /// In ar, this message translates to:
  /// **'اسم الشخص الذي ترعاه'**
  String get patientName;

  /// No description provided for @createPatient.
  ///
  /// In ar, this message translates to:
  /// **'إضافة ملف المريض'**
  String get createPatient;

  /// No description provided for @dashboard.
  ///
  /// In ar, this message translates to:
  /// **'الرئيسية'**
  String get dashboard;

  /// No description provided for @routine.
  ///
  /// In ar, this message translates to:
  /// **'الروتين'**
  String get routine;

  /// No description provided for @emergencies.
  ///
  /// In ar, this message translates to:
  /// **'الطوارئ'**
  String get emergencies;

  /// No description provided for @reports.
  ///
  /// In ar, this message translates to:
  /// **'التقارير'**
  String get reports;

  /// No description provided for @settings.
  ///
  /// In ar, this message translates to:
  /// **'الإعدادات'**
  String get settings;

  /// No description provided for @addReminder.
  ///
  /// In ar, this message translates to:
  /// **'إضافة تذكير دواء'**
  String get addReminder;

  /// No description provided for @medicationName.
  ///
  /// In ar, this message translates to:
  /// **'اسم الدواء'**
  String get medicationName;

  /// No description provided for @dosage.
  ///
  /// In ar, this message translates to:
  /// **'الجرعة المكتوبة'**
  String get dosage;

  /// No description provided for @time.
  ///
  /// In ar, this message translates to:
  /// **'الوقت'**
  String get time;

  /// No description provided for @save.
  ///
  /// In ar, this message translates to:
  /// **'حفظ'**
  String get save;

  /// No description provided for @cancel.
  ///
  /// In ar, this message translates to:
  /// **'إلغاء'**
  String get cancel;

  /// No description provided for @complete.
  ///
  /// In ar, this message translates to:
  /// **'تم'**
  String get complete;

  /// No description provided for @retry.
  ///
  /// In ar, this message translates to:
  /// **'إعادة المحاولة'**
  String get retry;

  /// No description provided for @noData.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد بيانات بعد'**
  String get noData;

  /// No description provided for @loading.
  ///
  /// In ar, this message translates to:
  /// **'جارٍ التحميل…'**
  String get loading;

  /// No description provided for @device.
  ///
  /// In ar, this message translates to:
  /// **'جهاز رفيق'**
  String get device;

  /// No description provided for @dailyProgress.
  ///
  /// In ar, this message translates to:
  /// **'إنجاز اليوم'**
  String get dailyProgress;

  /// No description provided for @activeAlerts.
  ///
  /// In ar, this message translates to:
  /// **'تنبيهات نشطة'**
  String get activeAlerts;

  /// No description provided for @privacy.
  ///
  /// In ar, this message translates to:
  /// **'لا يتم رفع الفيديو أو الصوت الخام افتراضياً.'**
  String get privacy;

  /// No description provided for @privacyTitle.
  ///
  /// In ar, this message translates to:
  /// **'الخصوصية'**
  String get privacyTitle;

  /// No description provided for @language.
  ///
  /// In ar, this message translates to:
  /// **'اللغة'**
  String get language;

  /// No description provided for @arabic.
  ///
  /// In ar, this message translates to:
  /// **'العربية'**
  String get arabic;

  /// No description provided for @english.
  ///
  /// In ar, this message translates to:
  /// **'English'**
  String get english;

  /// No description provided for @ok.
  ///
  /// In ar, this message translates to:
  /// **'حسناً'**
  String get ok;

  /// No description provided for @caregiver.
  ///
  /// In ar, this message translates to:
  /// **'مقدم رعاية'**
  String get caregiver;

  /// No description provided for @doctor.
  ///
  /// In ar, this message translates to:
  /// **'طبيب'**
  String get doctor;

  /// No description provided for @fullNameRequired.
  ///
  /// In ar, this message translates to:
  /// **'أدخل الاسم الكامل'**
  String get fullNameRequired;

  /// No description provided for @validEmailRequired.
  ///
  /// In ar, this message translates to:
  /// **'أدخل بريداً صحيحاً'**
  String get validEmailRequired;

  /// No description provided for @passwordLengthRequired.
  ///
  /// In ar, this message translates to:
  /// **'استخدم 8 أحرف على الأقل'**
  String get passwordLengthRequired;

  /// No description provided for @medications.
  ///
  /// In ar, this message translates to:
  /// **'الأدوية'**
  String get medications;

  /// No description provided for @tasks.
  ///
  /// In ar, this message translates to:
  /// **'المهام'**
  String get tasks;

  /// No description provided for @noActiveEmergency.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد حالة طارئة نشطة'**
  String get noActiveEmergency;

  /// No description provided for @deviceNotPaired.
  ///
  /// In ar, this message translates to:
  /// **'لم يتم إقران جهاز رفيق'**
  String get deviceNotPaired;

  /// No description provided for @pairSimulator.
  ///
  /// In ar, this message translates to:
  /// **'إقران جهاز المحاكاة'**
  String get pairSimulator;

  /// No description provided for @status.
  ///
  /// In ar, this message translates to:
  /// **'الحالة'**
  String get status;

  /// No description provided for @simulateSos.
  ///
  /// In ar, this message translates to:
  /// **'محاكاة ضغط زر SOS'**
  String get simulateSos;

  /// No description provided for @simulateFall.
  ///
  /// In ar, this message translates to:
  /// **'محاكاة اكتشاف سقوط'**
  String get simulateFall;

  /// No description provided for @emergencyHistory.
  ///
  /// In ar, this message translates to:
  /// **'سجل الطوارئ'**
  String get emergencyHistory;

  /// No description provided for @noEmergencyHistory.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد حالة طارئة مسجلة'**
  String get noEmergencyHistory;

  /// No description provided for @sosHelpRequest.
  ///
  /// In ar, this message translates to:
  /// **'طلب مساعدة SOS'**
  String get sosHelpRequest;

  /// No description provided for @fallDetected.
  ///
  /// In ar, this message translates to:
  /// **'اكتشاف سقوط'**
  String get fallDetected;

  /// No description provided for @result.
  ///
  /// In ar, this message translates to:
  /// **'النتيجة'**
  String get result;

  /// No description provided for @acknowledgeAlert.
  ///
  /// In ar, this message translates to:
  /// **'تأكيد استلام التنبيه'**
  String get acknowledgeAlert;

  /// No description provided for @fallVerificationQuestion.
  ///
  /// In ar, this message translates to:
  /// **'الجهاز يسأل المريض الآن: هل أنت بخير؟'**
  String get fallVerificationQuestion;

  /// No description provided for @patientIsOkay.
  ///
  /// In ar, this message translates to:
  /// **'أنا بخير'**
  String get patientIsOkay;

  /// No description provided for @simulateNoResponse.
  ///
  /// In ar, this message translates to:
  /// **'محاكاة عدم الرد'**
  String get simulateNoResponse;

  /// No description provided for @resolveEmergency.
  ///
  /// In ar, this message translates to:
  /// **'حل الحالة'**
  String get resolveEmergency;

  /// No description provided for @simulateSosTitle.
  ///
  /// In ar, this message translates to:
  /// **'محاكاة SOS'**
  String get simulateSosTitle;

  /// No description provided for @simulateSosConfirmation.
  ///
  /// In ar, this message translates to:
  /// **'سيتم إنشاء حالة طارئة تجريبية وإضافتها إلى السجل. هل تريد المتابعة؟'**
  String get simulateSosConfirmation;

  /// No description provided for @runSimulation.
  ///
  /// In ar, this message translates to:
  /// **'تشغيل المحاكاة'**
  String get runSimulation;

  /// No description provided for @resolveEmergencyTitle.
  ///
  /// In ar, this message translates to:
  /// **'حل الحالة الطارئة'**
  String get resolveEmergencyTitle;

  /// No description provided for @resolutionNote.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظة الحل'**
  String get resolutionNote;

  /// No description provided for @resolutionHint.
  ///
  /// In ar, this message translates to:
  /// **'مثال: تم التواصل والمريض بخير'**
  String get resolutionHint;

  /// No description provided for @saveAndResolve.
  ///
  /// In ar, this message translates to:
  /// **'حفظ وحل الحالة'**
  String get saveAndResolve;

  /// No description provided for @routineCompletion.
  ///
  /// In ar, this message translates to:
  /// **'إجمالي إكمال الروتين'**
  String get routineCompletion;

  /// No description provided for @medicationAdherence.
  ///
  /// In ar, this message translates to:
  /// **'التزام الدواء'**
  String get medicationAdherence;

  /// No description provided for @totalEmergencies.
  ///
  /// In ar, this message translates to:
  /// **'إجمالي حالات الطوارئ'**
  String get totalEmergencies;

  /// No description provided for @completedActivitySessions.
  ///
  /// In ar, this message translates to:
  /// **'جلسات النشاط المكتملة'**
  String get completedActivitySessions;

  /// No description provided for @memoryExercises.
  ///
  /// In ar, this message translates to:
  /// **'تمارين الذاكرة'**
  String get memoryExercises;

  /// No description provided for @medicalDisclaimer.
  ///
  /// In ar, this message translates to:
  /// **'هذه مؤشرات التزام ونشاط وليست تشخيصاً طبياً.'**
  String get medicalDisclaimer;

  /// No description provided for @clinicalDisclaimer.
  ///
  /// In ar, this message translates to:
  /// **'هذه مؤشرات التزام ونشاط وليست تشخيصاً أو قراراً سريرياً.'**
  String get clinicalDisclaimer;

  /// No description provided for @activities.
  ///
  /// In ar, this message translates to:
  /// **'الأنشطة'**
  String get activities;

  /// No description provided for @activitiesSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'تمارين الذاكرة والقراءة والمحادثة'**
  String get activitiesSubtitle;

  /// No description provided for @memorySupport.
  ///
  /// In ar, this message translates to:
  /// **'دعم الذاكرة'**
  String get memorySupport;

  /// No description provided for @memorySupportSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'العائلة والأصدقاء والأحداث'**
  String get memorySupportSubtitle;

  /// No description provided for @doctorFollowUp.
  ///
  /// In ar, this message translates to:
  /// **'الطبيب والمتابعة'**
  String get doctorFollowUp;

  /// No description provided for @doctorFollowUpSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'التعيين والملاحظات المشتركة'**
  String get doctorFollowUpSubtitle;

  /// No description provided for @cameraTest.
  ///
  /// In ar, this message translates to:
  /// **'اختبار الكاميرا'**
  String get cameraTest;

  /// No description provided for @cameraTestSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'معاينة كاميرا هذا الجهاز بأمان'**
  String get cameraTestSubtitle;

  /// No description provided for @cameraPrivacyNotice.
  ///
  /// In ar, this message translates to:
  /// **'معاينة مباشرة فقط. لا يسجل رفيق هذا الفيديو ولا يحفظه أو يرفعه.'**
  String get cameraPrivacyNotice;

  /// No description provided for @cameraPermissionPrompt.
  ///
  /// In ar, this message translates to:
  /// **'سيطلب Safari إذن الوصول إلى الكاميرا. اختر سماح لبدء الاختبار.'**
  String get cameraPermissionPrompt;

  /// No description provided for @startCameraTest.
  ///
  /// In ar, this message translates to:
  /// **'بدء اختبار الكاميرا'**
  String get startCameraTest;

  /// No description provided for @stopCamera.
  ///
  /// In ar, this message translates to:
  /// **'إيقاف الكاميرا'**
  String get stopCamera;

  /// No description provided for @switchCamera.
  ///
  /// In ar, this message translates to:
  /// **'تبديل الكاميرا'**
  String get switchCamera;

  /// No description provided for @liveCameraPreview.
  ///
  /// In ar, this message translates to:
  /// **'معاينة مباشرة للكاميرا'**
  String get liveCameraPreview;

  /// No description provided for @noCameraFound.
  ///
  /// In ar, this message translates to:
  /// **'لم يتم العثور على كاميرا في هذا الجهاز.'**
  String get noCameraFound;

  /// No description provided for @cameraPermissionDenied.
  ///
  /// In ar, this message translates to:
  /// **'تم رفض إذن الكاميرا. اسمح للموقع باستخدام الكاميرا من إعدادات Safari ثم حاول مرة أخرى.'**
  String get cameraPermissionDenied;

  /// No description provided for @cameraAccessRestricted.
  ///
  /// In ar, this message translates to:
  /// **'الوصول إلى الكاميرا مقيد بواسطة إعدادات الخصوصية أو الرقابة الأبوية في الجهاز.'**
  String get cameraAccessRestricted;

  /// No description provided for @cameraUnavailable.
  ///
  /// In ar, this message translates to:
  /// **'تعذر تشغيل الكاميرا. أغلق التطبيقات الأخرى التي تستخدمها ثم حاول مرة أخرى.'**
  String get cameraUnavailable;

  /// No description provided for @cameraSecureContextRequired.
  ///
  /// In ar, this message translates to:
  /// **'يتطلب الوصول إلى الكاميرا استخدام نسخة رفيق الآمنة عبر HTTPS.'**
  String get cameraSecureContextRequired;

  /// No description provided for @addActivityPrompt.
  ///
  /// In ar, this message translates to:
  /// **'أضف نشاطاً للقراءة أو الذاكرة أو المحادثة.'**
  String get addActivityPrompt;

  /// No description provided for @minutes.
  ///
  /// In ar, this message translates to:
  /// **'دقيقة'**
  String get minutes;

  /// No description provided for @activityDuration.
  ///
  /// In ar, this message translates to:
  /// **'{count, plural, =0{— دقيقة} other{{count} دقيقة}}'**
  String activityDuration(int count);

  /// No description provided for @start.
  ///
  /// In ar, this message translates to:
  /// **'ابدأ'**
  String get start;

  /// No description provided for @addActivity.
  ///
  /// In ar, this message translates to:
  /// **'إضافة نشاط'**
  String get addActivity;

  /// No description provided for @newActivity.
  ///
  /// In ar, this message translates to:
  /// **'نشاط جديد'**
  String get newActivity;

  /// No description provided for @activityTitle.
  ///
  /// In ar, this message translates to:
  /// **'عنوان النشاط'**
  String get activityTitle;

  /// No description provided for @activityType.
  ///
  /// In ar, this message translates to:
  /// **'النوع'**
  String get activityType;

  /// No description provided for @activityMemoryExercise.
  ///
  /// In ar, this message translates to:
  /// **'تمرين ذاكرة'**
  String get activityMemoryExercise;

  /// No description provided for @activityRecognizePhotos.
  ///
  /// In ar, this message translates to:
  /// **'التعرف على الصور'**
  String get activityRecognizePhotos;

  /// No description provided for @activityCompletePhrase.
  ///
  /// In ar, this message translates to:
  /// **'إكمال عبارة مألوفة'**
  String get activityCompletePhrase;

  /// No description provided for @activityReading.
  ///
  /// In ar, this message translates to:
  /// **'قراءة أو قرآن'**
  String get activityReading;

  /// No description provided for @activityConversation.
  ///
  /// In ar, this message translates to:
  /// **'محادثة ودية'**
  String get activityConversation;

  /// No description provided for @activityCalmMusic.
  ///
  /// In ar, this message translates to:
  /// **'موسيقى هادئة'**
  String get activityCalmMusic;

  /// No description provided for @activityCustom.
  ///
  /// In ar, this message translates to:
  /// **'نشاط مخصص'**
  String get activityCustom;

  /// No description provided for @activityInstructions.
  ///
  /// In ar, this message translates to:
  /// **'ابدأ النشاط بهدوء، ثم اضغط تم عند الانتهاء.'**
  String get activityInstructions;

  /// No description provided for @activityDone.
  ///
  /// In ar, this message translates to:
  /// **'تم النشاط'**
  String get activityDone;

  /// No description provided for @activityCompletionRecorded.
  ///
  /// In ar, this message translates to:
  /// **'تم تسجيل إكمال النشاط'**
  String get activityCompletionRecorded;

  /// No description provided for @addCategory.
  ///
  /// In ar, this message translates to:
  /// **'إضافة فئة'**
  String get addCategory;

  /// No description provided for @noMemoriesPrompt.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد ذكريات بعد. أضف فئة ثم ذكرى.'**
  String get noMemoriesPrompt;

  /// No description provided for @addMemory.
  ///
  /// In ar, this message translates to:
  /// **'إضافة ذكرى'**
  String get addMemory;

  /// No description provided for @newCategory.
  ///
  /// In ar, this message translates to:
  /// **'فئة جديدة'**
  String get newCategory;

  /// No description provided for @categoryName.
  ///
  /// In ar, this message translates to:
  /// **'اسم الفئة'**
  String get categoryName;

  /// No description provided for @addCategoryFirst.
  ///
  /// In ar, this message translates to:
  /// **'أضف فئة أولاً'**
  String get addCategoryFirst;

  /// No description provided for @newMemory.
  ///
  /// In ar, this message translates to:
  /// **'ذكرى جديدة'**
  String get newMemory;

  /// No description provided for @title.
  ///
  /// In ar, this message translates to:
  /// **'العنوان'**
  String get title;

  /// No description provided for @description.
  ///
  /// In ar, this message translates to:
  /// **'الوصف'**
  String get description;

  /// No description provided for @category.
  ///
  /// In ar, this message translates to:
  /// **'الفئة'**
  String get category;

  /// No description provided for @noDoctorAssigned.
  ///
  /// In ar, this message translates to:
  /// **'لم يتم تعيين طبيب بعد.'**
  String get noDoctorAssigned;

  /// No description provided for @inviteRegisteredDoctor.
  ///
  /// In ar, this message translates to:
  /// **'دعوة طبيب مسجل'**
  String get inviteRegisteredDoctor;

  /// No description provided for @followUpNotes.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظات المتابعة'**
  String get followUpNotes;

  /// No description provided for @noSharedNotes.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد ملاحظات مشتركة بعد.'**
  String get noSharedNotes;

  /// No description provided for @inviteDoctor.
  ///
  /// In ar, this message translates to:
  /// **'دعوة طبيب'**
  String get inviteDoctor;

  /// No description provided for @doctorAccountEmail.
  ///
  /// In ar, this message translates to:
  /// **'بريد حساب الطبيب'**
  String get doctorAccountEmail;

  /// No description provided for @invite.
  ///
  /// In ar, this message translates to:
  /// **'دعوة'**
  String get invite;

  /// No description provided for @doctorDashboard.
  ///
  /// In ar, this message translates to:
  /// **'لوحة الطبيب'**
  String get doctorDashboard;

  /// No description provided for @doctorPatients.
  ///
  /// In ar, this message translates to:
  /// **'المرضى'**
  String get doctorPatients;

  /// No description provided for @alerts.
  ///
  /// In ar, this message translates to:
  /// **'تنبيهات'**
  String get alerts;

  /// No description provided for @newReports.
  ///
  /// In ar, this message translates to:
  /// **'تقارير جديدة'**
  String get newReports;

  /// No description provided for @appointments.
  ///
  /// In ar, this message translates to:
  /// **'المواعيد'**
  String get appointments;

  /// No description provided for @patientList.
  ///
  /// In ar, this message translates to:
  /// **'قائمة المرضى'**
  String get patientList;

  /// No description provided for @medicalReports.
  ///
  /// In ar, this message translates to:
  /// **'التقارير الطبية'**
  String get medicalReports;

  /// No description provided for @emergencyCases.
  ///
  /// In ar, this message translates to:
  /// **'حالات الطوارئ'**
  String get emergencyCases;

  /// No description provided for @weekly.
  ///
  /// In ar, this message translates to:
  /// **'أسبوعي'**
  String get weekly;

  /// No description provided for @monthly.
  ///
  /// In ar, this message translates to:
  /// **'شهري'**
  String get monthly;

  /// No description provided for @quarterly.
  ///
  /// In ar, this message translates to:
  /// **'ربع سنوي'**
  String get quarterly;

  /// No description provided for @stable.
  ///
  /// In ar, this message translates to:
  /// **'مستقر'**
  String get stable;

  /// No description provided for @needsFollowUp.
  ///
  /// In ar, this message translates to:
  /// **'بحاجة متابعة'**
  String get needsFollowUp;

  /// No description provided for @criticalCondition.
  ///
  /// In ar, this message translates to:
  /// **'حالة حرجة'**
  String get criticalCondition;

  /// No description provided for @lastUpdated.
  ///
  /// In ar, this message translates to:
  /// **'آخر تحديث'**
  String get lastUpdated;

  /// No description provided for @yearsOld.
  ///
  /// In ar, this message translates to:
  /// **'سنة'**
  String get yearsOld;

  /// No description provided for @unknownAge.
  ///
  /// In ar, this message translates to:
  /// **'العمر غير مسجل'**
  String get unknownAge;

  /// No description provided for @backToPatients.
  ///
  /// In ar, this message translates to:
  /// **'رجوع لقائمة المرضى'**
  String get backToPatients;

  /// No description provided for @diagnosis.
  ///
  /// In ar, this message translates to:
  /// **'التشخيص'**
  String get diagnosis;

  /// No description provided for @contactFamily.
  ///
  /// In ar, this message translates to:
  /// **'اتصال بالعائلة'**
  String get contactFamily;

  /// No description provided for @sendReport.
  ///
  /// In ar, this message translates to:
  /// **'فتح التقرير'**
  String get sendReport;

  /// No description provided for @engagementLevel.
  ///
  /// In ar, this message translates to:
  /// **'مستوى التفاعل'**
  String get engagementLevel;

  /// No description provided for @fallCases.
  ///
  /// In ar, this message translates to:
  /// **'حالات السقوط'**
  String get fallCases;

  /// No description provided for @weeklyEngagement.
  ///
  /// In ar, this message translates to:
  /// **'التفاعل الأسبوعي'**
  String get weeklyEngagement;

  /// No description provided for @memoryExerciseResults.
  ///
  /// In ar, this message translates to:
  /// **'نتائج تمارين الذاكرة'**
  String get memoryExerciseResults;

  /// No description provided for @medicationsAndAdherence.
  ///
  /// In ar, this message translates to:
  /// **'الأدوية والالتزام'**
  String get medicationsAndAdherence;

  /// No description provided for @upcomingAppointments.
  ///
  /// In ar, this message translates to:
  /// **'المواعيد القادمة'**
  String get upcomingAppointments;

  /// No description provided for @noAppointments.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد مواعيد قادمة'**
  String get noAppointments;

  /// No description provided for @noMedications.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد أدوية مجدولة'**
  String get noMedications;

  /// No description provided for @addNewNote.
  ///
  /// In ar, this message translates to:
  /// **'أضف ملاحظة جديدة'**
  String get addNewNote;

  /// No description provided for @viewAllCases.
  ///
  /// In ar, this message translates to:
  /// **'عرض كل الحالات'**
  String get viewAllCases;

  /// No description provided for @patientDetails.
  ///
  /// In ar, this message translates to:
  /// **'تفاصيل المريض'**
  String get patientDetails;

  /// No description provided for @noConditionNotes.
  ///
  /// In ar, this message translates to:
  /// **'لم تُسجل ملاحظات عن الحالة.'**
  String get noConditionNotes;

  /// No description provided for @contactUnavailable.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد بيانات تواصل عائلية متاحة لهذا المريض.'**
  String get contactUnavailable;

  /// No description provided for @taken.
  ///
  /// In ar, this message translates to:
  /// **'تم'**
  String get taken;

  /// No description provided for @missed.
  ///
  /// In ar, this message translates to:
  /// **'لم يؤخذ'**
  String get missed;

  /// No description provided for @assignedPatients.
  ///
  /// In ar, this message translates to:
  /// **'المرضى المعيّنون'**
  String get assignedPatients;

  /// No description provided for @searchPatients.
  ///
  /// In ar, this message translates to:
  /// **'ابحث عن مريض'**
  String get searchPatients;

  /// No description provided for @patientSummary.
  ///
  /// In ar, this message translates to:
  /// **'ملخص المريض'**
  String get patientSummary;

  /// No description provided for @noAssignedPatients.
  ///
  /// In ar, this message translates to:
  /// **'لا يوجد مرضى معيّنون لهذا الحساب بعد'**
  String get noAssignedPatients;

  /// No description provided for @caregiverInviteDoctorHint.
  ///
  /// In ar, this message translates to:
  /// **'يمكن لمقدم الرعاية دعوة الطبيب باستخدام بريده الإلكتروني.'**
  String get caregiverInviteDoctorHint;

  /// No description provided for @adherenceActivityIndicators.
  ///
  /// In ar, this message translates to:
  /// **'مؤشرات الالتزام والنشاط'**
  String get adherenceActivityIndicators;

  /// No description provided for @medication.
  ///
  /// In ar, this message translates to:
  /// **'الدواء'**
  String get medication;

  /// No description provided for @addFollowUpNote.
  ///
  /// In ar, this message translates to:
  /// **'إضافة ملاحظة متابعة'**
  String get addFollowUpNote;

  /// No description provided for @doctorNotes.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظات الطبيب'**
  String get doctorNotes;

  /// No description provided for @noNotes.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد ملاحظات بعد'**
  String get noNotes;

  /// No description provided for @doctorNote.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظة الطبيب'**
  String get doctorNote;

  /// No description provided for @note.
  ///
  /// In ar, this message translates to:
  /// **'الملاحظة'**
  String get note;

  /// No description provided for @networkUnavailable.
  ///
  /// In ar, this message translates to:
  /// **'تعذر الاتصال بخدمة رفيق'**
  String get networkUnavailable;

  /// No description provided for @unexpectedError.
  ///
  /// In ar, this message translates to:
  /// **'حدث خطأ غير متوقع'**
  String get unexpectedError;

  /// No description provided for @statusPairing.
  ///
  /// In ar, this message translates to:
  /// **'جارٍ الإقران'**
  String get statusPairing;

  /// No description provided for @statusOnline.
  ///
  /// In ar, this message translates to:
  /// **'مستقر'**
  String get statusOnline;

  /// No description provided for @statusOffline.
  ///
  /// In ar, this message translates to:
  /// **'غير متصل'**
  String get statusOffline;

  /// No description provided for @statusDegraded.
  ///
  /// In ar, this message translates to:
  /// **'اتصال محدود'**
  String get statusDegraded;

  /// No description provided for @statusDisabled.
  ///
  /// In ar, this message translates to:
  /// **'معطل'**
  String get statusDisabled;

  /// No description provided for @statusUnpaired.
  ///
  /// In ar, this message translates to:
  /// **'غير مقترن'**
  String get statusUnpaired;

  /// No description provided for @statusPending.
  ///
  /// In ar, this message translates to:
  /// **'قيد الانتظار'**
  String get statusPending;

  /// No description provided for @statusReminded.
  ///
  /// In ar, this message translates to:
  /// **'تم إرسال التذكير'**
  String get statusReminded;

  /// No description provided for @statusCompleted.
  ///
  /// In ar, this message translates to:
  /// **'مكتمل'**
  String get statusCompleted;

  /// No description provided for @statusSnoozed.
  ///
  /// In ar, this message translates to:
  /// **'مؤجل'**
  String get statusSnoozed;

  /// No description provided for @statusMissed.
  ///
  /// In ar, this message translates to:
  /// **'فائت'**
  String get statusMissed;

  /// No description provided for @statusSkipped.
  ///
  /// In ar, this message translates to:
  /// **'تم التخطي'**
  String get statusSkipped;

  /// No description provided for @statusCancelled.
  ///
  /// In ar, this message translates to:
  /// **'ملغى'**
  String get statusCancelled;

  /// No description provided for @statusDetected.
  ///
  /// In ar, this message translates to:
  /// **'تم الاكتشاف'**
  String get statusDetected;

  /// No description provided for @statusVerifying.
  ///
  /// In ar, this message translates to:
  /// **'جارٍ التحقق'**
  String get statusVerifying;

  /// No description provided for @statusFalseAlarm.
  ///
  /// In ar, this message translates to:
  /// **'إنذار كاذب'**
  String get statusFalseAlarm;

  /// No description provided for @statusConfirmed.
  ///
  /// In ar, this message translates to:
  /// **'مؤكد'**
  String get statusConfirmed;

  /// No description provided for @statusNotified.
  ///
  /// In ar, this message translates to:
  /// **'تم تنبيه مقدم الرعاية'**
  String get statusNotified;

  /// No description provided for @statusAcknowledged.
  ///
  /// In ar, this message translates to:
  /// **'تم الاستلام'**
  String get statusAcknowledged;

  /// No description provided for @statusResolved.
  ///
  /// In ar, this message translates to:
  /// **'تم الحل'**
  String get statusResolved;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
