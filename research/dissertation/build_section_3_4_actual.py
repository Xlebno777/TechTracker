from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE_DIR = Path(__file__).resolve().parent
RUN_DIR = Path('/home/zulixo/projects/TechTracker/research/evaluation/run_20260415_140743_chapter3_4_refresh_20260415')
OUT_MD = BASE_DIR / 'section_3_4_actual_20260415.md'
OUT_DOCX = BASE_DIR / 'section_3_4_actual_20260415.docx'

BODY_FONT = 'Times New Roman'
BODY_SIZE = Pt(14)
TABLE_SIZE = Pt(12)
FIRST_LINE = Cm(1.25)
LINE_SPACING = 1.5


def read_csv_rows(name: str) -> list[dict[str, str]]:
    path = RUN_DIR / name
    with path.open('r', encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def as_float(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_num(value: Any, digits: int = 2) -> str:
    val = as_float(value)
    if val is None:
        return '—'
    return f'{val:.{digits}f}'.replace('.', ',')


def fmt_pct(value: Any, digits: int = 2) -> str:
    val = as_float(value)
    if val is None:
        return '—'
    return f'{val * 100:.{digits}f}%'.replace('.', ',')


def set_run_font(run, *, bold=None, italic=None, size=BODY_SIZE, name=BODY_FONT):
    run.font.name = name
    run._element.rPr.rFonts.set(qn('w:ascii'), name)
    run._element.rPr.rFonts.set(qn('w:hAnsi'), name)
    run._element.rPr.rFonts.set(qn('w:cs'), name)
    run.font.size = size
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def format_body_paragraph(p):
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = FIRST_LINE
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    for run in p.runs:
        set_run_font(run)


def format_heading_paragraph(p, *, center=False, before=6, after=6):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.first_line_indent = None
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    for run in p.runs:
        set_run_font(run, bold=True)


def format_caption_paragraph(p):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = None
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    for run in p.runs:
        set_run_font(run)


def add_body(doc: Document, text: str):
    p = doc.add_paragraph(text)
    format_body_paragraph(p)
    return p


def add_heading(doc: Document, text: str, *, level: int = 1):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, bold=True)
    if level == 1:
        format_heading_paragraph(p, center=True, before=12, after=6)
    else:
        format_heading_paragraph(p, center=False, before=6, after=6)
    return p


def add_caption(doc: Document, text: str):
    p = doc.add_paragraph(text)
    format_caption_paragraph(p)
    return p


def add_picture_with_caption(doc: Document, image_path: Path, caption: str, *, width_cm: float = 15.5):
    if not image_path.exists():
        add_body(doc, f'[{caption}: файл {image_path.name} не найден.]')
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(image_path), width=Cm(width_cm))
    add_caption(doc, caption)


def shade_cell(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill)
    tc_pr.append(shd)


def set_cell_text(cell, text: str, *, bold=False, align='left', size=TABLE_SIZE):
    cell.text = ''
    p = cell.paragraphs[0]
    p.alignment = {
        'left': WD_ALIGN_PARAGRAPH.LEFT,
        'center': WD_ALIGN_PARAGRAPH.CENTER,
        'right': WD_ALIGN_PARAGRAPH.RIGHT,
        'justify': WD_ALIGN_PARAGRAPH.JUSTIFY,
    }[align]
    p.paragraph_format.first_line_indent = None
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(str(text))
    set_run_font(run, bold=bold, size=size)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def add_table(doc: Document, caption: str, headers: list[str], rows: list[list[str]], *, col_widths_cm: list[float] | None = None):
    add_caption(doc, caption)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for idx, text in enumerate(headers):
        set_cell_text(hdr[idx], text, bold=True, align='center')
        shade_cell(hdr[idx], 'D9EAF7')
        if col_widths_cm and idx < len(col_widths_cm):
            hdr[idx].width = Cm(col_widths_cm[idx])
    for row in rows:
        cells = table.add_row().cells
        for idx, text in enumerate(row):
            align = 'center' if idx > 0 else 'left'
            set_cell_text(cells[idx], text, align=align)
            if col_widths_cm and idx < len(col_widths_cm):
                cells[idx].width = Cm(col_widths_cm[idx])
    doc.add_paragraph('')
    return table


