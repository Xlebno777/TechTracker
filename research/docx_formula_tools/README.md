# DOCX Formula Tools

Утилиты для вставки и восстановления формул в `.docx` без `python-docx` и LibreOffice.

Текущий сценарий:
- берёт Word-совместимые OMML-формулы из шаблонного документа;
- вставляет их в целевой документ по известным позициям абзацев;
- при необходимости обновляет соседние поясняющие абзацы, чтобы текст не ссылался на пропавшие inline-символы.

## Запуск

```bash
python research/docx_formula_tools/restore_article_formulas.py \
  --source research/dissertation/article.docx \
  --target research/dissertation/article_vak.docx
```

## Что восстанавливается
- формула SARIMA;
- формулы LSTM;
- формула ансамблирования SARIMA + LSTM;
- формулы RMSE и MAE.
