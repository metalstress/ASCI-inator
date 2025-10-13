╔══════════════════════════════════════════════════════════╗
║       УСТАНОВКА ШРИФТА HELVETICA NEUE ДЛЯ UI            ║
╚══════════════════════════════════════════════════════════╝

⚠️ ВАЖНО: Qt НЕ ПОДДЕРЖИВАЕТ ФОРМАТ .woff
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Нужен формат .ttf или .otf (НЕ .woff или .woff2)

✅ TrueType = .ttf - ЭТО ТО ЧТО НУЖНО!


📥 ШАГ 1: СКАЧАЙТЕ TTF ФАЙЛЫ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАРИАНТ 1 (Fontsgeek - Рекомендуется):
👉 https://fontsgeek.com/fonts/Helvetica-Neue-Regular

1. Нажмите "Download" на странице
2. Распакуйте ZIP архив
3. Найдите файлы:
   - HelveticaNeue-Regular.ttf
   - HelveticaNeue-Medium.ttf
4. Скопируйте оба в папку fonts/

ВАРИАНТ 2 (Font Meme):
👉 https://fontmeme.com/fonts/helvetica-neue-font/
1. Download font
2. Извлеките TTF файлы
3. Скопируйте в fonts/

ВАРИАНТ 3 (Mac пользователи):
Если у вас Mac, шрифт уже установлен системно!
Можно скопировать из:
/System/Library/Fonts/HelveticaNeue.ttc


📂 ШАГ 2: СКОПИРУЙТЕ В ПАПКУ fonts/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Скопируйте ОБА файла для лучшего результата:
  ✓ HelveticaNeue-Medium.ttf    (для табов ⭐⭐⭐)
  ✓ HelveticaNeue-Regular.ttf   (для основного UI ⭐)

Альтернативные имена файлов (тоже работают):
  • HelveticaNeue.ttf
  • helvetica-neue-medium.ttf
  • helvetica-neue-regular.ttf

💡 РЕКОМЕНДАЦИЯ: Положи ОБА файла:
   • HelveticaNeue-Medium.ttf  - для табов (font-weight: 500)
   • HelveticaNeue-Regular.ttf - для остального UI (font-weight: 400)


📁 СТРУКТУРА ПАПКИ
━━━━━━━━━━━━━━━━━
gen16/
├── fonts/
│   ├── HelveticaNeue-Medium.ttf    ← для табов (Medium)
│   ├── HelveticaNeue-Regular.ttf   ← для UI (Regular)
│   └── README.txt
└── ascii_wave_animator.py


✅ ШАГ 3: ЗАПУСТИТЕ ПРОГРАММУ
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Запустите и проверьте консоль:
  [OK] UI font loaded: Helvetica Neue   ← Успех!
  [WARNING] Helvetica Neue not found    ← Проверьте путь


🔄 КОНВЕРТАЦИЯ .woff → .ttf
━━━━━━━━━━━━━━━━━━━━━━━━━━
Если у вас только .woff или .woff2:

ОНЛАЙН КОНВЕРТЕРЫ:
  • https://cloudconvert.com/woff-to-ttf
  • https://convertio.co/ru/woff-ttf/
  • https://www.fontsquirrel.com/tools/webfont-generator

ЛОКАЛЬНО (Python):
  pip install fonttools
  fonttools ttLib.woff2 decompress your-font.woff2


🔧 ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ
━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ .ttf  (TrueType Font)
  ✅ .otf  (OpenType Font)
  ✅ .ttc  (TrueType Collection - для Mac)
  ❌ .woff (Web Open Font Format - НЕ РАБОТАЕТ)
  ❌ .woff2 (НЕ РАБОТАЕТ)


💡 FALLBACK ШРИФТЫ
━━━━━━━━━━━━━━━━━
Если Helvetica Neue не найден, приложение использует:
  1. Segoe UI (системный Windows UI шрифт)
  2. Helvetica (системный macOS/Linux)
  3. Arial (универсальный Windows)
  4. Sans-serif (базовый fallback)


📝 О ШРИФТЕ HELVETICA NEUE
━━━━━━━━━━━━━━━━━━━━━━━━
• Helvetica Neue - культовый швейцарский шрифт
• Редизайн классической Helvetica (1983)
• Используется Apple в macOS и iOS
• Один из самых популярных UI шрифтов в мире
• Нейтральный, четкий, профессиональный
• Отличная читаемость на экранах

⚖️ ВАЖНО О ЛИЦЕНЗИИ:
Helvetica Neue - коммерческий шрифт от Linotype.
Для личного использования обычно доступен бесплатно.
Для коммерческого использования требуется лицензия.


🎯 РЕКОМЕНДУЕМЫЕ НАЧЕРТАНИЯ
━━━━━━━━━━━━━━━━━━━━━━━━━
• HelveticaNeue-Medium.ttf  - Для табов, акцентов (⭐ weight: 500)
• HelveticaNeue-Regular.ttf - Для основного UI (⭐ weight: 400)
• HelveticaNeue-Light.ttf   - Легкий вариант (weight: 300)
• HelveticaNeue-Bold.ttf    - Жирный для заголовков (weight: 700)


🌍 АЛЬТЕРНАТИВЫ (бесплатные, похожие):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Если не можешь найти Helvetica Neue:

1. Arial (системный, предустановлен в Windows)
   - Почти идентичен визуально
   - Бесплатный

2. Roboto (Google Fonts)
   - Современная альтернатива
   - 100% бесплатный

3. Inter (rsms.me/inter)
   - Оптимизирован для UI
   - Open Source

════════════════════════════════════════════════════════════