model_h = read_csv_rows('forecast_metrics_by_model_horizon.csv')
variant_h = read_csv_rows('forecast_metrics_by_variant_horizon.csv')
dm_rows = read_csv_rows('forecast_dm_tests.csv')
delta_rows = read_csv_rows('decision_delta_r_by_horizon.csv')
report_md = (RUN_DIR / 'dissertation_evaluation_report.md').read_text(encoding='utf-8')


def by_horizon(h: str):
    return [row for row in model_h if row.get('horizon') == h]


def model_row(rows: list[dict[str, str]], model: str):
    for row in rows:
        if row.get('model_kind') == model:
            return row
    return {}


def sarima_variant_row(horizon: str, key: str):
    for row in variant_h:
        if row.get('horizon') == horizon and row.get('variant_key') == key:
            return row
    return {}


def dm_row(horizon: str, a: str, b: str):
    for row in dm_rows:
        if row.get('horizon') == horizon and row.get('model_a') == a and row.get('model_b') == b:
            return row
    return {}


rows_24 = by_horizon('24h')
rows_7 = by_horizon('7d')
rows_30 = by_horizon('30d')

sarima_24 = model_row(rows_24, 'sarima')
lstm_24 = model_row(rows_24, 'lstm')
ensemble_24 = model_row(rows_24, 'ensemble')

sarima_7 = model_row(rows_7, 'sarima')
lstm_7 = model_row(rows_7, 'lstm')
ensemble_7 = model_row(rows_7, 'ensemble')

sarima_30 = model_row(rows_30, 'sarima')
lstm_30 = model_row(rows_30, 'lstm')
ensemble_30 = model_row(rows_30, 'ensemble')

v24_stl = sarima_variant_row('24h', 'sarima:stl_reseasonalized')
v24_seasonal = sarima_variant_row('24h', 'sarima:sarima_seasonal')
v7_stl = sarima_variant_row('7d', 'sarima:stl_reseasonalized')
v7_seasonal = sarima_variant_row('7d', 'sarima:sarima_seasonal')
v30_stl = sarima_variant_row('30d', 'sarima:stl_reseasonalized')
v30_seasonal = sarima_variant_row('30d', 'sarima:sarima_seasonal')

dm_24_lstm_ens = dm_row('24h', 'lstm', 'ensemble')
dm_24_sarima_ens = dm_row('24h', 'sarima', 'ensemble')
dm_7_lstm_ens = dm_row('7d', 'lstm', 'ensemble')
dm_7_sarima_ens = dm_row('7d', 'sarima', 'ensemble')
dm_30_sarima_ens = dm_row('30d', 'sarima', 'ensemble')

delta_24 = next((r for r in delta_rows if r.get('horizon') == '24h'), {})
delta_30 = next((r for r in delta_rows if r.get('horizon') == '30d'), {})

intro = f'''3.4 Вычислительный эксперимент на базе собранных метрик

Актуализированный вычислительный эксперимент выполнен на текущем состоянии проекта TechTracker после переработки ветвей SARIMA, удалённого LSTM-прогноза, оркестрации моделей и модуля диссертационной верификации. В качестве источника результатов используется фактически выполненный запуск `run_20260415_140743_chapter3_4_refresh_20260415`, сформированный штатной командой `run_dissertation_evaluation` по устройству `DEMO-SARIMA-001`. В эксперименте использован единый научный протокол: горизонты прогноза `24h`, `7d`, `30d`; модели `sarima`, `lstm`, `ensemble`; режим `strict intersection = True`; статистическая проверка различий через Diebold–Mariano test; доверительные интервалы метрик на основе moving block bootstrap с 300 итерациями.

Принципиально важно, что данный раздел построен не по старым промежуточным артефактам, а по актуальному состоянию системы после последних инженерных доработок. Это означает, что в текст включены результаты уже с траекторным прогнозом, переработанной LSTM-ветвью, winner-aware оркестрацией, unified state inference и актуальной логикой расчёта риска и экономического эффекта.

В итоговую выборку попало 360001 прогнозная точка. Для всех этих точек найден фактический ряд, а после применения режима строгого пересечения для сопоставления моделей осталось 336849 точек, то есть 93,57% от общего числа. Количество независимых ключей сравнения составило 8085. Следовательно, эксперимент нельзя считать малой проверкой на отдельных примерах: сравнение проводится на крупной выборке зрелых прогнозных наблюдений и потому пригодно для использования в диссертационном тексте.
'''

