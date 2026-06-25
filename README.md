# Netpeak AI Request Triage

Сервіс структурує внутрішні запити до AI-юніту.

## Поточний стан

Наразі реалізовано каркас проєкту, конфігурацію, доменні Pydantic-схеми,
читання CSV, prompt builder та Gemini client. Gemini API підключено через
офіційний пакет `google-genai`. LLM-відповідь проходить Pydantic-валідацію,
одну спробу repair для невалідного structured output та безпечний fallback без
падіння всього процесу. Після обробки сервіс створює структурований JSON,
Markdown-звіт і чергу ручної перевірки.

Fallback направляє запит на ручну перевірку з `needs_clarification=true`,
`confidence=low` та `routing_recommendation="Manual triage"`.

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

Заповніть API-ключ у `.env`:

```env
GEMINI_API_KEY=...
```

## Запуск

```bash
pip install -r requirements.txt
python -m src.main
```

Запуск із явними шляхами:

```bash
python -m src.main --input data/input_requests.csv --output-dir output
```

Після завершення в директорії результатів створюються:

- `output.json` — повний структурований результат і технічні метадані;
- `report.md` — агрегований Markdown-звіт;
- `review_queue.json` — запити для ручної перевірки.

До черги ручної перевірки потрапляють запити, що потребують уточнення, мають
низьку впевненість, отримали fallback або мають неоднозначну класифікацію
`поза скоупом`.

## Обмеження

Помилки квоти або rate limit Gemini API обробляються як fallback для окремого
запиту. Фактична доступність моделі та ліміти залежать від Google project і
usage tier. За відсутності доступної квоти результат матиме
`validation_status="fallback"` і потрапить до `review_queue.json`.

Сервіс синхронно витримує мінімальний інтервал між усіма Gemini API-викликами.
За замовчуванням це `13` секунд, що підходить для Free tier з обмеженням
5 RPM. Значення можна локально змінити через
`GEMINI_MIN_REQUEST_INTERVAL_SECONDS` у `.env`. Repair-запит також рахується
як окремий API-виклик. Фактичні квоти залежать від Google project, моделі та
usage tier, тому цей інтервал не гарантує відсутність 429 у всіх середовищах.

`output.json` містить безпечну технічну категорію причини fallback:
rate limit або quota, API error чи empty output. Сервіс не записує до
`processing_error` секрети, текст вихідного запиту, повну відповідь провайдера
або stack trace.

## Тести

```bash
pytest
```

## Структура

```text
src/       конфігурація, обробка, CLI та генерація артефактів
tests/     автоматизовані тести
data/input_requests.csv  вхідне вивантаження запитів
output/    результати обробки
```

Файл `data/input_requests.csv` очікується у форматі UTF-8 CSV з колонками
`id`, `channel`, `timestamp`, `raw_text`.

> API-ключ Gemini не повинен потрапляти до Git. Зберігайте його лише в
> локальному файлі `.env` як `GEMINI_API_KEY`.
