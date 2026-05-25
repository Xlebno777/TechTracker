<template>
  <div class="evaluation-page p-4">
    <Toast />

    <PageHeader
      title="Оценка прогноза"
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: оценка прогноза"
      help-intro="Страница сравнивает качество прогнозов и экономический эффект рекомендаций."
      :help-steps="evaluationHelpSteps"
      help-note="Каждый запуск формирует артефакты в папке `research/evaluation/run_*`."
      @refresh="refreshAll"
    />

    <FilterPanel
      class="mb-3"
      title="Параметры запуска"
    >
      <template #actions>
        <ModeSwitch
          v-model="evaluationUiMode"
          aria-label="Режим интерфейса оценки прогноза"
          :hidden-items="evaluationBasicHidden"
          :show-basic-hint="false"
        />
      </template>

      <div class="filters-grid filters-grid--primary">
        <div class="field-block field-block--wide">
          <label>Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            :loading="loadingDevices"
            class="w-full"
            placeholder="Все устройства"
            showClear
          />
        </div>

        <div class="field-block field-block--wide">
          <label>Горизонты</label>
          <div class="checkbox-grid">
            <label v-for="option in horizonOptions" :key="option.value" class="checkbox-chip">
              <Checkbox v-model="selectedHorizons" :inputId="`horizon-${option.value}`" :value="option.value" />
              <span>{{ option.label }}</span>
            </label>
          </div>
        </div>

        <div class="field-block field-block--wide">
          <label>Модели</label>
          <div class="checkbox-grid">
            <label v-for="option in modelOptions" :key="option.value" class="checkbox-chip">
              <Checkbox v-model="selectedModels" :inputId="`model-${option.value}`" :value="option.value" />
              <span>{{ option.label }}</span>
            </label>
          </div>
        </div>
      </div>

      <div class="range-panels mt-3">
        <div class="range-panel">
          <div class="range-panel__head">
            <div>
              <h5 class="m-0">Интервал прогноза</h5>
              <span class="text-500 text-sm">Какие прогнозные точки брать для сравнения.</span>
            </div>
          </div>
          <div class="range-grid mt-2">
            <div class="field-block">
              <label>От</label>
              <InputText v-model="targetDateFrom" type="date" class="w-full" />
            </div>
            <div class="field-block">
              <label>До</label>
              <InputText v-model="targetDateTo" type="date" class="w-full" />
            </div>
          </div>
          <small class="switch-caption">
            {{ targetRangeLabel }}
          </small>
        </div>

        <div class="range-panel">
          <div class="range-panel__head">
            <div>
              <h5 class="m-0">Интервал факта</h5>
              <span class="text-500 text-sm">Где искать реальные значения для RMSE/MAE.</span>
            </div>
            <Button
              text
              size="small"
              icon="pi pi-copy"
              label="Факт = прогноз"
              @click="copyForecastRangeToActual"
            />
          </div>
          <div class="range-grid mt-2">
            <div class="field-block">
              <label>От</label>
              <InputText v-model="actualDateFrom" type="date" class="w-full" />
            </div>
            <div class="field-block">
              <label>До</label>
              <InputText v-model="actualDateTo" type="date" class="w-full" />
            </div>
          </div>
          <small class="switch-caption">
            {{ actualRangeLabel }}
          </small>
        </div>
      </div>

      <div v-if="isEvaluationExpert" class="filters-grid filters-grid--expert mt-3">
        <div class="field-block">
          <label>Forecast run</label>
          <MultiSelect
            v-model="selectedForecastRunIds"
            :options="forecastRunOptions"
            optionLabel="label"
            optionValue="value"
            :loading="loadingForecastRuns"
            class="w-full"
            display="chip"
            filter
            placeholder="Все доступные прогнозные запуски"
            selectedItemsLabel="{0} run выбрано"
            maxSelectedLabels="2"
          />
          <small class="switch-caption">Можно ограничить расчёт конкретными прогонами из базы.</small>
        </div>

        <div class="field-block">
          <label>Эталонное действие (baseline)</label>
          <InputText v-model="baselineActionCode" class="w-full" placeholder="Обычно no_action" />
          <small class="switch-caption">С чем сравнивать СППР по экономическому эффекту. Для обычной оценки оставляйте `no_action`.</small>
        </div>

        <div class="field-block">
          <label>Тег запуска (опц.)</label>
          <InputText v-model="runTag" class="w-full" placeholder="chapter7" />
          <small class="switch-caption">Попадает в имя run-папки для серии экспериментов.</small>
        </div>

        <div class="field-block">
          <label>Strict intersection</label>
          <div class="switch-field">
            <InputSwitch v-model="strictIntersection" />
            <span>{{ strictIntersection ? 'Включен' : 'Выключен' }}</span>
          </div>
          <small class="switch-caption">Оставляет только временные бакеты, где прогноз и факт есть у всех выбранных моделей на одном шаге времени.</small>
        </div>

        <div class="field-block">
          <label>Статистические тесты</label>
          <div class="switch-field">
            <InputSwitch v-model="enableStatTests" />
            <span>{{ enableStatTests ? 'DM-test и bootstrap включены' : 'Отключены' }}</span>
          </div>
          <small class="switch-caption">Нужно для диссертационной статистической проверки, не для повседневной оценки.</small>
        </div>

        <div class="field-block">
          <label>Bootstrap итераций</label>
          <InputNumber
            v-model="bootstrapSamples"
            :min="50"
            :max="2000"
            :disabled="!enableStatTests"
            class="w-full"
          />
          <small class="switch-caption">Рекомендуемо 300-600 итераций.</small>
        </div>

        <div class="field-block">
          <label>Размер блока L (bootstrap)</label>
          <InputNumber
            v-model="bootstrapBlockSize"
            :min="0"
            :max="5000"
            :disabled="!enableStatTests"
            class="w-full"
          />
          <small class="switch-caption">0 = авто. Длина блока временной зависимости.</small>
        </div>
      </div>

      <div v-if="validationMessage" class="evaluation-form-note mt-3">
        <i class="pi pi-info-circle" />
        <span>{{ validationMessage }}</span>
      </div>

      <div class="actions-row mt-3">
        <Button
          icon="pi pi-database"
          label="Проверить доступность данных"
          severity="secondary"
          outlined
          :loading="previewLoading"
          :disabled="previewLoading || !canEvaluate"
          @click="previewEvaluationAvailability"
        />
        <Button
          icon="pi pi-play"
          label="Запустить оценку"
          :loading="runningEvaluation"
          :disabled="runningEvaluation || !canEvaluate"
          @click="runEvaluation"
        />
      </div>

      <div v-if="availabilityPreview" class="availability-preview mt-3">
        <div class="table-head">
          <h4 class="m-0">Доступность данных для RMSE/MAE</h4>
          <span class="text-500 text-sm">Оценка окна до запуска расчёта</span>
        </div>
        <div class="summary-grid summary-grid--quality mt-2">
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Прогнозные точки</span></div>
            <div class="summary-main">
              <strong>{{ availabilitySummary.forecast_points_total ?? 0 }}</strong>
              <span class="text-500 text-sm">Выбранные точки прогноза</span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Фактические точки</span></div>
            <div class="summary-main">
              <strong>{{ availabilitySummary.raw_metric_points_total ?? 0 }}</strong>
              <span class="text-500 text-sm">Raw-метрики в интервале факта</span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Точек с фактом</span></div>
            <div class="summary-main">
              <strong>{{ availabilitySummary.forecast_points_with_actual_raw ?? 0 }}</strong>
              <span class="text-500 text-sm">Прогнозы, у которых найден близкий факт</span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Точек для сравнения</span></div>
            <div class="summary-main">
              <strong>{{ availabilitySummary.forecast_points_compared ?? 0 }}</strong>
              <span class="text-500 text-sm">После режима strict intersection</span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Покрытие</span></div>
            <div class="summary-main">
              <strong>{{ percent(availabilitySummary.forecast_coverage_compared) }}</strong>
              <span class="text-500 text-sm">Итоговая доля точек для RMSE/MAE</span>
            </div>
          </div>
          <div class="summary-card">
            <div class="summary-label-row"><span class="summary-label">Готовность</span></div>
            <div class="summary-main">
              <strong>{{ previewReadinessLabel }}</strong>
              <span class="text-500 text-sm">{{ previewReadinessNote }}</span>
            </div>
          </div>
        </div>
        <div v-if="availabilityWarnings.length" class="chart-note-list mt-2">
          <span v-for="warning in availabilityWarnings" :key="warning" class="chart-note-chip">
            {{ warning }}
          </span>
        </div>
        <DataTable
          v-if="availabilityRows.length"
          :value="availabilityRows"
          responsiveLayout="scroll"
          stripedRows
          size="small"
          class="mt-3"
        >
          <Column header="Модель">
            <template #body="{ data }">{{ humanModel(data.model_kind) }}</template>
          </Column>
          <Column header="Горизонт">
            <template #body="{ data }">{{ humanHorizon(data.horizon) }}</template>
          </Column>
          <Column field="forecast_points" header="Прогнозных точек" />
          <Column field="with_actual" header="С найденным фактом" />
          <Column field="compared_points" header="Для сравнения" />
          <Column header="Raw coverage">
            <template #body="{ data }">{{ percent(data.coverage_raw) }}</template>
          </Column>
          <Column header="Итоговое покрытие">
            <template #body="{ data }">{{ percent(data.coverage_compared) }}</template>
          </Column>
        </DataTable>
      </div>
    </FilterPanel>

    <div v-if="!selectedRun && !loadingDetail" class="card p-3 mb-3">
      <EmptyStateCard
        icon="pi pi-chart-line"
        title="Запуск оценки не выбран"
        description="Выберите run из истории или запустите новую оценку, чтобы увидеть метрики и артефакты."
      />
    </div>

    <div v-if="selectedRun" class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">Итоги последнего выбранного запуска</h4>
        <span class="text-500 text-sm">{{ formatDateTime(selectedRun.generated_at) }}</span>
      </div>
      <div class="summary-grid summary-grid--extended mt-2">
        <div v-for="card in summaryCards" :key="card.title" class="summary-card">
          <div class="summary-label-row">
            <span class="summary-label">{{ card.title }}</span>
            <InfoHint
              v-if="card.tooltipLines?.length"
              :title="card.title"
              :lines="card.tooltipLines"
              placement="top-left"
            />
          </div>
          <div class="summary-main">
            <strong>{{ card.value }}</strong>
            <span class="text-500 text-sm">{{ card.note }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectedRun" class="card p-3 mb-3">
      <div class="table-head">
        <div class="title-with-hint">
          <h4 class="m-0">Вероятностное качество прогноза</h4>
          <InfoHint
            title="Как читать блок вероятностного качества"
            :lines="[
              'Этот блок оценивает не только точность одной точки прогноза, но и качество интервала неопределенности.',
              'Pinball: чем меньше, тем лучше квантильный прогноз.',
              'PICP80: доля фактов внутри интервала [p10, p90]. Хорошо, когда близко к 80%.',
              'ACE80: отклонение PICP80 от целевых 80%. Чем ближе к нулю, тем лучше.',
              'Winkler80: штраф за слишком широкий интервал и за факты вне интервала. Чем меньше, тем лучше.'
            ]"
          />
        </div>
        <span class="text-500 text-sm">Pinball • PICP80 • ACE80 • Winkler80</span>
      </div>
      <div class="chart-toolbar mt-2">
        <div class="field-block chart-toolbar__field">
          <label>Метрика верхней аналитики</label>
          <Dropdown
            v-model="selectedMetricScope"
            :options="bucketMetricOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="chart-toolbar__note">
          <strong>{{ selectedMetricScopeLabel }}</strong>
          <span v-if="activeMetricScope === metricScopeAll">Смешанный итог по всем метрикам в разных единицах. Выбор ниже помогает уйти от такого смешивания.</span>
          <span v-else>Выбранная метрика используется для Pinball, PICP/ACE и верхних графиков RMSE/MAE.</span>
        </div>
      </div>
      <div class="summary-grid summary-grid--quality mt-2">
        <div v-for="card in probabilisticCards" :key="card.title" class="summary-card">
          <div class="summary-label-row">
            <span class="summary-label">{{ card.title }}</span>
            <InfoHint
              v-if="card.tooltipLines?.length"
              :title="card.title"
              :lines="card.tooltipLines"
              placement="top-left"
            />
          </div>
          <div class="summary-main">
            <strong>{{ card.value }}</strong>
            <span class="text-500 text-sm">{{ card.note }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectedRun" class="grid gap-3 mb-3 charts-grid">
      <div class="card p-3">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">RMSE/MAE по моделям и горизонтам</h4>
            <InfoHint
              title="Как читать график RMSE/MAE"
              :lines="[
                'Сравнивайте модели внутри одного и того же горизонта.',
                'Ниже столбцы = меньше средняя ошибка прогноза.',
                'RMSE сильнее штрафует крупные промахи, MAE показывает средний абсолютный промах.',
                'Если по горизонту нет столбца, значит для него еще нет достаточного факта.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">Меньше — лучше</span>
        </div>
        <div v-if="modelChartMissingNotes.length" class="chart-note-list mt-2">
          <span v-for="note in modelChartMissingNotes" :key="note" class="chart-note-chip">
            {{ note }}
          </span>
        </div>
        <div class="chart-wrap mt-2">
          <Chart type="bar" :data="modelChartData" :options="modelChartOptions" class="chart-box" />
        </div>
      </div>
      <div class="card p-3">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">Pinball по моделям и горизонтам</h4>
            <InfoHint
              title="Как читать график Pinball"
              :lines="[
                'Pinball оценивает качество квантилей q10, q50 и q90.',
                'Ниже значения = лучше модель угадывает не только центр, но и нижнюю/верхнюю границы.',
                'Линия Pinball avg помогает быстро увидеть общий баланс качества по квантилям.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">{{ activeMetricScope === metricScopeAll ? 'q10/q50/q90 + средний score' : `${selectedMetricScopeLabel} • q10/q50/q90 + средний score` }}</span>
        </div>
        <div v-if="probabilisticChartMissingNotes.length" class="chart-note-list mt-2">
          <span v-for="note in probabilisticChartMissingNotes" :key="note" class="chart-note-chip">
            {{ note }}
          </span>
        </div>
        <div class="chart-wrap mt-2">
          <Chart type="bar" :data="probabilisticChartData" :options="probabilisticChartOptions" class="chart-box" />
        </div>
      </div>
      <div class="card p-3">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">Калибровка интервала 80%</h4>
            <InfoHint
              title="Как читать калибровку интервала"
              :lines="[
                'Зеленые столбцы PICP80 показывают, как часто факт попадал внутрь [p10, p90].',
                'Хороший результат: PICP80 близко к 80%.',
                'Красная линия ACE80 показывает отклонение от цели. Чем ближе к нулю, тем лучше.',
                'Если PICP80 сильно ниже 80%, интервалы слишком узкие. Если сильно выше, интервалы слишком широкие.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">{{ activeMetricScope === metricScopeAll ? 'PICP80 vs целевые 80% + ACE80' : `${selectedMetricScopeLabel} • PICP80 vs целевые 80% + ACE80` }}</span>
        </div>
        <div v-if="calibrationChartMissingNotes.length" class="chart-note-list mt-2">
          <span v-for="note in calibrationChartMissingNotes" :key="note" class="chart-note-chip">
            {{ note }}
          </span>
        </div>
        <div class="chart-wrap mt-2">
          <Chart type="bar" :data="calibrationChartData" :options="calibrationChartOptions" class="chart-box" />
        </div>
      </div>
      <div class="card p-3">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">Сравнение режимов SARIMA</h4>
            <InfoHint
              title="Как читать сравнение режимов SARIMA"
              :lines="[
                'Сравниваются разные варианты учета сезонности в SARIMA.',
                'RMSE и MAE лучше читать как основную ошибку: ниже лучше.',
                'MAPE показывает относительную ошибку в процентах: ниже лучше.',
                'Сравнивайте режимы только внутри одного горизонта.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">RMSE/MAE + MAPE по горизонтам</span>
        </div>
        <div v-if="sarimaVariantMissingNotes.length" class="chart-note-list mt-2">
          <span v-for="note in sarimaVariantMissingNotes" :key="note" class="chart-note-chip">
            {{ note }}
          </span>
        </div>
        <div v-if="sarimaVariantRows.length" class="chart-wrap mt-2">
          <Chart type="bar" :data="sarimaVariantChartData" :options="sarimaVariantChartOptions" class="chart-box" />
        </div>
        <div v-else class="mt-2">
          <EmptyStateCard
            icon="pi pi-chart-bar"
            title="Сравнение режимов SARIMA пока недоступно"
            description="Нужны оцененные SARIMA-точки с фактическими значениями. Пока для новых режимов сезонности нет достаточного факта на выбранных горизонтах."
          />
        </div>
      </div>
      <div class="card p-3">
        <div class="table-head">
          <div class="title-with-hint">
            <h4 class="m-0">Экономический эффект по горизонтам</h4>
            <InfoHint
              title="Как читать экономический эффект"
              :lines="[
                'Экономический эффект считается по запускам СППР, а не по прогнозным точкам.',
                'Формула: ΔR = ожидаемые потери baseline - ожидаемые потери рекомендованного действия.',
                'Если ΔR > 0, выбранная рекомендация снижает ожидаемые потери относительно baseline.',
                'На графике теперь показаны три величины: потери без СППР, потери с рекомендацией и экономия ΔR.',
                'Если запусков мало, вывод нужно читать осторожно: смотрите N и долю положительного эффекта.'
              ]"
            />
          </div>
          <div class="chart-head-actions">
            <span class="text-500 text-sm">Потери baseline, потери СППР и экономия ΔR</span>
            <label class="chart-mode-switch" aria-label="Режим агрегации экономического эффекта">
              <span :class="{ 'chart-mode-switch__label--active': deltaChartMode === 'mean' }">Среднее</span>
              <InputSwitch v-model="deltaMedianMode" />
              <span :class="{ 'chart-mode-switch__label--active': deltaChartMode === 'median' }">Медиана</span>
            </label>
          </div>
        </div>
        <div class="economic-formula mt-2">
          <strong>Как читать:</strong>
          <span>чем выше зелёная экономия ΔR, тем больше ожидаемых потерь удалось избежать. Красный ΔR означал бы, что рекомендация хуже baseline.</span>
        </div>
        <div v-if="deltaChartNotes.length" class="chart-note-list mt-2">
          <span v-for="note in deltaChartNotes" :key="note" class="chart-note-chip">
            {{ note }}
          </span>
        </div>
        <div class="chart-wrap mt-2">
          <Chart type="bar" :data="deltaChartData" :options="deltaChartOptions" class="chart-box" />
        </div>
        <div v-if="economicHorizonRows.length" class="economic-grid mt-3">
          <div v-for="row in economicHorizonRows" :key="row.horizon" class="economic-card">
            <div class="economic-card__head">
              <strong>{{ humanHorizon(row.horizon) }}</strong>
              <span>N={{ row.samples }}</span>
            </div>
            <div class="economic-card__line">
              <span>Без СППР</span>
              <strong>{{ money(row.expectedWithout) }}</strong>
            </div>
            <div class="economic-card__line">
              <span>С рекомендацией</span>
              <strong>{{ money(row.expectedWith) }}</strong>
            </div>
            <div class="economic-card__line economic-card__line--accent">
              <span>Экономия ΔR</span>
              <strong>{{ money(row.delta) }}</strong>
            </div>
            <div class="economic-card__foot">
              <span>Снижение потерь: {{ percent(row.deltaPct) }}</span>
              <span>ΔR &gt; 0: {{ percent(row.sharePositive) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectedRun" class="card p-3 mb-3">
      <div class="table-head">
        <div class="title-with-hint">
          <h4 class="m-0">Статистическая значимость</h4>
          <InfoHint
            title="Как читать статистическую значимость"
            :lines="[
              'DM-test проверяет, значима ли разница в ошибках между двумя моделями.',
              'p-value < 0.05 обычно трактуем как статистически значимое отличие.',
              'Bootstrap CI95 показывает диапазон неопределенности метрик качества.',
              'Если доверительные интервалы широкие, вывод по качеству пока нестабилен.'
            ]"
          />
        </div>
        <span class="text-500 text-sm">DM-test и bootstrap CI95</span>
      </div>
      <div class="summary-grid summary-grid--quality mt-2">
        <div v-for="card in significanceCards" :key="card.title" class="summary-card">
          <div class="summary-label-row">
            <span class="summary-label">{{ card.title }}</span>
            <InfoHint
              v-if="card.tooltipLines?.length"
              :title="card.title"
              :lines="card.tooltipLines"
              placement="top-left"
            />
          </div>
          <div class="summary-main">
            <strong>{{ card.value }}</strong>
            <span class="text-500 text-sm">{{ card.note }}</span>
          </div>
        </div>
      </div>

      <div class="tables-grid mt-3">
        <div>
          <h5 class="m-0 mb-2">DM-test по горизонтам</h5>
          <DataTable :value="dmRows" responsiveLayout="scroll" stripedRows size="small">
            <template #empty>
              <EmptyStateCard
                icon="pi pi-chart-line"
                title="DM-test недоступен"
                description="Недостаточно пересечений фактов для статистического сравнения."
              />
            </template>
            <Column header="Горизонт" style="width: 100px">
              <template #body="{ data }">{{ humanHorizon(data.horizon) }}</template>
            </Column>
            <Column header="Пара моделей" style="min-width: 190px">
              <template #body="{ data }">{{ humanModel(data.model_a) }} vs {{ humanModel(data.model_b) }}</template>
            </Column>
            <Column field="samples" header="N" style="width: 80px" />
            <Column header="Δloss (A-B)" style="width: 120px">
              <template #body="{ data }">{{ num(data.mean_loss_diff, 4) }}</template>
            </Column>
            <Column header="DM stat" style="width: 110px">
              <template #body="{ data }">{{ num(data.dm_stat, 4) }}</template>
            </Column>
            <Column header="p-value" style="width: 120px">
              <template #body="{ data }">{{ pValue(data.p_value) }}</template>
            </Column>
            <Column header="Значимость" style="width: 120px">
              <template #body="{ data }">
                <span :class="['stat-chip', isSignificantDm(data) ? 'stat-chip--yes' : 'stat-chip--no']">
                  {{ isSignificantDm(data) ? 'p < 0.05' : 'не значимо' }}
                </span>
              </template>
            </Column>
            <Column header="Победитель" style="width: 130px">
              <template #body="{ data }">{{ data.winner ? humanModel(data.winner) : '-' }}</template>
            </Column>
          </DataTable>
        </div>

        <div>
          <h5 class="m-0 mb-2">Bootstrap CI95</h5>
          <DataTable :value="bootstrapRows" responsiveLayout="scroll" stripedRows size="small">
            <template #empty>
              <EmptyStateCard
                icon="pi pi-chart-bar"
                title="Bootstrap CI недоступен"
                description="В текущем run недостаточно валидных точек для построения доверительных интервалов."
              />
            </template>
            <Column header="Модель" style="width: 110px">
              <template #body="{ data }">{{ humanModel(data.model_kind) }}</template>
            </Column>
            <Column header="Горизонт" style="width: 100px">
              <template #body="{ data }">{{ humanHorizon(data.horizon) }}</template>
            </Column>
            <Column field="metric" header="Метрика" style="width: 130px" />
            <Column field="samples" header="N" style="width: 80px" />
            <Column header="Оценка" style="width: 100px">
              <template #body="{ data }">{{ num(data.estimate, 4) }}</template>
            </Column>
            <Column header="CI95 low" style="width: 100px">
              <template #body="{ data }">{{ num(data.ci95_low, 4) }}</template>
            </Column>
            <Column header="CI95 high" style="width: 100px">
              <template #body="{ data }">{{ num(data.ci95_high, 4) }}</template>
            </Column>
            <Column header="B" style="width: 80px">
              <template #body="{ data }">{{ data.bootstrap_samples || '-' }}</template>
            </Column>
            <Column header="L" style="width: 80px">
              <template #body="{ data }">{{ Number(data.bootstrap_block_size || 0) > 0 ? data.bootstrap_block_size : 'auto' }}</template>
            </Column>
          </DataTable>
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">История запусков</h4>
        <span class="text-500 text-sm">Запусков: {{ filteredHistoryRows.length }} / {{ historyRows.length }}</span>
      </div>
      <div class="table-toolbar mt-2">
        <TablePresetBar
          v-model="historyTablePreset"
          title="Пресет истории"
          aria-label="Пресеты истории evaluation"
          :presets="historyTablePresets"
        />
      </div>
      <DataTable :value="filteredHistoryRows" dataKey="run_id" responsiveLayout="scroll" class="mt-2" stripedRows>
        <template #empty>
          <EmptyStateCard
            icon="pi pi-history"
            title="История запусков пуста"
            description="Сделайте первый запуск оценки, чтобы сформировать историю и артефакты."
          />
        </template>
        <Column field="run_id" header="Run ID" style="min-width: 240px" />
        <Column header="Дата" style="min-width: 170px">
          <template #body="{ data }">
            {{ formatDateTime(data.generated_at) }}
          </template>
        </Column>
        <Column header="Покрытие" style="width: 130px">
          <template #body="{ data }">
            {{ percent(data.summary?.forecast_coverage) }}
          </template>
        </Column>
        <Column header="ΔR среднее" style="width: 130px">
          <template #body="{ data }">
            {{ money(data.summary?.delta_r?.delta_r_mean) }}
          </template>
        </Column>
        <Column header="ΔR &gt; 0" style="width: 130px">
          <template #body="{ data }">
            {{ percent(data.summary?.delta_r?.share_positive) }}
          </template>
        </Column>
        <Column header="Действия" style="width: 120px">
          <template #body="{ data }">
            <Button size="small" label="Открыть" @click="selectRun(data.run_id)" />
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="selectedRun" class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">Артефакты запуска {{ selectedRun.run_id }}</h4>
        <span class="text-500 text-sm">
          {{ formatDateTime(selectedRun.generated_at) }} • {{ filteredArtifactRows.length }} / {{ artifactRows.length }}
        </span>
      </div>
      <div class="table-toolbar mt-2">
        <TablePresetBar
          v-model="artifactTablePreset"
          title="Пресет артефактов"
          aria-label="Пресеты артефактов evaluation"
          :presets="artifactTablePresets"
        />
      </div>
      <DataTable :value="filteredArtifactRows" dataKey="key" responsiveLayout="scroll" class="mt-2" stripedRows>
        <template #empty>
          <EmptyStateCard
            icon="pi pi-folder-open"
            title="Артефакты не найдены"
            description="Для выбранного запуска пока нет CSV/PDF артефактов."
          />
        </template>
        <Column field="key" header="Ключ" style="min-width: 220px" />
        <Column field="file_name" header="Файл" style="min-width: 220px" />
        <Column field="path" header="Путь" style="min-width: 300px" />
        <Column header="Скачать" style="width: 130px">
          <template #body="{ data }">
            <Button
              size="small"
              icon="pi pi-download"
              label="Скачать"
              :loading="downloadKey === data.key"
              @click="downloadArtifact(data.key, data.file_name)"
            />
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import InputText from 'primevue/inputtext';
import MultiSelect from 'primevue/multiselect';
import Toast from 'primevue/toast';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Chart from 'primevue/chart';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import InfoHint from '@/components/ui/InfoHint.vue';
import TablePresetBar from '@/components/ui/TablePresetBar.vue';
import ModeSwitch from '@/components/ui/ModeSwitch.vue';
import { useTableFiltersState, useTablePresetState } from '@/composables/useMonitoringTableState';

const toast = useToast();
const EVALUATION_FILTERS_KEY = 'monitoring_evaluation_filters';
const EVALUATION_HISTORY_PRESET_KEY = 'monitoring_evaluation_history_preset';
const EVALUATION_ARTIFACT_PRESET_KEY = 'monitoring_evaluation_artifact_preset';
const EVALUATION_UI_MODE_KEY = 'monitoring_evaluation_ui_mode';
const evaluationHelpSteps = [
  'Выберите устройство, горизонты и модели для сравнения.',
  'Явно задайте интервал прогноза и интервал факта. Без дат расчёт не запускается.',
  'Включайте Strict intersection для научно-корректного сравнения моделей на одинаковых временных бакетах выбранной частоты.',
  'Для CI95 используется moving block bootstrap; параметр L задает длину временного блока (0 = авто).',
  'Нажмите «Запустить оценку» и дождитесь появления нового run в истории.',
  'Откройте run, чтобы увидеть точечные метрики, вероятностные метрики (Pinball/PICP/ACE), сравнение режимов SARIMA и эффект ΔR.',
  'Выбор forecast run позволяет ограничить оценку конкретными уже выполненными прогонами из базы.',
  'Код baseline-действия — это эталонный реактивный сценарий, с которым сравнивается экономический эффект СППР.',
  'Тег запуска — это произвольная метка, которая попадет в имя папки run и поможет отделять серии экспериментов.',
  'В таблицах истории и артефактов используйте пресеты для быстрого отбора.',
  'Скачивайте CSV/PDF артефакты для включения в главу верификации диссертации.',
];
const evaluationUiMode = ref((() => {
  const raw = localStorage.getItem(EVALUATION_UI_MODE_KEY);
  return raw === 'expert' ? 'expert' : 'basic';
})());
const isEvaluationExpert = computed(() => evaluationUiMode.value === 'expert');
const evaluationBasicHidden = [
  'Выбор конкретных forecast run из базы',
  'baseline action code, tag и строгий strict intersection',
  'DM-test, bootstrap и размер блока L',
];
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();

const loadingDevices = ref(false);
const loadingHistory = ref(false);
const loadingDetail = ref(false);
const loadingForecastRuns = ref(false);
const runningEvaluation = ref(false);
const previewLoading = ref(false);
const downloadKey = ref('');
let evaluationLongTimer = null;

const devices = ref([]);
const forecastRuns = ref([]);
const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});

