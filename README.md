# Academic Paper Generator

Сервис автоматической генерации учебных работ (курсовых, дипломов) на основе анализа Git-репозиториев.

## Описание

Учебные заведения требуют формальные курсовые и дипломные работы по результатам практических проектов. Разработчики часто имеют реальный код в публичных Git-репозиториях, но тратят значительное время на подготовку академического текста: обоснование, описание архитектуры, функционала и выводов.

Данный сервис решает проблему за счёт строгого разделения ролей:
- **Логика сервиса** выполняет детерминированный анализ проекта и формирует структурированный набор фактов (`facts.json`)
- **LLM** используется строго как генератор текста на основе предоставленных фактов, структуры документа и кратких резюме уже сгенерированных разделов

Модель не получает исходный код и не хранит состояние (stateless), что снижает расходы токенов и повышает воспроизводимость.

## Основные возможности

- Анализ публичных Git-репозиториев (GitHub, GitLab, Bitbucket)
- Детерминированное извлечение фактов с доказательствами (`facts.json`)
- Поэтапная генерация разделов через LLM (outline -> theory -> practice -> conclusion)
- Автоматические скриншоты для web-проектов через headless-браузер
- Экспорт в DOCX с корректной нумерацией разделов, рисунков и ссылок
- Перегенерация отдельных разделов без полной пересборки
- Плагинная система анализаторов для новых языков/стеков

## Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend API | Python 3.11+, Django 5, Django REST Framework |
| База данных | SQLite (dev) / PostgreSQL 15 (prod) |
| Кэш/Очереди | Redis 7, Celery |
| Документы | python-docx |
| Скриншоты | Playwright (Chromium) |
| LLM | OpenAI API |
| Frontend | React + TypeScript + TailwindCSS + Vite |
| Контейнеризация | Docker/Compose |

## Структура проекта

```
academic-paper-generator/
├── server/                         # Backend (Django 5 + DRF)
│   ├── config/                     # Django settings, urls, celery
│   ├── apps/                       # Django applications
│   │   ├── core/                   # Core (test page, API endpoints)
│   │   ├── accounts/               # Auth & users (TODO)
│   │   └── projects/               # Projects, documents, sections, artifacts
│   ├── services/
│   │   ├── analyzer/               # Repo Analyzer - facts extraction
│   │   ├── llm/                    # LLM Client - OpenAI integration
│   │   ├── prompting/              # Context Packs & Slicing
│   │   ├── pipeline/               # Document Pipeline orchestration
│   │   ├── enrichment/             # Section enrichment from facts
│   │   └── editor/                 # Grounded editing (L1/L2/L3)
│   ├── tasks/                      # Celery tasks
│   ├── templates/                  # Django templates
│   ├── tests/                      # Backend tests (120+ tests)
│   ├── manage.py
│   └── requirements.txt
│
├── client/                         # Frontend (React + TypeScript + TailwindCSS)
│   ├── src/
│   │   ├── components/             # UI компоненты
│   │   ├── pages/                  # Страницы
│   │   ├── services/               # API клиент
│   │   ├── hooks/                  # React hooks
│   │   └── types/                  # TypeScript типы
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
│
├── docs/
│   ├── spec/                       # Спецификация проекта
│   └── PROMPTING_PLAYBOOK.md       # Technical docs for content quality
│
└── README.md
```

## Быстрый старт

### Backend

```bash
cd server
python -m venv venv
./venv/Scripts/activate    # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

- http://localhost:8000/test/ - тестовая страница analyzer
- http://localhost:8000/api/docs/ - Swagger документация

### Frontend

```bash
cd client
npm install
npm run dev
```

- http://localhost:5173/ - React приложение

## API

### v1 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyzer/analyze/` | Анализ репозитория |

**Request:**
```json
{
  "repo_url": "https://github.com/username/repository"
}
```

**Response:**
```json
{
  "status": "success",
  "facts": {
    "schema": "facts.v1",
    "repo": { "url": "...", "commit": "...", "detected_at": "..." },
    "languages": [...],
    "frameworks": [...],
    "architecture": {...},
    "modules": [...],
    "api": { "endpoints": [...], "total_count": 0 },
    "frontend_routes": [...],
    "models": [...],
    "runtime": { "dependencies": [...], "build_files": [...], "entrypoints": [...] }
  }
}
```

## Quality Guarantees

The system implements several mechanisms to ensure high-quality, traceable output:

### Traceability
- **Prompt Versioning**: Every generated artifact includes `prompt_version`
- **Prompt Fingerprint**: SHA256 hash of (system_prompt + user_prompt + facts + budget)
- **Artifact Chain**: section → context_pack → facts, fully traceable

### Groundedness
- **Editor Levels**: L1 (basic), L2 (medium), L3 (university-grade)
- **Grounding Rule**: L2/L3 can only use information from original text + facts
- **facts_used Tracking**: Every edit declares which facts were used

### Anti-Template Measures
- **Practice Guardrails**: Require entities, algorithms, tables in practice sections
- **Content Validation**: Automatic scoring of practice content (0-1 scale)
- **Terminology Consistency**: Detect mixed synonym usage

See [docs/PROMPTING_PLAYBOOK.md](docs/PROMPTING_PLAYBOOK.md) for technical details.

## Документация

- [docs/spec/](docs/spec/) - Спецификация проекта
- [docs/PROMPTING_PLAYBOOK.md](docs/PROMPTING_PLAYBOOK.md) - Техническая документация по качеству генерации

## Лицензия

MIT
