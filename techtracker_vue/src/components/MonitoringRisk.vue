<template>
  <div class="risk-page p-4">
    <Toast />
    <Dialog
      v-model:visible="riskErrorDialogVisible"
      modal
      header="Расчет риска остановлен"
      :style="{ width: 'min(92vw, 38rem)' }"
      :closable="true"
    >
      <div class="risk-error-dialog">
        <p class="risk-error-text">{{ riskErrorDialogMessage }}</p>
      </div>
      <template #footer>
        <Button label="ОК" autofocus @click="riskErrorDialogVisible = false" />
      </template>
    </Dialog>

    <PageHeader
      title="Оценка риска отказа"
      :refreshable="true"
      :loading="loadingDevices || loadingRisk"
      help-title="Гайд: оценка риска отказа"
      help-intro="Страница оценивает риск отказа по прогнозам метрик и по динамике состояний S0/S1/S2."
      :help-steps="riskHelpSteps"
      help-note="Для регулярной работы используйте пресет «Сбалансированный», для инцидентов — «Оперативный»."
      @refresh="refreshAll"
    />

    <FilterPanel
      class="mb-3"
      title="Параметры расчета"
    >
      <template #actions>
        <ModeSwitch
          v-model="riskUiMode"
          aria-label="Режим параметров риска"
          :hidden-items="riskBasicHidden"
          :show-basic-hint="false"
        />
      </template>
      <div class="filters-grid">
        <div class="field-block">
          <label>Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            :loading="loadingDevices"
            class="w-full"
            placeholder="Выберите устройство"
          />
        </div>
        <div class="field-block">
          <label>Горизонт</label>
          <Dropdown
            v-model="selectedHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Источник прогноза</label>
          <Dropdown
            v-model="preferredModelKind"
            :options="modelSourceOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Персонализация порогов</label>
          <div class="switch-inline">
            <InputSwitch v-model="personalizedThresholds" />
            <span>{{ personalizedThresholds ? 'Включена' : 'Отключена' }}</span>
          </div>
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>История порогов (дней)</label>
          <InputNumber v-model="thresholdLookbackDays" :min="7" :max="720" class="w-full" />
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>Марков: история (дней)</label>
          <InputNumber v-model="markovLookbackDays" :min="7" :max="720" class="w-full" />
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>Марков: сглаживание</label>
          <InputNumber
            v-model="markovSmoothing"
            :min="0.001"
            :max="10"
            :step="0.1"
            mode="decimal"
            :minFractionDigits="3"
            :maxFractionDigits="3"
            class="w-full"
          />
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>Вес профиля типа сервера</label>
          <InputNumber
            v-model="typeBlend"
            :min="0"
            :max="5"
            :step="0.05"
            mode="decimal"
            :minFractionDigits="2"
            :maxFractionDigits="2"
            class="w-full"
          />
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>Вес Маркова (w_markov)</label>
          <InputNumber
            v-model="overallWeightMarkov"
            :min="0"
            :max="1"
            :step="0.05"
            mode="decimal"
            :minFractionDigits="2"
            :maxFractionDigits="2"
            class="w-full"
          />
        </div>
        <div v-if="isRiskExpert" class="field-block">
          <label>Глубина истории (запусков)</label>
          <InputNumber v-model="historyLimit" :min="3" :max="64" class="w-full" />
        </div>
      </div>

      <div class="actions-row mt-3">
        <Button
          icon="pi pi-play"
          label="Рассчитать риск"
          :loading="loadingRisk"
          :disabled="!selectedDeviceId || loadingDevices"
          @click="runRiskEvaluation"
        />
      </div>
    </FilterPanel>

    <div v-if="selectedResult" class="grid gap-3 mb-3 summary-grid">
      <div class="card p-3 risk-explainer-card summary-grid-span">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">Что такое риск в системе</h4>
            <InfoHint
              title="Как понимать риск"
              :lines="[
                'Риск на этой странице — это интегральный индекс угрозы отказа на выбранном горизонте, приведённый к шкале 0–100%.',
                'Это не абсолютная гарантия поломки, а нормированная оценка того, насколько прогнозы и модель состояний указывают на опасную динамику.',
                'Сначала система считает риск по отдельным метрикам, затем вероятность деградации до S2 по модели состояний.',
                'После этого оба сигнала смешиваются в общий риск. Чем выше процент, тем хуже прогноз для выбранного горизонта.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">Все значения внутри сервиса хранятся в шкале 0..1, а в интерфейсе показываются как 0..100%.</span>
        </div>
        <div class="formula-grid mt-3">
          <div class="formula-chip">
            <strong>1. Риск метрики</strong>
            <span>Для обычных метрик система смотрит, насколько верхняя граница прогноза p90 подходит к порогу. Для изнашиваемых компонентов используется условная вероятность отказа по Вейбуллу.</span>
          </div>
          <div class="formula-chip">
            <strong>2. Агрегат метрик</strong>
            <span>Риск по метрикам собирается как 0.55 × средневзвешенный риск + 0.45 × максимальный риск. Так система учитывает и общий фон, и самый опасный сигнал.</span>
          </div>
          <div class="formula-chip">
            <strong>3. Марковский риск</strong>
            <span>Марковский риск — это вероятность того, что система перейдёт в S2 к концу горизонта, если динамика S0/S1/S2 сохранится.</span>
          </div>
          <div class="formula-chip">
            <strong>4. Общий риск</strong>
            <span>{{ overallRiskFormulaText }}</span>
          </div>
        </div>
      </div>
      <div class="card summary-card">
        <div class="summary-label-row">
          <span class="summary-label">Общий риск отказа</span>
          <InfoHint
            title="Общий риск отказа"
            :lines="[
              'Это главный итоговый показатель страницы.',
              'Он объединяет два сигнала: риск по прогнозным метрикам и вероятность состояния S2.',
              overallRiskFormulaText,
              'Используйте его как интегральную оценку угрозы отказа на выбранном горизонте.'
            ]"
            placement="top-left"
          />
        </div>
        <div class="summary-main">
          <strong>{{ formatPercent(selectedResult.overall_risk) }}</strong>
          <Tag :value="riskLabel(selectedResult.overall_risk)" :severity="riskSeverity(selectedResult.overall_risk)" />
        </div>
      </div>
      <div class="card summary-card">
        <div class="summary-label-row">
          <span class="summary-label">Надежность</span>
          <InfoHint
            title="Надежность"
            :lines="[
              'Это обратная величина к риску.',
              'Формула: reliability = 1 - overall_risk.',
              'Если общий риск растёт, надёжность падает.'
            ]"
            placement="top-left"
          />
        </div>
        <div class="summary-main">
          <strong>{{ formatPercent(selectedResult.reliability) }}</strong>
          <span class="text-500 text-sm">1 - риск отказа</span>
        </div>
      </div>
      <div class="card summary-card">
        <div class="summary-label-row">
          <span class="summary-label">Риск метрик (агрегат)</span>
          <InfoHint
            title="Риск метрик"
            :lines="[
              'Это риск, собранный только из прогнозных метрик без учёта Маркова.',
              'Для каждой метрики строится локальный риск, затем они агрегируются.',
              'Именно этот показатель отвечает на вопрос: насколько плохи сами прогнозные метрики.'
            ]"
            placement="top-left"
          />
        </div>
        <div class="summary-main">
          <strong>{{ formatPercent(selectedResult.metric_aggregate_risk) }}</strong>
          <span class="text-500 text-sm">Вейбулл + превышение порогов</span>
        </div>
      </div>
      <div class="card summary-card">
        <div class="summary-label-row">
          <span class="summary-label">Марковский риск S2</span>
          <InfoHint
            title="Марковский риск S2"
            :lines="[
              'Это вероятность оказаться в состоянии S2 на выбранном горизонте.',
              'S2 трактуется как предаварийное состояние системы.',
              'Показатель строится из текущего распределения S0/S1/S2 и матрицы переходов Маркова.'
            ]"
            placement="top-left"
          />
        </div>
        <div class="summary-main">
          <strong>{{ formatPercent(selectedResult.markov_projected_p_s2) }}</strong>
          <span class="text-500 text-sm">Прогноз состояния на {{ selectedResult.horizon }}</span>
        </div>
      </div>
    </div>

    <div v-if="selectedResult" class="card p-3 mb-3">
      <div class="state-head">
        <div class="title-with-hint">
          <h4 class="m-0">Состояния S0/S1/S2</h4>
          <InfoHint
            title="Что значат S0, S1, S2"
            :lines="[
              'S0 — нормальная работа.',
              'S1 — деградация: есть тревожные признаки, но система ещё не предаварийная.',
              'S2 — предаварийное состояние, где риск уже требует реакции.',
              'Текущее состояние — это оценка сейчас, прогноз состояния — оценка на выбранный горизонт.'
            ]"
          />
        </div>
        <span class="text-500 text-sm">
          Модель: {{ modelKindLabel(selectedResult.model_kind_used) }}
          <template v-if="selectedResult.run_id_used"> • Run #{{ selectedResult.run_id_used }}</template>
        </span>
      </div>
      <div class="states-grid mt-3">
        <div class="state-box">
          <div class="state-box-title">Текущее состояние (π_t)</div>
          <div class="state-lines">
            <div v-for="s in stateRows(selectedResult.current_state)" :key="`curr-${s.key}`" class="state-line">
              <span>{{ s.label }}</span>
              <span>{{ formatPercent(s.value) }}</span>
            </div>
          </div>
        </div>
        <div class="state-box">
          <div class="state-box-title">Прогноз состояния (π_t+k)</div>
          <div class="state-lines">
            <div v-for="s in stateRows(selectedResult.projected_state)" :key="`proj-${s.key}`" class="state-line">
              <span>{{ s.label }}</span>
              <span>{{ formatPercent(s.value) }}</span>
            </div>
          </div>
        </div>
        <div class="state-box">
          <div class="state-box-title state-box-title--with-hint">
            <span>Матрица переходов Маркова (heatmap)</span>
            <InfoHint
              title="Как читать матрицу переходов"
              :lines="[
                'Строка показывает, из какого состояния стартуем.',
                'Столбец показывает, в какое состояние перейдём за один шаг модели.',
                'Чем выше вероятность S1→S2 или S2→S2, тем опаснее траектория.',
                'Heatmap нужен для понимания динамики деградации, а не только текущего уровня риска.'
              ]"
              placement="top-left"
            />
          </div>
          <div class="heatmap-wrap">
            <div class="heatmap-header"></div>
            <div v-for="col in markovLabels" :key="`h-col-${col}`" class="heatmap-axis">{{ col }}</div>
            <template v-for="(row, rowIdx) in selectedResult.transition_matrix || []" :key="`h-row-${rowIdx}`">
              <div class="heatmap-axis">{{ markovLabels[rowIdx] }}</div>
              <div
                v-for="(value, colIdx) in row"
                :key="`h-cell-${rowIdx}-${colIdx}`"
                class="heatmap-cell"
                :style="heatmapCellStyle(value)"
                :title="`${markovLabels[rowIdx]} -> ${markovLabels[colIdx]}: ${formatPercent(value)}`"
              >
                {{ formatPercent(value) }}
              </div>
            </template>
          </div>
          <div class="matrix-meta text-500">
            Переходов устройства: {{ selectedResult.transition_meta?.device_transitions ?? 0 }},
            класса: {{ selectedResult.transition_meta?.peer_transitions ?? 0 }},
            шаг модели: {{ formatStepLabel(selectedResult.markov_step_sec) }},
            k: {{ selectedResult.steps }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="riskTimelineLabels.length" class="card p-3 mb-3">
      <div class="chart-head">
        <div>
          <div class="title-with-hint">
            <h4 class="m-0">История риска (последние {{ historyLimit }} запусков)</h4>
            <InfoHint
              title="Как читать историю риска"
              :lines="[
                'Зелёная линия — общий риск по каждому запуску.',
                'Красная пунктирная линия — вероятность S2 по Маркову.',
                'Если обе линии растут, система стабильно движется к опасному состоянию.',
                'Если растёт только общий риск, проблема чаще в отдельных метриках, а не в устойчивой деградации состояний.'
              ]"
            />
          </div>
          <p class="text-500 m-0">
            Показывает, как менялись общий риск и вероятность S2 по последним расчетам для источника
            {{ historySourceLabel }}.
          </p>
        </div>
      </div>
      <div class="chart-wrap mt-2">
        <Chart type="line" :data="timelineChartData" :options="timelineChartOptions" class="timeline-chart" />
      </div>
    </div>

    <div v-if="selectedResult" class="card p-3 mb-3">
      <div class="chart-head">
        <div>
          <div class="title-with-hint">
            <h4 class="m-0">Риск по метрикам</h4>
            <InfoHint
              title="Как читать риск по метрикам"
              :lines="[
                'Каждый столбец — это риск отдельной метрики на выбранном горизонте.',
                'Чем длиннее столбец, тем сильнее метрика тянет систему к риску.',
                'Обычные метрики считаются через отношение p90 к порогу, wear-метрики — через Вейбулла.',
                'В расчёт берутся только метрики, реально влияющие на модель состояния или wear-риск.'
              ]"
            />
          </div>
          <p class="text-500 m-0">
            Топ рисков на горизонте {{ selectedResult.horizon }}. В расчете учитываются текущие прогнозные точки
            и история состояний метрик из прошлых прогнозных запусков.
          </p>
        </div>
      </div>
      <div v-if="metricChartData.datasets[0].data.length" class="chart-wrap mt-2">
        <Chart type="bar" :data="metricChartData" :options="metricChartOptions" class="risk-chart" />
      </div>
      <EmptyStateCard
        v-else
        class="mt-2"
        icon="pi pi-chart-bar"
        title="Недостаточно данных для графика"
        description="Проверьте наличие прогнозных точек на выбранном горизонте и источник прогноза."
      />
    </div>

    <div v-if="selectedResult" class="card p-3">
      <div class="table-head">
        <div class="title-with-hint">
          <h4 class="m-0">Детализация риска по метрикам</h4>
          <InfoHint
            title="Как читать детализацию"
            :lines="[
              'Риск — итоговый риск конкретной метрики после учёта прогноза и истории состояний.',
              'Вклад — насколько эта метрика влияет на общий агрегат внутри группы метрик.',
              'База — риск только по текущему прогнозу; если итог выше базы, его усилила история состояний.',
              'В аналитическом режиме можно раскрыть строку и увидеть формулу и входные параметры.'
            ]"
          />
        </div>
        <span class="text-500 text-sm">
          Пресет: {{ activeRiskPresetLabel }} • Метрик: {{ filteredMetricRows.length }} / {{ metricRows.length }}
        </span>
      </div>

      <div class="risk-legend mt-2 mb-2">
        <span class="legend-title">Легенда риска:</span>
        <span class="legend-chip legend-low">Низкий: &lt; 40%</span>
        <span class="legend-chip legend-medium">Средний: 40%-65%</span>
        <span class="legend-chip legend-high">Высокий: 65%-85%</span>
        <span class="legend-chip legend-critical">Критический: &gt;= 85%</span>
      </div>

      <div class="table-toolbar mb-2">
        <TablePresetBar
          v-model="riskTablePreset"
          title="Пресет таблицы"
          aria-label="Пресеты таблицы риска"
          :presets="riskTablePresets"
        />
      </div>
      <DataTable
        v-model:expandedRows="expandedMetricRows"
        :value="filteredMetricRows"
        dataKey="metric_code"
        :rowClass="metricRowClass"
        scrollable
        scrollHeight="28rem"
        stripedRows
        responsiveLayout="scroll"
      >
        <template #empty>
          <EmptyStateCard
            icon="pi pi-list"
            title="Нет строк риска"
            description="Для выбранного пресета и горизонта метрики не найдены."
          />
        </template>
        <Column v-if="showRiskExpander" expander style="width: 3rem" />
        <Column field="metric_code" header="Метрика">
          <template #body="{ data }">
            <div class="metric-cell">
              <div class="metric-title">{{ metricLabel(data.metric_code) }}</div>
              <div v-if="showRiskDetailColumns" class="metric-meta">
                <Tag
                  v-if="data.supplemented_from_state_history"
                  value="Из истории состояний"
                  severity="info"
                />
                <Tag
                  v-else-if="Number(data.state_history_signal || 0) > 0"
                  value="История состояний учтена"
                  severity="secondary"
                />
                <span v-if="data.state_history_last_model_kind" class="metric-meta-text">
                  Последний сигнал: {{ modelKindLabel(data.state_history_last_model_kind) }}
                </span>
              </div>
            </div>
          </template>
        </Column>
        <Column field="method" header="Метод">
          <template #body="{ data }">
            <Tag :value="methodLabel(data.method)" :severity="data.method === 'weibull' ? 'info' : 'secondary'" />
          </template>
        </Column>
        <Column v-if="showRiskDetailColumns" header="Текущее значение">
          <template #body="{ data }">
            {{ formatMetricValue(data.metric_code, data.current_value) }}
          </template>
        </Column>
        <Column v-if="showRiskDetailColumns" header="Прогноз p90">
          <template #body="{ data }">
            {{ formatMetricValue(data.metric_code, data.forecast?.p90) }}
          </template>
        </Column>
        <Column v-if="showRiskDetailColumns" header="Параметры">
          <template #body="{ data }">
            <div v-if="data.method === 'weibull'">
              eta={{ formatNum(data.details?.eta, 2) }}, beta={{ formatNum(data.details?.beta, 2) }}
            </div>
            <div v-else>
              порог={{ formatMetricValue(data.metric_code, data.threshold) }}
            </div>
          </template>
        </Column>
        <Column v-if="showRiskDetailColumns">
          <template #header>
            <div class="column-header-with-hint">
              <span>База</span>
              <InfoHint
                title="База"
                :lines="[
                  'База — риск метрики только по текущему прогнозу, без усиления от истории состояний.',
                  'Если итоговый риск выше базы, значит сигнал был усилен накопленной историей проблем по этой метрике.',
                  'Это удобно для сравнения «что даёт сам прогноз» и «что добавляет история».'
                ]"
                placement="top-left"
              />
            </div>
          </template>
          <template #body="{ data }">
            <div class="base-risk-cell">
              <span>{{ formatPercent(data.base_risk) }}</span>
              <span
                v-if="Number(data.base_risk || 0) !== Number(data.risk || 0)"
                class="risk-subline"
              >
                итог {{ formatPercent(data.risk) }}
              </span>
            </div>
          </template>
        </Column>
        <Column v-if="showRiskDetailColumns">
          <template #header>
            <div class="column-header-with-hint">
              <span>История состояний</span>
              <InfoHint
                title="История состояний"
                :lines="[
                  'Показывает накопленный сигнал этой метрики по прошлым оценкам состояния.',
                  'Чем выше значение, тем чаще метрика уже проявлялась как важная для деградации или риска.',
                  'Если колонка пустая, значит история по этой метрике либо отсутствует, либо пока не усиливает риск.'
                ]"
                placement="top-left"
              />
            </div>
          </template>
          <template #body="{ data }">
            <div class="state-history-cell">
              <span v-if="Number(data.state_history_signal || 0) > 0">
                {{ formatPercent(data.state_history_signal) }}
              </span>
              <span v-else>—</span>
              <span
                v-if="Number(data.state_history_signal || 0) > 0 && data.state_history_count"
                class="risk-subline"
              >
                {{ data.state_history_count }} запуск(ов)
              </span>
              <span
                v-if="Number(data.state_history_signal || 0) > 0 && data.state_history_last_model_kind"
                class="risk-subline"
              >
                {{ modelKindLabel(data.state_history_last_model_kind) }}
              </span>
            </div>
          </template>
        </Column>
        <Column>
          <template #header>
            <div class="column-header-with-hint">
              <span>Риск</span>
              <InfoHint
                title="Риск"
                :lines="[
                  'Итоговый риск конкретной метрики после учёта прогноза и, при наличии, истории состояний.',
                  'Именно это значение участвует в агрегировании общего риска по метрикам.',
                  'Чем ближе к 100%, тем опаснее вклад метрики на выбранном горизонте.'
                ]"
                placement="top-left"
              />
            </div>
          </template>
          <template #body="{ data }">
            <div class="risk-cell">
              <Tag :value="formatPercent(data.risk)" :severity="riskSeverity(data.risk)" />
              <span
                v-if="showRiskDetailColumns && Number(data.base_risk || 0) !== Number(data.risk || 0)"
                class="risk-subline"
              >
                усилен относительно базы
              </span>
            </div>
          </template>
        </Column>
        <Column>
          <template #header>
            <div class="column-header-with-hint">
              <span>Вклад</span>
              <InfoHint
                title="Вклад"
                :lines="[
                  'Вклад показывает долю этой метрики в агрегированном риске по метрикам.',
                  'Это относительный вес внутри текущего набора метрик, а не абсолютная вероятность отказа.',
                  'Если вклад высокий, именно эта метрика сильнее других формирует итоговый риск.'
                ]"
                placement="top-left"
              />
            </div>
          </template>
          <template #body="{ data }">
            {{ formatPercent(data.contribution) }}
          </template>
        </Column>
        <template v-if="showRiskExpander" #expansion="{ data }">
          <div class="expansion-box">
            <div class="expansion-title">Как считалось</div>
            <div class="expansion-line">
              Формула: <code>{{ data.formula || formulaByMethod(data.method) }}</code>
            </div>
            <div class="expansion-line">
              Входные данные:
              <code>{{ formulaInputsText(data) }}</code>
            </div>
            <div class="expansion-line" v-if="Number(data.state_history_signal || 0) > 0">
              История состояний:
              <strong>{{ formatPercent(data.state_history_signal) }}</strong>
              <template v-if="data.state_history_count"> • запусков: {{ data.state_history_count }}</template>
              <template v-if="data.state_history_last_model_kind">
                • последний источник: {{ modelKindLabel(data.state_history_last_model_kind) }}
              </template>
            </div>
            <div class="expansion-line" v-if="data.supplemented_from_state_history">
              Эта строка была добавлена не из текущего run, а из истории состояний метрик по прогнозу.
            </div>
            <div class="expansion-line">
              Итоговый риск метрики: <strong>{{ formatPercent(data.risk) }}</strong>
            </div>
          </div>
        </template>
      </DataTable>
    </div>

    <div v-if="!selectedResult && !loadingRisk" class="card p-3">
      <EmptyStateCard
        icon="pi pi-shield"
        title="Расчет риска еще не запускался"
        description="Выберите устройство, настройте параметры и нажмите «Рассчитать риск»."
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import Dialog from 'primevue/dialog';
import Chart from 'primevue/chart';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import ModeSwitch from '@/components/ui/ModeSwitch.vue';
import TablePresetBar from '@/components/ui/TablePresetBar.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import InfoHint from '@/components/ui/InfoHint.vue';
import { useTablePresetState } from '@/composables/useMonitoringTableState';

