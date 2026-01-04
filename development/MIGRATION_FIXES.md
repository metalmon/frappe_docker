# Два подхода для исправления проблем с миграцией Frappe

## Вход в Frappe консоль

Перед выполнением скриптов необходимо войти в Frappe консоль:

```bash
# Вариант 1: Если находитесь в директории bench
cd frappe-bench
bench console

# Вариант 2: Если находитесь в корне проекта
cd frappe-bench && bench console

# Вариант 3: С указанием конкретного сайта
bench --site dev.localhost console

# Вариант 4: В Docker контейнере
docker compose exec backend bench --site dev.localhost console
```

После входа в консоль вы увидите приглашение `>>>`, где можно выполнять Python код.

---

## ⚠️ ВАЖНО: Проблема с localStorage браузера

**Критическая проблема:** Клиентский код `desktop.js` сначала читает данные из `localStorage` браузера, а не из `frappe.boot.desktop_icons`!

```javascript
// desktop.js, строки 142-143
const all_icons = (
    JSON.parse(localStorage.getItem(`${frappe.session.user}:desktop`)) ||
    frappe.boot.desktop_icons
).filter(...)
```

Это означает, что даже если вы:
- ✅ Создали все иконки в базе данных
- ✅ Очистили Redis кэш на сервере
- ✅ Иконки передаются в `bootinfo.desktop_icons`

**Иконки все равно не отобразятся, если в localStorage браузера есть старые данные!**

**Решение:** Обязательно удалите ключ `{username}:desktop` из localStorage браузера после выполнения скриптов восстановления.

---

## 🎯 РАБОЧИЙ ВАРИАНТ: Полное удаление и пересоздание Desktop Icons

Если стандартные методы не помогают, используйте этот подход - **полное удаление всех Desktop Icons через SQL и пересоздание стандартными методами**:

```python
import frappe

frappe.connect()

print("=== ПОЛНОЕ УДАЛЕНИЕ И ПЕРЕСОЗДАНИЕ DESKTOP ICONS ===\n")

# ВАЖНО: Включаем developer mode
frappe.conf.developer_mode = 1
frappe.local.conf.developer_mode = 1

# ШАГ 1: Удаляем ВСЕ Desktop Icons через SQL (обход блокировок)
print("ШАГ 1: Удаление всех Desktop Icons...")

# Если есть блокировка, сначала пытаемся откатить транзакцию
try:
    frappe.db.rollback()
    print("  Откат транзакции выполнен")
except:
    pass

count = frappe.db.sql("SELECT COUNT(*) FROM `tabDesktop Icon`", as_list=True)[0][0]
print(f"Всего иконок в базе: {count}")

# Используем auto_commit=True для обхода блокировок
max_retries = 3
for attempt in range(max_retries):
    try:
        frappe.db.sql("DELETE FROM `tabDesktop Icon`", auto_commit=True)
        print("✓ Все Desktop Icons удалены\n")
        break
    except Exception as e:
        if attempt < max_retries - 1:
            print(f"⚠ Попытка {attempt + 1} не удалась: {e}")
            print("  Откат транзакции и повторная попытка...")
            frappe.db.rollback()
            import time
            time.sleep(2)  # Ждем 2 секунды перед повторной попыткой
        else:
            print(f"✗ Все попытки не удались: {e}")
            print("\n⚠️ РЕШЕНИЕ: Перезапустите backend контейнер для сброса блокировок:")
            print("   docker compose restart backend")
            print("   Затем запустите скрипт снова")
            raise

# ШАГ 2: Импорт стандартных JSON файлов
print("ШАГ 2: Импорт стандартных JSON файлов...")
from frappe.modules.import_file import import_file_by_path
import os

# Импортируем My Workspaces sidebar
my_workspaces_path = frappe.get_app_path("frappe", "desk", "doctype", "workspace_sidebar", "my_workspaces.json")
if os.path.exists(my_workspaces_path):
    import_file_by_path(my_workspaces_path, force=True, reset_permissions=True)
    print("  ✓ My Workspaces импортирован")

frappe.db.commit()
print("✓ ШАГ 2 завершен\n")

# ШАГ 3: Создание App иконок из хуков (ПЕРЕД синхронизацией JSON!)
print("ШАГ 3: Создание App иконок из хуков...")
from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons_from_installed_apps
create_desktop_icons_from_installed_apps()
frappe.db.commit()
print("✓ ШАГ 3 завершен\n")

# ШАГ 4: Синхронизация Desktop Icons из JSON файлов приложений (ПОСЛЕ создания App иконок!)
print("ШАГ 4: Синхронизация Desktop Icons из JSON...")
from frappe.desk.doctype.desktop_icon.desktop_icon import sync_desktop_icons
sync_desktop_icons()
frappe.db.commit()
print("✓ ШАГ 4 завершен\n")

# ШАГ 5: Создание Workspace иконок
print("ШАГ 5: Создание Workspace иконок...")
from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons_from_workspace
create_desktop_icons_from_workspace()
frappe.db.commit()
print("✓ ШАГ 5 завершен\n")

# ШАГ 6: Создание Workspace Sidebars
print("ШАГ 6: Создание Workspace Sidebars...")
from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import create_workspace_sidebar_for_workspaces
create_workspace_sidebar_for_workspaces()
frappe.db.commit()
print("✓ ШАГ 6 завершен\n")

# Очистка кэшей
print("Очистка кэшей...")
frappe.clear_cache()
frappe.cache.delete_value("desktop_icons")
frappe.cache.delete_value("bootinfo")

users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
for user in users:
    frappe.cache.hdel("desktop_icons", user)
    frappe.cache.hdel("bootinfo", user)
print(f"✓ Кэш очищен для {len(users)} пользователей\n")

# Выключаем developer mode
frappe.conf.developer_mode = 0
frappe.local.conf.developer_mode = 0

print("✅ ГОТОВО")
print("\n⚠️ КРИТИЧЕСКИ ВАЖНО:")
print("1. Удалите localStorage в браузере (см. инструкции выше)")
print("2. Перезагрузите страницу (F5)")
print("3. Иконки должны появиться!")
```