p341 = f'''3.4.1 Организация эксперимента и состав выборки

Эксперимент был проведён на данных одного демонстрационного сервера `DEMO-SARIMA-001`, для которого в системе накоплена длительная история сырых метрик, прогнозных запусков и решений СППР. Такой выбор оправдан тем, что именно для этого устройства в проекте была последовательно отлажена полная цепочка «телеметрия → прогноз → состояние → риск → рекомендация → оценка качества». В отличие от лабораторного сравнения на отрывочных рядах, здесь используются данные реального программного контура, включая результаты удалённого LSTM-сервиса.

Окно отбора прогнозных точек составило период с 17.10.2025 по 15.04.2026 по целевым временам прогноза, а окно фактических значений — с 15.10.2025 по 17.04.2026. Выбор такого окна позволяет включить только созревшие прогнозы, по которым уже известен факт. Благодаря этому исключается ситуация, когда качество модели оценивается по незавершённому горизонту. Для краткосрочного, среднесрочного и долгосрочного прогнозов одновременно использовались горизонты `24h`, `7d` и `30d`.

Всего в анализ было вовлечено 141312 фактических точек сырых метрик по восьми потокам телеметрии. Для каждой модели доступность факта различается незначительно, однако после включения `strict intersection` сохраняется достаточно большая выборка: для SARIMA по горизонту 30 суток в финальное сравнение вошло 86326 точек, для LSTM — 54799 точек, для оркестра — 80458 точек. Это позволяет делать не только описательные, но и статистически устойчивые выводы.
'''

table_34_rows = [
    ['Устройство', 'DEMO-SARIMA-001', 'Единый объект сравнения всех моделей и модулей СППР.'],
    ['Горизонты', '24h, 7d, 30d', 'Сопоставление краткосрочного, среднесрочного и долгосрочного прогноза.'],
    ['Модели', 'SARIMA, LSTM, Оркестр', 'Сравнение локальной статистической, удалённой нейросетевой и интегрированной ветвей.'],
    ['Режим сравнения', 'strict intersection = True', 'Сравнение только на общих зрелых точках, где факт найден у всех выбранных моделей.'],
    ['Bootstrap', '300 итераций, moving block, L = auto', 'Оценка доверительных интервалов с учётом временной зависимости ошибок.'],
    ['Общий объём прогноза', '360001 точка', 'Полное множество прогнозных наблюдений в окне эксперимента.'],
    ['Финальная выборка сравнения', '336849 точек (93,57%)', 'Подвыборка, использованная для прямого сравнения качества моделей.'],
]

