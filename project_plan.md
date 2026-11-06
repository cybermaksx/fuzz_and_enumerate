# WebProbe — справочник для самостоятельной разработки

Nov 5, 2026 · @Maks

## 1. Как пользоваться справочником и окружение

Здесь собрано всё, что нужно для WebProbe: API каждой библиотеки с короткими примерами вызовов, ссылки на официальную документацию, ловушки и чек-лист по уровням. Логику модулей пишешь сам; примеры показывают только, как вызывать библиотеку, а не как решать задачу.

**Правило работы:** застрял, значит сначала раздел 9 (как найти ответ самому), потом официальная документация, потом исходник библиотеки.

### Окружение

```bash
mkdir webprobe && cd webprobe
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 pytest flask
pip freeze > requirements.txt
git init
```

Версия Python: 3.10+ (нужны `match`, `X | None` в аннотациях). Проверить: `python3 --version`.

### Структура проекта

```
webprobe/
├── webprobe/
│   ├── __init__.py
│   ├── __main__.py      # позволяет запускать python -m webprobe
│   ├── cli.py
│   ├── http_client.py
│   ├── fingerprint.py
│   ├── crawler.py
│   ├── fuzzer.py
│   ├── analyzer.py
│   ├── models.py        # dataclasses
│   ├── reporter.py
│   └── data/
│       ├── technologies.json
│       ├── errors.json
│       └── payloads/
├── tests/
│   ├── lab_app.py       # уязвимый Flask-стенд
│   └── test_*.py
├── requirements.txt
├── README.md
└── .gitignore           # .venv/, __pycache__/, reports/
```

Запуск из корня проекта: `python -m webprobe -u http://127.0.0.1:5000/`.

### Главная документация