const { state: filterState } = useTableFiltersState(EVALUATION_FILTERS_KEY, {
  daysBack: 120,
  targetDateFrom: '',
  targetDateTo: '',
  actualDateFrom: '',
  actualDateTo: '',
  selectedForecastRunIds: [],
  selectedMetricScope: '',
  selectedHorizons: ['24h', '7d', '30d'],
  selectedModels: ['sarima', 'lstm', 'ensemble'],
  baselineActionCode: 'no_action',
  runTag: '',
  strictIntersection: true,
  enableStatTests: true,
  bootstrapSamples: 300,
  bootstrapBlockSize: 0,
});
const targetDateFrom = computed({
  get: () => String(filterState.targetDateFrom || ''),
  set: (value) => { filterState.targetDateFrom = String(value || ''); },
});
const targetDateTo = computed({
  get: () => String(filterState.targetDateTo || ''),
  set: (value) => { filterState.targetDateTo = String(value || ''); },
});
const actualDateFrom = computed({
  get: () => String(filterState.actualDateFrom || ''),
  set: (value) => { filterState.actualDateFrom = String(value || ''); },
});
const actualDateTo = computed({
  get: () => String(filterState.actualDateTo || ''),
  set: (value) => { filterState.actualDateTo = String(value || ''); },
});
const selectedForecastRunIds = computed({
  get: () => (Array.isArray(filterState.selectedForecastRunIds) ? filterState.selectedForecastRunIds : []),
  set: (value) => { filterState.selectedForecastRunIds = Array.isArray(value) ? value : []; },
});
const selectedMetricScope = computed({
  get: () => String(filterState.selectedMetricScope || ''),
  set: (value) => { filterState.selectedMetricScope = String(value || ''); },
});
const selectedHorizons = computed({
  get: () => Array.isArray(filterState.selectedHorizons) ? filterState.selectedHorizons : ['24h', '7d', '30d'],
  set: (value) => { filterState.selectedHorizons = Array.isArray(value) ? value : ['24h', '7d', '30d']; },
});
const selectedModels = computed({
  get: () => Array.isArray(filterState.selectedModels) ? filterState.selectedModels : ['sarima', 'lstm', 'ensemble'],
  set: (value) => { filterState.selectedModels = Array.isArray(value) ? value : ['sarima', 'lstm', 'ensemble']; },
});
const baselineActionCode = computed({
  get: () => String(filterState.baselineActionCode || 'no_action'),
  set: (value) => { filterState.baselineActionCode = String(value || 'no_action'); },
});
const runTag = computed({
  get: () => String(filterState.runTag || ''),
  set: (value) => { filterState.runTag = String(value || ''); },
});
const strictIntersection = computed({
  get: () => Boolean(filterState.strictIntersection ?? true),
  set: (value) => { filterState.strictIntersection = Boolean(value); },
});
const enableStatTests = computed({
  get: () => Boolean(filterState.enableStatTests ?? true),
  set: (value) => { filterState.enableStatTests = Boolean(value); },
});
const bootstrapSamples = computed({
  get: () => Number(filterState.bootstrapSamples ?? 300),
  set: (value) => { filterState.bootstrapSamples = Number(value ?? 300); },
});
const bootstrapBlockSize = computed({
  get: () => Number(filterState.bootstrapBlockSize ?? 0),
  set: (value) => { filterState.bootstrapBlockSize = Number(value ?? 0); },
});
const historyTablePreset = useTablePresetState(EVALUATION_HISTORY_PRESET_KEY, 'all', ['all', 'with_delta', 'high_coverage']);
const artifactTablePreset = useTablePresetState(EVALUATION_ARTIFACT_PRESET_KEY, 'all', ['all', 'csv', 'pdf']);
const deltaMedianMode = ref(false);