p342 = f'''3.4.2 Результаты на горизонте 24 часа

На горизонте 24 часа лучшую точность по RMSE показала модель SARIMA: {fmt_num(sarima_24.get('rmse'),4)} при MAE {fmt_num(sarima_24.get('mae'),4)}. Оркестр оказался близок к ней по RMSE и составил {fmt_num(ensemble_24.get('rmse'),4)}, однако уступил по центральной ошибке. LSTM на этом горизонте показала худший RMSE ({fmt_num(lstm_24.get('rmse'),4)}), но при этом обеспечила наименьший MAE ({fmt_num(lstm_24.get('mae'),4)}). Это означает, что нейросетевая ветвь на кратком горизонте лучше удерживает типичную ошибку по модулю, но хуже реагирует на тяжёлые отклонения, которые сильнее влияют на RMSE.

По вероятностным метрикам лучшая средняя pinball-ошибка зафиксирована у LSTM: {fmt_num(lstm_24.get('pinball_avg'),4)}. В то же время по калибровке интервала наиболее близким к целевому покрытию 80% оказался оркестр: его PICP80 составил {fmt_pct(ensemble_24.get('picp80'),2)}, а ACE80 — {fmt_pct(ensemble_24.get('ace80'),2)}. Хотя это покрытие всё ещё заметно ниже идеального уровня, оркестр на данном горизонте даёт более интерпретируемую неопределённость, чем изолированные модели.

Diebold–Mariano test показывает, что на общей для LSTM и оркестра подвыборке из 154 ключей различие значимо в пользу оркестра: DM-stat = {fmt_num(dm_24_lstm_ens.get('dm_stat'),4)}, p-value = {fmt_num(dm_24_lstm_ens.get('p_value'),6)}. Для пары SARIMA–оркестр различие уже не достигает уровня значимости 0,05: p-value = {fmt_num(dm_24_sarima_ens.get('p_value'),6)}. Следовательно, на 24 часах статистически корректно трактовать SARIMA и оркестр как близкие по качеству варианты, при этом оркестр выигрывает по интерпретации неопределённости.
'''

table_35_rows = []
for label, row in [('SARIMA', sarima_24), ('LSTM', lstm_24), ('Оркестр', ensemble_24)]:
    table_35_rows.append([
        label,
        row.get('samples','—'),
        fmt_num(row.get('mae'),4),
        fmt_num(row.get('rmse'),4),
        fmt_pct(row.get('smape'),2),
        fmt_num(row.get('pinball_avg'),4),
        fmt_pct(row.get('picp80'),2),
        fmt_pct(row.get('ace80'),2),
    ])

p343 = f'''3.4.3 Результаты на горизонте 7 суток

На среднесрочном горизонте 7 суток лучшей по точечной ошибке стала SARIMA. Значения составили: MAE = {fmt_num(sarima_7.get('mae'),4)}, RMSE = {fmt_num(sarima_7.get('rmse'),4)}. Оркестр и LSTM на этом горизонте оказались практически сопоставимыми между собой по RMSE ({fmt_num(ensemble_7.get('rmse'),4)} и {fmt_num(lstm_7.get('rmse'),4)} соответственно), но уступили статистической ветви. Тем самым текущая конфигурация системы показывает, что на хорошо выраженной суточно-недельной структуре серверных метрик локальная SARIMA остаётся очень сильным baseline даже после существенного усиления нейросетевой ветви.

По вероятностным метрикам ситуация более неоднозначна. Наилучший `Pinball(avg)` на горизонте 7 суток показал оркестр: {fmt_num(ensemble_7.get('pinball_avg'),4)}. Это означает, что интегрированная модель лучше, чем отдельные ветви, согласует медианный прогноз и интервальные квантили. Однако и на этом горизонте все модели демонстрируют недопокрытие интервалов: PICP80 находится в диапазоне от {fmt_pct(lstm_7.get('picp80'),2)} до {fmt_pct(ensemble_7.get('picp80'),2)}, что существенно ниже целевого 80%.

Статистическая проверка даёт два важных результата. Во-первых, на общей подвыборке для LSTM и оркестра разница значима в пользу оркестра: DM-stat = {fmt_num(dm_7_lstm_ens.get('dm_stat'),4)}, p-value = {fmt_num(dm_7_lstm_ens.get('p_value'),6)}. Во-вторых, при сравнении SARIMA и оркестра различие также статистически значимо, но уже в пользу SARIMA: DM-stat = {fmt_num(dm_7_sarima_ens.get('dm_stat'),4)}, p-value = {fmt_num(dm_7_sarima_ens.get('p_value'),6)}. Следовательно, на 7 сутках оркестр уже полезен как слой вероятностной агрегации, но по центральной точности пока не превосходит статистическую модель.
'''

table_36_rows = []
for label, row in [('SARIMA', sarima_7), ('LSTM', lstm_7), ('Оркестр', ensemble_7)]:
    table_36_rows.append([
        label,
        row.get('samples','—'),
        fmt_num(row.get('mae'),4),
        fmt_num(row.get('rmse'),4),
        fmt_pct(row.get('smape'),2),
        fmt_num(row.get('pinball_avg'),4),
        fmt_pct(row.get('picp80'),2),
        fmt_pct(row.get('ace80'),2),
    ])