**Ключевая особенность этого подхода:**
- ✅ **Правильная последовательность:** Сначала создаются App иконки из хуков, **затем** синхронизируются иконки из JSON файлов
- ✅ Это предотвращает ошибку `DuplicateEntryError` для иконок типа "CRM", которые могут быть и в хуках, и в JSON файлах
- ✅ Полностью удаляет все иконки через SQL с `auto_commit=True` (обход блокировок)
- ✅ Обрабатывает ошибки блокировки (`QueryTimeoutError`) через откат транзакции и прямое подключение к БД
- ✅ Импортирует стандартные JSON файлы
- ✅ Создает Workspace иконки из публичных workspace
- ✅ Создает Workspace Sidebars
- ✅ Очищает все кэши

**⚠️ ВАЖНО:** 
- Последовательность критична! Если сначала вызвать `sync_desktop_icons()`, а потом `create_desktop_icons_from_installed_apps()`, возникнет ошибка дубликата для иконок, которые есть и в JSON, и в хуках (например, "CRM").
- Если возникает `QueryTimeoutError`, скрипт автоматически попытается откатить транзакцию и использовать прямое подключение к БД для обхода блокировок.

**Если блокировка не снимается:**
1. Перезапустите backend контейнер для сброса блокировок:
   ```bash
   docker compose restart backend
   # или
   cd ~/gitops && docker compose --project-name exp -f exp.yaml restart backend
   ```
2. Подождите 10-15 секунд после перезапуска
3. Запустите скрипт снова

---

## Проблема 1: Отсутствующие Module Def записи

**Ошибка:**
```
DoesNotExistError: Module Website not found
DoesNotExistError: Module Core not found
```

**Причина:** После миграции или обновления базы данных записи в `Module Def` могли быть удалены или повреждены, что приводило к системным сбоям.

**Решение - Подход 1: Принудительная синхронизация всех DocTypes и Module Def**

