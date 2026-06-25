# Netpeak AI Request Triage

Сервіс структурує внутрішні запити до AI-юніту.

## Поточний стан

Наразі реалізовано каркас проєкту, конфігурацію, доменні Pydantic-схеми,
читання CSV, prompt builder та Gemini client. Gemini API підключено через
офіційний пакет `google-genai`. Наступні етапи додадуть валідацію відповідей,
retry/fallback та формування звітів.

## Вимоги

- Python 3.11+

## Встановлення

```bash
python -m venv .venv
```

Активуйте віртуальне середовище:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Встановіть runtime- та dev-залежності:

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

Створіть локальний файл конфігурації:

```bash
# Linux/macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

## Тести

```bash
pytest
```

## Структура

```text
src/       конфігурація та доменні схеми
tests/     тести схем
data/input_requests.csv  вхідне вивантаження запитів
output/    демонстраційні результати майбутніх етапів
```

Файл `data/input_requests.csv` очікується у форматі UTF-8 CSV з колонками
`id`, `channel`, `timestamp`, `raw_text`.

> API-ключ Gemini не повинен потрапляти до Git. Зберігайте його лише в
> локальному файлі `.env` як `GEMINI_API_KEY`.