const toast = useToast();
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();
const RISK_UI_MODE_KEY = 'monitoring_risk_ui_mode';
const RISK_TABLE_PRESET_KEY = 'monitoring_risk_table_preset';

const devices = ref([]);
const loadingDevices = ref(false);
const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});
const selectedHorizon = ref('24h');
const preferredModelKind = ref('auto');
const personalizedThresholds = ref(true);
const thresholdLookbackDays = ref(60);
const markovLookbackDays = ref(120);
const markovSmoothing = ref(1.0);
const typeBlend = ref(0.35);
const overallWeightMarkov = ref(0.65);
const historyLimit = ref(12);
const riskUiMode = ref((() => {
  const raw = localStorage.getItem(RISK_UI_MODE_KEY);
  return raw === 'expert' ? 'expert' : 'basic';
})());
const isRiskExpert = computed(() => riskUiMode.value === 'expert');

const loadingRisk = ref(false);
const riskPayload = ref(null);
const riskErrorDialogVisible = ref(false);
const riskErrorDialogMessage = ref('');
const riskTablePreset = useTablePresetState(
  RISK_TABLE_PRESET_KEY,
  'balanced',
  ['ops', 'balanced', 'analysis'],
);
const expandedMetricRows = ref({});

const horizonOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const modelSourceOptions = [
  { label: 'Авто (последний успешный)', value: 'auto' },
  { label: 'Оркестр (ensemble)', value: 'ensemble' },
  { label: 'SARIMA', value: 'sarima' },
  { label: 'LSTM', value: 'lstm' },
];