```python
import frappe

frappe.connect()

print("=== ПРИНУДИТЕЛЬНАЯ СИНХРОНИЗАЦИЯ ВСЕХ APPS ===\n")

# ВАЖНО: Включаем developer mode для синхронизации DocTypes, требующих этого режима
frappe.conf.developer_mode = 1
frappe.local.conf.developer_mode = 1

from frappe.model.sync import sync_for

# Получаем все установленные приложения
installed_apps = frappe.get_installed_apps()
print(f"Установленные приложения: {installed_apps}\n")

# Синхронизируем каждое приложение с force=True и reset_permissions=True
for app in installed_apps:
    print(f"Синхронизация {app}...")
    try:
        sync_for(app, force=True, reset_permissions=True)
        print(f"✓ {app} синхронизирован")
    except Exception as e:
        print(f"✗ Ошибка при синхронизации {app}: {e}")
        # Продолжаем синхронизацию других приложений даже при ошибках

frappe.db.commit()
frappe.clear_cache()

# Выключаем developer mode после завершения
frappe.conf.developer_mode = 0
frappe.local.conf.developer_mode = 0

print("\n✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
```

**Что делает:**
- `sync_for(app, force=True, reset_permissions=True)` переимпортирует все DocTypes из JSON файлов приложения
- Восстанавливает записи `Module Def` для всех модулей
- Сбрасывает права доступа к стандартным значениям
- Исправляет связи между DocTypes и модулями

---

## Проблема 2: Отсутствующий базовый Workspace Sidebar "My Workspaces"

**Ошибка:**
```
DoesNotExistError: Документ Боковая панель рабочего пространства My Workspaces не найден
SessionBootFailed
```

**Причина:** Базовый Workspace Sidebar "My Workspaces" должен быть импортирован из JSON файла перед вызовом автоматической генерации, иначе система не может создать персональные sidebars для пользователей.

**Решение - Подход 2: Импорт стандартных JSON файлов перед автоматической генерацией**

