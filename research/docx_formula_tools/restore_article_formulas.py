from __future__ import annotations

import argparse
import copy
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
    'xml': 'http://www.w3.org/XML/1998/namespace',
}

ET.register_namespace('w', NS['w'])
ET.register_namespace('xml', NS['xml'])

# body paragraph indexes in source -> body paragraph indexes in target
FORMULA_PARAGRAPH_MAP = {
    12: 12,  # SARIMA display formula
    17: 17,  # LSTM gate formula line 1
    18: 18,  # LSTM gate formula line 2
    21: 21,  # ensemble formula
    36: 33,  # RMSE/MAE formula
}

TEXT_FIXES = {
    5: 'ВВЕДЕНИЕ Современная серверная инфраструктура характеризуется высокой плотностью сервисов и жесткими требованиями к непрерывности работы. В этих условиях для ИТ-службы особую значимость приобретает переход от реактивного мониторинга к упреждающему анализу, основанному на прогнозировании поведения эксплуатационных метрик во времени [4].',
    11: '1. Линейное прогнозирование сезонных метрик (SARIMA). Для метрик, обладающих строгой цикличностью, используется сезонная интегрированная модель авторегрессии и скользящего среднего SARIMA(p, d, q) × (P, D, Q)s [2; 4]. Она позволяет описывать сезонный профиль нагрузки и переносить его на будущие интервалы при умеренных вычислительных затратах. Математически модель задаётся следующим выражением:',
    13: 'где Xt — текущее значение метрики; B — оператор обратного сдвига; s — период сезонности; φ и θ — полиномы авторегрессии и скользящего среднего; d и D — порядки обычного и сезонного интегрирования; εt — белый шум.',
    14: '2. Нелинейное прогнозирование метрик со сложной динамикой (LSTM). Для метрик, в которых одновременно проявляются сезонность, локальный тренд и нелинейные зависимости, применяется нейросетевая модель типа Long Short-Term Memory (LSTM) [3].',
    16: 'Архитектура ячейки LSTM решает проблему затухающего градиента за счёт системы вентилей, что позволяет модели учитывать как краткосрочные, так и долгосрочные зависимости. В работе используется стандартное представление ячейки LSTM в виде следующих уравнений [3]:',
    19: 'где ft, it и ot — вентили забывания, входа и выхода соответственно; Ct — состояние памяти ячейки; ht — скрытое состояние; σ(·) — сигмоидная функция активации.',
    20: '3. Механизм адаптивной интеграции. Итоговый прогноз на горизонт h формируется как взвешенная комбинация статистической и нейросетевой моделей [1; 6; 7]:',
    22: 'где X^(SARIMA)_(t+h) — прогноз модели SARIMA; X^(LSTM)_(t+h) — прогноз модели LSTM; α — динамический весовой коэффициент ансамбля.',
    23: 'Коэффициент α пересчитывается на каждом временном окне на основе исторического качества моделей: чем меньше ошибка модели на валидационной выборке, тем больший вес она получает в ансамбле. За счёт этого статистическая ветвь доминирует на выраженно сезонных рядах, а нейросетевая — на рядах со сложной нелинейной динамикой [1; 6; 7].',
    30: 'Следует отметить, что преимущество ансамбля проявляется не одинаково для всех наблюдаемых величин. Для отдельных сетевых метрик лучшей может оказаться статистическая модель, тогда как для нагрузочных и температурных признаков итоговый ансамбль обеспечивает более устойчивое качество. Поэтому в практической системе оценка выполняется по каждой метрике отдельно, а не по смешанному интегральному показателю [5].',
    32: 'Для количественной оценки результатов использовались метрики средней абсолютной ошибки (MAE) и среднеквадратической ошибки (RMSE) [5]:',
}


def paragraph_text(node: ET.Element) -> str:
    return ''.join(t.text or '' for t in node.findall('.//w:t', NS)).strip()


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


def load_body(docx_path: Path) -> ET.Element:
    with zipfile.ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read('word/document.xml'))
    body = root.find('w:body', NS)
    if body is None:
        raise RuntimeError(f'No document body in {docx_path}')
    return body


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    args = parser.parse_args()

    source_root = ET.fromstring(zipfile.ZipFile(args.source).read('word/document.xml'))
    target_root = ET.fromstring(zipfile.ZipFile(args.target).read('word/document.xml'))

    source_body = source_root.find('w:body', NS)
    target_body = target_root.find('w:body', NS)
    if source_body is None or target_body is None:
        raise RuntimeError('Failed to load source or target body')

    source_children = list(source_body)
    target_children = list(target_body)

    for src_idx, dst_idx in FORMULA_PARAGRAPH_MAP.items():
        src_node = copy.deepcopy(source_children[src_idx - 1])
        old_node = target_children[dst_idx - 1]
        target_body.remove(old_node)
        target_body.insert(dst_idx - 1, src_node)
        target_children = list(target_body)

    for idx, text in TEXT_FIXES.items():
        node = list(target_body)[idx - 1]
        clear_and_set_text(node, text)

    rebuild_docx_from_tree(args.target, target_root, args.target)

    xml = zipfile.ZipFile(args.target).read('word/document.xml').decode('utf-8', 'ignore')
    print(f'Updated: {args.target}')
    print(f'OMML tokens: {xml.count("oMath")}')


if __name__ == '__main__':
    main()
