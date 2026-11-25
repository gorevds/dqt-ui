# DQT — open-source UI для мониторинга скорингов: как мы убрали Streamlit-самосбор и SAS из риск-команды

*Черновик статьи для Habr. Целевая аудитория: data scientists и риск-аналитики в банках, финтехе, BNPL и страховании. Длина — ~7-9 минут чтения.*

---

## TL;DR

Каждая команда кредитного скоринга, фрода и propensity, которую я
видел за последние 5 лет, в какой-то момент строила свой **дашборд
мониторинга стабильности скорингов** на Streamlit, Dash, Plotly или
прямо в Jupyter. Все они выглядят примерно одинаково: дерево-биннинг
по признаку, target rate по бинам помесячно, светофор PSI 0.10 / 0.25,
выделение красным.

DQT — это тот же дашборд, упакованный в open-source инструмент. MIT
лицензия, чистый Python, один процесс, нет внешних SDK, нет AGPL.
Готов к тому, чтобы лечь рядом с внутренним кодом без юридической
экспертизы.

```bash
pip install dqtui
dqt analyze applications.parquet -o report.html --fail-on=red
```

Один URL для шеринга, CLI с exit-кодами для CI, REST API для
интеграций, операторы для Airflow / MLflow / GitHub Actions / dbt из
коробки.