p344 = f'''3.4.4 Результаты на горизонте 30 суток в строгом режиме сравнения

Наиболее важным для диссертационной интерпретации является долгосрочный горизонт 30 суток, поскольку именно он позволяет судить о пригодности системы к раннему предупреждению неблагоприятных сценариев. В актуальном эксперименте лучшей по точечным метрикам оказалась LSTM: MAE = {fmt_num(lstm_30.get('mae'),4)}, RMSE = {fmt_num(lstm_30.get('rmse'),4)}. SARIMA заняла второе место (RMSE = {fmt_num(sarima_30.get('rmse'),4)}), а оркестр показал наибольшую точечную ошибку (RMSE = {fmt_num(ensemble_30.get('rmse'),4)}). Этот результат принципиально важен: он означает, что после последних доработок нейросетевая ветвь на длинном горизонте уже не проваливается в заведомо заниженный прогноз и в текущей конфигурации превосходит статистический baseline по центральной ошибке.

Однако по вероятностной интерпретации лидером становится не LSTM, а оркестр. Для него получены лучшие значения PICP80 = {fmt_pct(ensemble_30.get('picp80'),2)} и ACE80 = {fmt_pct(ensemble_30.get('ace80'),2)} среди трёх рассматриваемых моделей. Иными словами, ensemble по-прежнему уступает по точке, но лучше выражает неопределённость прогноза на длинном горизонте. Это полностью согласуется с текущей ролью оркестра в системе: он полезен как механизм объединения прогностических ветвей и построения более осторожного интервала, даже если не даёт минимальную точечную ошибку.

DM-test на 30 сутках зафиксировал статистически значимое превосходство SARIMA над оркестром: DM-stat = {fmt_num(dm_30_sarima_ens.get('dm_stat'),4)}, p-value ≈ 0. Для пары SARIMA–LSTM и LSTM–оркестр на общей подвыборке сравнение в текущем run не сформировано, что указывает на различия в доступности пересекающихся зрелых точек. Поэтому в тексте диссертации важно корректно формулировать вывод: на 30 сутках по фактическим агрегированным метрикам качества лучшая точечная точность принадлежит LSTM, а наиболее аккуратная интервальная калибровка — оркестру; при этом статистически подтверждённое превосходство над оркестром показала SARIMA на общей подвыборке пересечения.
'''

table_37_rows = []
for label, row in [('SARIMA', sarima_30), ('LSTM', lstm_30), ('Оркестр', ensemble_30)]:
    table_37_rows.append([
        label,
        row.get('samples','—'),
        fmt_num(row.get('mae'),4),
        fmt_num(row.get('rmse'),4),
        fmt_pct(row.get('smape'),2),
        fmt_num(row.get('pinball_avg'),4),
        fmt_pct(row.get('picp80'),2),
        fmt_pct(row.get('ace80'),2),
    ])

p345 = f'''3.4.5 Анализ влияния режима сезонности SARIMA

Отдельной задачей эксперимента было подтвердить количественно, насколько оправдан переход от прямой сезонной SARIMA к схеме `STL + возврат сезонности`, которая ранее была внедрена в baseline-ветвь системы. Актуальный run показывает, что эта доработка остаётся одной из наиболее результативных во всём проекте. На горизонте 24 часа новый режим дал RMSE {fmt_num(v24_stl.get('rmse'),4)} против {fmt_num(v24_seasonal.get('rmse'),4)} у режима «сезонность в модели». На горизонте 7 суток соотношение составляет {fmt_num(v7_stl.get('rmse'),4)} против {fmt_num(v7_seasonal.get('rmse'),4)}. На горизонте 30 суток выигрыш становится особенно большим: {fmt_num(v30_stl.get('rmse'),4)} против {fmt_num(v30_seasonal.get('rmse'),4)}.

Следовательно, улучшение SARIMA за счёт явного отделения и возврата сезонной компоненты является не локальным косметическим изменением, а устойчивым инженерным решением, которое улучшает прогноз на всех исследованных горизонтах. Именно этот результат позволяет уверенно использовать вариант `STL + возврат сезонности` как основной baseline для дальнейшего сравнения с LSTM и оркестром.
'''