const historyRows = ref([]);
const selectedRun = ref(null);
const availabilityPreview = ref(null);

const loadingAny = computed(() => (
  loadingDevices.value || loadingHistory.value || loadingDetail.value || runningEvaluation.value
));

const deviceOptions = computed(() => (
  devices.value.map((d) => ({
    id: d.id,
    serial: d.serial_number || '',
    label: d.serial_number ? `${d.name} (${d.serial_number})` : d.name,
  }))
));

const unwrap = (res) => (Array.isArray(res?.data) ? res.data : (res?.data?.results || []));

const metricMap = {
  cpu_load_total: { label: 'Загрузка CPU' },
  mem_usage_percent: { label: 'Использование памяти' },
  net_bytes_recv: { label: 'Трафик входящий' },
  net_bytes_sent: { label: 'Трафик исходящий' },
  ping_latency_gateway: { label: 'Ping до шлюза' },
  system_temperature: { label: 'Температура системы' },
  storcli_drive_temperature: { label: 'Температура диска RAID' },
  storcli_predictive_failure_count: { label: 'Predictive Failure Count' },
};

const selectedDevice = computed(() => (
  deviceOptions.value.find((row) => row.id === selectedDeviceId.value) || null
));

const forecastRunOptions = computed(() => {
  const seen = new Set();
  const rows = [];
  for (const run of forecastRuns.value) {
    const id = Number(run?.id);
    if (!Number.isFinite(id) || seen.has(id)) continue;
    seen.add(id);
    rows.push({
      value: id,
      label: `#${id} • ${humanModel(run?.model_kind)} • ${horizonSetLabel(run?.horizon_set)} • ${formatDateTime(run?.created_at)}`,
      meta: run,
    });
  }
  for (const rawId of selectedForecastRunIds.value) {
    const id = Number(rawId);
    if (!Number.isFinite(id) || seen.has(id)) continue;
    seen.add(id);
    rows.push({
      value: id,
      label: `#${id} • запуск вне текущей выборки`,
      meta: null,
    });
  }
  return rows;
});