const riskBasicHidden = [
  'история порогов и марковских переходов',
  'сглаживание и вес профиля типа сервера',
  'тонкая настройка коэффициента смешивания и глубины истории риска',
];

const riskTablePresets = [
  { value: 'ops', label: 'Оперативный', description: 'Только критичные метрики и компактный состав колонок.' },
  { value: 'balanced', label: 'Сбалансированный', description: 'Полная таблица для ежедневной работы.' },
  { value: 'analysis', label: 'Аналитический', description: 'Полная таблица + раскрытие формул расчета по строкам.' },
];
const riskHelpSteps = [
  'Выберите устройство, горизонт и источник прогноза в верхнем блоке.',
  'Риск на этой странице — это интегральный индекс угрозы отказа на горизонте, приведённый к шкале 0–100%.',
  'Нажмите «Рассчитать риск» — система соберет риск из метрик и модели переходов состояний.',
  'Общий риск смешивает два источника: риск по метрикам и вероятность состояния S2 по Маркову.',
  'В карточках результата смотрите общий риск, надежность, агрегат по метрикам и марковский риск S2.',
  'В блоке S0/S1/S2 проверяйте вероятности текущего и будущего состояния плюс матрицу переходов.',
  'Ниже в таблице используйте пресеты: «Оперативный» для быстрого просмотра, «Аналитический» для деталей.',
  'Если риск высокий, переходите в СППР для расчета конкретных действий.',
];