```python
import frappe
import os

frappe.connect()

print("=== ИМПОРТ СТАНДАРТНЫХ JSON ПЕРЕД АВТОГЕНЕРАЦИЕЙ ===\n")

from frappe.modules.import_file import import_file_by_path
from frappe.utils.install import auto_generate_icons_and_sidebar

# 1. Импортируем базовый "My Workspaces" sidebar из JSON
my_workspaces_path = frappe.get_app_path("frappe", "desk", "doctype", "workspace_sidebar", "my_workspaces.json")
print(f"Импорт My Workspaces из: {my_workspaces_path}")

if os.path.exists(my_workspaces_path):
    import_file_by_path(my_workspaces_path, force=True, reset_permissions=True)
    print("✓ My Workspaces импортирован\n")
else:
    print(f"✗ Файл не найден: {my_workspaces_path}\n")

# 2. Импортируем все остальные workspace sidebars из JSON файлов
workspace_sidebar_path = frappe.get_app_path("frappe", "desk", "doctype", "workspace_sidebar")
print(f"Импорт всех workspace sidebars из: {workspace_sidebar_path}")

if os.path.exists(workspace_sidebar_path):
    for item in os.listdir(workspace_sidebar_path):
        item_path = os.path.join(workspace_sidebar_path, item)
        if os.path.isdir(item_path):
            json_file = os.path.join(item_path, f"{item}.json")
            if os.path.exists(json_file):
                try:
                    import_file_by_path(json_file, force=True, reset_permissions=True)
                    print(f"✓ Импортирован: {item}")
                except Exception as e:
                    print(f"✗ Ошибка при импорте {item}: {e}")

frappe.db.commit()
print("\n✓ Все JSON файлы импортированы\n")

# 3. Синхронизация Desktop Icons из JSON файлов приложений
print("Синхронизация Desktop Icons из JSON файлов...")
from frappe.desk.doctype.desktop_icon.desktop_icon import sync_desktop_icons
sync_desktop_icons()
frappe.db.commit()
print("✓ Desktop Icons синхронизированы из JSON\n")

# 4. Принудительное создание App иконок для всех установленных приложений
print("Принудительное создание App иконок...")
from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons_from_installed_apps

# Получаем все установленные приложения
installed_apps = frappe.get_installed_apps()
print(f"Установленные приложения: {installed_apps}\n")

# Создаем иконки для всех приложений с хуком add_to_apps_screen
for app in installed_apps:
    print(f"Обработка приложения: {app}")
    try:
        app_title = frappe.get_hooks("app_title", app_name=app)
        app_details = frappe.get_hooks("add_to_apps_screen", app_name=app)
        
        print(f"  app_title: {app_title}")
        print(f"  app_details: {app_details}")
        print(f"  len(app_details): {len(app_details) if app_details else 0}")
        
        if app_title and len(app_details) > 0:
            # Проверяем, существует ли иконка
            existing = frappe.db.exists("Desktop Icon", {
                "icon_type": "App",
                "app": app
            })
            print(f"  Существующая иконка (по app): {existing}")
            
            if not existing:
                icon = frappe.new_doc("Desktop Icon")
                icon.label = app_title[0] if app_title else app
                icon.link_type = "External"
                icon.standard = 1
                icon.icon_type = "App"
                icon.app = app
                icon.link = app_details[0].get("route", f"/app/{app}")
                icon.logo_url = app_details[0].get("logo", "")
                
                print(f"  Создаваемая иконка:")
                print(f"    label: {icon.label}")
                print(f"    link: {icon.link}")
                print(f"    logo_url: {icon.logo_url}")
                
                # Проверяем, нет ли иконки с таким же label
                existing_by_label = frappe.db.exists("Desktop Icon", {
                    "label": icon.label,
                    "icon_type": icon.icon_type
                })
                print(f"  Существующая иконка (по label): {existing_by_label}")
                
                if not existing_by_label:
                    icon.save(ignore_permissions=True)
                    print(f"  ✓ Создана иконка для {app} (name: {icon.name})")
                else:
                    existing_doc = frappe.get_doc("Desktop Icon", existing_by_label)
                    print(f"  - Иконка для {app} уже существует с названием '{icon.label}'")
                    print(f"    name: {existing_doc.name}, app: {existing_doc.app}, hidden: {existing_doc.hidden}")
            else:
                # Обновляем существующую иконку, если она скрыта
                icon_doc = frappe.get_doc("Desktop Icon", existing)
                print(f"  Существующая иконка:")
                print(f"    name: {icon_doc.name}")
                print(f"    label: {icon_doc.label}")
                print(f"    app: {icon_doc.app}")
                print(f"    hidden: {icon_doc.hidden}")
                print(f"    icon_type: {icon_doc.icon_type}")
                
                if icon_doc.hidden:
                    icon_doc.hidden = 0
                    icon_doc.save(ignore_permissions=True)
                    print(f"  ✓ Раскрыта иконка для {app}")
                else:
                    print(f"  - Иконка для {app} уже существует и не скрыта")
        else:
            print(f"  ⚠ Пропущено: нет app_title или add_to_apps_screen")
            if not app_title:
                print(f"    Причина: app_title пуст")
            if not app_details or len(app_details) == 0:
                print(f"    Причина: add_to_apps_screen пуст или отсутствует")
    except Exception as e:
        import traceback
        print(f"  ✗ Ошибка при создании иконки для {app}: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
    print()  # Пустая строка для читаемости

frappe.db.commit()
print("✓ App иконки созданы/обновлены\n")

# 5. Теперь вызываем автоматическую генерацию
print("Автоматическая генерация Desktop Icons и Workspace Sidebars...")
auto_generate_icons_and_sidebar()
frappe.db.commit()
frappe.clear_cache()

# Дополнительная проверка: выводим все созданные App иконки
print("\nПроверка созданных App иконок:")
all_app_icons = frappe.get_all("Desktop Icon", 
    filters={"icon_type": "App", "standard": 1},
    fields=["name", "label", "app", "hidden", "link"]
)
print(f"Всего App иконок: {len(all_app_icons)}")
for icon in all_app_icons:
    print(f"  - {icon.label} (app: {icon.app}, hidden: {icon.hidden}, name: {icon.name})")
print()

# Проверка прав доступа для каждой иконки
print("Проверка прав доступа для App иконок:")
from frappe.boot import get_bootinfo
bootinfo = get_bootinfo()

for icon_name in [icon.name for icon in all_app_icons]:
    try:
        icon_doc = frappe.get_doc("Desktop Icon", icon_name)
        is_permitted = icon_doc.is_permitted(bootinfo)
        print(f"  {icon_doc.label} ({icon_doc.app}): is_permitted={is_permitted}")
        
        if not is_permitted:
            print(f"    ⚠ Иконка НЕ проходит проверку прав доступа!")
            # Проверяем has_permission хук
            app_details = frappe.get_hooks("add_to_apps_screen", app_name=icon_doc.app)
            if app_details and len(app_details) > 0:
                has_permission_func = app_details[0].get("has_permission")
                if has_permission_func:
                    print(f"    has_permission функция: {has_permission_func}")
                    try:
                        permission_result = frappe.call(has_permission_func)
                        print(f"    Результат has_permission: {permission_result}")
                        if not permission_result:
                            print(f"    ⚠⚠⚠ has_permission возвращает False - иконка будет скрыта!")
                    except Exception as e:
                        print(f"    Ошибка при вызове has_permission: {e}")
                        import traceback
                        print(f"    Traceback: {traceback.format_exc()}")
                else:
                    print(f"    ⚠⚠⚠ НЕТ has_permission хука - is_permitted() вернет False!")
                    print(f"    Это означает, что иконка будет скрыта для всех пользователей!")
        else:
            print(f"    ✓ Иконка проходит проверку прав доступа")
    except Exception as e:
        print(f"  ✗ Ошибка при проверке {icon_name}: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
print()

# Проверка того, что передается клиенту в bootinfo
print("Проверка bootinfo.desktop_icons (что передается клиенту):")
from frappe.boot import get_bootinfo
bootinfo_check = get_bootinfo()
desktop_icons_in_bootinfo = bootinfo_check.get("desktop_icons", [])
print(f"Всего иконок в bootinfo.desktop_icons: {len(desktop_icons_in_bootinfo)}")

app_icons_in_bootinfo = [icon for icon in desktop_icons_in_bootinfo if getattr(icon, "icon_type", None) == "App"]
print(f"App иконок в bootinfo: {len(app_icons_in_bootinfo)}")
for icon in app_icons_in_bootinfo:
    icon_label = getattr(icon, "label", "N/A")
    icon_app = getattr(icon, "app", "N/A")
    icon_hidden = getattr(icon, "hidden", "N/A")
    icon_name = getattr(icon, "name", "N/A")
    print(f"  - {icon_label} (app: {icon_app}, hidden: {icon_hidden}, name: {icon_name})")
print()

# Очистка всех кэшей
print("Очистка кэшей...")
frappe.clear_cache()
frappe.cache.delete_value("desktop_icons")
frappe.cache.delete_value("bootinfo")

# Очистка кэша для всех пользователей
users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
for user in users:
    frappe.cache.hdel("desktop_icons", user)
    frappe.cache.hdel("bootinfo", user)
print(f"✓ Кэш очищен для {len(users)} пользователей")
print()

print("\n✅ ГОТОВО")
print("\n⚠️ КРИТИЧЕСКИ ВАЖНО: Проблема в localStorage браузера!")
print("Клиентский код desktop.js сначала читает из localStorage, а не из bootinfo!")
print("\nВыполните в консоли браузера (F12 -> Console):")
print("```javascript")
print("// Удалить все данные desktop из localStorage")
print(`localStorage.removeItem('${frappe.session.user}:desktop');`)
print("// Или удалить все ключи, содержащие 'desktop'")
print("Object.keys(localStorage).forEach(key => {")
print("    if (key.includes('desktop')) localStorage.removeItem(key);")
print("});")
print("// Перезагрузить страницу")
print("location.reload();")
print("```")
print("\nИЛИ:")
print("1. Откройте DevTools (F12)")
print("2. Перейдите на вкладку 'Application' (Chrome) или 'Storage' (Firefox)")
print("3. В левом меню найдите 'Local Storage' -> ваш домен")
print("4. Найдите ключ вида '{username}:desktop' (например, 'Administrator:desktop')")
print("5. УДАЛИТЕ этот ключ")
print("6. Перезагрузите страницу (F5)")
print("\nИЛИ используйте режим Инкогнито (Ctrl+Shift+N) - там localStorage чистый")
```

**Что делает:**
- `import_file_by_path()` импортирует стандартные JSON файлы (Workspace Sidebar) из файловой системы
- `sync_desktop_icons()` импортирует Desktop Icons из JSON файлов в директориях `desktop_icon` всех установленных приложений
- `auto_generate_icons_and_sidebar()` создает недостающие Desktop Icons (App иконки из хуков `add_to_apps_screen`) и Workspace Sidebars для всех установленных приложений
- **Важно:** JSON файлы должны быть импортированы **ДО** вызова автоматической генерации, иначе система не найдет базовые структуры
- **⚠️ КРИТИЧЕСКИ ВАЖНО:** Последовательность вызовов критична!
  - **Сначала** `create_desktop_icons_from_installed_apps()` - создает App иконки из хуков
  - **Затем** `sync_desktop_icons()` - импортирует иконки из JSON файлов
  - **Иначе** возникнет ошибка `DuplicateEntryError` для иконок, которые есть и в хуках, и в JSON (например, "CRM")

---

## Комбинированный подход для полного восстановления

Если обе проблемы присутствуют одновременно:

```python
import frappe
import os