const selectedSummary = computed(() => selectedRun.value?.summary || {});
const selectedInsights = computed(() => selectedRun.value?.insights || {});
const selectedChartData = computed(() => selectedRun.value?.chart_data || {});
const selectedLatestDecision = computed(() => selectedSummary.value?.latest_decision_run || null);
const selectedConfig = computed(() => selectedRun.value?.config || {});
const deltaChartMode = computed(() => (deltaMedianMode.value ? 'median' : 'mean'));
const availabilitySummary = computed(() => availabilityPreview.value?.summary || {});
const availabilityRows = computed(() => (
  Array.isArray(availabilityPreview.value?.availability_rows)
    ? availabilityPreview.value.availability_rows
    : []
));
const availabilityWarnings = computed(() => (
  Array.isArray(availabilityPreview.value?.warnings)
    ? availabilityPreview.value.warnings
    : []
));
const requiredDatesFilled = computed(() => (
  !!String(targetDateFrom.value || '').trim()
  && !!String(targetDateTo.value || '').trim()
  && !!String(actualDateFrom.value || '').trim()
  && !!String(actualDateTo.value || '').trim()
));
const datesAreOrdered = computed(() => {
  const pairs = [
    [targetDateFrom.value, targetDateTo.value],
    [actualDateFrom.value, actualDateTo.value],
  ];
  return pairs.every(([from, to]) => {
    if (!String(from || '').trim() || !String(to || '').trim()) return true;
    return Date.parse(`${from}T00:00:00`) <= Date.parse(`${to}T00:00:00`);
  });
});
const validationMessage = computed(() => {
  if (!requiredDatesFilled.value) {
    return 'Для оценки нужно явно задать оба интервала: прогноза и факта.';
  }
  if (!datesAreOrdered.value) {
    return 'Дата начала интервала не может быть позже даты окончания.';
  }
  if (!selectedHorizons.value.length || !selectedModels.value.length) {
    return 'Выберите хотя бы один горизонт и одну модель.';
  }
  return '';
});
const canEvaluate = computed(() => (
  requiredDatesFilled.value
  && datesAreOrdered.value
  && selectedHorizons.value.length > 0
  && selectedModels.value.length > 0
));
const targetRangeLabel = computed(() => buildRangeLabel(targetDateFrom.value, targetDateTo.value, 'Укажите даты прогноза'));
const actualRangeLabel = computed(() => buildRangeLabel(actualDateFrom.value, actualDateTo.value, 'Укажите даты факта'));
const previewReadinessLabel = computed(() => {
  const value = String(availabilitySummary.value?.readiness || '').toLowerCase();
  if (value === 'good') return 'Хорошая';
  if (value === 'partial') return 'Частичная';
  if (value === 'weak') return 'Слабая';
  return 'Недостаточно данных';
});
const previewReadinessNote = computed(() => {
  const value = String(availabilitySummary.value?.readiness || '').toLowerCase();
  if (value === 'good') return 'Окно пригодно для полноценного расчёта RMSE/MAE.';
  if (value === 'partial') return 'Сравнение возможно, но покрытие неполное.';
  if (value === 'weak') return 'Расчёт выполнится, но выводы будут нестабильны.';
  return 'Сначала нужно получить больше пересечений прогноза и факта.';
});

const horizonOptions = [
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
  { value: '30d', label: '30 дней' },
];
const modelOptions = [
  { value: 'sarima', label: 'SARIMA' },
  { value: 'lstm', label: 'LSTM' },
  { value: 'ensemble', label: 'Оркестр' },
];
const horizonOrder = { '24h': 1, '7d': 2, '30d': 3 };
const modelOrder = { 'sarima': 1, 'lstm': 2, 'ensemble': 3 };
const metricScopeAll = '__all__';

const bucketMetricRows = computed(() => (
  Array.isArray(selectedChartData.value?.forecast_metrics_by_bucket)
    ? selectedChartData.value.forecast_metrics_by_bucket
    : []
));

const bucketMetricOptions = computed(() => {
  const uniq = new Set();
  const rows = [];
  for (const row of bucketMetricRows.value) {
    const code = String(row?.metric_code || '').trim();
    if (!code || uniq.has(code)) continue;
    uniq.add(code);
    rows.push({
      value: code,
      label: humanMetric(code),
    });
  }
  rows.sort((a, b) => a.label.localeCompare(b.label, 'ru'));
  return [
    { value: metricScopeAll, label: 'Все метрики (смешанный итог)' },
    ...rows,
  ];
});

const activeMetricScope = computed(() => {
  const selected = String(selectedMetricScope.value || '').trim();
  const available = new Set(bucketMetricOptions.value.map((row) => row.value));
  if (selected && available.has(selected)) return selected;
  return bucketMetricOptions.value[1]?.value || metricScopeAll;
});

const selectedMetricScopeLabel = computed(() => {
  const match = bucketMetricOptions.value.find((row) => row.value === activeMetricScope.value);
  return match?.label || 'Все метрики';
});

const modelChartRows = computed(() => {
  const rows = activeMetricScope.value === metricScopeAll
    ? selectedChartData.value?.forecast_metrics_by_model_horizon
    : bucketMetricRows.value.filter((row) => String(row?.metric_code || '') === activeMetricScope.value);
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => Number.isFinite(Number(row?.rmse)) || Number.isFinite(Number(row?.mae)))
    .slice()
    .sort((a, b) => {
      const horizonCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
      if (horizonCmp !== 0) return horizonCmp;
      return (modelOrder[String(a?.model_kind || '')] || 99) - (modelOrder[String(b?.model_kind || '')] || 99);
    });
});

const probabilisticRows = computed(() => {
  const rows = activeMetricScope.value === metricScopeAll
    ? (
      Array.isArray(selectedChartData.value?.forecast_prob_metrics_by_model_horizon)
        ? selectedChartData.value?.forecast_prob_metrics_by_model_horizon
        : selectedChartData.value?.forecast_metrics_by_model_horizon
    )
    : bucketMetricRows.value.filter((row) => String(row?.metric_code || '') === activeMetricScope.value);
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => Number.isFinite(Number(row?.pinball_avg)))
    .slice()
    .sort((a, b) => {
      const horizonCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
      if (horizonCmp !== 0) return horizonCmp;
      return (modelOrder[String(a?.model_kind || '')] || 99) - (modelOrder[String(b?.model_kind || '')] || 99);
    });
});

const calibrationRows = computed(() => {
  const rows = activeMetricScope.value === metricScopeAll
    ? (
      Array.isArray(selectedChartData.value?.forecast_interval_calibration_by_model_horizon)
        ? selectedChartData.value?.forecast_interval_calibration_by_model_horizon
        : selectedChartData.value?.forecast_metrics_by_model_horizon
    )
    : bucketMetricRows.value.filter((row) => String(row?.metric_code || '') === activeMetricScope.value);
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => Number.isFinite(Number(row?.picp80)) || Number.isFinite(Number(row?.ace80)))
    .slice()
    .sort((a, b) => {
      const horizonCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
      if (horizonCmp !== 0) return horizonCmp;
      return (modelOrder[String(a?.model_kind || '')] || 99) - (modelOrder[String(b?.model_kind || '')] || 99);
    });
});

const deltaChartRows = computed(() => {
  const rows = selectedChartData.value?.decision_delta_r_by_horizon;
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => Number.isFinite(Number(row?.delta_r_mean)) || Number.isFinite(Number(row?.share_positive)))
    .slice()
    .sort((a, b) => (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99));
});

function finiteOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function pickAggregation(row, baseKey) {
  const mode = deltaChartMode.value === 'median' ? 'median' : 'mean';
  return finiteOrNull(row?.[`${baseKey}_${mode}`]);
}

const economicHorizonRows = computed(() => (
  deltaChartRows.value.map((row) => {
    const delta = pickAggregation(row, 'delta_r') ?? finiteOrNull(row?.delta_r_median) ?? finiteOrNull(row?.delta_r_mean);
    let expectedWithout = pickAggregation(row, 'expected_loss_without_system');
    let expectedWith = pickAggregation(row, 'expected_loss_with_system');
    let deltaPct = pickAggregation(row, 'delta_r_pct');

    if (expectedWithout === null && expectedWith !== null && delta !== null) {
      expectedWithout = expectedWith + delta;
    }
    if (expectedWith === null && expectedWithout !== null && delta !== null) {
      expectedWith = expectedWithout - delta;
    }
    if (deltaPct === null && expectedWithout !== null && Math.abs(expectedWithout) > 1e-9 && delta !== null) {
      deltaPct = delta / expectedWithout;
    }

    return {
      horizon: row?.horizon,
      samples: Number(row?.samples ?? 0),
      expectedWithout,
      expectedWith,
      delta,
      deltaPct,
      sharePositive: finiteOrNull(row?.share_positive),
      raw: row,
    };
  })
));