const metricMap = {
  cpu_load_total: { label: 'Загрузка CPU', unit: '%' },
  mem_usage_percent: { label: 'Использование памяти', unit: '%' },
  net_bytes_sent: { label: 'Трафик исходящий', unit: 'KB/s' },
  net_bytes_recv: { label: 'Трафик входящий', unit: 'KB/s' },
  ping_latency_gateway: { label: 'Ping до шлюза', unit: 'ms' },
  system_temperature: { label: 'Температура системы', unit: 'C' },
  storcli_drive_temperature: { label: 'Температура диска RAID', unit: 'C' },
  storcli_predictive_failure_count: { label: 'Predictive Failure Count', unit: 'count' },
  storcli_drive_wear_percent: { label: 'Износ диска RAID', unit: '%' },
  storcli_ssd_wear_percent: { label: 'Износ SSD', unit: '%' },
  nvme_percentage_used: { label: 'NVMe wear used', unit: '%' },
  ssd_tbw_used: { label: 'SSD TBW used', unit: 'TBW' },
  disk_tbw_used: { label: 'Disk TBW used', unit: 'TBW' },
};

const deviceOptions = computed(() => (
  devices.value.map((d) => ({
    id: d.id,
    label: d.serial_number ? `${d.name} (${d.serial_number})` : d.name,
    serial: d.serial_number || '',
  }))
));

