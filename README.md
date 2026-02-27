# Telegram Content Manager Bot

Бот для управления контентом Telegram-канала:
- принимает ссылки (сайт или Telegram-пост);
- извлекает текст и медиа;
- делает адаптацию/рерайт на русском через LLM API;
- предлагает публикацию с исходным медиа, сгенерированным изображением или без медиа;
- публикует в канал с учетом лимитов Telegram;
- хранит источники/API-ключи в SQLite (ключи в зашифрованном виде);
- ведет аудит действий и защищает от дублей ссылок.

## Локальный запуск

1. Установить зависимости:

```powershell
pip install -r requirements.txt
```

2. Создать `.env`:

```powershell
Copy-Item .env.example .env
```

3. Заполнить `.env`:
- `BOT_TOKEN`
- `CHANNEL_ID`
- `ALLOWED_USER_IDS`
- `ENCRYPTION_KEY`

4. Запуск:

```powershell
python bot_main.py
```

## Docker запуск

```powershell
docker compose up -d --build
```

Остановка:

```powershell
docker compose down
```

Логи:

```powershell
docker compose logs -f
```

## Первый деплой на VPS

1. Подключиться к серверу и установить Docker + Docker Compose plugin.
2. Клонировать репозиторий в, например, `/opt/tlg_bot_n`.
3. Создать `.env` на VPS из `.env.example` и заполнить секреты.
4. Запустить:

```bash
cd /opt/tlg_bot_n
docker compose up -d --build
```

5. Проверить логи:

```bash
docker compose logs -f
```

## Автодеплой через GitHub Actions (по push в main)

В проект добавлен workflow: `.github/workflows/deploy.yml`.

Он делает на VPS:
- переход в папку проекта;
- `git pull --ff-only origin main`;
- `docker compose up -d --build`.

### Какие GitHub Secrets нужны

В репозитории GitHub: `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`.

Добавьте:
- `VPS_HOST` - IP или домен VPS
- `VPS_USER` - SSH пользователь
- `VPS_SSH_KEY` - приватный SSH ключ (которым GitHub войдет на сервер)
- `VPS_SSH_PORT` - обычно `22`
- `VPS_DEPLOY_PATH` - путь проекта на VPS, например `/opt/tlg_bot_n`

После этого любой `git push` в `main` автоматически обновит бота на сервере.

## Интерфейс бота

Основная работа через кнопки:
- `Новый пост` - отправка ссылки и публикация;
- `Источники` - просмотр и управление источниками;
- `API-ключи` - добавление/переключение ключей;
- `Инструкция` - пошаговые подсказки по разделам;
- `Логи` - последние действия.

Команды оставлены как резерв:
- `/help`
- `/sources`
- `/source_add <name> <type> <base_url|-> <priority> <domains_csv|-> [settings_json]`
- `/source_update <source_id> <base_url|-> [settings_json|->]`
- `/cred_add <source_id> <label> <secret_name>`
- `/logs [limit]`

Для обработки контента отправьте боту URL.

## Как вносить изменения

1. Изменить код локально.
2. Проверить, что Python-файлы валидны:

```powershell
python -c "import pathlib,ast; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.py')]; print('AST_OK')"
```

3. Закоммитить и отправить:

```powershell
git add .
git commit -m "update bot"
git push origin main
```

4. Дождаться автодеплоя GitHub Actions.
5. Проверить на VPS:

```bash
cd /opt/tlg_bot_n
docker compose ps
docker compose logs -f --tail=100
```