[Демо](https://dqt.gorev.space) · [GitHub](https://github.com/gorevds/dqt-ui)

---

## Зачем ещё один drift-инструмент

Если вы пробовали Evidently или NannyML, вы знаете, что они отличные —
но не для скоринг-команд:

| | Evidently | NannyML | DQT |
|---|---|---|---|
| Терминология | embedding distance, conditional drift | CBPE, DLE, performance estimation | **bins, PSI 0.10/0.25, monotonicity** |
| Web UI (free) | ❌ только cloud | ❌ только cloud | ✅ |
| Tree-binning per feature | ❌ | ❌ | ✅ |
| AGPL | ❌ Apache | ❌ Apache | ✅ MIT |
| Лицензия для on-prem банка | ✅ | ✅ | ✅ |
| Идеален для | LLM, embeddings, ML monitoring | performance без меток | scorecard / fraud / propensity |

Конкретный пример того, что DQT делает хорошо, а Evidently — мимо. У
вас есть скор `score_external_a`, его распределение `N(600, 80)` не
изменилось — все распределенческие метрики (PSI, KS, Wasserstein)
говорят «всё стабильно». Но per-bin target rate в bin'е "лучших"
заёмщиков (top-decile) пополз вверх с 1.5% дефолтов до 4%, а в bin'е
"худших" — упал с 25% до 18%. Скоринг сломан, но distribution-level
drift это не ловит. **DQT ловит — потому что считает разделимость
бинов внутри каждого периода.**

См. [docs/benchmark_metrics.md](../docs/benchmark_metrics.md) — там
синтетический бенчмарк, где pairwise z-stability отрабатывает на
concept drift'е, на котором PSI / KS / JSD / Wasserstein стоят на нулях.

## Как это выглядит для аналитика

### 1. Загрузка датасета

UI: `dqt serve` → http://localhost:8050 → drag-n-drop CSV / Parquet.

CLI:

```bash
dqt analyze applications_2026.parquet \
    --time application_date \
    --target default_flag \
    --granularity month \
    --fail-on red \
    -o report.html
```

Из ноутбука:

```python
from dqt import analyze
report = analyze(df)              # автодетект time/target/features
report.severity_counts()           # {'green': 19, 'yellow': 5, 'red': 3}
report.save_html("dq.html")
```

### 2. Что считается под капотом

Для каждого признака:

- **PSI** — числовой и категориальный, по дереву биннинга или
  квантилям (на выбор), стандартные пороги 0.10 / 0.25.
- **Pairwise z-stability бинов** — для каждой пары бинов считается
  two-proportion z-test, `Φ(z)` усредняется по парам внутри периода.
  1 = бины разделимы, 0.5 = перекрываются. Метрика, которую
  используют скоринг-команды для проверки качества дискретизации, но
  которой нет ни в Evidently, ни в NannyML, ни в optbinning.
- **Target rate по бинам по периодам** — с CI на bin'у. Видно сразу,
  если конкретный bin поплыл по мере времени.
- **Drift-чеки**: missingness, доля выбросов (IQR / Z), консистентность
  типов.
- **Severity** — STABLE / WATCH / DRIFT по worst-of-метрик. Пороги
  переопределяются глобально или per-feature через
  `DQT_THRESHOLDS_PATH`.

### 3. Triage в UI

Sticky-сайдбар со светофором, поиск по имени признака, multi-direction
сортировка (по PSI, по stability, по severity). На отчётах из 30+
признаков это разница между «листать 5 минут» и «найти проблему за 30
секунд».

[скриншот: docs/screenshot-report.png]

### 4. Интеграция в CI / cron

`dqt analyze --fail-on=red` возвращает exit code 2, если хоть один
признак в red. Любой CI-гейт эту схему понимает.

GitHub Actions — отдельный action:

```yaml
- uses: gorevds/dqt-ui/actions/dqt@main
  with:
    data: data/applications_history.parquet
    time: snapshot_date
    target: default_flag
    fail-on: red
    notify: ${{ secrets.SLACK_WEBHOOK_URL }}
```

Airflow — отдельный оператор:

```python
from dqt.integrations.airflow import DQTAnalyzeOperator

drift_check = DQTAnalyzeOperator(
    task_id="drift_check",
    input_path="/data/{{ ds }}.parquet",
    time_col="snapshot_date",
    target_col="default_flag",
    fail_on="red",
)
```

MLflow — логирование одной строкой:

```python
from dqt.integrations.mlflow import log_report

with mlflow.start_run():
    report = analyze(df)
    log_report(report)            # html, json, метрики dqt.green/yellow/red как Run-метрики
```

dbt — резолвится по manifest.json:

```bash
dqt analyze --from-dbt target/manifest.json --dbt-model my_model \
            --sql-uri snowflake://... --time created_at --target default_flag
```

## Архитектура за 30 секунд

Слоистая, без циклов:

```
┌─────────────────────────────────────────────┐
│  dqt.app   ─ Dash UI                        │
│  dqt.api / cli / runs / notify / config     │
│  dqt.plots / report                         │
│  dqt.core  ─ pandas/sklearn/scipy           │
└─────────────────────────────────────────────┘
```

`dqt.core` ничего не знает про UI. Можно использовать как headless
библиотеку. UI — это тонкий слой Dash callback'ов поверх той же функции
`run_analysis`, что вызывает CLI. Один движок, три surface'а.

## On-prem и 152-ФЗ

Конкретно для российских команд:

- Чистый Python + sklearn + pandas. Никаких внешних SDK, никакой
  телеметрии. Данные не покидают периметр.
- Один Docker-образ, gunicorn внутри, 1 worker — без Redis, без БД (для
  истории CLI-прогонов используется локальный SQLite).
- Подходит для air-gapped установок: образ публикуется в GHCR, легко
  зеркалируется в корпоративную registry. Docker Hub / public PyPI
  можно заменить на локальные зеркала (`devpi`, `pypicloud`).
- В `deploy/install.sh` — рабочий рецепт под Ubuntu/Debian с nginx +
  Let's Encrypt + systemd, который мы используем сами на
  https://dqt.gorev.space.

## Что DQT не делает (намеренно)

- **LLM / эмбеддинги / картинки drift** — это
  [Evidently](https://github.com/evidentlyai/evidently). Их
  embedding-сценарии очень хорошо проработаны, и они там сильнее.
- **Performance estimation без меток** —
  [NannyML](https://nannyml.readthedocs.io/) специализируется именно
  на этом. Если вы оцениваете точность модели до того, как пришли
  ground-truth метки, идите туда.
- **Schema enforcement / data contracts** —
  [great_expectations](https://github.com/great-expectations/great_expectations) /
  [pandera](https://github.com/unionai-oss/pandera) /
  [soda-core](https://github.com/sodadata/soda-core).
- **EDA snapshot one-shot** —
  [ydata-profiling](https://github.com/ydataai/ydata-profiling).

DQT — узкая, опинионированная штука для **табличных данных с колонкой
времени и таргетом**. Если ваш datapath укладывается в это, она
сэкономит вам Streamlit-самосбор. Если нет — другие инструменты выше
закрывают остальное.

## Текущий статус

- v1.1: интеграции (GitHub Action, Airflow, MLflow, dbt, REST API) +
  bug-fix wave.
- 159 unit-тестов, ruff-clean, type hints везде.
- MIT лицензия. PR welcome,
  [CONTRIBUTING.md](https://github.com/gorevds/dqt-ui/blob/main/CONTRIBUTING.md)
  и [ARCHITECTURE.md](https://github.com/gorevds/dqt-ui/blob/main/ARCHITECTURE.md)
  как entry point.

## Roadmap

- Multi-user workspaces + read-only sharing (без login'а — токенизированные
  ссылки).
- Snowflake / BigQuery / ClickHouse native push-down (сейчас через
  SQLAlchemy, выкачивает строки).
- Регуляторные шаблоны для SR 11-7 model risk / IFRS 9 staging.
- Локализованные verdict'ы (`DQT_VERDICT_LOCALE=ru` и далее).

## Попробовать

```bash
pip install dqtui
dqt serve --port 8050
# или
docker run --rm -p 8050:8050 ghcr.io/gorevds/dqt-ui:latest
```

UI понимает CSV, TSV, Parquet, кнопка «Load demo dataset» — синтетический
портфель кредитных заявок за 24 месяца с заранее внесёнными drift-сигналами,
если хочется потыкать без своих данных.

GitHub: https://github.com/gorevds/dqt-ui
Demo: https://dqt.gorev.space
Issues / feature requests: https://github.com/gorevds/dqt-ui/issues

---

*Если используете похожий self-built Streamlit/Dash на работе и
готовы поделиться скриншотом своего варианта — закидывайте в
комментарии. DQT строится в том числе на feedback'е таких команд.*

---

### Что я хочу спросить у читателей

1. Какая метрика стабильности у вас сейчас на проде — PSI? IV? Что-то
   своё?
2. Чего не хватает в DQT, чтобы вы её попробовали в реальной работе?
3. Кто пишет на R `scorecard::perf_psi` и почему ещё не съехал на
   Python?