const selectedDevice = computed(() => (
  deviceOptions.value.find((d) => d.id === selectedDeviceId.value) || null
));

const selectedResult = computed(() => {
  const rows = riskPayload.value?.horizons;
  if (!Array.isArray(rows) || !rows.length) return null;
  return rows.find((r) => r.horizon === selectedHorizon.value) || rows[0];
});

const metricRows = computed(() => (
  Array.isArray(selectedResult.value?.metrics) ? selectedResult.value.metrics : []
));
const metricChartRows = computed(() => (
  [...metricRows.value]
    .sort((a, b) => Number(b.risk || 0) - Number(a.risk || 0))
    .slice(0, 10)
));

const filteredMetricRows = computed(() => {
  if (riskTablePreset.value !== 'ops') return metricRows.value;
  return metricRows.value.filter((row) => Number(row.risk || 0) >= 0.85);
});
const activeRiskPresetLabel = computed(() => (
  riskTablePresets.find((item) => item.value === riskTablePreset.value)?.label || '—'
));
const showRiskDetailColumns = computed(() => riskTablePreset.value !== 'ops');
const showRiskExpander = computed(() => riskTablePreset.value === 'analysis');

const markovLabels = ['S0', 'S1', 'S2'];

const riskTimelineRows = computed(() => (
  Array.isArray(riskPayload.value?.risk_history) ? riskPayload.value.risk_history : []
));
const historySourceLabel = computed(() => modelKindLabel(selectedResult.value?.model_kind_used));
const overallRiskFormulaText = computed(() => {
  const wMarkov = Number(selectedResult.value?.overall_formula?.w_markov ?? overallWeightMarkov.value ?? 0.65);
  const wMetric = Number(selectedResult.value?.overall_formula?.w_metric ?? (1.0 - wMarkov));
  return `overall_risk = ${wMarkov.toFixed(2)} × markov_p_s2 + ${wMetric.toFixed(2)} × metric_aggregate_risk`;
});