const economicChartHasLossColumns = computed(() => (
  economicHorizonRows.value.some((row) => row.expectedWithout !== null && row.expectedWith !== null)
));
const sarimaVariantRows = computed(() => {
  const dedicatedRows = selectedChartData.value?.forecast_metrics_by_sarima_variant_horizon;
  const rows = Array.isArray(dedicatedRows)
    ? dedicatedRows
    : selectedChartData.value?.forecast_metrics_by_variant_horizon;
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => String(row?.model_kind || '').toLowerCase() === 'sarima')
    .filter((row) => String(row?.variant_key || '') !== 'sarima:unknown')
    .filter((row) => Number.isFinite(Number(row?.rmse)) || Number.isFinite(Number(row?.mae)) || Number.isFinite(Number(row?.mape)))
    .slice()
    .sort((a, b) => {
      const hCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
      if (hCmp !== 0) return hCmp;
      return String(a?.variant_label || '').localeCompare(String(b?.variant_label || ''));
    });
});
const dmRows = computed(() => {
  const rows = selectedChartData.value?.stat_tests_dm;
  if (!Array.isArray(rows)) return [];
  return rows.slice().sort((a, b) => {
    const hCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
    if (hCmp !== 0) return hCmp;
    const pA = Number.isFinite(Number(a?.p_value)) ? Number(a.p_value) : 1e9;
    const pB = Number.isFinite(Number(b?.p_value)) ? Number(b.p_value) : 1e9;
    if (pA !== pB) return pA - pB;
    const modelPairA = `${String(a?.model_a || '')}:${String(a?.model_b || '')}`;
    const modelPairB = `${String(b?.model_a || '')}:${String(b?.model_b || '')}`;
    return modelPairA.localeCompare(modelPairB);
  });
});
const bootstrapRows = computed(() => {
  const rows = selectedChartData.value?.bootstrap_ci;
  if (!Array.isArray(rows)) return [];
  return rows.slice().sort((a, b) => {
    const metricA = String(a?.metric || '');
    const metricB = String(b?.metric || '');
    if (metricA !== metricB) return metricA.localeCompare(metricB);
    const hCmp = (horizonOrder[String(a?.horizon || '')] || 99) - (horizonOrder[String(b?.horizon || '')] || 99);
    if (hCmp !== 0) return hCmp;
    return (modelOrder[String(a?.model_kind || '')] || 99) - (modelOrder[String(b?.model_kind || '')] || 99);
  });
});
const historyTablePresets = [
  { value: 'all', label: 'Все', description: 'Показывает все запускы верификации.' },
  { value: 'with_delta', label: 'С ΔR', description: 'Только запуски, где рассчитан экономический эффект ΔR.' },
  { value: 'high_coverage', label: 'Покрытие >= 50%', description: 'Запуски с достаточным покрытием фактическими данными.' },
];
const artifactTablePresets = [
  { value: 'all', label: 'Все', description: 'CSV, PDF и дополнительные служебные файлы.' },
  { value: 'csv', label: 'Только CSV', description: 'Табличные артефакты для анализа в Excel/ноутбуках.' },
  { value: 'pdf', label: 'Только PDF', description: 'Итоговые отчеты в формате PDF.' },
];
const filteredHistoryRows = computed(() => {
  if (historyTablePreset.value === 'with_delta') {
    return historyRows.value.filter((row) => Number.isFinite(Number(row?.summary?.delta_r?.delta_r_mean)));
  }
  if (historyTablePreset.value === 'high_coverage') {
    return historyRows.value.filter((row) => Number(row?.summary?.forecast_coverage ?? 0) >= 0.5);
  }
  return historyRows.value;
});

const summaryCards = computed(() => {
  const latest = selectedLatestDecision.value;
  const bestRmse = selectedInsights.value?.best_rmse;
  const pointsCompared = Number(selectedSummary.value?.forecast_points_compared ?? selectedSummary.value?.forecast_points_with_actual ?? 0);
  const pointsRaw = Number(selectedSummary.value?.forecast_points_with_actual_raw ?? pointsCompared);
  const pointsTotal = Number(selectedSummary.value?.forecast_points_total ?? 0);
  const decisionRunsUsed = Number(selectedSummary.value?.decision_runs_used ?? 0);
  const decisionRunsTotal = Number(selectedSummary.value?.decision_runs_total ?? 0);
  const deltaSummary = selectedSummary.value?.delta_r || {};
  return [
    {
      title: 'Прогнозные точки',
      value: `${pointsCompared} из ${pointsTotal}`,
      note: `Покрытие ${percent(selectedSummary.value?.forecast_coverage)} • raw: ${pointsRaw}`,
      tooltipLines: [
        'Сколько прогнозных точек удалось сравнить с фактом внутри выбранного evaluation-run.',
        'Чем выше покрытие, тем надёжнее выводы о качестве моделей.',
        `Сейчас: ${pointsCompared} сравнено из ${pointsTotal} точек.`,
      ],
    },
    {
      title: 'СППР запуски',
      value: `${decisionRunsUsed} из ${decisionRunsTotal}`,
      note: 'Учтены в расчете эффекта',
      tooltipLines: [
        'Это не прогнозные точки, а реальные расчёты СППР, по которым удалось сравнить рекомендованное действие с baseline.',
        'Если запусков мало, график экономического эффекта нужно читать осторожно.',
        `Сейчас: ${decisionRunsUsed} использовано из ${decisionRunsTotal}.`,
      ],
    },
    {
      title: 'Экономия на последнем запуске СППР',
      value: latest ? money(latest.delta_r) : 'Нет данных',
      note: latest ? `${humanHorizon(latest.horizon)} • ${formatDateTime(latest.created_at)}` : 'Нет завершенного запуска СППР',
      tooltipLines: [
        'Берётся только последний успешный DecisionRun внутри выбранного evaluation-run.',
        'Формула: ΔR = expected_loss baseline - expected_loss рекомендованного действия.',
        latest
          ? `Сейчас: ${money(latest.expected_loss_without_system)} - ${money(latest.expected_loss_with_system)} = ${money(latest.delta_r)}.`
          : 'Для выбранного запуска пока нет завершённого DecisionRun.',
      ],
    },
    {
      title: 'Средняя экономия',
      value: money(deltaSummary?.delta_r_mean),
      note: 'Средний эффект по выбранному evaluation-run',
      tooltipLines: [
        'Это среднее значение ΔR по всем использованным запускам СППР.',
        'Среднее удобно для общего итога, но оно чувствительно к очень большим выигрышам/потерям.',
        `Медиана для этого run: ${money(deltaSummary?.delta_r_median)}.`,
      ],
    },
    {
      title: 'Эффективность рекомендаций',
      value: percent(deltaSummary?.share_positive),
      note: 'Доля запусков, где рекомендации дали экономию',
      tooltipLines: [
        'Показывает, в какой доле запусков ΔR оказался положительным.',
        'Это более устойчивый показатель, чем среднее, когда есть выбросы.',
        'Например, 60% означает: в 6 из 10 запусков рекомендации были выгоднее baseline.',
      ],
    },
    {
      title: 'Лучшая связка по RMSE',
      value: bestRmse ? `${humanModel(bestRmse.model_kind)} / ${humanHorizon(bestRmse.horizon)}` : 'Нет данных',
      note: bestRmse ? `RMSE ${num(bestRmse.rmse, 4)}` : 'Недостаточно фактических значений',
      tooltipLines: [
        'Ищется модель/горизонт с минимальным RMSE среди всех сравнимых результатов.',
        'RMSE сильнее штрафует крупные ошибки, поэтому хорошо показывает устойчивость прогноза к большим промахам.',
        'Сравнивать корректно только между моделями на одном и том же наборе фактов.',
      ],
    },
  ];
});

const probabilisticCards = computed(() => {
  const bestPinball = probabilisticRows.value
    .filter((row) => Number.isFinite(Number(row?.pinball_avg)))
    .slice()
    .sort((a, b) => Number(a.pinball_avg) - Number(b.pinball_avg))[0] || null;
  const bestCalibration = calibrationRows.value
    .filter((row) => Number.isFinite(Number(row?.ace80)))
    .slice()
    .sort((a, b) => Math.abs(Number(a.ace80)) - Math.abs(Number(b.ace80)))[0] || null;
  const picpValues = calibrationRows.value
    .map((row) => Number(row?.picp80))
    .filter((v) => Number.isFinite(v));
  const aceValues = calibrationRows.value
    .map((row) => Number(row?.ace80))
    .filter((v) => Number.isFinite(v));
  const winklerValues = calibrationRows.value
    .map((row) => Number(row?.winkler80))
    .filter((v) => Number.isFinite(v));
  const meanErrorValues = modelChartRows.value
    .map((row) => Number(row?.mean_error))
    .filter((v) => Number.isFinite(v));

  const avgPicp = picpValues.length ? (picpValues.reduce((a, b) => a + b, 0) / picpValues.length) : null;
  const avgAce = aceValues.length ? (aceValues.reduce((a, b) => a + b, 0) / aceValues.length) : null;
  const avgWinkler = winklerValues.length ? (winklerValues.reduce((a, b) => a + b, 0) / winklerValues.length) : null;
  const avgMeanError = meanErrorValues.length ? (meanErrorValues.reduce((a, b) => a + b, 0) / meanErrorValues.length) : null;

  return [
    {
      title: 'Лучшая связка по Pinball',
      value: bestPinball ? `${humanModel(bestPinball.model_kind)} / ${humanHorizon(bestPinball.horizon)}` : 'Нет данных',
      note: bestPinball
        ? `${activeMetricScope.value === metricScopeAll ? 'Все метрики' : humanMetric(activeMetricScope.value)} • Pinball avg ${num(bestPinball.pinball_avg, 4)}`
        : 'Недостаточно валидных квантильных точек',
      tooltipLines: [
        'Pinball оценивает качество квантильных прогнозов q10/q50/q90.',
        'Чем меньше Pinball, тем лучше модель предсказывает нижнюю, центральную и верхнюю границы.',
        'Эта карточка показывает лучшую модель по среднему Pinball.',
      ],
    },
    {
      title: 'Лучшая калибровка интервала',
      value: bestCalibration ? `${humanModel(bestCalibration.model_kind)} / ${humanHorizon(bestCalibration.horizon)}` : 'Нет данных',
      note: bestCalibration
        ? `${activeMetricScope.value === metricScopeAll ? 'Все метрики' : humanMetric(activeMetricScope.value)} • ACE80 ${percent(bestCalibration.ace80)} • PICP80 ${percent(bestCalibration.picp80)}`
        : 'Недостаточно интервалов p10/p90',
      tooltipLines: [
        'Интервал считается хорошим, если реальный факт попадает внутрь него примерно в 80% случаев.',
        'ACE80 показывает отклонение от этой цели: чем ближе к нулю, тем лучше.',
        'PICP80 показывает фактическое покрытие интервала [p10, p90].',
      ],
    },
    {
      title: 'Средний bias (ME)',
      value: avgMeanError !== null ? num(avgMeanError, 4) : 'Нет данных',
      note: avgMeanError === null
        ? 'Нужны прогноз и факт'
        : (avgMeanError > 0 ? 'Плюс = модель завышает прогноз' : avgMeanError < 0 ? 'Минус = модель занижает прогноз' : 'Около нуля = систематического сдвига почти нет'),
      tooltipLines: [
        'Mean Error = predicted - actual.',
        'Положительное значение означает систематическое завышение прогноза.',
        'Отрицательное значение означает систематическое занижение прогноза.',
        'Этот показатель не заменяет RMSE/MAE, а показывает именно направленный сдвиг модели.',
      ],
    },
    {
      title: 'Средний PICP80',
      value: avgPicp !== null ? percent(avgPicp) : 'Нет данных',
      note: 'Целевая калибровка: 80.0%',
      tooltipLines: [
        'PICP80 = доля фактических значений, которые попали внутрь прогнозного интервала [p10, p90].',
        'Цель для интервала 80%: около 80%.',
        'Ниже 80%: интервалы слишком узкие и самоуверенные.',
        'Сильно выше 80%: интервалы слишком широкие и малоинформативные.',
      ],
    },
    {
      title: 'Средний Winkler80',
      value: avgWinkler !== null ? num(avgWinkler, 4) : 'Нет данных',
      note: avgAce !== null ? `Средний ACE80 ${percent(avgAce)}` : 'Оценка интервала по ширине и штрафам',
      tooltipLines: [
        'Winkler80 оценивает качество интервала: его ширину плюс штраф, если факт вышел за границы.',
        'Чем меньше Winkler80, тем лучше интервал: он либо узкий и точный, либо хотя бы редко промахивается.',
        'Высокий Winkler80 означает слишком широкий интервал или частые выходы факта за его границы.',
      ],
    },
  ];
});
const significanceCards = computed(() => {
  const dmTotal = dmRows.value.length;
  const dmSignificant = dmRows.value.filter((row) => isSignificantDm(row)).length;
  const bestDm = dmRows.value
    .filter((row) => Number.isFinite(Number(row?.p_value)))
    .sort((a, b) => Number(a.p_value) - Number(b.p_value))[0] || null;
  const strictEnabled = Boolean(selectedSummary.value?.strict_intersection_enabled ?? selectedConfig.value?.strict_intersection ?? false);
  const strictKeys = Number(selectedSummary.value?.strict_intersection_keys ?? 0);
  return [
    {
      title: 'Пары DM-test',
      value: `${dmTotal}`,
      note: `Значимых (p < 0.05): ${dmSignificant}`,
      tooltipLines: [
        'DM-test сравнивает ошибки двух моделей на одном и том же наборе фактов.',
        'Значимых пар столько, сколько сравнений показали отличие с p-value < 0.05.',
        'Если значимых пар мало, говорить о преимуществе одной модели нужно осторожно.',
      ],
    },
    {
      title: 'Минимальный p-value',
      value: bestDm ? pValue(bestDm.p_value) : 'Нет данных',
      note: bestDm ? `${humanModel(bestDm.model_a)} vs ${humanModel(bestDm.model_b)} • ${humanHorizon(bestDm.horizon)}` : 'Пока нет статистики',
      tooltipLines: [
        'Это самое сильное статистическое различие между двумя моделями в текущем run.',
        'Чем меньше p-value, тем увереннее различие неслучайно.',
        'Обычно порог значимости: p < 0.05.',
      ],
    },
    {
      title: 'Bootstrap CI строк',
      value: `${bootstrapRows.value.length}`,
      note: `B: ${bootstrapRows.value[0]?.bootstrap_samples ?? '-'} • L: ${bootstrapRows.value[0]?.bootstrap_block_size ?? 'auto'}`,
      tooltipLines: [
        'Сколько строк метрик качества получили доверительный интервал CI95 через bootstrap.',
        'B = число bootstrap-итераций, L = размер временного блока.',
        'Чем уже CI95, тем устойчивее оценка качества прогноза.',
      ],
    },
    {
      title: 'Режим сравнения',
      value: strictEnabled ? 'Strict intersection' : 'Полное покрытие',
      note: strictEnabled ? `Общих ключей: ${strictKeys}` : 'Без пересечения по ключам',
      tooltipLines: [
        'Strict intersection означает: модели сравниваются только на тех же временных бакетах, где прогноз и факт есть у всех выбранных моделей.',
        'Это наиболее корректный научный режим сравнения.',
        'Без strict intersection покрытие выше, но сравнение между моделями менее строгое.',
      ],
    },
  ];
});