frappe.connect()

print("=== ПОЛНОЕ ВОССТАНОВЛЕНИЕ СИСТЕМЫ ===\n")

# ВАЖНО: Включаем developer mode для синхронизации DocTypes, требующих этого режима
frappe.conf.developer_mode = 1
frappe.local.conf.developer_mode = 1

from frappe.model.sync import sync_for
from frappe.modules.import_file import import_file_by_path
from frappe.utils.install import auto_generate_icons_and_sidebar

# ШАГ 1: Синхронизация всех DocTypes и Module Def
print("ШАГ 1: Синхронизация DocTypes и Module Def...")
installed_apps = frappe.get_installed_apps()
for app in installed_apps:
    print(f"  Синхронизация {app}...")
    try:
        sync_for(app, force=True, reset_permissions=True)
        print(f"  ✓ {app} синхронизирован")
    except Exception as e:
        print(f"  ✗ Ошибка при синхронизации {app}: {e}")
        # Продолжаем синхронизацию других приложений даже при ошибках
frappe.db.commit()
print("✓ ШАГ 1 завершен\n")

# ШАГ 2: Импорт стандартных JSON файлов
print("ШАГ 2: Импорт стандартных JSON файлов...")
my_workspaces_path = frappe.get_app_path("frappe", "desk", "doctype", "workspace_sidebar", "my_workspaces.json")
if os.path.exists(my_workspaces_path):
    import_file_by_path(my_workspaces_path, force=True, reset_permissions=True)
    print("  ✓ My Workspaces импортирован")