const riskTimelineLabels = computed(() => (
  riskTimelineRows.value.map((row) => {
    const ts = row?.run_created_at ? new Date(row.run_created_at) : null;
    if (!ts || Number.isNaN(ts.getTime())) return `run #${row?.run_id ?? '-'}`;
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(ts);
  })
));

const metricChartData = computed(() => {
  const rows = metricChartRows.value;

  return {
    labels: rows.map((row) => metricLabel(row.metric_code)),
    datasets: [
      {
        label: 'Риск',
        data: rows.map((row) => Number((row.risk || 0) * 100)),
        backgroundColor: rows.map((row) => metricRiskColor(row.risk)),
        borderWidth: 0,
      },
    ],
  };
});

const metricChartOptions = {
  maintainAspectRatio: false,
  indexAxis: 'y',
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const row = metricChartRows.value[ctx.dataIndex];
          if (!row) return ` ${Number(ctx.raw || 0).toFixed(1)}%`;
          const parts = [`Итог: ${Number(ctx.raw || 0).toFixed(1)}%`];
          if (Number(row.base_risk || 0) !== Number(row.risk || 0)) {
            parts.push(`база ${formatPercent(row.base_risk)}`);
          }
          if (Number(row.state_history_signal || 0) > 0) {
            parts.push(`история состояний ${formatPercent(row.state_history_signal)}`);
          }
          return parts.join(' • ');
        },
        footer: (items) => {
          const row = metricChartRows.value[items?.[0]?.dataIndex ?? -1];
          if (!row) return '';
          return `Метод: ${methodLabel(row.method)} • вклад ${formatPercent(row.contribution)}`;
        },
      },
    },
  },
  scales: {
    x: {
      min: 0,
      max: 100,
      ticks: {
        callback: (value) => `${value}%`,
      },
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
    },
    y: {
      grid: { display: false },
    },
  },
};

const timelineChartData = computed(() => ({
  labels: riskTimelineLabels.value,
  datasets: [
    {
      label: 'Общий риск',
      data: riskTimelineRows.value.map((row) => Number((row?.overall_risk || 0) * 100)),
      borderColor: 'rgba(15, 118, 110, 1)',
      backgroundColor: 'rgba(15, 118, 110, 0.18)',
      pointRadius: 3.2,
      tension: 0.25,
      fill: false,
    },
    {
      label: 'Марковский риск S2',
      data: riskTimelineRows.value.map((row) => Number((row?.markov_p_s2 || 0) * 100)),
      borderColor: 'rgba(220, 38, 38, 0.95)',
      backgroundColor: 'rgba(220, 38, 38, 0.2)',
      pointRadius: 2.8,
      tension: 0.25,
      borderDash: [6, 5],
      fill: false,
    },
  ],
}));