const deltaChartNotes = computed(() => {
  const configuredHorizons = Array.isArray(selectedConfig.value?.horizons) ? selectedConfig.value.horizons : [];
  const existingRows = new Map(
    deltaChartRows.value.map((row) => [String(row?.horizon || ''), row]),
  );
  const notes = economicHorizonRows.value.map((row) => {
    const modeLabel = deltaChartMode.value === 'median' ? 'медиана' : 'среднее';
    return `${humanHorizon(row.horizon)}: N=${row.samples}, ${modeLabel} ΔR ${money(row.delta)}, снижение ${percent(row.deltaPct)}`;
  });
  for (const horizon of configuredHorizons) {
    if (!existingRows.has(horizon)) {
      notes.push(`${humanHorizon(horizon)}: нет DecisionRun с baseline для расчета ΔR`);
    }
  }
  return notes;
});

const modelChartMissingNotes = computed(() => {
  const configuredHorizons = Array.isArray(selectedConfig.value?.horizons) ? selectedConfig.value.horizons : [];
  const configuredModels = Array.isArray(selectedConfig.value?.model_kinds) ? selectedConfig.value.model_kinds : [];
  if (!configuredHorizons.length || !configuredModels.length) return [];
  const existing = new Set(modelChartRows.value.map((row) => `${row.model_kind}:${row.horizon}`));
  const notes = [];
  for (const modelKind of configuredModels) {
    for (const horizon of configuredHorizons) {
      if (existing.has(`${modelKind}:${horizon}`)) continue;
      if (activeMetricScope.value === metricScopeAll) {
        notes.push(`${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет факта для расчета RMSE/MAE/MAPE`);
      } else {
        notes.push(`${humanMetric(activeMetricScope.value)} • ${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет факта для расчета RMSE/MAE/MAPE`);
      }
    }
  }
  return notes;
});

const probabilisticChartMissingNotes = computed(() => {
  const configuredHorizons = Array.isArray(selectedConfig.value?.horizons) ? selectedConfig.value.horizons : [];
  const configuredModels = Array.isArray(selectedConfig.value?.model_kinds) ? selectedConfig.value.model_kinds : [];
  if (!configuredHorizons.length || !configuredModels.length) return [];
  const existing = new Set(probabilisticRows.value.map((row) => `${row.model_kind}:${row.horizon}`));
  const notes = [];
  for (const modelKind of configuredModels) {
    for (const horizon of configuredHorizons) {
      if (existing.has(`${modelKind}:${horizon}`)) continue;
      if (activeMetricScope.value === metricScopeAll) {
        notes.push(`${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет данных для Pinball по выбранному окну.`);
      } else {
        notes.push(`${humanMetric(activeMetricScope.value)} • ${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет данных для Pinball.`);
      }
    }
  }
  return notes;
});

const calibrationChartMissingNotes = computed(() => {
  const configuredHorizons = Array.isArray(selectedConfig.value?.horizons) ? selectedConfig.value.horizons : [];
  const configuredModels = Array.isArray(selectedConfig.value?.model_kinds) ? selectedConfig.value.model_kinds : [];
  if (!configuredHorizons.length || !configuredModels.length) return [];
  const existing = new Set(calibrationRows.value.map((row) => `${row.model_kind}:${row.horizon}`));
  const notes = [];
  for (const modelKind of configuredModels) {
    for (const horizon of configuredHorizons) {
      if (existing.has(`${modelKind}:${horizon}`)) continue;
      if (activeMetricScope.value === metricScopeAll) {
        notes.push(`${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет интервалов p10/p90 для калибровки.`);
      } else {
        notes.push(`${humanMetric(activeMetricScope.value)} • ${humanModel(modelKind)} / ${humanHorizon(horizon)}: пока нет интервалов p10/p90.`);
      }
    }
  }
  return notes;
});

const sarimaVariantMissingNotes = computed(() => {
  const configuredHorizons = Array.isArray(selectedConfig.value?.horizons) ? selectedConfig.value.horizons : [];
  const configuredModels = Array.isArray(selectedConfig.value?.model_kinds) ? selectedConfig.value.model_kinds : [];
  if (!configuredHorizons.length || !configuredModels.includes('sarima')) return [];
  const existingByHorizon = new Set(sarimaVariantRows.value.map((row) => String(row.horizon || '')));
  const notes = [];
  for (const horizon of configuredHorizons) {
    if (existingByHorizon.has(horizon)) continue;
    notes.push(`SARIMA / ${humanHorizon(horizon)}: режимы сезонности еще не сравниваются, потому что нет оцененных точек с фактом`);
  }
  return notes;
});

const modelChartData = computed(() => ({
  labels: modelChartRows.value.map((row) => `${humanModel(row.model_kind)} • ${humanHorizon(row.horizon)}`),
  datasets: [
    {
      type: 'bar',
      label: 'RMSE',
      data: modelChartRows.value.map((row) => Number(row.rmse ?? 0)),
      backgroundColor: 'rgba(37, 99, 235, 0.85)',
      borderRadius: 6,
    },
    {
      type: 'bar',
      label: 'MAE',
      data: modelChartRows.value.map((row) => Number(row.mae ?? 0)),
      backgroundColor: 'rgba(124, 58, 237, 0.78)',
      borderRadius: 6,
    },
  ],
}));

const modelChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  scales: {
    x: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      ticks: { maxRotation: 45, minRotation: 30 },
    },
    y: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      beginAtZero: true,
    },
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${ctx.dataset.label}: ${num(ctx.raw, 4)}`,
        footer: () => 'Ниже значение = лучше качество прогноза.',
      },
    },
  },
};

const probabilisticChartData = computed(() => ({
  labels: probabilisticRows.value.map((row) => `${humanModel(row.model_kind)} • ${humanHorizon(row.horizon)}`),
  datasets: [
    {
      type: 'bar',
      label: 'Pinball q10',
      data: probabilisticRows.value.map((row) => Number(row.pinball_q10 ?? 0)),
      backgroundColor: 'rgba(14, 165, 233, 0.78)',
      borderRadius: 6,
    },
    {
      type: 'bar',
      label: 'Pinball q50',
      data: probabilisticRows.value.map((row) => Number(row.pinball_q50 ?? 0)),
      backgroundColor: 'rgba(168, 85, 247, 0.78)',
      borderRadius: 6,
    },
    {
      type: 'bar',
      label: 'Pinball q90',
      data: probabilisticRows.value.map((row) => Number(row.pinball_q90 ?? 0)),
      backgroundColor: 'rgba(217, 119, 6, 0.78)',
      borderRadius: 6,
    },
    {
      type: 'line',
      label: 'Pinball avg',
      data: probabilisticRows.value.map((row) => Number(row.pinball_avg ?? 0)),
      borderColor: 'rgba(15, 23, 42, 0.95)',
      backgroundColor: 'rgba(15, 23, 42, 0.15)',
      pointRadius: 3,
      tension: 0.25,
    },
  ],
}));

const probabilisticChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  interaction: { mode: 'index', intersect: false },
  scales: {
    x: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      ticks: { maxRotation: 45, minRotation: 24 },
    },
    y: {
      beginAtZero: true,
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      title: { display: true, text: 'Pinball loss' },
    },
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${ctx.dataset.label}: ${num(ctx.raw, 4)}`,
        footer: () => 'Ниже Pinball = лучше квантильный прогноз.',
      },
    },
  },
};

const calibrationChartData = computed(() => ({
  labels: calibrationRows.value.map((row) => `${humanModel(row.model_kind)} • ${humanHorizon(row.horizon)}`),
  datasets: [
    {
      type: 'bar',
      label: 'PICP80 (факт), %',
      data: calibrationRows.value.map((row) => Number(row.picp80 ?? 0) * 100),
      backgroundColor: 'rgba(16, 185, 129, 0.78)',
      borderRadius: 6,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'Цель (80%)',
      data: calibrationRows.value.map(() => 80),
      borderColor: 'rgba(59, 130, 246, 0.95)',
      borderDash: [6, 4],
      pointRadius: 0,
      tension: 0,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'ACE80, %',
      data: calibrationRows.value.map((row) => Number(row.ace80 ?? 0) * 100),
      borderColor: 'rgba(239, 68, 68, 0.95)',
      backgroundColor: 'rgba(239, 68, 68, 0.14)',
      pointRadius: 4,
      tension: 0.24,
      yAxisID: 'y1',
    },
  ],
}));

const calibrationChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  interaction: { mode: 'index', intersect: false },
  scales: {
    x: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      ticks: { maxRotation: 45, minRotation: 24 },
    },
    y: {
      min: 0,
      max: 100,
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      title: { display: true, text: 'PICP80, %' },
      ticks: {
        callback: (value) => `${value}%`,
      },
    },
    y1: {
      position: 'right',
      min: 0,
      max: 100,
      grid: { drawOnChartArea: false },
      title: { display: true, text: 'ACE80, %' },
      ticks: {
        callback: (value) => `${value}%`,
      },
    },
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${ctx.dataset.label}: ${num(ctx.raw, 2)}%`,
        footer: (items) => {
          const row = calibrationRows.value[items?.[0]?.dataIndex ?? -1];
          if (!row) return '';
          return `PICP ближе к 80%, ACE ближе к 0%. N=${row.samples ?? 0}`;
        },
      },
    },
  },
};

const deltaChartData = computed(() => {
  const rows = economicHorizonRows.value;
  const baseDatasets = [];
  if (economicChartHasLossColumns.value) {
    baseDatasets.push(
      {
        type: 'bar',
        label: 'Ожидаемые потери без СППР',
        data: rows.map((row) => row.expectedWithout ?? 0),
        backgroundColor: 'rgba(100, 116, 139, 0.70)',
        borderRadius: 6,
        yAxisID: 'y',
      },
      {
        type: 'bar',
        label: 'Ожидаемые потери с рекомендацией',
        data: rows.map((row) => row.expectedWith ?? 0),
        backgroundColor: 'rgba(59, 130, 246, 0.72)',
        borderRadius: 6,
        yAxisID: 'y',
      },
    );
  }
  baseDatasets.push({
    type: 'bar',
    label: deltaChartMode.value === 'median' ? 'Экономия ΔR, медиана' : 'Экономия ΔR, среднее',
    data: rows.map((row) => row.delta ?? 0),
    backgroundColor: rows.map((row) => (Number(row.delta ?? 0) >= 0 ? 'rgba(16, 185, 129, 0.86)' : 'rgba(239, 68, 68, 0.86)')),
    borderRadius: 6,
    yAxisID: 'y',
  });
  return {
    labels: rows.map((row) => humanHorizon(row.horizon)),
    datasets: baseDatasets,
  };
});

const deltaChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  interaction: { mode: 'index', intersect: false },
  scales: {
    x: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
    },
    y: {
      position: 'left',
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      title: { display: true, text: 'Ожидаемые потери / экономия' },
      ticks: {
        callback: (value) => money(value),
      },
    },
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          return ` ${ctx.dataset.label}: ${money(ctx.raw)}`;
        },
        afterBody: (items) => {
          const row = economicHorizonRows.value[items?.[0]?.dataIndex ?? -1];
          if (!row) return [];
          return [
            `N запусков: ${row.samples ?? 0}`,
            `Без СППР: ${money(row.expectedWithout)}`,
            `С рекомендацией: ${money(row.expectedWith)}`,
            `Экономия ΔR: ${money(row.delta)}`,
            `Снижение потерь: ${percent(row.deltaPct)}`,
            `Доля ΔR > 0: ${percent(row.sharePositive)}`,
          ];
        },
        footer: () => 'Положительный ΔR означает, что СППР снижает ожидаемые потери.',
      },
    },
  },
};

const sarimaVariantChartData = computed(() => ({
  labels: sarimaVariantRows.value.map((row) => `${humanHorizon(row.horizon)} • ${row.variant_label || '-'}`),
  datasets: [
    {
      type: 'bar',
      label: 'RMSE',
      data: sarimaVariantRows.value.map((row) => Number(row.rmse ?? 0)),
      backgroundColor: 'rgba(14, 165, 233, 0.84)',
      borderRadius: 6,
      yAxisID: 'y',
    },
    {
      type: 'bar',
      label: 'MAE',
      data: sarimaVariantRows.value.map((row) => Number(row.mae ?? 0)),
      backgroundColor: 'rgba(168, 85, 247, 0.78)',
      borderRadius: 6,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'MAPE (%)',
      data: sarimaVariantRows.value.map((row) => Number(row.mape ?? 0) * 100),
      borderColor: 'rgba(217, 119, 6, 0.95)',
      backgroundColor: 'rgba(217, 119, 6, 0.18)',
      yAxisID: 'y1',
      tension: 0.24,
      pointRadius: 4,
    },
  ],
}));

const sarimaVariantChartOptions = {
  maintainAspectRatio: false,
  responsive: true,
  interaction: { mode: 'index', intersect: false },
  scales: {
    x: {
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      ticks: { maxRotation: 45, minRotation: 24 },
    },
    y: {
      position: 'left',
      beginAtZero: true,
      grid: { color: 'rgba(148, 163, 184, 0.18)' },
      title: { display: true, text: 'RMSE / MAE' },
    },
    y1: {
      position: 'right',
      beginAtZero: true,
      grid: { drawOnChartArea: false },
      title: { display: true, text: 'MAPE, %' },
      ticks: {
        callback: (value) => `${value}%`,
      },
    },
  },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          if (ctx.dataset.yAxisID === 'y1') {
            return ` ${ctx.dataset.label}: ${num(ctx.raw, 2)}%`;
          }
          return ` ${ctx.dataset.label}: ${num(ctx.raw, 4)}`;
        },
        footer: () => 'Сравнивайте режимы SARIMA внутри одного горизонта: ниже = лучше.',
      },
    },
  },
};

const artifactRows = computed(() => {
  const rows = selectedRun.value?.artifacts || {};
  return Object.entries(rows).map(([key, path]) => {
    const text = String(path || '');
    const fileName = text.split('/').pop() || text;
    return {
      key,
      path: text,
      file_name: fileName,
    };
  });
});
const filteredArtifactRows = computed(() => {
  if (artifactTablePreset.value === 'csv') {
    return artifactRows.value.filter((row) => String(row.file_name || '').toLowerCase().endsWith('.csv'));
  }
  if (artifactTablePreset.value === 'pdf') {
    return artifactRows.value.filter((row) => String(row.file_name || '').toLowerCase().endsWith('.pdf'));
  }
  return artifactRows.value;
});

function formatDateTime(value) {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(dt);
}

function num(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function pValue(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  if (n < 0.0001) return n.toExponential(2);
  return n.toFixed(4);
}

function percent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${(n * 100).toFixed(1)}%`;
}

function money(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return num(n, 2);
}

function humanModel(value) {
  const raw = String(value || '').toLowerCase();
  if (raw === 'sarima') return 'SARIMA';
  if (raw === 'lstm') return 'LSTM';
  if (raw === 'ensemble') return 'Оркестр';
  return raw ? raw.toUpperCase() : '-';
}

function humanHorizon(value) {
  const raw = String(value || '').toLowerCase();
  if (raw === '24h') return '24 часа';
  if (raw === '7d') return '7 дней';
  if (raw === '30d') return '30 дней';
  return raw || '-';
}

function horizonSetLabel(rawValue) {
  const rows = Array.isArray(rawValue)
    ? rawValue
    : String(rawValue || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  if (!rows.length) return 'горизонты не указаны';
  return rows.map((item) => humanHorizon(item)).join(', ');
}

function humanMetric(code) {
  const raw = String(code || '').trim();
  return metricMap[raw]?.label || raw || 'Метрика';
}

function isSignificantDm(row) {
  if (!row || typeof row !== 'object') return false;
  if (row.significant_005 === true) return true;
  const p = Number(row.p_value);
  return Number.isFinite(p) && p < 0.05;
}

function buildRangeLabel(from, to, fallback) {
  const start = String(from || '').trim();
  const end = String(to || '').trim();
  if (!start || !end) return fallback;
  const startTs = Date.parse(`${start}T00:00:00`);
  const endTs = Date.parse(`${end}T00:00:00`);
  if (!Number.isFinite(startTs) || !Number.isFinite(endTs)) return fallback;
  const diffDays = Math.max(1, Math.ceil((endTs - startTs) / 86400000) + 1);
  return `${start} → ${end} • ${diffDays} дн.`;
}

function deriveDaysBackFromTargetRange() {
  const start = String(targetDateFrom.value || '').trim();
  const end = String(targetDateTo.value || '').trim();
  if (!start || !end) return 120;
  const startTs = Date.parse(`${start}T00:00:00`);
  const endTs = Date.parse(`${end}T00:00:00`);
  if (!Number.isFinite(startTs) || !Number.isFinite(endTs)) return 120;
  const diffDays = Math.max(1, Math.ceil(Math.abs(endTs - startTs) / 86400000) + 1);
  return diffDays;
}

function copyForecastRangeToActual() {
  actualDateFrom.value = targetDateFrom.value;
  actualDateTo.value = targetDateTo.value;
}

function isoDateOffset(baseIso, days) {
  const baseTs = Date.parse(baseIso);
  if (!Number.isFinite(baseTs)) return '';
  return new Date(baseTs - (Math.max(1, Number(days) || 1) - 1) * 86400000).toISOString().slice(0, 10);
}

function applyEvaluationConfig(config = {}, rowMeta = {}) {
  if (!config || typeof config !== 'object') return;
  if (config.serial) {
    const match = deviceOptions.value.find((row) => row.serial === String(config.serial));
    if (match) selectedDeviceId.value = match.id;
  }
  const generatedAt = String(rowMeta.generated_at || '').trim();
  const fallbackDays = Math.max(1, Number(config.days_back) || 120);
  const fallbackEnd = generatedAt ? generatedAt.slice(0, 10) : '';
  const fallbackStart = generatedAt ? isoDateOffset(generatedAt, fallbackDays) : '';
  targetDateFrom.value = String(config.target_date_from || fallbackStart || '').slice(0, 10);
  targetDateTo.value = String(config.target_date_to || fallbackEnd || '').slice(0, 10);
  actualDateFrom.value = String(config.actual_date_from || targetDateFrom.value || fallbackStart || '').slice(0, 10);
  actualDateTo.value = String(config.actual_date_to || targetDateTo.value || fallbackEnd || '').slice(0, 10);
  selectedHorizons.value = Array.isArray(config.horizons) && config.horizons.length ? config.horizons : selectedHorizons.value;
  selectedModels.value = Array.isArray(config.model_kinds) && config.model_kinds.length ? config.model_kinds : selectedModels.value;
  selectedForecastRunIds.value = Array.isArray(config.forecast_run_ids) ? config.forecast_run_ids.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : selectedForecastRunIds.value;
  baselineActionCode.value = String(config.baseline_action_code || baselineActionCode.value || 'no_action');
  runTag.value = String(config.tag || runTag.value || '');
  strictIntersection.value = typeof config.strict_intersection === 'boolean' ? config.strict_intersection : strictIntersection.value;
  enableStatTests.value = typeof config.enable_stat_tests === 'boolean' ? config.enable_stat_tests : enableStatTests.value;
  if (config.bootstrap_samples != null) bootstrapSamples.value = Number(config.bootstrap_samples) || bootstrapSamples.value;
  if (config.bootstrap_block_size != null) bootstrapBlockSize.value = Number(config.bootstrap_block_size) || 0;
}

function buildEvaluationPayload() {
  return {
    serial: selectedDevice.value?.serial || null,
    days_back: deriveDaysBackFromTargetRange(),
    target_date_from: String(targetDateFrom.value || '').trim() || null,
    target_date_to: String(targetDateTo.value || '').trim() || null,
    actual_date_from: String(actualDateFrom.value || '').trim() || null,
    actual_date_to: String(actualDateTo.value || '').trim() || null,
    horizons: selectedHorizons.value,
    model_kinds: selectedModels.value,
    forecast_run_ids: selectedForecastRunIds.value,
    baseline_action_code: String(baselineActionCode.value || 'no_action').trim() || 'no_action',
    tag: String(runTag.value || '').trim(),
    strict_intersection: Boolean(strictIntersection.value),
    enable_stat_tests: Boolean(enableStatTests.value),
    bootstrap_samples: Number(bootstrapSamples.value) || 300,
    bootstrap_block_size: Number(bootstrapBlockSize.value) || 0,
  };
}

async function loadDevices() {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = Array.isArray(res.data) ? res.data : [];
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch (err) {
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить устройства', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
}

async function loadForecastRuns() {
  loadingForecastRuns.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-created_at');
    params.set('status', 'success');
    params.set('limit', '200');
    if (selectedDeviceId.value) params.set('device', String(selectedDeviceId.value));
    const res = await apiClient.get(`forecast-runs/?${params.toString()}`);
    forecastRuns.value = unwrap(res);
  } catch (err) {
    forecastRuns.value = [];
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Не удалось загрузить список прогнозных запусков', life: 3200 });
  } finally {
    loadingForecastRuns.value = false;
  }
}

async function loadHistory() {
  loadingHistory.value = true;
  try {
    const res = await apiClient.get('dissertation-evaluation/history/?limit=30');
    historyRows.value = Array.isArray(res.data) ? res.data : [];
    if (!historyRows.value.length) {
      selectedRun.value = null;
    } else {
      applyEvaluationConfig(historyRows.value[0]?.config || {}, historyRows.value[0] || {});
    }
  } catch (err) {
    historyRows.value = [];
    selectedRun.value = null;
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'История evaluation пока недоступна', life: 3200 });
  } finally {
    loadingHistory.value = false;
  }
}