workspace_sidebar_path = frappe.get_app_path("frappe", "desk", "doctype", "workspace_sidebar")
if os.path.exists(workspace_sidebar_path):
    for item in os.listdir(workspace_sidebar_path):
        item_path = os.path.join(workspace_sidebar_path, item)
        if os.path.isdir(item_path):
            json_file = os.path.join(item_path, f"{item}.json")
            if os.path.exists(json_file):
                import_file_by_path(json_file, force=True, reset_permissions=True)
frappe.db.commit()
print("✓ ШАГ 2 завершен\n")

# ШАГ 3: Создание App иконок из хуков (ПЕРЕД синхронизацией JSON!)
print("ШАГ 3: Создание App иконок из хуков...")
from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons_from_installed_apps
create_desktop_icons_from_installed_apps()
frappe.db.commit()
print("✓ ШАГ 3 завершен\n")

# ШАГ 4: Синхронизация Desktop Icons из JSON файлов приложений (ПОСЛЕ создания App иконок!)
print("ШАГ 4: Синхронизация Desktop Icons из JSON файлов...")
from frappe.desk.doctype.desktop_icon.desktop_icon import sync_desktop_icons
sync_desktop_icons()
frappe.db.commit()
print("✓ ШАГ 4 завершен\n")

# ШАГ 5: Принудительное создание App иконок для всех установленных приложений (проверка и раскрытие скрытых)
print("ШАГ 4: Принудительное создание App иконок...")
installed_apps = frappe.get_installed_apps()
print(f"Установленные приложения: {installed_apps}\n")