const timelineChartOptions = {
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${ctx.dataset.label}: ${Number(ctx.raw || 0).toFixed(1)}%`,
        footer: () => 'Общий риск = смесь риска по метрикам и вероятности S2.',
      },
    },
  },
  scales: {
    x: {
      ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
      grid: { color: 'rgba(148, 163, 184, 0.16)' },
    },
    y: {
      min: 0,
      max: 100,
      ticks: { callback: (value) => `${value}%` },
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
    },
  },
};

const loadDevices = async () => {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = Array.isArray(res.data) ? res.data : (res.data?.results || []);
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch {
    devices.value = [];
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить устройства', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
};

const runRiskEvaluation = async () => {
  if (!selectedDevice.value?.serial) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Выберите устройство', life: 2500 });
    return;
  }
  loadingRisk.value = true;
  try {
    const payload = {
      serial: selectedDevice.value.serial,
      horizons: [selectedHorizon.value],
      preferred_model_kind: preferredModelKind.value,
      personalized_thresholds: personalizedThresholds.value,
      threshold_lookback_days: thresholdLookbackDays.value,
      markov_lookback_days: markovLookbackDays.value,
      markov_smoothing: markovSmoothing.value,
      type_blend: typeBlend.value,
      overall_weight_markov: overallWeightMarkov.value,
      history_limit: historyLimit.value,
    };
    const res = await apiClient.post('risk-assessment/evaluate/', payload);
    riskPayload.value = res.data;
    expandedMetricRows.value = {};
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Расчет риска не выполнен';
    riskPayload.value = null;
    expandedMetricRows.value = {};
    riskErrorDialogMessage.value = detail;
    riskErrorDialogVisible.value = true;
  } finally {
    loadingRisk.value = false;
  }
};

const refreshAll = async () => {
  await loadDevices();
  if (selectedDeviceId.value) await runRiskEvaluation();
};

const riskSeverity = (value) => {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'danger';
  if (raw >= 0.65) return 'warning';
  if (raw >= 0.4) return 'info';
  return 'success';
};

const riskLabel = (value) => {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'Критический';
  if (raw >= 0.65) return 'Высокий';
  if (raw >= 0.4) return 'Средний';
  return 'Низкий';
};

const metricRiskColor = (value) => {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'rgba(239, 68, 68, 0.85)';
  if (raw >= 0.65) return 'rgba(245, 158, 11, 0.85)';
  if (raw >= 0.4) return 'rgba(14, 165, 233, 0.85)';
  return 'rgba(34, 197, 94, 0.85)';
};

const modelKindLabel = (value) => {
  if (value === 'ensemble') return 'Оркестр';
  if (value === 'sarima') return 'SARIMA';
  if (value === 'lstm') return 'LSTM';
  if (value === 'raw_proxy') return 'Raw proxy';
  return 'Нет данных';
};

const metricLabel = (code) => metricMap[code]?.label || code;
const metricUnit = (code) => metricMap[code]?.unit || '';
const methodLabel = (method) => (method === 'weibull' ? 'Вейбулл' : 'Превышение');
const formulaByMethod = (method) => (
  method === 'weibull'
    ? 'P_fail(h)=1-S(tf)/S(t0), S(t)=exp(-(t/eta)^beta)'
    : 'risk=clamp((p90/threshold-0.75)/0.75)'
);

const formatNum = (value, digits = 2) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(digits);
};

const formatPercent = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${(n * 100).toFixed(1)}%`;
};

const formatMetricValue = (metricCode, value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const unit = metricUnit(metricCode);
  return `${n.toFixed(2)}${unit ? ` ${unit}` : ''}`;
};

const formatStepLabel = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return '—';
  const hours = n / 3600;
  if (hours < 24) return `${hours.toFixed(1)} ч`;
  return `${(hours / 24).toFixed(1)} д`;
};

const heatmapCellStyle = (value) => {
  const p = Math.max(0, Math.min(1, Number(value || 0)));
  return {
    backgroundColor: `rgba(14, 165, 233, ${0.12 + 0.72 * p})`,
    color: p >= 0.55 ? '#ffffff' : '#0f172a',
  };
};

const formulaInputsText = (row) => {
  const input = row?.formula_inputs || {};
  if (row?.method === 'weibull') {
    return `t0=${formatNum(input.t0, 3)}, tf=${formatNum(input.tf, 3)}, eta=${formatNum(input.eta, 3)}, beta=${formatNum(input.beta, 3)}`;
  }
  const parts = [
    `p90=${formatNum(input.p90, 3)}`,
    `threshold=${formatNum(input.threshold, 3)}`,
    `ratio=${formatNum(input.ratio, 3)}`,
    `source=${input.threshold_source || 'n/a'}`,
  ];
  if (Number(input.state_history_signal || 0) > 0) {
    parts.push(`state_history_signal=${formatNum(input.state_history_signal, 3)}`);
    parts.push(`history_count=${input.state_history_count ?? 0}`);
    parts.push(`blend=${formatNum(input.history_blend, 3)}`);
  }
  return parts.join(', ');
};

const stateRows = (stateObj) => ([
  { key: 's0', label: 'S0', value: Number(stateObj?.s0 || 0) },
  { key: 's1', label: 'S1', value: Number(stateObj?.s1 || 0) },
  { key: 's2', label: 'S2', value: Number(stateObj?.s2 || 0) },
]);

const metricRowClass = (row) => {
  const classes = [];
  const raw = Number(row?.risk || 0);
  if (raw >= 0.85) classes.push('row-risk-critical');
  else if (raw >= 0.65) classes.push('row-risk-high');
  else if (raw >= 0.4) classes.push('row-risk-medium');
  if (row?.supplemented_from_state_history) classes.push('row-risk-history');
  return classes.join(' ');
};

watch(selectedHorizon, () => {
  expandedMetricRows.value = {};
  if (riskPayload.value?.horizons?.length) {
    const exists = riskPayload.value.horizons.some((item) => item.horizon === selectedHorizon.value);
    if (!exists) runRiskEvaluation();
  }
});

watch(riskUiMode, (value) => {
  localStorage.setItem(RISK_UI_MODE_KEY, value);
});

watch(riskTablePreset, () => {
  expandedMetricRows.value = {};
});

onMounted(async () => {
  await loadDevices();
  if (selectedDeviceId.value) await runRiskEvaluation();
});
</script>

<style scoped>
.risk-page {
  width: 100%;
  min-width: 0;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 0.8rem;
  align-items: end;
}

.field-block {
  min-width: 0;
}

.field-block label {
  display: block;
  margin-bottom: 0.35rem;
  color: #475569;
  font-size: 0.84rem;
  font-weight: 600;
}