table_38_rows = [
    ['24h', fmt_num(v24_stl.get('rmse'),4), fmt_num(v24_seasonal.get('rmse'),4), fmt_num(as_float(v24_seasonal.get('rmse'))/as_float(v24_stl.get('rmse')) if as_float(v24_stl.get('rmse')) else None, 2)],
    ['7d', fmt_num(v7_stl.get('rmse'),4), fmt_num(v7_seasonal.get('rmse'),4), fmt_num(as_float(v7_seasonal.get('rmse'))/as_float(v7_stl.get('rmse')) if as_float(v7_stl.get('rmse')) else None, 2)],
    ['30d', fmt_num(v30_stl.get('rmse'),4), fmt_num(v30_seasonal.get('rmse'),4), fmt_num(as_float(v30_seasonal.get('rmse'))/as_float(v30_stl.get('rmse')) if as_float(v30_stl.get('rmse')) else None, 2)],
]

p346 = f'''3.4.6 Экономический эффект и итоговая интерпретация эксперимента

Поскольку разработанная система является не просто предиктором, а СППР, в эксперимент включён и прикладной критерий полезности — экономический эффект от использования рекомендаций. В актуальном run по истории `DecisionRun` было найдено 23 валидных случая сравнения с baseline-действием `no_action`. Среднее значение `ΔR = R(без системы) - R(с системой)` составило {fmt_num(373003.70533752296,2)}, медиана — {fmt_num(189648.02420357367,2)}, а доля положительного эффекта достигла {fmt_pct(0.6956521739130435,2)}.

При разбиении по горизонтам видно, что на 24 часах положительный эффект наблюдается во всех случаях: среднее ΔR составило {fmt_num(delta_24.get('delta_r_mean'),2)} при доле ΔR > 0, равной {fmt_pct(delta_24.get('share_positive'),2)}. На горизонте 30 суток среднее ΔR ещё выше — {fmt_num(delta_30.get('delta_r_mean'),2)}, однако доля положительного эффекта снижается до {fmt_pct(delta_30.get('share_positive'),2)}. Это естественный результат: чем длиннее горизонт, тем выше неопределённость прогноза и тем осторожнее следует интерпретировать решения СППР.

В сумме проведённый эксперимент позволяет сделать три основных вывода. Во-первых, после последних улучшений система действительно демонстрирует качественно иные результаты, чем ранние версии: LSTM стала конкурентоспособной на длинном горизонте, а SARIMA в режиме `STL + возврат сезонности` подтвердило свою роль сильного baseline. Во-вторых, оркестр пока не является универсальным лидером по точечной ошибке, но остаётся наиболее полезным слоем интеграции неопределённости и устойчивым входом для модулей риска и СППР. В-третьих, даже в текущей конфигурации система показывает измеримый прикладной эффект по критерию ожидаемых потерь, что принципиально важно для диссертационной работы по системам поддержки принятия решений.
'''

table_39_rows = [
    ['24h', delta_24.get('samples','—'), fmt_num(delta_24.get('delta_r_mean'),2), fmt_num(delta_24.get('delta_r_median'),2), fmt_pct(delta_24.get('share_positive'),2)],
    ['30d', delta_30.get('samples','—'), fmt_num(delta_30.get('delta_r_mean'),2), fmt_num(delta_30.get('delta_r_median'),2), fmt_pct(delta_30.get('share_positive'),2)],
    ['Итого', '23', fmt_num(373003.70533752296,2), fmt_num(189648.02420357367,2), fmt_pct(0.6956521739130435,2)],
]

md_parts = [intro, p341, p342, p343, p344, p345, p346]
OUT_MD.write_text('\n\n'.join(md_parts), encoding='utf-8')