async function selectRun(runId) {
  if (!runId) return;
  loadingDetail.value = true;
  try {
    const res = await apiClient.get(`dissertation-evaluation/detail/?run_id=${encodeURIComponent(runId)}`);
    const manifest = res.data?.manifest || {};
    selectedRun.value = {
      run_id: runId,
      generated_at: manifest.generated_at || null,
      summary: manifest.summary || {},
      config: manifest.config || {},
      artifacts: manifest.artifacts || {},
      chart_data: res.data?.chart_data || manifest.chart_data || {},
      insights: res.data?.insights || manifest.summary?.insights || {},
    };
  } catch (err) {
    selectedRun.value = null;
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось открыть детали запуска', life: 3500 });
  } finally {
    loadingDetail.value = false;
  }
}

async function previewEvaluationAvailability() {
  previewLoading.value = true;
  try {
    if (!canEvaluate.value) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала задайте оба интервала и отметьте горизонты/модели', life: 3200 });
      return;
    }
    const payload = buildEvaluationPayload();
    const res = await apiClient.post('dissertation-evaluation/preview/', payload);
    availabilityPreview.value = res.data || null;
    const warnings = Array.isArray(res.data?.warnings) ? res.data.warnings : [];
    toast.add({
      severity: warnings.length ? 'warn' : 'success',
      summary: 'Проверка завершена',
      detail: warnings.length ? `Есть предупреждения: ${warnings[0]}` : 'Окно данных пригодно для оценки.',
      life: 3200,
    });
  } catch (err) {
    availabilityPreview.value = null;
    const detail = err?.response?.data?.detail || 'Не удалось проверить доступность данных';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    previewLoading.value = false;
  }
}

function clearEvaluationLongTimer() {
  if (evaluationLongTimer) {
    clearTimeout(evaluationLongTimer);
    evaluationLongTimer = null;
  }
}

function startEvaluationLongTimer() {
  clearEvaluationLongTimer();
  evaluationLongTimer = setTimeout(() => {
    if (!runningEvaluation.value) return;
    toast.add({
      severity: 'warn',
      summary: 'Оценка выполняется долго',
      detail: 'Оценка прогноза выполняется долго. Это нормально для больших интервалов, но можно сузить даты, горизонты или модели.',
      life: 7000,
    });
  }, 60_000);
}

async function runEvaluation() {
  runningEvaluation.value = true;
  startEvaluationLongTimer();
  try {
    if (!canEvaluate.value) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала задайте оба интервала и отметьте горизонты/модели', life: 3200 });
      return;
    }
    const payload = buildEvaluationPayload();
    const res = await apiClient.post('dissertation-evaluation/run/', payload);
    const warnings = Array.isArray(res.data?.warnings) ? res.data.warnings : [];
    const detail = warnings.length
      ? `Оценка выполнена, но есть предупреждения (${warnings.length}).`
      : 'Оценка выполнена, обновляю историю.';
    toast.add({ severity: warnings.length ? 'warn' : 'success', summary: 'Готово', detail, life: 3000 });

    await loadHistory();
    const maybeRunId = String(res.data?.output_dir || '').split('/').pop();
    if (maybeRunId?.startsWith('run_')) {
      await selectRun(maybeRunId);
    } else if (historyRows.value.length) {
      await selectRun(historyRows.value[0].run_id);
    }
  } catch (err) {
    const detail = err?.response?.data?.detail || 'Не удалось выполнить оценку';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    runningEvaluation.value = false;
    clearEvaluationLongTimer();
  }
}

async function downloadArtifact(artifactKey, fileName) {
  if (!selectedRun.value?.run_id || !artifactKey) return;
  downloadKey.value = artifactKey;
  try {
    const res = await apiClient.get('dissertation-evaluation/download/', {
      params: {
        run_id: selectedRun.value.run_id,
        artifact: artifactKey,
      },
      responseType: 'blob',
    });

    const blob = new Blob([res.data]);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName || `${artifactKey}.dat`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось скачать артефакт', life: 3500 });
  } finally {
    downloadKey.value = '';
  }
}

async function refreshAll() {
  await loadDevices();
  await Promise.all([loadHistory(), loadForecastRuns()]);
  if (historyRows.value.length) {
    applyEvaluationConfig(historyRows.value[0]?.config || {}, historyRows.value[0] || {});
  }
  if (selectedRun.value?.run_id) {
    await selectRun(selectedRun.value.run_id);
  } else if (historyRows.value.length) {
    await selectRun(historyRows.value[0].run_id);
  } else {
    selectedRun.value = null;
  }
}

onMounted(async () => {
  await refreshAll();
});

onUnmounted(() => {
  clearEvaluationLongTimer();
});

watch(evaluationUiMode, (value) => {
  localStorage.setItem(EVALUATION_UI_MODE_KEY, value);
});

watch(
  [selectedDeviceId, targetDateFrom, targetDateTo, actualDateFrom, actualDateTo, selectedHorizons, selectedModels, selectedForecastRunIds, strictIntersection],
  () => {
    availabilityPreview.value = null;
  },
);

watch(selectedDeviceId, () => {
  loadForecastRuns();
});

watch(bucketMetricOptions, (options) => {
  const values = new Set(options.map((row) => row.value));
  if (selectedMetricScope.value && values.has(selectedMetricScope.value)) return;
  selectedMetricScope.value = options[1]?.value || metricScopeAll;
}, { immediate: true });
</script>

<style scoped>
.evaluation-page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(210px, 1fr));
  gap: 0.75rem;
}

.filters-grid--primary {
  grid-template-columns: minmax(260px, 1.3fr) minmax(260px, 1fr) minmax(260px, 1fr);
}

.filters-grid--expert {
  grid-template-columns: repeat(3, minmax(220px, 1fr));
}

.field-block--wide {
  min-width: 0;
}

.range-panels {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 0.9rem;
}

.range-panel {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
  padding: 0.9rem;
}

.range-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.chart-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(220px, 1fr);
  gap: 0.9rem;
  align-items: end;
}

.chart-toolbar__field {
  min-width: 0;
}

.chart-toolbar__note {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.2rem;
  min-width: 0;
  color: #64748b;
  font-size: 0.92rem;
}

.chart-toolbar__note strong {
  color: #1e293b;
}

.range-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 0.75rem;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.field-block label {
  font-size: 0.86rem;
  color: #334155;
  font-weight: 600;
}

.switch-field {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.1rem;
}

.switch-caption {
  font-size: 0.77rem;
  color: #64748b;
}

.actions-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.evaluation-form-note {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.7rem 0.85rem;
  border: 1px solid #dbe3ee;
  border-radius: 12px;
  background: #f8fafc;
  color: #475569;
}

.checkbox-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.checkbox-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid #dbe3ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #334155;
  font-size: 0.92rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
}

.summary-grid--extended {
  grid-template-columns: repeat(3, minmax(220px, 1fr));
}

.summary-grid--quality {
  grid-template-columns: repeat(4, minmax(220px, 1fr));
}

.summary-card {
  padding: 0.9rem;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.summary-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.45rem;
}

.summary-label {
  font-size: 0.8rem;
  color: #64748b;
  min-width: 0;
}

.summary-main {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.title-with-hint {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}

.chart-head-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.75rem;
  min-width: 0;
}

.chart-mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.35rem 0.6rem;
  border: 1px solid #dbe3ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 0.82rem;
}

.chart-mode-switch__label--active {
  color: #0f172a;
  font-weight: 700;
}

.insights-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(220px, 1fr));
  gap: 0.75rem;
}

.insight-item {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.insight-label {
  font-size: 0.8rem;
  color: #64748b;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
}

.chart-wrap {
  height: 360px;
}

.chart-note-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chart-note-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.4rem 0.7rem;
  border-radius: 999px;
  background: #fff7ed;
  border: 1px solid #fdba74;
  color: #9a3412;
  font-size: 0.82rem;
}

.economic-formula {
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  flex-wrap: wrap;
  padding: 0.65rem 0.8rem;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: #eff6ff;
  color: #334155;
  font-size: 0.9rem;
}

.economic-formula strong {
  color: #1e3a8a;
}

.economic-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(220px, 1fr));
  gap: 0.75rem;
}

.economic-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
  padding: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.economic-card__head,
.economic-card__line,
.economic-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.economic-card__head {
  color: #0f172a;
}

.economic-card__head span,
.economic-card__foot {
  color: #64748b;
  font-size: 0.82rem;
}

.economic-card__line {
  color: #475569;
  font-size: 0.9rem;
}

.economic-card__line strong {
  color: #1e293b;
}

.economic-card__line--accent strong {
  color: #059669;
}

.economic-card__foot {
  align-items: flex-start;
  flex-direction: column;
  gap: 0.2rem;
  padding-top: 0.35rem;
  border-top: 1px solid #e2e8f0;
}

.chart-box {
  height: 100%;
}

.tables-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 0.9rem;
}

.stat-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.75rem;
  font-weight: 700;
}

.stat-chip--yes {
  color: #065f46;
  background: #d1fae5;
}

.stat-chip--no {
  color: #92400e;
  background: #fef3c7;
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}

@media (max-width: 1100px) {
  .filters-grid {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }

  .filters-grid--primary,
  .filters-grid--expert,
  .range-panels {
    grid-template-columns: 1fr;
  }

  .summary-grid,
  .summary-grid--extended {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }

  .summary-grid--quality {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }

  .insights-grid,
  .charts-grid,
  .economic-grid {
    grid-template-columns: 1fr;
  }

  .chart-toolbar {
    grid-template-columns: 1fr;
  }

  .tables-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .chart-head-actions {
    justify-content: flex-start;
  }

  .filters-grid,
  .filters-grid--primary,
  .filters-grid--expert,
  .summary-grid,
  .summary-grid--extended,
  .summary-grid--quality,
  .range-grid,
  .range-panels {
    grid-template-columns: 1fr;
  }

  .checkbox-grid {
    gap: 0.45rem;
  }

  .checkbox-chip {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
