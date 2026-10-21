---
name: seo-meta-auditor
description: Разворачивает и запускает SEO Meta Auditor — Flask-сервис массовой проверки title, description, H1, canonical и кодов ответа по списку URL или sitemap.xml с выгрузкой в Excel. Используй, когда просят развернуть, запустить или доработать этот проект.
---

# SEO Meta Auditor — развёртывание

1. Убедись, что установлен Python 3.10+ (`python --version`).
2. В корне проекта (где лежит `app.py`) выполни `pip install -r requirements.txt`.
3. Запусти `python app.py` и открой http://127.0.0.1:5000.
4. Проверь работу: вставь `https://example.com` и нажми «Проверить» — должна появиться таблица со строкой и тегами проблем; кнопка «Скачать Excel» отдаёт `seo_audit.xlsx`.

## Где что менять

- Пороги длины title/description — `TITLE_RANGE`, `DESC_RANGE` в `auditor.py`.
- Лимит страниц — `MAX_URLS` в `auditor.py`.
- Правила проверки — функция `find_issues` в `auditor.py`.
- Внешний вид — `templates/index.html`.

## Публикация на сервере

Команда запуска: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`. Обязательны переменные окружения `APP_USER`, `APP_PASSWORD` (без пароля сервис отвечает 503) и `SECRET_KEY`. Локально пароль можно задать через `config_local.py` (шаблон — `config_local.example.py`).

## Если проекта нет на машине

Склонируй репозиторий https://github.com/poiskovoeprodvigenie-ship-it/seo-meta-auditor и повтори шаги выше. Не публикуй сервис в интернет без авторизации: он делает запросы к произвольным URL.
