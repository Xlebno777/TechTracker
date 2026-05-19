from __future__ import annotations

import copy
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'xml': 'http://www.w3.org/XML/1998/namespace',
}
ET.register_namespace('w', NS['w'])
ET.register_namespace('xml', NS['xml'])

TEXT_FIXES = {
    5: 'ВВЕДЕНИЕ Современная серверная инфраструктура характеризуется высокой плотностью сервисов и жесткими требованиями к непрерывности работы. В этих условиях для ИТ-службы особую значимость приобретает переход от реактивного мониторинга к упреждающему анализу, основанному на прогнозировании поведения эксплуатационных метрик во времени [4].',
    11: '1. Линейное прогнозирование сезонных метрик (SARIMA). Для метрик, обладающих строгой цикличностью, используется сезонная интегрированная модель авторегрессии и скользящего среднего SARIMA(p, d, q) × (P, D, Q)s [2; 4]. Она позволяет описывать сезонный профиль нагрузки и переносить его на будущие интервалы при умеренных вычислительных затратах. Математически модель задаётся следующим выражением:',
    14: '2. Нелинейное прогнозирование метрик со сложной динамикой (LSTM). Для метрик, в которых одновременно проявляются сезонность, локальный тренд и нелинейные зависимости, применяется нейросетевая модель типа Long Short-Term Memory (LSTM) [3].',
    15: 'Архитектура ячейки LSTM решает проблему затухающего градиента за счёт системы вентилей, что позволяет модели учитывать как краткосрочные, так и долгосрочные зависимости. В работе используется стандартное представление ячейки LSTM в виде следующих уравнений [3]:',
    17: '3. Механизм адаптивной интеграции. Итоговый прогноз на горизонт h формируется как взвешенная комбинация статистической и нейросетевой моделей [1; 6; 7]:',
    19: 'Коэффициент α пересчитывается на каждом временном окне на основе исторического качества моделей: чем меньше ошибка модели на валидационной выборке, тем больший вес она получает в ансамбле. За счёт этого статистическая ветвь доминирует на выраженно сезонных рядах, а нейросетевая — на рядах со сложной нелинейной динамикой [1; 6; 7].',
    22: 'Качество прогнозов оценивалось раздельно по каждой метрике. Это принципиально важно, поскольку агрегирование в один показатель рядов с единицами %, °C, KB/s и ms приводит к методически некорректной интерпретации итоговой ошибки [5].',
    30: 'Следует отметить, что преимущество ансамбля проявляется не одинаково для всех наблюдаемых величин. Для отдельных сетевых метрик лучшей может оказаться статистическая модель, тогда как для нагрузочных и температурных признаков итоговый ансамбль обеспечивает более устойчивое качество. Поэтому в практической системе оценка выполняется по каждой метрике отдельно, а не по смешанному интегральному показателю [5].',
    32: 'Для количественной оценки результатов использовались метрики средней абсолютной ошибки (MAE) и среднеквадратической ошибки (RMSE) [5]:',
}

REFERENCES = [
    '[1] Bates J.M., Granger C.W.J. The Combination of Forecasts // Operational Research Quarterly. 1969. Vol. 20, No. 4. P. 451–468. DOI: 10.1057/jors.1969.103.',
    '[2] Box G.E.P., Jenkins G.M., Reinsel G.C., Ljung G.M. Time Series Analysis: Forecasting and Control. 5th ed. Hoboken: John Wiley & Sons, 2015. 712 p.',
    '[3] Hochreiter S., Schmidhuber J. Long Short-Term Memory // Neural Computation. 1997. Vol. 9, No. 8. P. 1735–1780. DOI: 10.1162/neco.1997.9.8.1735.',
    '[4] Hyndman R.J., Athanasopoulos G. Forecasting: Principles and Practice. 3rd ed. Melbourne: OTexts, 2021. URL: https://otexts.com/fpp3/ (accessed: 09.04.2026).',
    '[5] Hyndman R.J., Koehler A.B. Another look at measures of forecast accuracy // International Journal of Forecasting. 2006. Vol. 22, No. 4. P. 679–688. DOI: 10.1016/j.ijforecast.2006.03.001.',
    '[6] Khashei M., Bijari M. A novel hybridization of artificial neural networks and ARIMA models for time series forecasting // Applied Soft Computing. 2011. Vol. 11, No. 2. P. 2664–2675. DOI: 10.1016/j.asoc.2010.10.015.',
    '[7] Zhang G.P. Time series forecasting using a hybrid ARIMA and neural network model // Neurocomputing. 2003. Vol. 50. P. 159–175. DOI: 10.1016/S0925-2312(01)00702-0.',
]


def rebuild_docx_from_tree(source_docx: Path, root: ET.Element, target_docx: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(source_docx, 'r') as zf:
            zf.extractall(td_path)
        doc_path = td_path / 'word' / 'document.xml'
        ET.ElementTree(root).write(doc_path, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(target_docx, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            for file in sorted(td_path.rglob('*')):
                if file.is_file():
                    out.write(file, file.relative_to(td_path))


def clear_and_set_text(paragraph: ET.Element, text: str) -> None:
    ppr = paragraph.find(f'{{{NS["w"]}}}pPr')
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    run = ET.Element(f'{{{NS["w"]}}}r')
    text_node = ET.SubElement(run, f'{{{NS["w"]}}}t')
    if text[:1].isspace() or text[-1:].isspace():
        text_node.set(f'{{{NS["xml"]}}}space', 'preserve')
    text_node.text = text
    paragraph.append(run)


def main() -> None:
    target = Path('research/dissertation/article_vak.docx')
    root = ET.fromstring(zipfile.ZipFile(target).read('word/document.xml'))
    body = root.find(f'{{{NS["w"]}}}body')
    if body is None:
        raise RuntimeError('No body found')

    children = list(body)

    for idx, text in TEXT_FIXES.items():
        node = children[idx - 1]
        clear_and_set_text(node, text)

    # References start after heading paragraph 41 in current doc.
    ref_heading_idx = 41
    first_ref_idx = ref_heading_idx + 1

    # choose template paragraph from first existing reference or previous paragraph
    template_para = copy.deepcopy(children[first_ref_idx - 1])

    # remove existing reference paragraphs until the next non-reference paragraph / section end
    remove_nodes = []
    cur_children = list(body)
    i = first_ref_idx - 1
    while i < len(cur_children):
        node = cur_children[i]
        if node.tag != f'{{{NS["w"]}}}p':
            break
        text = ''.join(t.text or '' for t in node.findall('.//w:t', NS)).strip()
        # remove old refs and trailing blanks after refs heading
        if i == first_ref_idx - 1 or text.startswith('[') or text == '':
            remove_nodes.append(node)
            i += 1
            continue
        break
    for node in remove_nodes:
        body.remove(node)

    insert_pos = list(body).index(list(body)[ref_heading_idx - 1]) + 1
    for ref in REFERENCES:
        para = copy.deepcopy(template_para)
        clear_and_set_text(para, ref)
        body.insert(insert_pos, para)
        insert_pos += 1

    rebuild_docx_from_tree(target, root, target)

    with zipfile.ZipFile(target) as zf:
        xml = zf.read('word/document.xml').decode('utf-8', 'ignore')
    print('Updated', target)
    print('Bracket citations count:', xml.count('['))
    print('DOI count:', xml.count('DOI:'))


if __name__ == '__main__':
    main()
