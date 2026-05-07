# DQT — Data Quality Tool

[English](README.md) | **Русский**

> **Open-source UI для мониторинга скорингов: tree-binning + PSI (числовой и категориальный) + парная z-стабильность бинов во времени.**

Если ваша команда строила Streamlit-дашборды поверх `optbinning` /
`scorecardpy`, чтобы мониторить стабильность бинов и PSI по месяцам —
это та задача, на которую DQT отвечает.

Закидываете CSV → получаете самодостаточный HTML-отчёт со светофором
green/yellow/red на каждый признак, делитесь по `?session=<sid>`,
ставите гейт в CI через `--fail-on=red`. MIT-лицензия, чистый Python,
один процесс — без Redis, без Postgres, без AGPL-ловушек.

[![tests](https://github.com/gorevds/dqt-ui/actions/workflows/test.yml/badge.svg)](https://github.com/gorevds/dqt-ui/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![demo](https://img.shields.io/badge/demo-dqt.gorev.space-1f6feb)](https://dqt.gorev.space)

![DQT report screenshot](docs/screenshot-report.png)

## Что внутри

- **Распределение признака во времени** — квантильные ленты для
  числовых, stacked share для категориальных.
- **Target rate по дереву-биннингу за период** — держится ли связь
  каждого признака с таргетом по месяцам.
- **Drift-метрики** — PSI для числовых и категориальных, доля
  пропусков, доля выбросов (IQR / Z), консистентность типов.
- **Парная z-стабильность бинов** — Φ(z) по всем парам бинов, среднее.
  1 = бины разделимы, 0.5 = перекрываются. Та же методология, из
  которой исторически растут банковские scorecard'ы.
- **Свето́фор по признаку** — STABLE / WATCH / DRIFT, человечное
  однострочное описание, sticky-сайдбар, поиск + сортировка.
- **HTML-экспорт одним файлом** — для рассылки и архива.
- **CLI** — `dqt analyze data.csv -o report.html --fail-on=red`
  возвращает ненулевой exit code, когда что-то поплыло.

Тип таргета: бинарный, мультикласс, регрессия. Кейсы: кредитный
скоринг, anti-fraud, propensity, marketing attribution, A/B-shifts,
сенсорика — везде, где есть колонка времени и таргет, и нужно следить,
как они эволюционируют.

---

## Почему DQT для скоринг-команд и риск-моделирования

Если вам когда-либо приходилось отвечать **«калиброван ли скор в этом
месяце?»** перед model risk committee — скорее всего, вы уже строили
какой-то вариант этого дашборда сами: разбить признак на бины,
отрисовать target rate по бинам помесячно, подсветить PSI > 0.25
красным. DQT — это тот же дашборд, упакованный в продукт:

- **Тот же словарь**: бины, PSI 0.10 / 0.25, monotonicity, IV-style
  separation. Без «embedding drift»-жаргона, который приходится
  переводить.
- **MIT, Apache-friendly юридический профиль**: ложится рядом с
  внутренним кодом без юридической экспертизы, которую запускает
  AGPL.
- **152-ФЗ / on-prem-friendly**: чистый Python, никаких внешних SDK,
  работает на изолированном контуре — см.
  [docs/benchmark_metrics.md](docs/benchmark_metrics.md) о
  компромиссах метрик.
- **CI-гейт, понятный риск-команде**: `--fail-on=red` в
  Jenkins / GitHub Actions / GitLab CI роняет билд, когда любой
  отслеживаемый признак пробивает банковские пороги.

Сценарии, которые DQT ловит: trip PSI на app_amount / external_score;
смена долей бинов после bump'а версии feature-store; пропуски
переползли за 20 % в критичном предикторе.

---

## Сравнение с альтернативами

DQT живёт на пересечении **drift-мониторинга**
([Evidently](https://github.com/evidentlyai/evidently),
[NannyML](https://nannyml.readthedocs.io/)) и
**scoring-style биннинга**
([optbinning](https://github.com/guillermo-navas-palencia/optbinning),
[scorecardpy](https://github.com/ShichenXie/scorecardpy)). Связку —
дерево-биннинг по признаку + PSI + парная z-стабильность +
интерактивный UI под одним URL — целиком не закрывает ни один
существующий инструмент.

| Возможность | **DQT** | Evidently (OSS) | optbinning | ydata-profiling | NannyML |
|---|:-:|:-:|:-:|:-:|:-:|
| Интерактивный web UI (open-source) | ✅ | — (только cloud) | — | — | — (только cloud) |
| Standalone HTML-отчёт | ✅ | ✅ | частично | ✅ | ✅ |
| Tree-биннинг по признаку | ✅ | — | ✅ | — | — |
| PSI — числовой **и** категориальный | ✅ | ✅ | ✅ | — | ✅ |
| Парная z-стабильность бинов | ✅ | — | — | — | — |
| Свето́фор-светофор в UI | ✅ | частично | — | — | частично |
| Drift / метрики во времени | ✅ | ✅ | частично | — | ✅ |
| Outliers / missingness | ✅ | ✅ | — | ✅ | — |
| CLI с exit-кодами для CI | ✅ | частично | — | — | — |
| Демо-датасет «из коробки» | ✅ | — | — | — | — |
| LLM / текст / картинки drift | — | ✅ | — | — | — |
| Performance estimation без меток | — | — | — | — | ✅ |

### Чего DQT сознательно НЕ делает

- **LLM / текст / картинки / эмбеддинги drift** — это
  [Evidently](https://github.com/evidentlyai/evidently).
- **Performance estimation без меток** —
  [NannyML](https://nannyml.readthedocs.io/).
- **Общий EDA snapshot** —
  [ydata-profiling](https://github.com/ydataai/ydata-profiling).
- **Жёсткие data-validation правила** («`amount` > 0», schema
  enforcement) —
  [great_expectations](https://github.com/great-expectations/great_expectations) /
  [pandera](https://github.com/unionai-oss/pandera) /
  [soda-core](https://github.com/sodadata/soda-core).

DQT — для **табличных данных с колонкой времени и таргетом**, где
важно увидеть, как признаки и их связь с таргетом эволюционируют, на
языке скоринг-команд (бины, PSI, stability).

---

## Установка

```bash
pip install dqtui          # имя на PyPI
# from dqt import analyze  # имя для импорта
```

Или Docker (образ в GitHub Container Registry):

```bash
docker run --rm -p 8050:8050 ghcr.io/gorevds/dqt-ui:latest
# или:  docker compose up
```

## Быстрый старт

**Интерактивный UI** — `http://localhost:8050`, 4 шага
(Upload → Columns → Settings → Report):

```bash
dqt serve
```

**Headless HTML-отчёт** для CI / cron:

```bash
dqt analyze data.csv -o report.html              # автодетект time/target/features
dqt analyze data.parquet -o report.html \
            --time snapshot_date --target default \
            --fail-on red                        # exit 2 если есть DRIFT
```

**Python-библиотека** — для ноутбука:

```python
from dqt import analyze
report = analyze(df)                # автодетект колонок
report.severity_counts()            # {'green': 19, 'yellow': 5, 'red': 3}
report.save_html("dq.html")
report                              # rich repr в Jupyter
```

## Демо-датасет

Внутри пакета есть синтетический датасет про кредитные заявки за 24
месяца, со специально внесёнными drift-сигналами (растущие пропуски,
дрейф числовых, сдвиг долей категорий, выбросы):

```bash
python -c "from dqt.demo import make_demo_dataset; make_demo_dataset(2000).to_csv('/tmp/demo.csv', index=False)"
dqt analyze /tmp/demo.csv -o /tmp/demo.html
```

В UI: нажмите «Load demo dataset» — будет тот же.

## Конфигурация

Переменные окружения, которые DQT понимает:

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `DQT_MAX_UPLOAD_MB` | 250 | Лимит размера загружаемого файла в UI. |
| `DQT_DEMO_ROWS` | 8000 | Сколько строк генерировать в демо-датасете. |
| `DQT_SESSION_DIR` | (не задано) | Если задано — DataFrame сессии и метаданные сохраняются на диск; `?session=<sid>`-ссылки переживут рестарт сервиса. |
| `DQT_RUNS_DB` | `~/.dqt/runs.db` | Путь к SQLite с историей CLI-прогонов. |
| `DQT_THRESHOLDS_PATH` | (не задано) | YAML/JSON с переопределением порогов severity (per-feature). |

## Соответствие требованиям РФ

- **152-ФЗ**: данные не покидают ваш контур — DQT работает локально или
  на on-prem сервере, никаких внешних SDK, никакой телеметрии.
- **Аудит-лог**: записи в `~/.dqt/runs.db` (SQLite) дают неизменяемую
  историю «кто что когда измерил».
- **Air-gapped**: образ публикуется в GHCR, можно зеркалировать в
  любую корпоративную registry. Зависимости — публичный PyPI, можно
  поднять локальное зеркало (`devpi`, `pypicloud`).

Подробнее — `deploy/install.sh` для разворачивания на голом
Ubuntu/Debian с nginx + Let's Encrypt + systemd.

## Помощь и обратная связь

- Issues: https://github.com/gorevds/dqt-ui/issues
- Контрибьютор-гайд: [CONTRIBUTING.md](CONTRIBUTING.md)
- Архитектура для разработчиков: [ARCHITECTURE.md](ARCHITECTURE.md)

## Лицензия

MIT — см. [LICENSE](LICENSE). Коммерческое использование разрешено.