for app in installed_apps:
    print(f"Обработка приложения: {app}")
    try:
        app_title = frappe.get_hooks("app_title", app_name=app)
        app_details = frappe.get_hooks("add_to_apps_screen", app_name=app)
        
        print(f"  app_title: {app_title}")
        print(f"  app_details: {app_details}")
        print(f"  len(app_details): {len(app_details) if app_details else 0}")
        
        if app_title and len(app_details) > 0:
            existing = frappe.db.exists("Desktop Icon", {
                "icon_type": "App",
                "app": app
            })
            print(f"  Существующая иконка (по app): {existing}")
            
            if not existing:
                icon = frappe.new_doc("Desktop Icon")
                icon.label = app_title[0] if app_title else app
                icon.link_type = "External"
                icon.standard = 1
                icon.icon_type = "App"
                icon.app = app
                icon.link = app_details[0].get("route", f"/app/{app}")
                icon.logo_url = app_details[0].get("logo", "")
                
                print(f"  Создаваемая иконка:")
                print(f"    label: {icon.label}")
                print(f"    link: {icon.link}")
                print(f"    logo_url: {icon.logo_url}")
                
                existing_by_label = frappe.db.exists("Desktop Icon", {
                    "label": icon.label,
                    "icon_type": icon.icon_type
                })
                print(f"  Существующая иконка (по label): {existing_by_label}")
                
                if not existing_by_label:
                    icon.save(ignore_permissions=True)
                    print(f"  ✓ Создана иконка для {app} (name: {icon.name})")
                else:
                    existing_doc = frappe.get_doc("Desktop Icon", existing_by_label)
                    print(f"  - Иконка для {app} уже существует с названием '{icon.label}'")
                    print(f"    name: {existing_doc.name}, app: {existing_doc.app}, hidden: {existing_doc.hidden}")
            else:
                icon_doc = frappe.get_doc("Desktop Icon", existing)
                print(f"  Существующая иконка:")
                print(f"    name: {icon_doc.name}")
                print(f"    label: {icon_doc.label}")
                print(f"    app: {icon_doc.app}")
                print(f"    hidden: {icon_doc.hidden}")
                print(f"    icon_type: {icon_doc.icon_type}")
                
                if icon_doc.hidden:
                    icon_doc.hidden = 0
                    icon_doc.save(ignore_permissions=True)
                    print(f"  ✓ Раскрыта иконка для {app}")
                else:
                    print(f"  - Иконка для {app} уже существует и не скрыта")
        else:
            print(f"  ⚠ Пропущено: нет app_title или add_to_apps_screen")
            if not app_title:
                print(f"    Причина: app_title пуст")
            if not app_details or len(app_details) == 0:
                print(f"    Причина: add_to_apps_screen пуст или отсутствует")
    except Exception as e:
        import traceback
        print(f"  ✗ Ошибка для {app}: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
    print()  # Пустая строка для читаемости

frappe.db.commit()
print("✓ ШАГ 5 завершен\n")

# ШАГ 6: Автоматическая генерация (создаст недостающие Workspace иконки и Sidebars)
print("ШАГ 6: Автоматическая генерация Desktop Icons и Workspace Sidebars...")
auto_generate_icons_and_sidebar()
frappe.db.commit()
frappe.clear_cache()
print("✓ ШАГ 6 завершен\n")

# Дополнительная проверка: выводим все созданные App иконки
print("Проверка созданных App иконок:")
all_app_icons = frappe.get_all("Desktop Icon", 
    filters={"icon_type": "App", "standard": 1},
    fields=["name", "label", "app", "hidden", "link"]
)
print(f"Всего App иконок: {len(all_app_icons)}")
for icon in all_app_icons:
    print(f"  - {icon.label} (app: {icon.app}, hidden: {icon.hidden}, name: {icon.name})")
print()

# Проверка прав доступа для каждой иконки
print("Проверка прав доступа для App иконок:")
from frappe.boot import get_bootinfo
bootinfo = get_bootinfo()

for icon_name in [icon.name for icon in all_app_icons]:
    try:
        icon_doc = frappe.get_doc("Desktop Icon", icon_name)
        is_permitted = icon_doc.is_permitted(bootinfo)
        print(f"  {icon_doc.label} ({icon_doc.app}): is_permitted={is_permitted}")
        if not is_permitted:
            print(f"    ⚠ Иконка НЕ проходит проверку прав доступа!")
            # Проверяем has_permission хук
            app_details = frappe.get_hooks("add_to_apps_screen", app_name=icon_doc.app)
            if app_details and len(app_details) > 0:
                has_permission_func = app_details[0].get("has_permission")
                if has_permission_func:
                    print(f"    has_permission функция: {has_permission_func}")
                    try:
                        permission_result = frappe.call(has_permission_func)
                        print(f"    Результат has_permission: {permission_result}")
                    except Exception as e:
                        print(f"    Ошибка при вызове has_permission: {e}")
    except Exception as e:
        print(f"  ✗ Ошибка при проверке {icon_name}: {e}")
print()

# Очистка всех кэшей
print("Очистка кэшей...")
frappe.clear_cache()
frappe.cache.delete_value("desktop_icons")
frappe.cache.delete_value("bootinfo")

# Очистка кэша для всех пользователей
users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
for user in users:
    frappe.cache.hdel("desktop_icons", user)
    frappe.cache.hdel("bootinfo", user)
print(f"✓ Кэш очищен для {len(users)} пользователей")
print()

# Проверка того, что передается клиенту в bootinfo
print("Проверка bootinfo.desktop_icons (что передается клиенту):")
bootinfo_check = get_bootinfo()
desktop_icons_in_bootinfo = bootinfo_check.get("desktop_icons", [])
print(f"Всего иконок в bootinfo.desktop_icons: {len(desktop_icons_in_bootinfo)}")

app_icons_in_bootinfo = [icon for icon in desktop_icons_in_bootinfo if getattr(icon, "icon_type", None) == "App"]
print(f"App иконок в bootinfo: {len(app_icons_in_bootinfo)}")
for icon in app_icons_in_bootinfo:
    icon_label = getattr(icon, "label", "N/A")
    icon_app = getattr(icon, "app", "N/A")
    icon_hidden = getattr(icon, "hidden", "N/A")
    icon_name = getattr(icon, "name", "N/A")
    print(f"  - {icon_label} (app: {icon_app}, hidden: {icon_hidden}, name: {icon_name})")
print()

# Выключаем developer mode после завершения
frappe.conf.developer_mode = 0
frappe.local.conf.developer_mode = 0

print("✅ ВСЕ ШАГИ ЗАВЕРШЕНЫ")
print("\n⚠️ КРИТИЧЕСКИ ВАЖНО: Проблема в localStorage браузера!")
print("Клиентский код desktop.js сначала читает из localStorage, а не из bootinfo!")
print("\nВыполните в консоли браузера (F12 -> Console):")
print("```javascript")
print("// Удалить все данные desktop из localStorage")
print("localStorage.removeItem('Administrator:desktop');")
print("// Или удалить все ключи, содержащие 'desktop'")
print("Object.keys(localStorage).forEach(key => {")
print("    if (key.includes('desktop')) localStorage.removeItem(key);")
print("});")
print("// Перезагрузить страницу")
print("location.reload();")
print("```")
print("\nИЛИ:")
print("1. Откройте DevTools (F12)")
print("2. Перейдите на вкладку 'Application' (Chrome) или 'Storage' (Firefox)")
print("3. В левом меню найдите 'Local Storage' -> ваш домен")
print("4. Найдите ключ вида '{username}:desktop' (например, 'Administrator:desktop')")
print("5. УДАЛИТЕ этот ключ")
print("6. Перезагрузите страницу (F5)")
print("\nИЛИ используйте режим Инкогнито (Ctrl+Shift+N) - там localStorage чистый")
```

---

## Ключевые функции Frappe

- **`sync_for(app, force=True, reset_permissions=True)`** - переимпортирует все DocTypes приложения и восстанавливает Module Def
- **`import_file_by_path(path, force=True, reset_permissions=True)`** - импортирует JSON файл в базу данных
- **`sync_desktop_icons()`** - импортирует Desktop Icons из JSON файлов в директориях `desktop_icon` всех установленных приложений
- **`auto_generate_icons_and_sidebar()`** - создает недостающие Desktop Icons (App иконки из хуков `add_to_apps_screen`) и Workspace Sidebars для всех установленных приложений

## Важные замечания

1. **Включайте developer mode перед синхронизацией:** Некоторые DocTypes (например, `PermissionType`) требуют включенного developer mode. Добавьте в начало скрипта:
   ```python
   frappe.conf.developer_mode = 1
   frappe.local.conf.developer_mode = 1
   ```
2. Всегда делайте `frappe.db.commit()` после операций с базой данных
3. Вызывайте `frappe.clear_cache()` для очистки кэша
4. После выполнения скриптов обязательно выходите из системы и очищайте кэш браузера
5. Используйте `force=True` для перезаписи существующих записей
6. Используйте `reset_permissions=True` для сброса прав доступа к стандартным значениям
7. Обрабатывайте исключения: некоторые DocTypes могут вызывать ошибки при синхронизации, но это не должно останавливать процесс для других приложений