.switch-inline {
  width: 100%;
  min-height: 2.6rem;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  color: #334155;
  background: #fff;
}

.actions-row {
  display: flex;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.risk-error-dialog {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.risk-error-text {
  margin: 0;
  color: #334155;
  line-height: 1.55;
  white-space: pre-line;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
  align-items: stretch;
}

.summary-card {
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  padding: 0.75rem;
  min-width: 0;
}

.summary-grid-span {
  grid-column: 1 / -1;
}

.risk-explainer-card {
  border-color: #cfe8e3;
  background: linear-gradient(180deg, rgba(240, 253, 250, 0.92), #ffffff);
}

.summary-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.summary-label {
  color: #64748b;
  font-size: 0.8rem;
}

.summary-main {
  margin-top: 0.35rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.7rem;
}

.summary-main strong {
  font-size: 1.2rem;
  color: #0f172a;
}

.state-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.title-with-hint {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}

.formula-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.formula-chip {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.8rem;
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  background: #fff;
  min-width: 0;
}

.formula-chip strong {
  color: #0f172a;
  font-size: 0.88rem;
}

.formula-chip span {
  color: #475569;
  font-size: 0.82rem;
  line-height: 1.5;
}

.states-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 0.8rem;
}

.state-box {
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  padding: 0.7rem;
  background: #fff;
  min-width: 0;
  overflow: hidden;
}

.state-box-title {
  color: #0f172a;
  font-size: 0.88rem;
  font-weight: 700;
  margin-bottom: 0.45rem;
}

.state-box-title--with-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.state-lines {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.state-line {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  color: #334155;
  font-size: 0.84rem;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
}

.matrix-table th,
.matrix-table td {
  border: 1px solid #e2e8f0;
  padding: 0.25rem 0.35rem;
  text-align: center;
  font-size: 0.8rem;
}

.matrix-table th {
  background: #f8fafc;
  color: #334155;
  font-weight: 700;
}

.matrix-meta {
  margin-top: 0.45rem;
  font-size: 0.75rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.heatmap-wrap {
  display: grid;
  grid-template-columns: 58px repeat(3, minmax(56px, 1fr));
  gap: 0.35rem;
  align-items: stretch;
  min-width: 0;
}

.heatmap-axis {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dbe6f2;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-weight: 700;
  font-size: 0.78rem;
  min-height: 2rem;
}

.heatmap-header {
  min-height: 2rem;
}

.heatmap-cell {
  border: 1px solid #dbe6f2;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78rem;
  font-weight: 700;
  min-height: 2rem;
}

.chart-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  padding: 0.7rem;
  min-width: 0;
  overflow: hidden;
}

.risk-chart {
  height: 22rem;
}

.timeline-chart {
  height: 19rem;
}

.table-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.risk-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
}

.legend-title {
  color: #475569;
  font-size: 0.82rem;
  font-weight: 700;
}

.legend-chip {
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  padding: 0.2rem 0.6rem;
  border: 1px solid transparent;
}

.legend-low {
  color: #166534;
  background: #dcfce7;
  border-color: #86efac;
}

.legend-medium {
  color: #92400e;
  background: #fef3c7;
  border-color: #fcd34d;
}

.legend-high {
  color: #9a3412;
  background: #ffedd5;
  border-color: #fdba74;
}

.legend-critical {
  color: #991b1b;
  background: #fee2e2;
  border-color: #fca5a5;
}

.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.65rem;
}

.metric-cell {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
}

.column-header-with-hint {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}

.metric-title {
  color: #0f172a;
  font-weight: 600;
}

.metric-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.metric-meta-text,
.param-subline,
.risk-subline {
  color: #64748b;
  font-size: 0.76rem;
}

.risk-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
}

.base-risk-cell,
.state-history-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.2rem;
}

.expansion-box {
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  padding: 0.6rem 0.7rem;
  background: #f8fafc;
}

.expansion-title {
  color: #0f172a;
  font-weight: 700;
  margin-bottom: 0.25rem;
}

.expansion-line {
  color: #334155;
  font-size: 0.82rem;
  margin-top: 0.2rem;
  overflow-wrap: anywhere;
}

:deep(.row-risk-critical > td) {
  background: rgba(254, 226, 226, 0.65) !important;
}

:deep(.row-risk-high > td) {
  background: rgba(255, 237, 213, 0.58) !important;
}

:deep(.row-risk-medium > td) {
  background: rgba(254, 243, 199, 0.55) !important;
}

:deep(.row-risk-history > td:first-child) {
  box-shadow: inset 3px 0 0 #0ea5e9;
}

.risk-page :deep(.tt-filter-panel__head),
.risk-page :deep(.tt-page-header),
.risk-page :deep(.tt-mode-switch__buttons) {
  flex-wrap: wrap;
}

.risk-page :deep(.p-dropdown),
.risk-page :deep(.p-inputnumber),
.risk-page :deep(.p-inputnumber-input) {
  width: 100%;
  min-width: 0;
}

.risk-page :deep(.p-datatable-wrapper) {
  overflow: auto;
}

@media (max-width: 1180px) {
  .filters-grid {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  }

  .states-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .summary-main {
    align-items: flex-start;
  }

  .heatmap-wrap {
    overflow-x: auto;
    padding-bottom: 0.2rem;
  }
}

@media (max-width: 640px) {
  .filters-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .summary-card,
  .state-box,
  .chart-wrap {
    padding-left: 0.65rem;
    padding-right: 0.65rem;
  }

  .state-line {
    font-size: 0.8rem;
  }
}
</style>
