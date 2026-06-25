# Netpeak AI Request Triage

Сервіс структурує внутрішні запити до AI-юніту.

## Поточний стан

Реалізовано сервіс для структурування внутрішніх запитів до AI-юніту за допомогою Gemini API.

Сервіс:

* читає CSV із вхідними запитами;
* визначає категорію, цільовий відділ, пріоритет і потребу в уточненні;
* генерує короткий summary, перелік запитаних дій та уточнювальні питання;
* перевіряє structured output через Pydantic;
* виконує одну repair-спробу для невалідної відповіді;
* безпечно обробляє quota, rate limit, API errors та empty output через fallback;
* формує `output.json`, `report.md` і `review_queue.json`.

До репозиторію додано результат успішного реального запуску: 18 із 18 запитів валідно оброблено без fallback.

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

Сервіс синхронно витримує мінімальний інтервал між усіма Gemini API-викликами. За замовчуванням інтервал становить `13` секунд і налаштовується локально через `GEMINI_MIN_REQUEST_INTERVAL_SECONDS` у `.env`. Repair-запит також є окремим API-викликом. Фактичні квоти та рекомендований інтервал залежать від вибраної моделі, Google project і usage tier.

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