doc = Document()
style = doc.styles['Normal']
style.font.name = BODY_FONT
style.font.size = BODY_SIZE
style._element.rPr.rFonts.set(qn('w:ascii'), BODY_FONT)
style._element.rPr.rFonts.set(qn('w:hAnsi'), BODY_FONT)
style._element.rPr.rFonts.set(qn('w:cs'), BODY_FONT)
style.paragraph_format.first_line_indent = FIRST_LINE
style.paragraph_format.line_spacing = LINE_SPACING

add_heading(doc, '3.4 Вычислительный эксперимент на базе собранных метрик', level=1)
for text in intro.split('\n\n')[1:]:
    add_body(doc, text)

add_heading(doc, '3.4.1 Организация эксперимента и состав выборки', level=2)
for text in p341.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.4 — Параметры актуализированного экспериментального протокола', ['Параметр', 'Значение', 'Назначение'], table_34_rows, col_widths_cm=[4.2, 5.0, 7.0])
add_picture_with_caption(doc, RUN_DIR / 'evaluation_summary_page.png', 'Рисунок 3.5 — Сводная страница актуального evaluation-run', width_cm=15.2)

add_heading(doc, '3.4.2 Результаты на горизонте 24 часа', level=2)
for text in p342.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.5 — Качество прогноза на горизонте 24 часа', ['Модель', 'N', 'MAE', 'RMSE', 'sMAPE', 'Pinball(avg)', 'PICP80', 'ACE80'], table_35_rows, col_widths_cm=[2.8, 1.5, 2.1, 2.2, 2.3, 2.6, 2.1, 2.1])

add_heading(doc, '3.4.3 Результаты на горизонте 7 суток', level=2)
for text in p343.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.6 — Качество прогноза на горизонте 7 суток', ['Модель', 'N', 'MAE', 'RMSE', 'sMAPE', 'Pinball(avg)', 'PICP80', 'ACE80'], table_36_rows, col_widths_cm=[2.8, 1.5, 2.1, 2.2, 2.3, 2.6, 2.1, 2.1])

add_heading(doc, '3.4.4 Результаты на горизонте 30 суток в строгом режиме сравнения', level=2)
for text in p344.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.7 — Качество прогноза на горизонте 30 суток', ['Модель', 'N', 'MAE', 'RMSE', 'sMAPE', 'Pinball(avg)', 'PICP80', 'ACE80'], table_37_rows, col_widths_cm=[2.8, 1.5, 2.1, 2.2, 2.3, 2.6, 2.1, 2.1])
add_picture_with_caption(doc, RUN_DIR / 'chart_rmse_by_model_horizon.png', 'Рисунок 3.6 — Сравнение RMSE по моделям и горизонтам в актуальном запуске', width_cm=14.8)

add_heading(doc, '3.4.5 Анализ влияния режима сезонности SARIMA', level=2)
for text in p345.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.8 — Сравнение двух режимов сезонности SARIMA по RMSE', ['Горизонт', 'STL + возврат сезонности', 'Сезонность в модели', 'Во сколько раз хуже второй режим'], table_38_rows, col_widths_cm=[2.2, 4.2, 4.2, 4.6])
add_picture_with_caption(doc, RUN_DIR / 'chart_sarima_modes_rmse_by_horizon.png', 'Рисунок 3.7 — Влияние режима сезонности SARIMA на качество прогноза', width_cm=14.8)

add_heading(doc, '3.4.6 Экономический эффект и итоговая интерпретация эксперимента', level=2)
for text in p346.split('\n\n')[1:]:
    add_body(doc, text)
add_table(doc, 'Таблица 3.9 — Экономический эффект использования СППР по данным актуального evaluation-run', ['Горизонт', 'N', 'ΔR среднее', 'ΔR медиана', 'Доля ΔR > 0'], table_39_rows, col_widths_cm=[2.2, 1.5, 3.5, 3.5, 3.0])
add_picture_with_caption(doc, RUN_DIR / 'chart_delta_r_by_horizon.png', 'Рисунок 3.8 — Экономический эффект по горизонтам в актуальном запуске', width_cm=14.8)

doc.save(str(OUT_DOCX))
print(OUT_MD)
print(OUT_DOCX)