- Python stdlib: [docs.python.org/3/library](https://docs.python.org/3/library/)
- requests: [requests.readthedocs.io](https://requests.readthedocs.io/en/latest/)
- BeautifulSoup: [crummy.com/software/BeautifulSoup/bs4/doc](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- pytest: [docs.pytest.org](https://docs.pytest.org/)
- Flask: [flask.palletsprojects.com](https://flask.palletsprojects.com/)
- Офлайн: `python3 -m pydoc -b` открывает браузер с документацией всего установленного

## 2. requests — HTTP-клиент

Весь сетевой код идёт через один объект `requests.Session`, обёрнутый в твой класс в `http_client.py`. Остальные модули никогда не импортируют requests напрямую. Документация: [Quickstart](https://requests.readthedocs.io/en/latest/user/quickstart/), [Advanced Usage](https://requests.readthedocs.io/en/latest/user/advanced/), [API](https://requests.readthedocs.io/en/latest/api/).

### Session

Session хранит cookies между запросами, переиспользует TCP-соединения и общие заголовки.

```python
import requests
s = requests.Session()
s.headers.update({"User-Agent": "WebProbe/0.1"})
s.cookies.set("session", "abc123")
s.proxies = {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
s.verify = False   # только для Burp/self-signed
```

### Отправка запроса

| Аргумент | Что делает | Пример |
| --- | --- | --- |
| `params` | query-строка, requests сам кодирует | `params={"id": "1'"}` |
| `data` | тело form-urlencoded | `data={"user": "a"}` |
| `json` | тело JSON + заголовок Content-Type | `json={"q": "x"}` |
| `headers` | заголовки этого запроса | `headers={"X-Forwarded-For": "'"}` |
| `cookies` | cookies этого запроса | `cookies={"lang": "'"}` |
| `timeout` | секунды; кортеж = (connect, read) | `timeout=(5, 15)` |
| `allow_redirects` | следовать ли 3xx | `allow_redirects=False` |

Универсальный вызов: `s.request(method, url, params=..., data=..., timeout=...)`. Удобно, когда метод приходит из формы.

### Объект Response

| Атрибут | Тип | Для чего тебе |
| --- | --- | --- |
| `r.status_code` | int | детект 500 |
| `r.headers` | CaseInsensitiveDict | `r.headers.get("server")` без учёта регистра |
| `r.text` | str | regex, парсинг HTML |
| `r.content` | bytes | favicon hash, точная длина |
| `r.cookies` | RequestsCookieJar | имена cookies для fingerprint |
| `r.url` | str | финальный URL после редиректов |
| `r.history` | list\[Response\] | цепочка редиректов |
| `r.elapsed` | timedelta | время до получения заголовков (не всего тела) |
| `r.encoding` | str | кодировка, которую угадал requests |
| `r.request` | PreparedRequest | что реально ушло на сервер |

Важно: `r.elapsed` не учитывает скачивание тела. Для тайминга оборачивай вызов в `time.perf_counter()`.

### Исключения

Все в `requests.exceptions`, базовый класс `RequestException`.

- `Timeout` (подклассы `ConnectTimeout`, `ReadTimeout`): ReadTimeout после payload'а сам по себе интересный сигнал
- `ConnectionError`: сервер упал или сбросил соединение
- `TooManyRedirects`
- `InvalidURL`, `MissingSchema`: ошибка в твоём коде или в URL от пользователя

Лови конкретные исключения, а не голый `except:`, иначе Ctrl+C тоже будет проглочен.

### Ретраи

Встроенный механизм через `urllib3.util.Retry` и `HTTPAdapter`:

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
s.mount("http://", HTTPAdapter(max_retries=retry))
s.mount("https://", HTTPAdapter(max_retries=retry))
```

Не добавляй 500 в `status_forcelist`: 500 для тебя находка, а не сбой. Документация Retry: [urllib3 Retry](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html).

### Сырые payload'ы

`params=` кодирует всё (`'` станет `%27`). Обычно это правильно. Когда нужно отправить символы как есть (двойное кодирование, невалидный `%C0`), собери строку запроса сам и передай URL целиком, без `params`. Посмотреть, что реально уйдёт: `req = requests.Request("GET", url, params=p); prep = s.prepare_request(req); print(prep.url)`.

### Отключить warning при verify=False

`import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)`.

## 3. urllib.parse — URL и кодирование

Фаззер постоянно разбирает URL, подменяет один параметр и собирает URL обратно. Всё это делает `urllib.parse`. Документация: [urllib.parse](https://docs.python.org/3/library/urllib.parse.html).

### Разбор

```python
from urllib.parse import urlparse, urlsplit, parse_qs, parse_qsl
u = urlsplit("https://t.lab:8443/item.php?id=5&cat=2#top")
# u.scheme='https' u.netloc='t.lab:8443' u.hostname='t.lab' u.port=8443
# u.path='/item.php' u.query='id=5&cat=2' u.fragment='top'
parse_qsl(u.query, keep_blank_values=True)   # [('id','5'), ('cat','2')]
parse_qs(u.query)                            # {'id':['5'], 'cat':['2']}
```

- `parse_qsl` сохраняет порядок и повторы (`a=1&a=2`); для фаззера он удобнее, чем `parse_qs`
- `keep_blank_values=True` обязательно, иначе параметр `?debug=` пропадёт
- `urlsplit` лучше `urlparse`: у второго есть устаревшее поле `params`

### Сборка

| Функция | Что делает |
| --- | --- |
| `urlencode(list_of_pairs)` | пары в строку `a=1&b=2` с кодированием |
| `urlencode(pairs, doseq=True)` | разворачивает списки значений |
| `urlunsplit((scheme, netloc, path, query, fragment))` | собирает URL из частей |
| `u._replace(query=new_q)` | копия SplitResult с одним изменённым полем |
| `urljoin(base, href)` | относительная ссылка из HTML в абсолютный URL |
| `urldefrag(url)` | отрезает `#fragment` (для нормализации в crawler'е) |

`urljoin` нужно знать хорошо, у него есть тонкости:

- `urljoin("http://a/b/c", "d")` даёт `http://a/b/d`
- `urljoin("http://a/b/c/", "d")` даёт `http://a/b/c/d`
- `urljoin("http://a/b/c", "/d")` даёт `http://a/d`
- `urljoin("http://a/b", "//evil/x")` даёт `http://evil/x` (другой origin, crawler должен это отсеять)

### Кодирование

| Функция | Пробел | Что не кодирует по умолчанию |
| --- | --- | --- |
| `quote(s)` | `%20` | `/` (параметр `safe='/'`) |
| `quote(s, safe='')` | `%20` | ничего, кроме букв, цифр и `_.-~` |
| `quote_plus(s)` | `+` | для значений в query |
| `unquote(s)` / `unquote_plus(s)` | обратное |  |

Двойное кодирование: `quote(quote(p, safe=''), safe='')`. Невалидные последовательности вроде `%C0%AF` вставляй как готовую строку, не прогоняя через `quote`.

### Same-origin проверка

Origin = `(scheme, hostname, port)`. Порт по умолчанию 80/443 может отсутствовать в URL, поэтому нормализуй: `u.port or {"http": 80, "https": 443}[u.scheme]`. Хост сравнивай в нижнем регистре.

## 4. Парсинг HTML

Начни с BeautifulSoup: так быстрее дойти до фаззинга. Если хочешь stdlib-only (как в pty-catcher), используй `html.parser.HTMLParser`, это событийный парсер. Не парси HTML регулярками: атрибуты в разном порядке, разные кавычки, переносы строк.

### BeautifulSoup

Документация: [bs4 docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/).

```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(r.text, "html.parser")
```

| Задача | Вызов |
| --- | --- |
| все формы | `soup.find_all("form")` |
| атрибут с дефолтом | `form.get("method", "get").lower()` |
| поля формы | `form.find_all(["input", "select", "textarea"])` |
| имя/значение поля | `tag.get("name")`, `tag.get("value", "")` |
| выбранный option | `sel.find("option", selected=True)` |
| meta generator | `soup.find("meta", attrs={"name": "generator"})` → `["content"]` |
| все скрипты с src | `soup.find_all("script", src=True)` |
| все ссылки | `soup.find_all("a", href=True)` |
| CSS-селектор | `soup.select("form input[type=hidden]")` |
| текст без тегов | `soup.get_text(" ", strip=True)` |
| title | `soup.title.string if soup.title else None` |

### Правила для форм

- нет `action` или он пустой → форма отправляется на текущий URL
- `action` относительный → `urljoin(page_url, action)`
- нет `method` → GET
- поля без `name` не отправляются, пропускай
- `type=submit/button/image/reset`: обычно не фаззишь, но `submit` с `name` нужно отправить, иначе бэкенд может не обработать форму
- `checkbox`/`radio` отправляются только отмеченные
- `type=file` пропускай (multipart это отдельная тема)
- `enctype="multipart/form-data"` → отправка через `files=`, а не `data=`

### Где ещё есть ссылки и точки входа

- `<a href>`, `<form action>`, `<iframe src>`, `<link href>`, `<script src>`, `<img src>`
- атрибуты `data-url`, `data-endpoint`
- inline JS: строки вида `fetch("/api/...")`, `axios.get("...")`, `$.ajax({url: ...})`. Вытаскиваются regex'ом по тексту `<script>`; это эвристика, ждать полноты не надо
- HTML-комментарии: `soup.find_all(string=lambda t: isinstance(t, Comment))` (импорт `from bs4 import Comment`). Там часто лежат пути и версии

### html.parser (stdlib)

Документация: [html.parser](https://docs.python.org/3/library/html.parser.html). Наследуешь `HTMLParser`, переопределяешь `handle_starttag(self, tag, attrs)` (attrs это список пар `(name, value)`), `handle_endtag`, `handle_data`, `handle_comment`. Состояние ("сейчас внутри формы") хранишь в атрибутах объекта. Вызов: `p = MyParser(); p.feed(html)`.

## 5. re — регулярные выражения

Regex понадобятся в двух местах: сигнатуры технологий (с извлечением версии) и сигнатуры ошибок. Документация: [re](https://docs.python.org/3/library/re.html), [Regex HOWTO](https://docs.python.org/3/howto/regex.html). Песочница для отладки: [regex101.com](https://regex101.com/) с флейвором Python.

### API

| Функция | Что возвращает | Когда |
| --- | --- | --- |
| `re.compile(p, flags)` | Pattern | один раз при загрузке JSON, не в цикле |
| `pat.search(s)` | Match или None | найти где угодно в строке (твой основной вызов) |
| `pat.match(s)` | Match или None | только с начала строки (почти не нужен) |
| `pat.findall(s)` | list | все совпадения (версии всех JS-библиотек) |
| `pat.finditer(s)` | итератор Match | то же с позициями |
| `m.group(1)`, `m.groups()` | str | извлечь версию |
| `m.group("ver")` | str | именованная группа `(?P<ver>...)` |
| `m.start()`, `m.end()` | int | позиция; для выдержки контекста вокруг ошибки |
| `re.escape(s)` | str | вставить литерал (маркер payload'а) в regex |

### Флаги

- `re.I` (IGNORECASE): почти всегда для сигнатур ошибок
- `re.S` (DOTALL): `.` захватывает перевод строки (стектрейсы многострочные)
- `re.M` (MULTILINE): `^`/`$` на каждой строке

### Шаблоны, которые пригодятся

| Цель | Шаблон |
| --- | --- |
| версия x.y.z | `(\d+(?:\.\d+){1,3})` |
| jQuery в имени файла | `jquery[.-]?(\d+(?:\.\d+)+)(?:\.min)?\.js` |
| Server: nginx/1.18.0 | `^nginx(?:/([\d.]+))?` |
| X-Powered-By: PHP/8.1.2 | `PHP/([\d.]+)` |
| Oracle-ошибка | `ORA-\d{5}` |
| строка PHP-ошибки | `(?:Fatal error\|Warning\|Notice):.{0,200}? on line \d+` |
| строка Java-стека | `at [\w$.]+\([\w$]+\.java:\d+\)` |

### Как хранить в JSON

В JSON обратный слэш экранируется: `\d` записывается как `"\\d"`. Проверка: `json.loads` + `re.compile` при старте. Если regex битый, ошибка вылетит сразу, а не посреди сканирования. Собери все ошибки компиляции и выведи списком с именем сигнатуры.

### Ловушки

- Пиши шаблоны в raw-строках: `r"\d+"`, иначе `\b` станет символом backspace
- Жадность: `.*` съест всё до последнего совпадения. Используй `.*?` и ограничивай длину: `.{0,200}?`
- Катастрофический бэктрекинг: вложенные квантификаторы вроде `(a+)+` на большой странице могут зависнуть. Тестируй на страницах размером в мегабайт
- Ограничивай текст: ищи в первых N КБ ответа, если страница огромная

## 6. Многопоточность и rate-limit

HTTP-запросы ждут сеть, поэтому потоки (threads) дают ускорение, несмотря на GIL. Используй `concurrent.futures.ThreadPoolExecutor`; asyncio/aiohttp оставь на потом. Документация: [concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html), [threading](https://docs.python.org/3/library/threading.html).

### API ThreadPoolExecutor

| Вызов | Что делает |
| --- | --- |
| `with ThreadPoolExecutor(max_workers=10) as ex:` | пул; при выходе из `with` ждёт все задачи |
| `fut = ex.submit(fn, *args)` | запустить одну задачу, вернуть Future |
| `as_completed(futures)` | итератор Future в порядке завершения |
| `fut.result(timeout=None)` | результат; если в задаче было исключение, оно поднимется здесь |
| `fut.exception()` | исключение без подъёма |
| `ex.map(fn, iterable)` | как map, результаты в исходном порядке |
| `ex.shutdown(cancel_futures=True)` | отменить ещё не начатые (Python 3.9+) |

Типичная форма: словарь `{future: input_point}`, затем цикл по `as_completed`, внутри `try: fut.result() except Exception`. Так одна упавшая задача не убьёт весь скан, и ты знаешь, к какому входу относится результат.

### Потокобезопасность

- `requests.Session` формально не гарантирует потокобезопасность. На практике его часто делят между потоками, но если меняешь cookies/headers во время скана, бери `threading.local()` и по Session на поток
- общий список находок: `list.append` атомарен в CPython, но для счётчиков и словарей используй `threading.Lock` (`with lock: ...`) или `queue.Queue`
- `print` из разных потоков перемешивает строки, поэтому пиши через `logging` (он потокобезопасен)

### Rate-limit

Простой ограничитель "не чаще N запросов в секунду" на все потоки: общий `Lock` + время последнего запроса (`time.monotonic()`). Внутри lock посчитать, сколько ждать, и `time.sleep(...)`. Это классический token bucket в упрощённом виде; почитай про него, если хочешь всплески.

Для тайминговой детекции потоки мешают: параллельная нагрузка сама по себе замедляет ответы. Тайминговые проверки запускай последовательно, с `max_workers=1`.

### Ctrl+C

В главном потоке лови `KeyboardInterrupt`, вызывай `ex.shutdown(wait=False, cancel_futures=True)`, сохраняй уже найденное в отчёт. Потеря результатов часового скана из-за Ctrl+C очень раздражает.

## 7. Stdlib: данные, CLI, анализ ответов

### dataclasses: модели данных

Документация: [dataclasses](https://docs.python.org/3/library/dataclasses.html). Вместо словарей с ключами-строками заведи классы в `models.py`. Опечатку в поле `finding.evidnce` поймает IDE, а опечатку в ключе словаря нет.

```python
from dataclasses import dataclass, field, asdict
@dataclass
class Example:
    name: str
    tags: list[str] = field(default_factory=list)   # не tags=[]!
    score: int = 0
asdict(Example("x"))   # {'name': 'x', 'tags': [], 'score': 0}, удобно для JSON
```

Какие модели скорее всего понадобятся (поля продумай сам): `Technology`, `InputPoint`, `Baseline`, `ProbeResult`, `Finding`. `@dataclass(frozen=True)` делает объект неизменяемым и хешируемым, поэтому его можно класть в set (дедупликация InputPoint).

### json

[json](https://docs.python.org/3/library/json.html): `json.load(f)` / `json.dump(obj, f, indent=2, ensure_ascii=False)`. Объект, который json не умеет (datetime, set), обрабатывай через `default=str` или конвертируй сам. Путь к файлам данных внутри пакета: `pathlib.Path(__file__).parent / "data" / "errors.json"`, тогда программа работает из любой директории.

### argparse

[argparse](https://docs.python.org/3/library/argparse.html), [tutorial](https://docs.python.org/3/howto/argparse.html).

| Нужно | Вызов |
| --- | --- |
| обязательный флаг | `add_argument("-u", "--url", required=True)` |
| число | `type=int, default=10` |
| булев флаг | `action="store_true"` |
| повторяемый | `action="append"` (несколько `-H`) |
| выбор | `choices=["json", "text"]` |
| группа взаимоисключающих | `add_mutually_exclusive_group()` |
| подкоманды | `add_subparsers(dest="cmd")` (`webprobe fp` / `webprobe fuzz`) |
| свой валидатор | `type=my_func`, внутри `raise argparse.ArgumentTypeError(...)` |

### logging

[logging HOWTO](https://docs.python.org/3/howto/logging.html). В каждом модуле `log = logging.getLogger(__name__)`; `basicConfig` вызывается один раз в `cli.py`. Уровни: `-v` = INFO, `-vv` = DEBUG. В DEBUG пиши каждый запрос и ответ (метод, URL, статус, длина, время), это главный инструмент отладки.

### hashlib, difflib, statistics, time

| Модуль | Вызов | Для чего |
| --- | --- | --- |
| [hashlib](https://docs.python.org/3/library/hashlib.html) | `hashlib.sha1(b).hexdigest()` | хеш нормализованного тела |
| [difflib](https://docs.python.org/3/library/difflib.html) | `SequenceMatcher(None, a, b).ratio()` | похожесть 0..1 (медленно на больших текстах; есть `quick_ratio()`) |
| [difflib](https://docs.python.org/3/library/difflib.html) | `unified_diff(a.splitlines(), b.splitlines())` | показать, что поменялось (в DEBUG-логе и отчёте) |
| [statistics](https://docs.python.org/3/library/statistics.html) | `mean`, `median`, `stdev` | baseline времени и длины |
| [time](https://docs.python.org/3/library/time.html) | `perf_counter()` | замер длительности запроса |
| [time](https://docs.python.org/3/library/time.html) | `monotonic()` | rate-limit (не прыгает при смене часов) |
| [base64](https://docs.python.org/3/library/base64.html) | `encodebytes(b)` | favicon hash в стиле Shodan: `mmh3.hash(base64.encodebytes(content))` |
| [secrets](https://docs.python.org/3/library/secrets.html) | `token_hex(4)` | уникальный маркер для проверки отражения |

### pathlib и шаблоны payload'ов

[pathlib](https://docs.python.org/3/library/pathlib.html): `Path(...).read_text().splitlines()`. В файлах payload'ов пропускай пустые строки и строки, начинающиеся с `#`, тогда в файлах можно писать комментарии.

Полезная идея: плейсхолдеры в payload'ах, например `{MARKER}` или `{ORIG}` (исходное значение параметра). Подстановка через `str.replace`, не через `.format()`: в payload'ах полно фигурных скобок (`{{7*7}}`), и `.format` на них упадёт.

## 8. Как писать свой код как библиотеку

Хороший инструмент можно импортировать из другого кода, а не только запускать из терминала. Например, `from webprobe.fingerprint import detect` внутри PYTHIA. Для этого CLI должен быть тонкой обёрткой над функциями, которые ничего не печатают и не вызывают `sys.exit`.

### Модули, пакеты, импорты

Документация: [Modules tutorial](https://docs.python.org/3/tutorial/modules.html), [Import system](https://docs.python.org/3/reference/import.html), [Packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

- папка с `__init__.py` = пакет; `__main__.py` запускается при `python -m webprobe`
- внутри пакета используй относительные импорты: `from .models import Finding`, `from . import analyzer`
- скрипт внутри пакета запускай через `python -m webprobe.cli`, а не `python webprobe/cli.py`, иначе относительные импорты падают с `ImportError: attempted relative import with no known parent package`
- `if __name__ == "__main__":` нужен только в точке входа
- циклический импорт (`a` импортирует `b`, `b` импортирует `a`) значит, что общий код надо вынести в третий модуль (обычно `models.py`)

### Правила API своих модулей

1. Функции получают данные и возвращают данные. `fingerprint` получает Response, возвращает список Technology. Печатает только `reporter`.
2. Зависимости передаются аргументами. Analyzer не создаёт свой HTTP-клиент, а получает его. Тогда в тестах можно подсунуть фейковый.
3. Один модуль = одна ответственность. Если в `fuzzer.py` появился regex для ошибок, он лежит не там.
4. Публичное без подчёркивания, внутреннее с `_`: `detect()` публичная, `_match_headers()` внутренняя.
5. Конфигурация через один объект (`ScanConfig` dataclass), а не глобальные переменные.

### Аннотации типов

[typing](https://docs.python.org/3/library/typing.html). Пиши `def detect(resp: requests.Response) -> list[Technology]:`. Python их не проверяет, но IDE подсказывает, а `mypy` (`pip install mypy`, `mypy webprobe/`) находит ошибки до запуска. Полезное: `X | None`, `Iterable[str]`, `Callable[[str], bool]`, `Protocol` (для фейкового клиента в тестах).

### Docstrings

[PEP 257](https://peps.python.org/pep-0257/). Первая строка говорит, что делает функция; дальше аргументы, возврат, исключения. Один стиль на весь проект (Google style читается легче всего):

```python
def example(text: str, limit: int = 100) -> list[str]:
    """Одна строка: что делает.

    Args:
        text: что это.
        limit: что ограничивает.

    Returns:
        Что возвращает и в каком случае пусто.

    Raises:
        ValueError: когда.
    """
```

Проверка: `help(webprobe.fingerprint)` в REPL должен показывать понятную документацию модуля.

### Собственные исключения

Заведи `errors.py` с базовым `class WebProbeError(Exception)` и наследниками (`TargetUnreachable`, `SignatureLoadError`). Библиотечный код поднимает их, CLI ловит `WebProbeError` и печатает человеческое сообщение. Внутри `except` используй `raise NewError(...) from e`, чтобы не терять исходную причину. Документация: [Errors tutorial](https://docs.python.org/3/tutorial/errors.html).

### Стиль

[PEP 8](https://peps.python.org/pep-0008/). Автоформат и линтер: `pip install ruff`, затем `ruff check .` и `ruff format .`. Это не AI, а механический анализатор, и он научит многим идиомам.

### README

Минимум для GitHub: что делает (1–2 предложения), установка, пример запуска с выводом, список флагов, как добавить свою сигнатуру или payload, дисклеймер про авторизованное тестирование, лицензия (MIT проще всего).

## 9. Как находить ответы самому

Этот раздел заменяет вопросы ко мне. Почти любой вопрос "как сделать X с библиотекой Y" решается за 5 минут одним из этих способов, по порядку.

### 1. Спросить сам объект (REPL)

Запусти `python3` в venv и исследуй живой объект:

| Вызов | Что покажет |
| --- | --- |
| `type(r)` | класс объекта |
| `dir(r)` | все атрибуты и методы (фильтр: `[a for a in dir(r) if not a.startswith("_")]`) |
| `help(r.json)` | docstring метода |
| `vars(obj)` | словарь атрибутов экземпляра |
| `inspect.signature(fn)` | аргументы функции |
| `inspect.getsource(fn)` | исходник функции прямо в консоли |
| `inspect.getfile(requests)` | где лежит файл библиотеки |

Удобнее с `pip install ipython`: там работают `r.<Tab>` для автодополнения, `fn?` для docstring и `fn??` для исходника.

### 2. Официальная документация

Ищи в ней через поиск по сайту, а не в Google: `site:docs.python.org urljoin`. Читай разделы API Reference, там перечислены все аргументы. Обращай внимание на пометки "Changed in version 3.x".

Офлайн: `python3 -m pydoc urllib.parse` в терминале или `python3 -m pydoc -b` в браузере.

### 3. Исходник библиотеки

Если документации мало, ответ точно в коде. `pip show -f requests` показывает, где установлен пакет. Читай `requests/sessions.py` (метод `request`) и `requests/models.py` (класс Response): это около 2000 строк понятного кода, и после этого вопросов по requests не останется. В VS Code: Ctrl+клик (Go to Definition) по любой функции.

### 4. Эксперимент

Не уверен, как поведёт себя функция? Напиши 3 строки в REPL и проверь. Например, что вернёт `parse_qsl("a=&b")` или что уйдёт на сервер при `params={"x": None}`. Эксперимент быстрее любого вопроса и запоминается лучше.

Для HTTP: подними `python3 -m http.server 8000` или `nc -lvnp 8000` и отправь туда запрос. Увидишь в сыром виде, что именно сформировал requests.

### 5. Ошибка в traceback

Читай traceback снизу вверх. Последняя строка показывает тип и сообщение, строки выше показывают путь вызовов. Ищи первую строку из своего файла, ошибка почти всегда там, а не в библиотеке. Сообщение ошибки в кавычках ищи в поиске дословно, только без своих имён переменных и путей.

### 6. Чужой код с похожей задачей

GitHub-поиск по коду: `path:*.py "parse_qsl" "urlencode" fuzz`. Смотри, как это решили в WhatWeb, wafw00f, sqlmap, Arjun (поиск скрытых параметров, Python). Цель в том, чтобы понять идею и написать своё, без копирования.

### 7. Stack Overflow

Ищи вопрос, а не ответ: часто проблема уже описана. Смотри дату: ответы 2012 года могут быть про Python 2.

## 10. Тестирование: pytest и свой стенд

Сканер, который ты не проверил на известных уязвимостях, нельзя считать работающим. Нужны две вещи: unit-тесты на логику и маленький Flask-стенд, где ты сам заложил ошибки и знаешь правильный ответ.

### pytest

Документация: [Getting started](https://docs.pytest.org/en/stable/getting-started.html), [fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html), [parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html).

- файлы `tests/test_*.py`, функции `test_*`, проверки через обычный `assert`
- запуск: `pytest -q`, один тест: `pytest -k normalize`, с выводом print: `pytest -s`
- `@pytest.mark.parametrize("inp,expected", [...])` прогоняет один тест на многих входах. Идеально для regex-сигнатур: по строке на каждую ошибку СУБД
- `with pytest.raises(SignatureLoadError):` проверяет, что исключение поднимается
- `tmp_path` (встроенная fixture) даёт временную папку для тестов загрузки JSON
- `pytest --cov=webprobe` (`pip install pytest-cov`) показывает, какие строки не покрыты тестами

### Что тестировать unit-тестами (без сети)

| Модуль | Что проверять |
| --- | --- |
| fingerprint | на сохранённых заголовках и HTML правильно находится технология и версия |
| errors.json | каждая сигнатура срабатывает на своём примере и не срабатывает на обычной странице |
| нормализация | две версии одной страницы с разными токенами и временем дают одинаковый хеш |
| fuzzer | подстановка меняет ровно один параметр, остальные на месте |
| crawler | форма без action, относительные ссылки, чужой origin |
| analyzer | на фейковых ответах: 500, отражение, длинный ответ |

Сохраняй реальные ответы как файлы в `tests/fixtures/` (HTML страниц WordPress, Django debug, Tomcat 404) и тестируй на них. Это быстро и не зависит от сети.

### Учебный стенд на Flask

Документация: [Flask quickstart](https://flask.palletsprojects.com/en/stable/quickstart/). Запуск: `flask --app tests/lab_app run` (по умолчанию слушает 127.0.0.1:5000). Слушай только localhost.

Какие эндпоинты заложить (реализуешь сам):

| Эндпоинт | Уязвимость | Что должен найти сканер |
| --- | --- | --- |
| `/item?id=` | SQL-запрос к sqlite3 через f-строку | SQL-ошибку от SQLite |
| `/hello?name=` | `render_template_string` с вводом | SSTI: `{{7*7}}` превращается в 49 |
| `/search?q=` | вывод без экранирования | отражение маркера |
| `/file?name=` | `open()` без проверки пути | ошибку файловой системы / traversal |
| `/calc?n=` | `int(n)` без try | 500 + traceback при `debug=True` |
| `/safe?q=` | всё экранировано | ничего (проверка ложных срабатываний) |
| `/dynamic` | случайный токен и время в каждом ответе | ничего (проверка нормализации) |
| `/slow?q=` | `time.sleep`, если в q есть кавычка | тайминговую аномалию |
| форма `/login` | POST + hidden CSRF-поле | crawler находит форму и все поля |

Добавь заголовки `X-Powered-By` и cookie, чтобы проверить fingerprint. Эндпоинты `/safe` и `/dynamic` важны не меньше уязвимых: они ловят ложные срабатывания.

Можно поднимать стенд прямо в pytest через fixture, запуская сервер в отдельном потоке, но проще держать его запущенным во втором терминале.

### Готовые цели (только авторизованные)

- DVWA: `docker run -p 8080:80 vulnerables/web-dvwa`
- OWASP Juice Shop: `docker run -p 3000:3000 bkimminich/juice-shop`
- testphp.vulnweb.com: публичный стенд Acunetix для сканеров
- PortSwigger Web Security Academy: SQLi, SSTI, information disclosure

## 11. Отладка и частые ошибки

### Инструменты

- **Burp как прокси:** `--proxy http://127.0.0.1:8080` + `verify=False`. В HTTP history видно каждый запрос в сыром виде; подозрительный ответ можно отправить в Repeater и проверить руками. Это главный способ понять, что сканер делает не то
- **logging DEBUG:** одна строка на запрос: метод, URL, параметр, payload, статус, длина, время
- **pdb:** вставь `breakpoint()` в нужное место, запусти программу. Команды: `n` (следующая строка), `s` (войти в функцию), `c` (продолжить), `p expr` (напечатать), `l` (показать код), `w` (стек), `q` (выход). Документация: [pdb](https://docs.python.org/3/library/pdb.html)
- **post-mortem:** `python -m pdb -m webprobe ...`: при падении откроет отладчик в месте ошибки
- **VS Code debugger:** точки останова кликом, просмотр переменных. Конфигурация `launch.json` с `"module": "webprobe"`

### Частые ошибки и что делать

| Симптом | Вероятная причина | Что проверить |
| --- | --- | --- |
| `ImportError: attempted relative import` | запуск файла напрямую | `python -m webprobe` из корня проекта |
| `ModuleNotFoundError: bs4` | не активирован venv | `which python` должен указывать в `.venv` |
| каждый payload даёт находку | нет нормализации или WAF | сравни два обычных ответа между собой; ищи 403/406 |
| ни одной находки на стенде | payload кодируется дважды или не тот параметр | посмотри запрос в Burp |
| `UnicodeDecodeError` / кракозябры | неверная кодировка | `r.encoding`, `r.apparent_encoding`; для регулярок по байтам используй `r.content` |
| `SSLError` | self-signed сертификат | `verify=False` (только в тестах) |
| скан зависает | нет таймаута | `timeout=` на каждом запросе |
| после логина всё 302 на /login | сессия умерла или CSRF | проверь `r.history`, заново получай токен |
| `KeyError` при `form["action"]` | атрибута нет | `.get("action", "")` |
| `re.error: bad escape` | обратные слэши в JSON | `"\\d"` в JSON, raw-строки в коде |
| `.format()` падает с `KeyError` | фигурные скобки в payload | `str.replace` вместо format |
| `RuntimeError: dictionary changed size during iteration` | изменение dict в цикле по нему | итерируйся по `list(d.items())` |
| `tags=[]` общий для всех объектов | мутабельный дефолт | `field(default_factory=list)` |
| 429 Too Many Requests | слишком быстро | `--delay`, меньше потоков, `Retry` с backoff |

### Привычка, которая экономит часы

Прежде чем писать модуль, руками проверь идею на одном запросе: в Burp Repeater или в REPL. Если глазами не видишь разницы между нормальным и сломанным ответом, код её тоже не увидит.

## 12. Чек-лист по уровням L0–L9

Каждый уровень заканчивается проверяемым результатом. Не переходи дальше, пока критерий не выполнен на стенде из раздела 10. В скобках указаны разделы справочника.

### L0. Скелет

- [ ] структура пакета, venv, git, `python -m webprobe --help` работает (1, 7, 8)
- [ ] `-u URL` → GET → печать статуса и заголовков (2)
- [ ] таймаут и понятное сообщение, если хост недоступен (2, 8)

### L1. Fingerprint по заголовкам

- [ ] Server, X-Powered-By, имена cookies → список технологий (2)
- [ ] правила пока прямо в коде
- [ ] на стенде определяется то, что ты сам выставил в заголовках

### L2. Сигнатуры в JSON

- [ ] `technologies.json`: headers, cookies, meta, html, scriptSrc + версия через группу (5, 7)
- [ ] битая сигнатура → ошибка при старте с именем сигнатуры (5, 8)
- [ ] confidence 0–100; pytest на сохранённых страницах WordPress/Django/nginx (10)

### L3. Активные пробы

- [ ] robots.txt, 404-страница со случайным путём, favicon hash (7)
- [ ] детект WAF/CDN по заголовкам
- [ ] итоговый отчёт по технологиям в консоли

### L4. Первый фаззинг

- [ ] разбор query-параметров, подмена ровно одного (3)
- [ ] payload'ы из файлов с комментариями (7)
- [ ] находка = статус 500; на стенде `/calc` найден, `/safe` чист

### L5. Baseline

- [ ] 2–3 обычных запроса: статус, длина, время, хеш нормализованного тела (7)
- [ ] `/dynamic` не даёт находок
- [ ] отклонение длины учитывает разброс baseline

### L6. Сигнатуры ошибок

- [ ] `errors.json` по категориям: SQL по СУБД, Python, PHP, Java, .NET, Node (5)
- [ ] в находке выдержка ±100 символов вокруг совпадения
- [ ] подтверждение повтором; пара `'` / `''` для SQL
- [ ] SSTI и отражение маркера; на стенде найдены `/item`, `/hello`, `/search`

### L7. Crawler

- [ ] ссылки same-origin, глубина, нормализация, без повторов (3, 4)
- [ ] формы GET/POST со всеми полями, включая hidden (4)
- [ ] cookies и заголовки как точки ввода
- [ ] свежий CSRF-токен перед каждым POST; найдена форма `/login`

### L8. Масштаб

- [ ] ThreadPoolExecutor, `--threads`, `--delay` (6)
- [ ] `--proxy`, `-H`, `--cookie` для авторизованного скана (2)
- [ ] Ctrl+C сохраняет найденное (6)
- [ ] скан DVWA с авторизацией проходит без падений

### L9. Финал

- [ ] JSON-отчёт + цветная консоль (`reporter.py`)
- [ ] приоритет payload'ов по найденному стеку (PHP+MySQL → сначала MySQL-сигнатуры)
- [ ] тайминговые проверки последовательно, `/slow` найден (6)
- [ ] README, лицензия, дисклеймер; `ruff` и `pytest` чистые (8, 10)
- [ ] модули импортируются из другого кода (8)

### Ориентиры для идей (читать, не копировать)

- [webappanalyzer](https://github.com/enthec/webappanalyzer): формат сигнатур технологий
- [WhatWeb](https://github.com/urbanadventurer/WhatWeb): плагины fingerprint
- [wafw00f](https://github.com/EnableSecurity/wafw00f): детект WAF на Python
- [sqlmap](https://github.com/sqlmapproject/sqlmap): `data/xml/errors.xml`, `lib/request/comparison.py`
- [Arjun](https://github.com/s0md3v/Arjun): поиск скрытых параметров
- [SecLists](https://github.com/danielmiessler/SecLists) и [PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings): payload'ы
- [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/): INFO-02, INFO-08, ERRH-01
