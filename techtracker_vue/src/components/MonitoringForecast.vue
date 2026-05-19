<template>
  <div class="forecast-page p-4 page-shell">
    <Toast />

    <PageHeader
      title="Прогнозы и состояния"
      :refreshable="true"
      :loading="loading"
      help-title="Гайд: прогнозы и состояния"
      help-intro="Эта страница запускает прогноз и показывает состояние устройства на выбранном горизонте."
      :help-steps="forecastHelpSteps"
      help-note="Если нужно быстро проверить UI без боевых данных, используйте вкладку «Мониторинг - Демо»."
      @refresh="refreshAll"
    />

    <FilterPanel
      class="mb-3"
      title="Контекст прогноза"
    >
      <template #actions>
        <ModeSwitch
          v-model="forecastUiMode"
          aria-label="Режим интерфейса прогнозов"
          :hidden-items="forecastBasicHidden"
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
            placeholder="Выберите устройство"
            class="w-full"
            :loading="loadingDevices"
          />
        </div>
        <div class="field-block">
          <label>Горизонт состояния и таблицы</label>
          <Dropdown
            v-model="selectedHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Последний запуск (типы прогноза)</label>
          <div class="run-icons-row">
            <div
              v-for="item in runTypeStatusIcons"
              :key="item.key"
              class="run-icon-item"
              :title="item.tooltip"
            >
              <i class="pi pi-circle-fill" :class="item.className"></i>
              <span>{{ item.shortLabel }}</span>
            </div>
          </div>
        </div>
      </div>
    </FilterPanel>

    <div class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">Центр фоновых задач (последние статусы)</h4>
        <Button
          size="small"
          text
          icon="pi pi-external-link"
          label="Открыть центр задач"
          @click="$router.push({ name: 'MonitoringTasks' })"
        />
      </div>
      <div class="task-widget-grid mt-2">
        <div v-for="row in latestTaskWidgetRows" :key="row.key" class="task-widget-item">
          <div class="task-widget-head">
            <span class="task-widget-title">{{ row.title }}</span>
            <Tag :value="runStatusLabel(row.status)" :severity="runStatusSeverity(row.status)" />
          </div>
          <div class="task-widget-meta">ID: {{ row.id || '—' }}</div>
          <div class="task-widget-meta">Обновлено: {{ formatDateTime(row.at) }}</div>
          <div class="task-widget-meta">{{ row.details || '—' }}</div>
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3 state-card-shell">
      <div class="state-head">
        <div>
          <h4 class="m-0">Оценка состояния</h4>
          <div class="state-head-subtitle">Система переводит прогнозные метрики в вероятности S0/S1/S2 и показывает, что сильнее всего повлияло на итог.</div>
        </div>
        <div class="state-head-actions">
          <div class="state-head-meta">
            <Tag :value="stateLabel(latestState?.state)" :severity="stateSeverity(latestState?.state)" />
            <span>Обновлено: {{ formatDateTime(latestState?.timestamp) }}</span>
            <span>Источник: {{ stateSourceLabel }}</span>
          </div>
          <Button
            icon="pi pi-sliders-v"
            label="Настроить модель состояния"
            text
            size="small"
            @click="$router.push({ name: 'Settings', query: { tab: 'forecast-state' } })"
          />
        </div>
      </div>

      <div class="state-cards-grid mt-3">
        <div v-for="card in stateCards" :key="card.key" class="state-mini" :class="{ active: latestState?.state === card.key }">
          <div class="state-mini-title">{{ card.title }}</div>
          <div class="state-mini-value">{{ formatPercent(card.value) }}</div>
        </div>
      </div>

      <div class="state-summary-grid mt-3">
        <div class="state-summary-card">
          <span class="summary-title">Итоговый сигнал</span>
          <strong>{{ stateOutcomeSummary.title }}</strong>
          <span>{{ stateOutcomeSummary.text }}</span>
        </div>
        <div class="state-summary-card">
          <span class="summary-title">Уверенность</span>
          <strong>{{ stateConfidenceLabel }}</strong>
          <span>{{ stateConfidenceHint }}</span>
        </div>
        <div class="state-summary-card">
          <span class="summary-title">Профиль модели</span>
          <strong>{{ stateProfileLabel }}</strong>
          <span>{{ stateProfileHint }}</span>
        </div>
        <div class="state-summary-card">
          <span class="summary-title">Источник прогноза</span>
          <strong>{{ modelInfluenceSummary.dominantLabel }}</strong>
          <span>SARIMA {{ modelInfluenceSummary.sarimaPct }}%, LSTM {{ modelInfluenceSummary.lstmPct }}%</span>
        </div>
      </div>

      <div v-if="riskDrivers.length" class="risk-drivers-grid mt-3">
        <div v-for="item in riskDrivers" :key="item.metric_code" class="driver-card">
          <div class="driver-title-row">
            <span class="driver-title">{{ metricLabel(item.metric_code) }}</span>
            <Tag :value="riskLabelByRatio(item.ratio)" :severity="riskSeverityByRatio(item.ratio)" />
          </div>
          <div class="driver-meta">
            Значение: {{ formatNum(item.value) }} {{ metricUnit(item.metric_code) || item.unit || '' }} / порог: {{ formatNum(item.threshold) }}
          </div>
          <div class="risk-track">
            <span class="risk-fill" :style="{ width: `${Math.min(100, item.risk_component * 100)}%` }"></span>
          </div>
          <div class="driver-meta">
            Вклад в итоговую оценку: {{ (item.risk_component * 100).toFixed(1) }}%.
            {{ driverExplanation(item) }}
          </div>
        </div>
      </div>
      <div v-else class="text-500 mt-3">Данных для расчета факторов риска пока недостаточно.</div>
    </div>

    <div class="card p-3 mb-3 workflow-card">
      <div class="workflow-head">
        <div>
          <h4 class="m-0">Запуск прогнозирования</h4>
        </div>
        <div class="workflow-status">
          <Tag :value="workflowStatusLabel" :severity="workflowStatusSeverity" />
        </div>
      </div>

      <Transition name="fade-slide" mode="out-in">
        <div :key="`workflow-step-${workflowUiStep}`" class="workflow-body mt-3">
          <div v-if="workflowUiStep === 1" class="workflow-step-start">
            <div class="wizard-step-title">Шаг 1 из 4: Выбор запуска</div>
            <div class="wizard-step-subtitle">Выберите тип запуска прогноза.</div>
            <div class="workflow-mode-row workflow-step1-row mt-3">
              <Button
                label="Полный запуск"
                icon="pi pi-sitemap"
                :outlined="workflowMode !== 'full'"
                :severity="workflowMode === 'full' ? 'primary' : 'secondary'"
                @click="setWorkflowMode('full')"
              />
              <Button
                label="Частичный запуск"
                icon="pi pi-sliders-h"
                :outlined="workflowMode !== 'partial'"
                :severity="workflowMode === 'partial' ? 'primary' : 'secondary'"
                @click="setWorkflowMode('partial')"
              />
            </div>
            <div class="workflow-actions workflow-step1-row workflow-step1-actions mt-3">
              <Button icon="pi pi-arrow-right" label="Далее" @click="workflowUiStep = 2" />
            </div>
          </div>

          <div v-else-if="workflowUiStep === 2">
            <div class="wizard-step-title">Шаг 2 из 4: Настройки</div>
            <div class="wizard-step-subtitle">Показываются только настройки выбранного режима запуска.</div>

            <div class="setting-panel mt-3">
              <div class="setting-title">Горизонты запуска</div>
              <div class="setting-desc">Выберите, какие горизонты нужно реально посчитать в этом запуске.</div>
              <div class="checkbox-grid mt-2">
                <label v-for="option in horizonOptions" :key="`launch-${option.value}`" class="checkbox-chip">
                  <Checkbox v-model="launchHorizons" :inputId="`launch-${option.value}`" :value="option.value" />
                  <span>{{ option.label }}</span>
                </label>
              </div>
            </div>

            <div v-if="workflowMode === 'full'" class="workflow-grid full-grid mt-3">
              <div class="setting-panel">
                <div class="setting-title">SARIMA настройки</div>
                <div class="setting-desc">Локальная baseline-модель на корпоративном сервере.</div>
                <div class="field-block mt-2">
                  <label>Период обучения (дней)</label>
                  <InputNumber v-model="baselineLookbackDays" :min="1" :max="365" class="w-full" />
                </div>
                <div class="field-block mt-2">
                  <label>Шаг агрегации</label>
                  <Dropdown v-model="baselineFreq" :options="freqOptions" optionLabel="label" optionValue="value" class="w-full" />
                </div>
                <div class="field-block mt-2">
                  <label>Режим сезонности</label>
                  <div class="seasonality-toggle-row mt-2">
                    <Button
                      v-for="item in baselineSeasonalityModes"
                      :key="item.value"
                      class="seasonality-toggle-btn"
                      :label="item.shortLabel"
                      :outlined="baselineSeasonalityMode !== item.value"
                      :severity="baselineSeasonalityMode === item.value ? 'primary' : 'secondary'"
                      @click="baselineSeasonalityMode = item.value"
                    />
                  </div>
                </div>
                <div class="seasonality-info-card mt-2">
                  <div class="seasonality-info-title">{{ activeBaselineSeasonalityMode.title }}</div>
                  <div class="seasonality-info-text">{{ activeBaselineSeasonalityMode.description }}</div>
                  <div class="seasonality-info-grid mt-2">
                    <div class="seasonality-info-block">
                      <div class="seasonality-info-label">Что улучшает</div>
                      <ul class="seasonality-info-list">
                        <li v-for="item in activeBaselineSeasonalityMode.improves" :key="`pro-${item}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="seasonality-info-block risk">
                      <div class="seasonality-info-label">Что ухудшает / ограничивает</div>
                      <ul class="seasonality-info-list">
                        <li v-for="item in activeBaselineSeasonalityMode.tradeoffs" :key="`con-${item}`">{{ item }}</li>
                      </ul>
                    </div>
                  </div>
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Сохранять STL-компоненты</label>
                  <div class="switch-inline">
                    <InputSwitch v-model="baselineSaveStl" />
                    <span>{{ baselineSaveStl ? 'Да' : 'Нет' }}</span>
                  </div>
                </div>
              </div>

              <div class="setting-panel">
                <div class="setting-title">LSTM настройки</div>
                <div class="setting-desc">Удаленный расчет на отдельном ПК через backend API.</div>
                <div class="field-block mt-2">
                  <label>Период обучения (дней)</label>
                  <InputNumber v-model="lstmLookbackDays" :min="1" :max="365" class="w-full" />
                </div>
                <div class="field-block mt-2">
                  <label>Шаг агрегации</label>
                  <Dropdown v-model="lstmFreq" :options="freqOptions" optionLabel="label" optionValue="value" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Эпохи обучения</label>
                  <InputNumber v-model="lstmEpochs" :min="1" :max="400" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Lookback окна LSTM (шагов)</label>
                  <InputNumber v-model="lstmSequenceLookback" :min="1" :max="5000" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Размер hidden state</label>
                  <InputNumber v-model="lstmHiddenSize" :min="8" :max="512" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Learning rate</label>
                  <InputNumber v-model="lstmLearningRate" :min="0.00001" :max="1" :step="0.0001" mode="decimal" :minFractionDigits="4" :maxFractionDigits="5" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Dropout</label>
                  <InputNumber v-model="lstmDropout" :min="0" :max="0.9" :step="0.01" mode="decimal" :minFractionDigits="2" :maxFractionDigits="2" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Weight decay</label>
                  <InputNumber v-model="lstmWeightDecay" :min="0" :max="0.1" :step="0.00001" mode="decimal" :minFractionDigits="5" :maxFractionDigits="5" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Batch size</label>
                  <InputNumber v-model="lstmBatchSize" :min="8" :max="512" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Режим сезонности LSTM</label>
                  <Dropdown v-model="lstmSeasonalityMode" :options="lstmSeasonalityOptions" optionLabel="label" optionValue="value" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Окно сезонности (дней)</label>
                  <InputNumber v-model="lstmSeasonalityWindowDays" :min="1" :max="60" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Функция потерь</label>
                  <Dropdown v-model="lstmLossKind" :options="lstmLossOptions" optionLabel="label" optionValue="value" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Режим обучения</label>
                  <Dropdown v-model="lstmTrainMode" :options="lstmTrainModeOptions" optionLabel="label" optionValue="value" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Лаги</label>
                  <InputText v-model="lstmLagsText" class="w-full" placeholder="1,24,168" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Календарные признаки</label>
                  <div class="switch-inline">
                    <InputSwitch v-model="lstmUseCalendarFeatures" />
                    <span>{{ lstmUseCalendarFeatures ? 'Да' : 'Нет' }}</span>
                  </div>
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Сезонный residual</label>
                  <div class="switch-inline">
                    <InputSwitch v-model="lstmUseSeasonalResidual" />
                    <span>{{ lstmUseSeasonalResidual ? 'Да' : 'Нет' }}</span>
                  </div>
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Интервал poll (сек)</label>
                  <InputNumber v-model="lstmPollIntervalSec" :min="1" :max="60" class="w-full" />
                </div>
                <div v-if="isForecastExpert" class="field-block mt-2">
                  <label>Макс. retries</label>
                  <InputNumber v-model="lstmMaxRetries" :min="0" :max="20" class="w-full" />
                </div>
              </div>

              <div v-if="isForecastExpert" class="setting-panel">
                <div class="setting-title">Калибровка оркестра</div>
                <div class="setting-desc">Параметры интеграции SARIMA и LSTM.</div>
                <div class="field-block mt-2">
                  <label>beta расхождения моделей</label>
                  <InputNumber v-model="ensembleBeta" :min="0" :max="5" :step="0.05" mode="decimal" :minFractionDigits="2" :maxFractionDigits="2" class="w-full" />
                </div>
                <div class="field-block mt-2">
                  <label>Вес SARIMA (prior)</label>
                  <InputNumber v-model="ensembleSarimaWeight" :min="0" :max="1" :step="0.05" mode="decimal" :minFractionDigits="2" :maxFractionDigits="2" class="w-full" />
                </div>
                <div class="field-block mt-2">
                  <label>Вес LSTM (prior)</label>
                  <InputNumber v-model="ensembleLstmWeight" :min="0" :max="1" :step="0.05" mode="decimal" :minFractionDigits="2" :maxFractionDigits="2" class="w-full" />
                </div>
              </div>
            </div>

            <div v-else class="mt-3">
              <div class="wizard-step-subtitle">Отметьте метод галочкой, чтобы открыть его настройки.</div>
              <div class="partial-check-row mt-2">
                <div class="partial-check-item">
                  <Checkbox v-model="partialSarimaChecked" :binary="true" inputId="partial_sarima" />
                  <label for="partial_sarima">SARIMA</label>
                </div>
                <div class="partial-check-item">
                  <Checkbox v-model="partialLstmChecked" :binary="true" inputId="partial_lstm" />
                  <label for="partial_lstm">LSTM</label>
                </div>
              </div>

              <div v-if="partialMethod === 'sarima'" class="workflow-grid partial-grid mt-3">
                <div class="setting-panel">
                  <div class="setting-title">SARIMA настройки</div>
                  <div class="setting-desc">Быстрый локальный baseline-прогноз.</div>
                  <div class="field-block mt-2">
                    <label>Период обучения (дней)</label>
                    <InputNumber v-model="baselineLookbackDays" :min="1" :max="365" class="w-full" />
                  </div>
                  <div class="field-block mt-2">
                    <label>Шаг агрегации</label>
                    <Dropdown v-model="baselineFreq" :options="freqOptions" optionLabel="label" optionValue="value" class="w-full" />
                  </div>
                  <div class="field-block mt-2">
                    <label>Режим сезонности</label>
                    <div class="seasonality-toggle-row mt-2">
                      <Button
                        v-for="item in baselineSeasonalityModes"
                        :key="item.value"
                        class="seasonality-toggle-btn"
                        :label="item.shortLabel"
                        :outlined="baselineSeasonalityMode !== item.value"
                        :severity="baselineSeasonalityMode === item.value ? 'primary' : 'secondary'"
                        @click="baselineSeasonalityMode = item.value"
                      />
                    </div>
                  </div>
                  <div class="seasonality-info-card mt-2">
                    <div class="seasonality-info-title">{{ activeBaselineSeasonalityMode.title }}</div>
                    <div class="seasonality-info-text">{{ activeBaselineSeasonalityMode.description }}</div>
                    <div class="seasonality-info-grid mt-2">
                      <div class="seasonality-info-block">
                        <div class="seasonality-info-label">Что улучшает</div>
                        <ul class="seasonality-info-list">
                          <li v-for="item in activeBaselineSeasonalityMode.improves" :key="`pro-partial-${item}`">{{ item }}</li>
                        </ul>
                      </div>
                      <div class="seasonality-info-block risk">
                        <div class="seasonality-info-label">Что ухудшает / ограничивает</div>
                        <ul class="seasonality-info-list">
                          <li v-for="item in activeBaselineSeasonalityMode.tradeoffs" :key="`con-partial-${item}`">{{ item }}</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Сохранять STL-компоненты</label>
                    <div class="switch-inline">
                      <InputSwitch v-model="baselineSaveStl" />
                      <span>{{ baselineSaveStl ? 'Да' : 'Нет' }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="partialMethod === 'lstm'" class="workflow-grid partial-grid mt-3">
                <div class="setting-panel">
                  <div class="setting-title">LSTM настройки</div>
                  <div class="setting-desc">Удаленный запуск через очередь backend.</div>
                  <div class="field-block mt-2">
                    <label>Период обучения (дней)</label>
                    <InputNumber v-model="lstmLookbackDays" :min="1" :max="365" class="w-full" />
                  </div>
                  <div class="field-block mt-2">
                    <label>Шаг агрегации</label>
                    <Dropdown v-model="lstmFreq" :options="freqOptions" optionLabel="label" optionValue="value" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Эпохи обучения</label>
                    <InputNumber v-model="lstmEpochs" :min="1" :max="400" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Lookback окна LSTM (шагов)</label>
                    <InputNumber v-model="lstmSequenceLookback" :min="1" :max="5000" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Размер hidden state</label>
                    <InputNumber v-model="lstmHiddenSize" :min="8" :max="512" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Learning rate</label>
                    <InputNumber v-model="lstmLearningRate" :min="0.00001" :max="1" :step="0.0001" mode="decimal" :minFractionDigits="4" :maxFractionDigits="5" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Dropout</label>
                    <InputNumber v-model="lstmDropout" :min="0" :max="0.9" :step="0.01" mode="decimal" :minFractionDigits="2" :maxFractionDigits="2" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Weight decay</label>
                    <InputNumber v-model="lstmWeightDecay" :min="0" :max="0.1" :step="0.00001" mode="decimal" :minFractionDigits="5" :maxFractionDigits="5" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Batch size</label>
                    <InputNumber v-model="lstmBatchSize" :min="8" :max="512" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Режим сезонности LSTM</label>
                    <Dropdown v-model="lstmSeasonalityMode" :options="lstmSeasonalityOptions" optionLabel="label" optionValue="value" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Окно сезонности (дней)</label>
                    <InputNumber v-model="lstmSeasonalityWindowDays" :min="1" :max="60" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Функция потерь</label>
                    <Dropdown v-model="lstmLossKind" :options="lstmLossOptions" optionLabel="label" optionValue="value" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Режим обучения</label>
                    <Dropdown v-model="lstmTrainMode" :options="lstmTrainModeOptions" optionLabel="label" optionValue="value" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Лаги</label>
                    <InputText v-model="lstmLagsText" class="w-full" placeholder="1,24,168" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Календарные признаки</label>
                    <div class="switch-inline">
                      <InputSwitch v-model="lstmUseCalendarFeatures" />
                      <span>{{ lstmUseCalendarFeatures ? 'Да' : 'Нет' }}</span>
                    </div>
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Сезонный residual</label>
                    <div class="switch-inline">
                      <InputSwitch v-model="lstmUseSeasonalResidual" />
                      <span>{{ lstmUseSeasonalResidual ? 'Да' : 'Нет' }}</span>
                    </div>
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Интервал poll (сек)</label>
                    <InputNumber v-model="lstmPollIntervalSec" :min="1" :max="60" class="w-full" />
                  </div>
                  <div v-if="isForecastExpert" class="field-block mt-2">
                    <label>Макс. retries</label>
                    <InputNumber v-model="lstmMaxRetries" :min="0" :max="20" class="w-full" />
                  </div>
                </div>
              </div>
            </div>

            <div class="workflow-actions mt-3">
              <Button icon="pi pi-arrow-left" label="Назад" severity="secondary" @click="workflowUiStep = 1" />
              <Button
                icon="pi pi-play"
                :label="workflowRunButtonLabel"
                :loading="workflowBusy"
                :disabled="workflowStep2StartDisabled"
                @click="startWorkflowFromStep2"
              />
            </div>
          </div>

          <div v-else-if="workflowUiStep === 3">
            <div class="wizard-step-title">Шаг 3 из 4: Выполнение прогноза</div>
            <div class="wizard-step-subtitle">Показывается только ход выполнения и текущий этап.</div>

            <div class="workflow-steps mt-3">
              <div
                v-for="step in workflowStepItems"
                :key="step.key"
                class="workflow-step"
                :class="`step-${step.state}`"
              >
                <div class="step-index">{{ step.index }}</div>
                <div class="step-body">
                  <div class="step-title">{{ step.title }}</div>
                  <div class="step-desc">{{ step.description }}</div>
                </div>
                <div class="step-status">{{ step.statusLabel }}</div>
              </div>
            </div>

            <div class="run-progress mt-3">
              <div class="loader-dot"></div>
              <div>
                <div class="loader-title">Выполняется расчет прогноза...</div>
                <div class="loader-subtitle">
                  Шаг: {{ workflowCurrentStepLabel }}. Статус: {{ workflowStatusLabel }}.
                </div>
              </div>
            </div>
          </div>

          <div v-else>
            <div class="wizard-step-title">Шаг 4 из 4: Результаты</div>
            <div class="wizard-step-subtitle">Итог запуска и ключевые показатели выполнения.</div>

            <div v-if="workflowSummaryRows.length" class="summary-grid mt-3">
              <div v-for="item in workflowSummaryRows" :key="item.key" class="summary-item">
                <span class="summary-label">{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div v-else class="text-500 mt-3">Результат пока не сформирован.</div>

            <div class="workflow-actions mt-3">
              <Button icon="pi pi-replay" label="Запустить прогноз заново" :loading="workflowBusy" @click="restartWorkflow" />
              <Button icon="pi pi-pencil" label="Изменить параметры" severity="secondary" @click="workflowUiStep = 1" />
            </div>
          </div>
        </div>
      </Transition>
    </div>

    <div class="card p-3 mb-3">
      <div class="chart-head">
        <div>
          <h4 class="m-0">Разброс данных по метрике</h4>
          <p class="text-500 m-0">Сырые точки + прогнозы SARIMA, LSTM и итоговый оркестр.</p>
        </div>
        <div class="freshness-stack text-500 text-sm">
          <span>Точек raw: {{ scatterPointCount }}</span>
          <span>Свежесть raw: {{ rawFreshnessLabel }}</span>
          <span>Период: {{ chartWindowLabel }}</span>
        </div>
      </div>

      <div class="chart-controls mt-2">
        <div class="field-block">
          <label>Метрика</label>
          <Dropdown
            v-model="selectedMetricCode"
            :options="metricOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            placeholder="Выберите метрику"
          />
        </div>
        <div class="field-block">
          <label>Период на графике</label>
          <Dropdown
            v-model="chartWindowMinutes"
            :options="chartWindowOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Горизонт прогноза на графике</label>
          <Dropdown
            v-model="chartForecastHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block chart-series-toggle">
          <label>Слои графика</label>
          <div class="series-switches">
            <Button size="small" :severity="showSeries.raw ? 'info' : 'secondary'" :outlined="!showSeries.raw" label="Raw" @click="showSeries.raw = !showSeries.raw" />
            <Button size="small" :severity="showSeries.sarima ? 'warning' : 'secondary'" :outlined="!showSeries.sarima" label="SARIMA" @click="showSeries.sarima = !showSeries.sarima" />
            <Button size="small" :severity="showSeries.lstm ? 'success' : 'secondary'" :outlined="!showSeries.lstm" label="LSTM" @click="showSeries.lstm = !showSeries.lstm" />
            <Button size="small" :severity="showSeries.ensemble ? 'primary' : 'secondary'" :outlined="!showSeries.ensemble" label="Оркестр" @click="showSeries.ensemble = !showSeries.ensemble" />
          </div>
        </div>
        <div class="field-block action-button">
          <Button
            icon="pi pi-sync"
            label="Обновить график"
            severity="secondary"
            class="w-full"
            :loading="chartLoading"
            @click="refreshChartData"
          />
        </div>
      </div>

      <div v-if="scatterHasAnyData" class="chart-wrap mt-3">
        <Chart type="scatter" :data="scatterChartData" :options="scatterChartOptions" class="scatter-chart" />
      </div>
      <EmptyStateCard
        v-else
        class="mt-3"
        icon="pi pi-chart-scatter"
        title="Нет данных для графика"
        description="Измените период или метрику, либо сгенерируйте demo-историю на вкладке «Мониторинг - Демо»."
      />
    </div>

    <div class="card p-3">
      <div class="table-head">
        <h4 class="m-0">Итоговые точки прогноза ({{ selectedHorizon }})</h4>
        <span class="text-500 text-sm">
          Источник: {{ primaryForecastModelLabel }} • пресет: {{ activeForecastPresetLabel }} • строк: {{ filteredForecastPoints.length }} / {{ representativeForecastPoints.length }} • точек: {{ primaryForecastPoints.length }}
        </span>
      </div>

      <div class="risk-legend mt-2 mb-2">
        <span class="legend-title">Легенда риска:</span>
        <span class="legend-chip legend-low">Низкий: p90/порог &lt; 70%</span>
        <span class="legend-chip legend-medium">Средний: 70%-85%</span>
        <span class="legend-chip legend-high">Высокий: 85%-100%</span>
        <span class="legend-chip legend-critical">Критический: >= 100%</span>
      </div>

      <div class="table-toolbar mb-2">
        <TablePresetBar
          v-model="forecastTablePreset"
          title="Пресет таблицы"
          aria-label="Пресеты таблицы прогноза"
          :presets="forecastTablePresets"
        />
        <div class="table-freshness text-500 text-sm">
          <span>Свежесть: {{ forecastFreshnessLabel }}</span>
          <span>Срез: {{ chartWindowLabel }}</span>
        </div>
      </div>

      <DataTable
        :value="filteredForecastPoints"
        dataKey="id"
        :loading="loading"
        :rowClass="forecastRowClass"
        scrollable
        scrollHeight="28rem"
        :virtualScrollerOptions="tableVirtualScrollerOptions"
        stripedRows
        responsiveLayout="scroll"
        class="table-compact"
      >
        <template #empty>
          <EmptyStateCard
            icon="pi pi-table"
            title="Нет строк прогноза"
            description="По выбранному пресету/горизонту данных нет. Проверьте запуски прогноза или запустите новый расчет."
          />
        </template>
        <Column field="metric_code" header="Метрика" sortable>
          <template #body="{ data }">
            <span :title="riskTooltip(data)">{{ metricLabel(data.metric_code) }}</span>
          </template>
        </Column>
        <Column v-if="showTrendColumn" header="Тренд">
          <template #body="{ data }">
            <div class="sparkline-cell" :title="sparklineTooltip(data.metric_code)">
              <svg class="sparkline-svg" viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true">
                <path class="sparkline-axis" d="M0 26.5 L120 26.5" />
                <path
                  v-if="sparklinePath(data.metric_code)"
                  :d="sparklinePath(data.metric_code)"
                  :stroke="metricColor(data.metric_code)"
                  class="sparkline-line"
                />
              </svg>
              <span v-if="!sparklinePath(data.metric_code)" class="sparkline-empty">-</span>
            </div>
          </template>
        </Column>
        <Column header="Ед. изм.">
          <template #body="{ data }">
            {{ metricUnit(data.metric_code) || '-' }}
          </template>
        </Column>
        <Column field="horizon" header="Горизонт" sortable />
        <Column v-if="showModelTargetColumns" field="model_kind" header="Модель" sortable>
          <template #body="{ data }">
            {{ modelKindLabel(data.model_kind) }}
          </template>
        </Column>
        <Column v-if="showModelTargetColumns" field="target_ts" header="Время цели" sortable>
          <template #body="{ data }">
            {{ formatDateTime(data.target_ts) }}
          </template>
        </Column>
        <Column field="y_hat" header="Прогноз (y_hat)" sortable>
          <template #body="{ data }">
            <span class="risk-cell" :class="riskCellClass(data)">{{ formatNum(data.y_hat) }}</span>
          </template>
        </Column>
        <Column v-if="showQuantileColumns" field="p10" header="p10">
          <template #body="{ data }">
            {{ formatNum(data.p10) }}
          </template>
        </Column>
        <Column v-if="showQuantileColumns" field="p50" header="p50">
          <template #body="{ data }">
            {{ formatNum(data.p50) }}
          </template>
        </Column>
        <Column field="p90" header="p90">
          <template #body="{ data }">
            <span class="risk-cell" :class="riskCellClass(data)">{{ formatNum(data.p90) }}</span>
          </template>
        </Column>
        <Column header="Риск по p90">
          <template #body="{ data }">
            <span :title="riskTooltip(data)">
              <Tag :value="riskLabel(data)" :severity="riskSeverity(data)" />
            </span>
          </template>
        </Column>
        <Column v-if="showAlphaColumn" field="alpha" :header="primaryAlphaHeader">
          <template #body="{ data }">
            <span :title="primaryAlphaTooltip(data)">{{ primaryAlphaValue(data) }}</span>
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Checkbox from 'primevue/checkbox';
import Toast from 'primevue/toast';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import Chart from 'primevue/chart';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import ModeSwitch from '@/components/ui/ModeSwitch.vue';
import TablePresetBar from '@/components/ui/TablePresetBar.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import { useTablePresetState } from '@/composables/useMonitoringTableState';

const toast = useToast();
const MAX_SPARKLINE_POINTS = 34;
const SPARKLINE_WIDTH = 120;
const SPARKLINE_HEIGHT = 28;
const FRESH_RUN_WINDOW_HOURS = 24;
const FORECAST_UI_MODE_KEY = 'monitoring_forecast_ui_mode';
const FORECAST_TABLE_PRESET_KEY = 'monitoring_forecast_table_preset';
const forecastHelpSteps = [
  'Выберите устройство и горизонт в верхнем блоке.',
  'Проверьте индикаторы последних запусков по типам прогноза (SARIMA, LSTM, оркестр).',
  'Запустите прогноз через пошаговый мастер: полный или частичный режим.',
  'В SARIMA-настройках выберите режим сезонности: прямая сезонная SARIMA или STL с возвратом сезонной волны.',
  'Дождитесь шага результата и проверьте карточки выполнения (время, модель, обработанные метрики).',
  'Ниже смотрите график разброса и итоговую таблицу точек прогноза с риском по p90.',
  'Для подробного контроля очереди и фоновых задач откройте «Центр задач».',
];
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();

const devices = ref([]);
const loadingDevices = ref(false);
const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});
const selectedHorizon = ref('24h');
const chartForecastHorizon = ref('24h');

const latestRun = ref(null);
const latestLstmRun = ref(null);
const latestEnsembleRun = ref(null);
const latestLstmQueueJob = ref(null);
const latestState = ref(null);

const forecastPoints = ref([]);
const lstmForecastPoints = ref([]);
const ensembleForecastPoints = ref([]);

const loading = ref(false);
const runningBaseline = ref(false);
const runningLstm = ref(false);
const runningOrchestrator = ref(false);
const pollingLstm = ref(false);
const lstmAutoPolling = ref(false);
const chartLoading = ref(false);

const baselineLookbackDays = ref(60);
const baselineFreq = ref('1h');
const baselineSaveStl = ref(true);
const baselineSeasonalityMode = ref('stl_reseasonalized');
const lstmLookbackDays = ref(365);
const lstmFreq = ref('1h');
const launchHorizons = ref(['24h', '7d', '30d']);
const lstmEpochs = ref(80);
const lstmSequenceLookback = ref(1440);
const lstmHiddenSize = ref(96);
const lstmLearningRate = ref(0.001);
const lstmDropout = ref(0.15);
const lstmWeightDecay = ref(0.00001);
const lstmBatchSize = ref(64);
const lstmSeasonalityMode = ref('rolling_profile');
const lstmSeasonalityWindowDays = ref(14);
const lstmLossKind = ref('quantile');
const lstmTrainMode = ref('warm_start');
const lstmLagsText = ref('1,24,168');
const lstmUseCalendarFeatures = ref(true);
const lstmUseSeasonalResidual = ref(true);
const lstmPollIntervalSec = ref(10);
const lstmMaxRetries = ref(5);

const ensembleBeta = ref(0.5);
const ensembleSarimaWeight = ref(0.5);
const ensembleLstmWeight = ref(0.5);

const workflowMode = ref('full');
const partialMethod = ref('');
const workflowUiStep = ref(1);
const lastWorkflowRequestedType = ref('full');
const workflowStartTs = ref(null);
const workflowFinishTs = ref(null);
const workflowBusy = computed(() => runningBaseline.value || runningLstm.value || runningOrchestrator.value);
const workflowStreamActive = ref(false);
const workflowStreamStatus = ref('idle');
const workflowStreamSnapshot = ref(null);
const workflowStreamError = ref('');
const workflowStreamLastEvent = ref('');
let workflowStreamController = null;

const selectedMetricCode = ref('cpu_load_total');
const chartWindowMinutes = ref(7 * 24 * 60);
const rawScatterPoints = ref([]);
const metricTrendMap = ref({});
const forecastUiMode = ref((() => {
  const raw = localStorage.getItem(FORECAST_UI_MODE_KEY);
  return raw === 'expert' ? 'expert' : 'basic';
})());
const isForecastExpert = computed(() => forecastUiMode.value === 'expert');
const forecastTablePreset = useTablePresetState(
  FORECAST_TABLE_PRESET_KEY,
  'balanced',
  ['ops', 'balanced', 'analysis'],
);

const forecastBasicHidden = [
  'калибровка оркестра (beta и веса SARIMA/LSTM)',
  'тонкая настройка polling и retries для LSTM',
  'переключатель сохранения STL-компонентов',
];

const forecastTablePresets = [
  { value: 'ops', label: 'Оперативный', description: 'Только рискованные строки и ключевые поля для быстрого реагирования.' },
  { value: 'balanced', label: 'Сбалансированный', description: 'Повседневный режим: все метрики без перегрузки деталями.' },
  { value: 'analysis', label: 'Аналитический', description: 'Расширенный разбор модели: дополнительные интервалы и параметры.' },
];

const showSeries = reactive({
  raw: true,
  sarima: true,
  lstm: true,
  ensemble: true,
});

let lstmPollTimer = null;

const tableVirtualScrollerOptions = { itemSize: 52 };

const horizonOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const recommendedLstmParamsForHorizons = (horizons) => {
  const values = Array.isArray(horizons) ? horizons.map((item) => String(item || '').trim()) : [];
  if (values.includes('30d')) {
    return { historyDays: 365, minHistoryDays: 180, sequenceLookback: 1440, horizonKey: '30d' };
  }
  if (values.includes('7d')) {
    return { historyDays: 120, minHistoryDays: 90, sequenceLookback: 672, horizonKey: '7d' };
  }
  return { historyDays: 60, minHistoryDays: 30, sequenceLookback: 336, horizonKey: '24h' };
};

const freqOptions = [
  { label: '1 час', value: '1h' },
  { label: '30 минут', value: '30min' },
  { label: '15 минут', value: '15min' },
];

const lstmSeasonalityOptions = [
  { label: 'Rolling profile', value: 'rolling_profile' },
  { label: 'Global profile', value: 'global_profile' },
  { label: 'STL-like local', value: 'stl_like_local' },
];

const lstmLossOptions = [
  { label: 'Quantile', value: 'quantile' },
  { label: 'Huber', value: 'huber' },
];

const lstmTrainModeOptions = [
  { label: 'Fit on request', value: 'fit_on_request' },
  { label: 'Warm start', value: 'warm_start' },
];

const baselineSeasonalityModes = [
  {
    value: 'sarima_seasonal',
    shortLabel: 'SARIMA с сезонностью',
    title: 'SARIMA напрямую учитывает сезонный ритм',
    description: 'Модель обучается на ряду вместе с сезонными колебаниями и старается повторить расписание нагрузки как часть прогноза.',
    improves: [
      'лучше повторяет стабильный суточный или недельный ритм',
      'проще объясняется как классическая сезонная SARIMA',
      'удобно, если важна точность регулярного расписания',
    ],
    tradeoffs: [
      'может сильнее подстроиться под расписание и слабее выделять деградацию',
      'хуже переносит нестабильную или «ломаную» сезонность',
      'при короткой истории сезонная часть может быть шумной',
    ],
  },
  {
    value: 'stl_reseasonalized',
    shortLabel: 'STL + вернуть сезонность',
    title: 'STL отделяет рутину, а затем сезонность возвращается в прогноз',
    description: 'Сначала система отделяет регулярный ритм от тренда и шума, прогнозирует очищенный ряд, затем добавляет сезонную волну обратно.',
    improves: [
      'лучше отделяет деградацию от обычного расписания',
      'устойчивее для диагностического baseline',
      'сохраняет сезонность в финальном прогнозе, а не теряет её',
    ],
    tradeoffs: [
      'сезонная волна восстанавливается повторением последнего цикла, это упрощение',
      'может быть грубее при резкой смене сезонного шаблона',
      'сложнее объяснять, чем прямую сезонную SARIMA',
    ],
  },
];

const baselineSeasonalityModeMap = baselineSeasonalityModes.reduce((acc, item) => {
  acc[item.value] = item;
  return acc;
}, {});

const activeBaselineSeasonalityMode = computed(() => (
  baselineSeasonalityModeMap[baselineSeasonalityMode.value] || baselineSeasonalityModes[1]
));

const chartWindowOptions = [
  { label: '24 часа', value: 24 * 60 },
  { label: '7 дней', value: 7 * 24 * 60 },
  { label: '30 дней', value: 30 * 24 * 60 },
  { label: '90 дней', value: 90 * 24 * 60 },
];

const metricOptions = [
  { label: 'Загрузка CPU', value: 'cpu_load_total', unit: '%' },
  { label: 'Использование памяти', value: 'mem_usage_percent', unit: '%' },
  { label: 'Трафик исходящий', value: 'net_bytes_sent', unit: 'KB/s' },
  { label: 'Трафик входящий', value: 'net_bytes_recv', unit: 'KB/s' },
  { label: 'Ping до шлюза', value: 'ping_latency_gateway', unit: 'ms' },
  { label: 'Температура системы', value: 'system_temperature', unit: 'C' },
  { label: 'Температура диска RAID', value: 'storcli_drive_temperature', unit: 'C' },
  { label: 'Predictive Failure Count', value: 'storcli_predictive_failure_count', unit: 'count' },
];

const metricMap = metricOptions.reduce((acc, item) => {
  acc[item.value] = item;
  return acc;
}, {});

const riskThresholdMap = {
  cpu_load_total: 90,
  mem_usage_percent: 92,
  ping_latency_gateway: 150,
  system_temperature: 80,
  storcli_drive_temperature: 58,
  storcli_predictive_failure_count: 1,
};

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const deviceOptions = computed(() => (
  devices.value.map((device) => ({
    id: device.id,
    label: device.serial_number ? `${device.name} (${device.serial_number})` : device.name,
    serial: device.serial_number || '',
    name: device.name || '',
  }))
));

const selectedDevice = computed(() => (
  deviceOptions.value.find((item) => item.id === selectedDeviceId.value) || null
));

const selectedSerial = computed(() => selectedDevice.value?.serial || '');

const chartWindowLabel = computed(() => {
  const found = chartWindowOptions.find((item) => item.value === chartWindowMinutes.value);
  return found?.label || `${chartWindowMinutes.value} мин`;
});

const launchHorizonCsv = computed(() => {
  const values = Array.isArray(launchHorizons.value)
    ? launchHorizons.value.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  return values.length ? values.join(',') : '24h,7d,30d';
});

const recommendedLstmParams = computed(() => recommendedLstmParamsForHorizons(launchHorizons.value));
const lastAutoLstmParams = ref({ historyDays: 365, sequenceLookback: 1440 });

const syncRecommendedLstmParams = ({ force = false } = {}) => {
  const recommended = recommendedLstmParams.value;
  const previous = lastAutoLstmParams.value || {};

  const shouldUpdateHistory =
    force
    || !Number.isFinite(Number(lstmLookbackDays.value))
    || Number(lstmLookbackDays.value) <= 0
    || Number(lstmLookbackDays.value) === Number(previous.historyDays)
    || Number(lstmLookbackDays.value) < Number(recommended.minHistoryDays);
  if (shouldUpdateHistory) {
    lstmLookbackDays.value = Number(recommended.historyDays);
  }

  const shouldUpdateLookback =
    force
    || !Number.isFinite(Number(lstmSequenceLookback.value))
    || Number(lstmSequenceLookback.value) <= 0
    || Number(lstmSequenceLookback.value) === Number(previous.sequenceLookback)
    || Number(lstmSequenceLookback.value) < Number(recommended.sequenceLookback);
  if (shouldUpdateLookback) {
    lstmSequenceLookback.value = Number(recommended.sequenceLookback);
  }

  if (force || !String(lstmTrainMode.value || '').trim() || lstmTrainMode.value === 'fit_on_request') {
    lstmTrainMode.value = 'warm_start';
  }
  if (force || !Number.isFinite(Number(lstmEpochs.value)) || Number(lstmEpochs.value) < 80) {
    lstmEpochs.value = 80;
  }

  lastAutoLstmParams.value = {
    historyDays: Number(recommended.historyDays),
    sequenceLookback: Number(recommended.sequenceLookback),
  };
};

const parseLstmLags = () => (
  String(lstmLagsText.value || '')
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((value) => Number.isFinite(value) && value > 0)
);

const buildLstmOptionsPayload = () => ({
  epochs: Math.max(1, Number(lstmEpochs.value) || 80),
  lookback: Math.max(1, Number(lstmSequenceLookback.value) || 336),
  hidden_size: Math.max(8, Number(lstmHiddenSize.value) || 96),
  learning_rate: Math.max(0.00001, Number(lstmLearningRate.value) || 0.001),
  use_calendar_features: Boolean(lstmUseCalendarFeatures.value),
  use_seasonal_residual: Boolean(lstmUseSeasonalResidual.value),
  seasonality_mode: String(lstmSeasonalityMode.value || 'rolling_profile'),
  seasonality_window_days: Math.max(1, Number(lstmSeasonalityWindowDays.value) || 14),
  lags: parseLstmLags(),
  loss_kind: String(lstmLossKind.value || 'quantile'),
  output_mode: 'direct_multi_horizon',
  dropout: Math.max(0, Number(lstmDropout.value) || 0),
  weight_decay: Math.max(0, Number(lstmWeightDecay.value) || 0),
  batch_size: Math.max(8, Number(lstmBatchSize.value) || 64),
  forecast_stride: 1,
  train_mode: String(lstmTrainMode.value || 'warm_start'),
  horizon_key: recommendedLstmParams.value.horizonKey,
});

const isoFromTimestamp = (value) => {
  const ts = Number(value);
  if (!Number.isFinite(ts) || ts <= 0) return null;
  return new Date(ts).toISOString();
};

const stateCards = computed(() => {
  const state = latestState.value || {};
  return [
    { key: 's0', title: 'S0 - Норма', value: state.p_s0 },
    { key: 's1', title: 'S1 - Деградация', value: state.p_s1 },
    { key: 's2', title: 'S2 - Предаварийное', value: state.p_s2 },
  ];
});

const timestampValue = (value) => {
  const ts = Number(new Date(value).getTime());
  return Number.isFinite(ts) ? ts : 0;
};

const modelKindLabel = (value) => {
  if (value === 'ensemble') return 'Оркестр';
  if (value === 'lstm') return 'LSTM';
  if (value === 'sarima') return 'SARIMA';
  return 'Нет данных';
};

const stateSourceLabel = computed(() => modelKindLabel(latestState.value?.run_model_kind));

const primaryRunKind = computed(() => {
  const candidates = [
    { kind: 'ensemble', run: latestEnsembleRun.value },
    { kind: 'sarima', run: latestRun.value },
    { kind: 'lstm', run: latestLstmRun.value },
  ]
    .filter((item) => item.run?.status === 'success')
    .sort((a, b) => timestampValue(b.run?.created_at) - timestampValue(a.run?.created_at));
  return candidates[0]?.kind || 'sarima';
});

const primaryRun = computed(() => {
  if (primaryRunKind.value === 'ensemble') return latestEnsembleRun.value;
  if (primaryRunKind.value === 'lstm') return latestLstmRun.value;
  return latestRun.value;
});

const primaryForecastPoints = computed(() => {
  let rows = [];
  if (primaryRunKind.value === 'ensemble' && ensembleForecastPoints.value.length) rows = ensembleForecastPoints.value;
  else if (primaryRunKind.value === 'lstm' && lstmForecastPoints.value.length) rows = lstmForecastPoints.value;
  else if (forecastPoints.value.length) rows = forecastPoints.value;
  else if (ensembleForecastPoints.value.length) rows = ensembleForecastPoints.value;
  else rows = lstmForecastPoints.value;
  return rows.filter((row) => String(row?.horizon || '') === selectedHorizon.value);
});

const primaryForecastModelLabel = computed(() => modelKindLabel(primaryRunKind.value));
const primaryAlphaHeader = computed(() => (
  primaryRunKind.value === 'ensemble' ? 'alpha (вес SARIMA/LSTM)' : 'Уровень интервала (alpha)'
));
const activeForecastPresetLabel = computed(() => (
  forecastTablePresets.find((item) => item.value === forecastTablePreset.value)?.label || '—'
));
const isOpsPreset = computed(() => forecastTablePreset.value === 'ops');
const isAnalysisPreset = computed(() => forecastTablePreset.value === 'analysis');
const showTrendColumn = computed(() => !isOpsPreset.value);
const showModelTargetColumns = computed(() => !isOpsPreset.value);
const showQuantileColumns = computed(() => isAnalysisPreset.value);
const showAlphaColumn = computed(() => !isOpsPreset.value);

const selectedMetricUnit = computed(() => metricMap[selectedMetricCode.value]?.unit || '');

const forecastScatterPoints = computed(() => (
  forecastPoints.value
    .filter((row) => row.metric_code === selectedMetricCode.value && String(row?.horizon || '') === chartForecastHorizon.value)
    .map((row) => ({ x: timestampValue(row.target_ts), y: Number(row.y_hat) }))
    .filter((p) => Number.isFinite(p.x) && p.x > 0 && Number.isFinite(p.y))
));

const lstmScatterPoints = computed(() => (
  lstmForecastPoints.value
    .filter((row) => row.metric_code === selectedMetricCode.value && String(row?.horizon || '') === chartForecastHorizon.value)
    .map((row) => ({ x: timestampValue(row.target_ts), y: Number(row.y_hat) }))
    .filter((p) => Number.isFinite(p.x) && p.x > 0 && Number.isFinite(p.y))
));

const ensembleScatterPoints = computed(() => (
  ensembleForecastPoints.value
    .filter((row) => row.metric_code === selectedMetricCode.value && String(row?.horizon || '') === chartForecastHorizon.value)
    .map((row) => ({ x: timestampValue(row.target_ts), y: Number(row.y_hat) }))
    .filter((p) => Number.isFinite(p.x) && p.x > 0 && Number.isFinite(p.y))
));

const collectChartForecastPoints = (metricCode) => {
  if (!metricCode) return [];
  return [
    ...forecastPoints.value,
    ...lstmForecastPoints.value,
    ...ensembleForecastPoints.value,
  ]
    .filter((row) => row.metric_code === metricCode && String(row?.horizon || '') === chartForecastHorizon.value)
    .map((row) => ({ x: timestampValue(row.target_ts), y: Number(row.y_hat) }))
    .filter((point) => Number.isFinite(point.x) && point.x > 0 && Number.isFinite(point.y));
};

const getChartForecastBounds = (metricCode) => {
  const points = collectChartForecastPoints(metricCode);
  if (!points.length) return null;
  const xs = points.map((point) => point.x).filter((value) => Number.isFinite(value) && value > 0);
  if (!xs.length) return null;
  return {
    minTs: Math.min(...xs),
    maxTs: Math.max(...xs),
  };
};

const scatterPointCount = computed(() => rawScatterPoints.value.length);
const scatterHasAnyData = computed(() => (
  rawScatterPoints.value.length || forecastScatterPoints.value.length || lstmScatterPoints.value.length || ensembleScatterPoints.value.length
));

const latestRawTimestamp = computed(() => {
  if (!rawScatterPoints.value.length) return null;
  const maxTs = rawScatterPoints.value.reduce((acc, point) => Math.max(acc, Number(point.x) || 0), 0);
  return maxTs > 0 ? maxTs : null;
});

const chartAxisBounds = computed(() => {
  const forecastBounds = getChartForecastBounds(selectedMetricCode.value);
  if (forecastBounds) {
    const startTs = forecastBounds.minTs - (Number(chartWindowMinutes.value) || 0) * 60000;
    return {
      minTs: startTs,
      maxTs: forecastBounds.maxTs,
    };
  }

  if (rawScatterPoints.value.length) {
    const xs = rawScatterPoints.value
      .map((point) => Number(point.x))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (xs.length) {
      return {
        minTs: Math.min(...xs),
        maxTs: Math.max(...xs),
      };
    }
  }
  return null;
});

const rawFreshnessLabel = computed(() => relativeFreshness(latestRawTimestamp.value));
const forecastFreshnessLabel = computed(() => {
  const base = primaryRun.value?.created_at || latestState.value?.timestamp || null;
  return relativeFreshness(base);
});

const normalizeLstmStatus = () => {
  const queueStatus = String(latestLstmQueueJob.value?.status || '').toLowerCase();
  if (queueStatus === 'success') return 'completed';
  if (queueStatus === 'failed') return 'failed';
  if (queueStatus === 'queued' || queueStatus === 'retry_wait') return 'queued';
  if (queueStatus === 'submitting' || queueStatus === 'submitted' || queueStatus === 'polling') return 'running';

  const runStatus = String(latestLstmRun.value?.status || '').toLowerCase();
  if (runStatus === 'success') return 'completed';
  if (runStatus === 'failed') return 'failed';
  if (runStatus === 'pending') return 'queued';
  if (runStatus === 'running') return 'running';
  return 'none';
};

const isLatestLstmOrchestrated = computed(() => (
  latestLstmRun.value?.parameters?.orchestrator_kind === 'sarima_lstm'
));

const workflowStatusKind = computed(() => {
  if (workflowStreamActive.value) return 'running';
  if (workflowStreamStatus.value === 'timeout') return 'timeout';
  if (workflowStreamStatus.value === 'failed') return 'failed';
  if (workflowStreamStatus.value === 'completed') return 'completed';

  if (runningBaseline.value || runningLstm.value || runningOrchestrator.value) return 'running';
  if (pollingLstm.value || lstmAutoPolling.value) return 'running';

  const lstmStatus = normalizeLstmStatus();
  if (lstmStatus === 'failed') return 'failed';
  if (lstmStatus === 'queued' || lstmStatus === 'running') return 'running';

  const run = workflowResultRun.value;
  if (!run) return 'idle';
  if (run.status === 'failed') return 'failed';
  if (run.status === 'success') return 'completed';
  if (run.status === 'running' || run.status === 'pending') return 'running';
  return 'idle';
});

const workflowStatusLabel = computed(() => {
  if (workflowStatusKind.value === 'completed') return 'Завершено';
  if (workflowStatusKind.value === 'timeout') return 'Таймаут';
  if (workflowStatusKind.value === 'failed') return 'Ошибка';
  if (workflowStatusKind.value === 'running') return 'Выполняется';
  return 'Ожидание запуска';
});

const workflowStatusSeverity = computed(() => {
  if (workflowStatusKind.value === 'completed') return 'success';
  if (workflowStatusKind.value === 'timeout') return 'warning';
  if (workflowStatusKind.value === 'failed') return 'danger';
  if (workflowStatusKind.value === 'running') return 'warning';
  return 'secondary';
});

const workflowCurrentStepLabel = computed(() => {
  const step = workflowStreamSnapshot.value?.current_step;
  const steps = workflowStreamSnapshot.value?.steps;
  if (!step || !Array.isArray(steps)) return 'подготовка';
  const found = steps.find((item) => item.key === step.key);
  return found?.title || step.key || 'подготовка';
});

const workflowStepItems = computed(() => {
  const snapshot = workflowStreamSnapshot.value;
  const rawSteps = Array.isArray(snapshot?.steps) && snapshot.steps.length
    ? snapshot.steps
    : (
      workflowMode.value === 'full'
        ? [
          { key: 'sarima', title: 'SARIMA baseline', description: 'Локальная предобработка и SARIMA.' },
          { key: 'lstm', title: 'Удаленный LSTM', description: 'Очередь и расчет на удаленном ПК.' },
          { key: 'ensemble', title: 'Интеграция прогноза', description: 'Сборка итогового оркестра.' },
        ]
        : [
          {
            key: workflowMode.value === 'partial' && partialMethod.value === 'lstm' ? 'lstm' : 'sarima',
            title: workflowMode.value === 'partial' && partialMethod.value === 'lstm' ? 'Удаленный LSTM' : 'SARIMA baseline',
            description: 'Выполнение выбранного сценария.',
          },
        ]
    );

  const currentIndex = Number(snapshot?.current_step?.index || 1);
  const globalStatus = snapshot?.status || workflowStatusKind.value;
  return rawSteps.map((step, idx) => {
    let state = 'pending';
    if (globalStatus === 'failed' && idx + 1 === currentIndex) state = 'failed';
    else if (globalStatus === 'timeout' && idx + 1 === currentIndex) state = 'failed';
    else if (idx + 1 < currentIndex) state = 'done';
    else if (idx + 1 === currentIndex && (globalStatus === 'running' || workflowStreamActive.value)) state = 'current';
    else if (globalStatus === 'completed') state = 'done';

    const statusLabel = state === 'done'
      ? 'Готово'
      : state === 'current'
        ? 'В работе'
        : state === 'failed'
          ? 'Ошибка'
          : 'Ожидание';
    return {
      ...step,
      index: idx + 1,
      state,
      statusLabel,
    };
  });
});

const runAgeHours = (value) => {
  const ts = timestampValue(value);
  if (!ts) return null;
  return Math.max(0, (Date.now() - ts) / 3600000);
};

const iconStatusForSarima = computed(() => {
  const run = latestRun.value;
  if (!run) return 'never';
  if (run.status === 'failed') return 'error';
  if (run.status === 'running' || run.status === 'pending') return 'running';
  if (run.status === 'success') {
    const age = runAgeHours(run.created_at);
    return age !== null && age > FRESH_RUN_WINDOW_HOURS ? 'stale' : 'fresh';
  }
  return 'never';
});

const iconStatusForLstm = computed(() => {
  const status = normalizeLstmStatus();
  if (status === 'failed') return 'error';
  if (status === 'queued' || status === 'running') return 'running';
  if (status === 'completed') {
    const age = runAgeHours(latestLstmRun.value?.created_at);
    return age !== null && age > FRESH_RUN_WINDOW_HOURS ? 'stale' : 'fresh';
  }
  return 'never';
});

const iconStatusForEnsemble = computed(() => {
  const run = latestEnsembleRun.value;
  if (run?.status === 'failed') return 'error';
  if (run?.status === 'running' || run?.status === 'pending') return 'running';
  if (run?.status === 'success') {
    const age = runAgeHours(run.created_at);
    return age !== null && age > FRESH_RUN_WINDOW_HOURS ? 'stale' : 'fresh';
  }

  const lstmStatus = normalizeLstmStatus();
  if (isLatestLstmOrchestrated.value && (lstmStatus === 'queued' || lstmStatus === 'running')) return 'running';
  return 'never';
});

const statusText = (status) => {
  if (status === 'fresh') return 'завершено успешно (<24ч)';
  if (status === 'stale') return 'успешно, но запуск старше 24ч';
  if (status === 'running') return 'производится расчет';
  if (status === 'error') return 'ошибка или неуспешный запуск';
  return 'не запускался';
};

const statusClass = (status) => {
  if (status === 'fresh') return 'run-dot-green';
  if (status === 'stale') return 'run-dot-gray';
  if (status === 'running') return 'run-dot-yellow';
  return 'run-dot-red';
};

const runTypeStatusIcons = computed(() => {
  const rows = [
    { key: 'sarima', shortLabel: 'SARIMA', status: iconStatusForSarima.value, run: latestRun.value },
    { key: 'lstm', shortLabel: 'LSTM', status: iconStatusForLstm.value, run: latestLstmRun.value },
    { key: 'ensemble', shortLabel: 'ОРКЕСТР', status: iconStatusForEnsemble.value, run: latestEnsembleRun.value },
  ];
  return rows.map((item) => {
    const dateText = item.run?.created_at ? formatDateTime(item.run.created_at) : 'не запускался';
    const tooltip = `${item.shortLabel}: ${statusText(item.status)}. Последний запуск: ${dateText}`;
    return {
      ...item,
      tooltip,
      className: statusClass(item.status),
    };
  });
});

const runStatusLabel = (status) => {
  const value = String(status || '').toLowerCase();
  if (value === 'success' || value === 'completed') return 'Успех';
  if (value === 'failed') return 'Ошибка';
  if (value === 'running' || value === 'polling' || value === 'submitting' || value === 'submitted') return 'В работе';
  if (value === 'pending' || value === 'queued' || value === 'retry_wait') return 'В очереди';
  return 'Нет данных';
};

const runStatusSeverity = (status) => {
  const value = String(status || '').toLowerCase();
  if (value === 'success' || value === 'completed') return 'success';
  if (value === 'failed') return 'danger';
  if (value === 'running' || value === 'polling' || value === 'submitting' || value === 'submitted') return 'warning';
  if (value === 'pending' || value === 'queued' || value === 'retry_wait') return 'info';
  return 'secondary';
};

const latestTaskWidgetRows = computed(() => ([
  {
    key: 'sarima',
    title: 'SARIMA run',
    status: latestRun.value?.status || null,
    id: latestRun.value?.id || null,
    at: latestRun.value?.updated_at || latestRun.value?.created_at || null,
    details: latestRun.value?.horizon_set || '',
  },
  {
    key: 'lstm',
    title: 'LSTM run',
    status: latestLstmRun.value?.status || null,
    id: latestLstmRun.value?.id || null,
    at: latestLstmRun.value?.updated_at || latestLstmRun.value?.created_at || null,
    details: latestLstmRun.value?.horizon_set || '',
  },
  {
    key: 'ensemble',
    title: 'Оркестр run',
    status: latestEnsembleRun.value?.status || null,
    id: latestEnsembleRun.value?.id || null,
    at: latestEnsembleRun.value?.updated_at || latestEnsembleRun.value?.created_at || null,
    details: latestEnsembleRun.value?.horizon_set || '',
  },
  {
    key: 'queue',
    title: 'Очередь LSTM',
    status: latestLstmQueueJob.value?.status || null,
    id: latestLstmQueueJob.value?.id || null,
    at: latestLstmQueueJob.value?.updated_at || latestLstmQueueJob.value?.created_at || null,
    details: latestLstmQueueJob.value?.remote_job_id ? `remote_job_id=${latestLstmQueueJob.value.remote_job_id}` : '',
  },
]));

const modelInfluenceSummary = computed(() => {
  if (primaryRunKind.value === 'ensemble') {
    const rows = primaryForecastPoints.value.filter((row) => Number.isFinite(Number(row.alpha)));
    if (rows.length) {
      const avgAlpha = rows.reduce((acc, row) => acc + Number(row.alpha), 0) / rows.length;
      const sarima = Math.max(0, Math.min(1, avgAlpha));
      const lstm = 1 - sarima;
      let dominantLabel = 'баланс SARIMA и LSTM';
      if (sarima >= 0.55) dominantLabel = 'SARIMA';
      if (lstm >= 0.55) dominantLabel = 'LSTM';
      return {
        dominantLabel,
        sarimaPct: (sarima * 100).toFixed(1),
        lstmPct: (lstm * 100).toFixed(1),
      };
    }
    return { dominantLabel: 'баланс SARIMA и LSTM', sarimaPct: '50.0', lstmPct: '50.0' };
  }
  if (primaryRunKind.value === 'sarima') return { dominantLabel: 'SARIMA', sarimaPct: '100.0', lstmPct: '0.0' };
  if (primaryRunKind.value === 'lstm') return { dominantLabel: 'LSTM', sarimaPct: '0.0', lstmPct: '100.0' };
  return { dominantLabel: 'нет данных', sarimaPct: '0.0', lstmPct: '0.0' };
});

const stateEvidence = computed(() => (
  (latestState.value?.evidence && typeof latestState.value.evidence === 'object')
    ? latestState.value.evidence
    : {}
));

const stateProfileLabel = computed(() => {
  const profile = stateEvidence.value?.profile;
  if (profile?.name) {
    return `${profile.name}${profile.version ? ` v${profile.version}` : ''}`;
  }
  return 'Встроенный профиль по умолчанию';
});

const stateProfileHint = computed(() => {
  const mode = stateEvidence.value?.inference_mode === 'risk_features_only'
    ? 'Оценка построена по агрегированным риск-признакам.'
    : 'Оценка построена по конкретным метрикам и их порогам.';
  return mode;
});

const stateConfidenceLabel = computed(() => (
  latestState.value?.confidence != null ? formatPercent(latestState.value.confidence) : '—'
));

const stateConfidenceHint = computed(() => {
  const value = Number(latestState.value?.confidence);
  if (!Number.isFinite(value)) return 'Confidence пока не рассчитан.';
  if (value >= 0.8) return 'Сигнал устойчивый: лидер среди состояний выражен явно.';
  if (value >= 0.6) return 'Сигнал умеренно устойчивый: система видит лидирующее состояние, но разрыв не максимальный.';
  return 'Сигнал слабый: состояние определено, но с небольшим отрывом от альтернатив.';
});

const stateOutcomeSummary = computed(() => {
  const state = latestState.value?.state;
  const top = riskDrivers.value[0];
  if (state === 's2') {
    return {
      title: 'S2 - Предаварийное',
      text: top
        ? `Главный вклад сейчас даёт метрика «${metricLabel(top.metric_code)}». Нужна реакция или проверка оборудования.`
        : 'Система видит высокий риск отказа и рекомендует ускоренную проверку.',
    };
  }
  if (state === 's1') {
    return {
      title: 'S1 - Деградация',
      text: top
        ? `Система видит ухудшение, сильнее всего влияет «${metricLabel(top.metric_code)}». Нужен контроль и проверка тренда.`
        : 'Состояние ещё не аварийное, но уже есть заметные признаки деградации.',
    };
  }
  if (state === 's0') {
    return {
      title: 'S0 - Норма',
      text: top
        ? `Критичных признаков нет. Самая заметная метрика сейчас: «${metricLabel(top.metric_code)}», но она не тянет систему в аварийный режим.`
        : 'Критичных признаков не найдено, система остаётся в рабочем состоянии.',
    };
  }
  return {
    title: 'Нет оценки',
    text: 'Для интерпретации состояния пока недостаточно данных.',
  };
});

const metricThreshold = (code) => riskThresholdMap[code] || null;

const riskDrivers = computed(() => {
  const evidenceComponents = Array.isArray(stateEvidence.value?.top_components)
    ? stateEvidence.value.top_components
    : [];
  if (evidenceComponents.length) {
    return evidenceComponents
      .map((item) => ({
        metric_code: item.metric_code,
        value: Number(item.value),
        threshold: Number(item.threshold),
        ratio: Number(item.ratio),
        risk_component: Number(item.risk_component),
        unit: metricUnit(item.metric_code),
        source: item.source,
      }))
      .filter((item) => item.metric_code && Number.isFinite(item.risk_component))
      .sort((a, b) => b.risk_component - a.risk_component);
  }

  const rows = representativeForecastPoints.value || [];
  const drivers = rows
    .map((row) => {
      const threshold = metricThreshold(row.metric_code);
      const p90 = Number(row.p90);
      if (!threshold || !Number.isFinite(p90) || threshold <= 0) return null;
      const ratio = p90 / threshold;
      const riskComponent = Math.max(0, Math.min(1, (ratio - 0.75) / 0.75));
      return {
        metric_code: row.metric_code,
        value: p90,
        threshold,
        ratio,
        risk_component: riskComponent,
        unit: metricUnit(row.metric_code),
        source: 'forecast_fallback',
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.risk_component - a.risk_component);

  const dedup = [];
  const seen = new Set();
  for (const item of drivers) {
    if (seen.has(item.metric_code)) continue;
    seen.add(item.metric_code);
    dedup.push(item);
    if (dedup.length >= 4) break;
  }
  return dedup;
});

const driverExplanation = (item) => {
  if (!Number.isFinite(Number(item?.ratio))) return 'Метрика попала в топ факторов риска.';
  if (Number(item.ratio) >= 1) return 'Значение уже выше порога и поэтому сильно тянет систему к S1/S2.';
  if (Number(item.ratio) >= 0.85) return 'Метрика очень близко подошла к порогу и заметно влияет на итог.';
  if (Number(item.ratio) >= 0.7) return 'Метрика ещё не критична, но уже формирует предупреждающий сигнал.';
  return 'Метрика учитывается в расчете, но её вклад пока умеренный.';
};

const workflowRunButtonLabel = computed(() => {
  if (workflowMode.value === 'full') return 'Запустить полный прогноз (SARIMA + LSTM + Оркестр)';
  if (partialMethod.value === 'sarima') return 'Запустить SARIMA прогноз';
  if (partialMethod.value === 'lstm') return 'Запустить LSTM прогноз';
  return 'Выберите метод';
});

const baselineSeasonalityModeLabel = (value) => (
  baselineSeasonalityModeMap[String(value || '').trim()]?.shortLabel || 'STL + вернуть сезонность'
);

const workflowStep2StartDisabled = computed(() => (
  workflowBusy.value
  || workflowStreamActive.value
  || !selectedSerial.value
  || !Array.isArray(launchHorizons.value)
  || !launchHorizons.value.length
  || (workflowMode.value === 'partial' && !partialMethod.value)
));

const partialSarimaChecked = computed({
  get: () => partialMethod.value === 'sarima',
  set: (checked) => {
    if (checked) {
      partialMethod.value = 'sarima';
      return;
    }
    if (partialMethod.value === 'sarima') partialMethod.value = '';
  },
});

const partialLstmChecked = computed({
  get: () => partialMethod.value === 'lstm',
  set: (checked) => {
    if (checked) {
      partialMethod.value = 'lstm';
      return;
    }
    if (partialMethod.value === 'lstm') partialMethod.value = '';
  },
});

const canPollWorkflow = computed(() => {
  if (workflowStreamActive.value) return false;
  if (!selectedSerial.value) return false;
  if (workflowMode.value === 'full') return !!latestLstmRun.value?.id;
  if (partialMethod.value === 'lstm') return !!latestLstmRun.value?.id;
  return false;
});

const workflowResultRun = computed(() => {
  if (lastWorkflowRequestedType.value === 'full') return latestEnsembleRun.value || latestLstmRun.value || latestRun.value;
  if (lastWorkflowRequestedType.value === 'lstm') return latestLstmRun.value;
  return latestRun.value;
});

const workflowCanRestart = computed(() => (
  workflowStatusKind.value === 'completed'
  || workflowStatusKind.value === 'failed'
  || workflowStatusKind.value === 'timeout'
));

const formatRuntime = (seconds) => {
  const n = Number(seconds);
  if (!Number.isFinite(n)) return '—';
  if (n < 1) return '< 1 сек';
  return `${n.toFixed(1)} сек`;
};

const workflowSummaryRows = computed(() => {
  if (!workflowCanRestart.value) return [];

  const run = workflowResultRun.value;
  const snapshot = workflowStreamSnapshot.value || {};
  const summary = snapshot.summary || {};
  const quality = run?.quality || {};
  const parameters = run?.parameters || {};
  const runPointRows = (
    lastWorkflowRequestedType.value === 'full'
      ? (ensembleForecastPoints.value.length ? ensembleForecastPoints.value : primaryForecastPoints.value)
      : (lastWorkflowRequestedType.value === 'lstm' ? lstmForecastPoints.value : forecastPoints.value)
  );
  const metricsProcessed = summary.metrics_processed
    ?? quality.metrics_processed
    ?? quality.remote_quality?.metrics_processed
    ?? quality.result?.quality?.metrics_processed
    ?? (runPointRows.length ? new Set(runPointRows.map((row) => row.metric_code).filter(Boolean)).size : null);
  const historyPoints = summary.history_points_total
    ?? quality.history_points_total
    ?? quality.remote_quality?.history_points_total
    ?? quality.result?.quality?.history_points_total;
  const pointsCreated = summary.points_created ?? quality.points_created;
  const pointsCreatedSafe = pointsCreated ?? (runPointRows.length || null);
  const summaryRuntime = Number(summary.duration_sec);
  const runtimeSec = (Number.isFinite(summaryRuntime) && summaryRuntime > 0.05)
    ? summaryRuntime
    : estimateRunDurationSec(run);

  const lookbackText = (() => {
    if (lastWorkflowRequestedType.value === 'full') {
      return `SARIMA ${baselineLookbackDays.value}д / LSTM ${lstmLookbackDays.value}д`;
    }
    if (lastWorkflowRequestedType.value === 'lstm') return `${lstmLookbackDays.value} дн`;
    return `${baselineLookbackDays.value} дн`;
  })();

  const freqText = (() => {
    if (lastWorkflowRequestedType.value === 'full') {
      return `SARIMA ${baselineFreq.value}, LSTM ${lstmFreq.value}`;
    }
    if (lastWorkflowRequestedType.value === 'lstm') return lstmFreq.value;
    return baselineFreq.value;
  })();

  const horizonText = summary.horizon_set || run?.horizon_set || asCsv(parameters.horizons) || '24h,7d,30d';
  const seasonalityModeText = (() => {
    if (lastWorkflowRequestedType.value === 'lstm') return 'Не используется';
    const mode = parameters.seasonality_mode
      || latestRun.value?.parameters?.seasonality_mode
      || baselineSeasonalityMode.value;
    return baselineSeasonalityModeLabel(mode);
  })();

  return [
    { key: 'ui_mode', label: 'Режим', value: isForecastExpert.value ? 'Экспертный' : 'Базовый' },
    { key: 'type', label: 'Тип запуска', value: workflowRunTypeLabel.value },
    { key: 'model', label: 'Итоговая модель', value: modelKindLabel(run?.model_kind) },
    { key: 'status', label: 'Статус', value: workflowStatusLabel.value },
    { key: 'runtime', label: 'Время выполнения', value: formatRuntime(runtimeSec) },
    { key: 'metrics', label: 'Метрик обработано', value: metricsProcessed ?? '—' },
    { key: 'history', label: 'Точек истории в расчете', value: historyPoints ?? '—' },
    { key: 'points', label: 'Точек прогноза', value: pointsCreatedSafe ?? '—' },
    { key: 'lookback', label: 'Период обучения', value: lookbackText },
    { key: 'freq', label: 'Шаг агрегации', value: freqText },
    { key: 'seasonality', label: 'Режим сезонности SARIMA', value: seasonalityModeText },
    { key: 'horizon', label: 'Дальность прогноза', value: horizonText },
  ];
});

const workflowRunTypeLabel = computed(() => {
  if (lastWorkflowRequestedType.value === 'full') return 'Полный (SARIMA + LSTM + оркестр)';
  if (lastWorkflowRequestedType.value === 'lstm') return 'Частичный: LSTM';
  return 'Частичный: SARIMA';
});

const scatterChartData = computed(() => {
  const datasets = [];

  if (showSeries.raw && rawScatterPoints.value.length) {
    datasets.push({
      label: 'Исторические точки',
      data: rawScatterPoints.value,
      borderColor: 'rgba(14, 165, 233, 0.9)',
      backgroundColor: 'rgba(14, 165, 233, 0.45)',
      pointRadius: 2.4,
      pointHoverRadius: 4,
      showLine: false,
    });
  }

  if (showSeries.sarima && forecastScatterPoints.value.length) {
    datasets.push({
      label: 'SARIMA-прогноз',
      data: forecastScatterPoints.value,
      borderColor: 'rgba(249, 115, 22, 1)',
      backgroundColor: 'rgba(249, 115, 22, 0.95)',
      pointRadius: 4.2,
      pointHoverRadius: 5.5,
      pointStyle: 'triangle',
      showLine: false,
    });
  }

  if (showSeries.lstm && lstmScatterPoints.value.length) {
    datasets.push({
      label: 'LSTM-прогноз',
      data: lstmScatterPoints.value,
      borderColor: 'rgba(34, 197, 94, 1)',
      backgroundColor: 'rgba(34, 197, 94, 0.95)',
      pointRadius: 4,
      pointHoverRadius: 5.2,
      pointStyle: 'rectRounded',
      showLine: false,
    });
  }

  if (showSeries.ensemble && ensembleScatterPoints.value.length) {
    datasets.push({
      label: 'Итоговый оркестр',
      data: ensembleScatterPoints.value,
      borderColor: 'rgba(15, 118, 110, 1)',
      backgroundColor: 'rgba(15, 118, 110, 0.95)',
      pointRadius: 4.4,
      pointHoverRadius: 5.8,
      pointStyle: 'star',
      showLine: false,
    });
  }

  return { datasets };
});

const scatterChartOptions = computed(() => ({
  maintainAspectRatio: false,
  animation: false,
  parsing: false,
  interaction: { mode: 'nearest', intersect: false },
  plugins: {
    legend: {
      display: true,
      labels: { boxWidth: 16 },
    },
    tooltip: {
      callbacks: {
        title: (items) => (items.length ? formatDateTime(items[0].parsed.x) : ''),
        label: (ctx) => {
          const unit = selectedMetricUnit.value ? ` ${selectedMetricUnit.value}` : '';
          return `${ctx.dataset.label}: ${formatNum(ctx.parsed.y)}${unit}`;
        },
      },
    },
  },
  scales: {
    x: {
      type: 'linear',
      min: chartAxisBounds.value?.minTs,
      max: chartAxisBounds.value?.maxTs,
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
      ticks: {
        maxTicksLimit: 9,
        callback: (value) => formatAxisTick(Number(value)),
      },
      title: { display: true, text: 'Время' },
    },
    y: {
      beginAtZero: true,
      max: selectedMetricUnit.value === '%' ? 100 : undefined,
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
      title: {
        display: true,
        text: selectedMetricUnit.value ? `Значение (${selectedMetricUnit.value})` : 'Значение',
      },
    },
  },
}));

const formatDateTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return String(value);
  }
};

const formatAxisTick = (value) => {
  if (!Number.isFinite(value)) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const formatNum = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

const asCsv = (value) => {
  if (Array.isArray(value)) return value.join(',');
  if (typeof value === 'string') return value;
  return '';
};

const estimateRunDurationSec = (run) => {
  const startTs = timestampValue(run?.started_at || workflowStartTs.value);
  const endTs = timestampValue(run?.finished_at || workflowFinishTs.value);
  if (!startTs) return null;
  if (!endTs) return Math.max(0, (Date.now() - startTs) / 1000);
  return Math.max(0, (endTs - startTs) / 1000);
};

const stateLabel = (value) => {
  if (value === 's0') return 'S0';
  if (value === 's1') return 'S1';
  if (value === 's2') return 'S2';
  return 'Неизвестно';
};

const stateSeverity = (value) => {
  if (value === 's0') return 'success';
  if (value === 's1') return 'warning';
  if (value === 's2') return 'danger';
  return 'secondary';
};

const metricLabel = (code) => metricMap[code]?.label || code;
const metricUnit = (code) => metricMap[code]?.unit || '';
const metricColor = (code) => {
  if (code === 'cpu_load_total') return '#f97316';
  if (code === 'mem_usage_percent') return '#0ea5e9';
  if (code === 'net_bytes_sent' || code === 'net_bytes_recv') return '#22c55e';
  if (code === 'ping_latency_gateway') return '#8b5cf6';
  if (code === 'system_temperature' || code === 'storcli_drive_temperature') return '#ef4444';
  if (code === 'storcli_predictive_failure_count') return '#e11d48';
  return '#64748b';
};

const riskRatioByRow = (row) => {
  const thr = metricThreshold(row?.metric_code);
  const upper = Number(row?.p90);
  if (!thr || !Number.isFinite(upper) || thr <= 0) return null;
  return upper / thr;
};

const riskLevelByRatio = (ratio) => {
  if (ratio === null || ratio === undefined) return 'none';
  if (ratio >= 1) return 'critical';
  if (ratio >= 0.85) return 'high';
  if (ratio >= 0.7) return 'medium';
  return 'low';
};

const riskLevelByRow = (row) => riskLevelByRatio(riskRatioByRow(row));

const riskLabelByRatio = (ratio) => {
  const level = riskLevelByRatio(ratio);
  if (level === 'critical') return 'Критический';
  if (level === 'high') return 'Высокий';
  if (level === 'medium') return 'Средний';
  if (level === 'low') return 'Низкий';
  return 'Н/Д';
};

const riskSeverityByRatio = (ratio) => {
  const level = riskLevelByRatio(ratio);
  if (level === 'critical') return 'danger';
  if (level === 'high') return 'warning';
  if (level === 'medium') return 'info';
  if (level === 'low') return 'success';
  return 'secondary';
};

const riskLabel = (row) => riskLabelByRatio(riskRatioByRow(row));
const riskSeverity = (row) => riskSeverityByRatio(riskRatioByRow(row));

const riskCellClass = (row) => {
  const level = riskLevelByRow(row);
  if (level === 'critical') return 'risk-cell-critical';
  if (level === 'high') return 'risk-cell-high';
  if (level === 'medium') return 'risk-cell-medium';
  if (level === 'low') return 'risk-cell-low';
  return 'risk-cell-none';
};

const riskTooltip = (row) => {
  const thr = metricThreshold(row?.metric_code);
  const upper = Number(row?.p90);
  if (!thr || !Number.isFinite(upper)) {
    return `Метрика: ${metricLabel(row?.metric_code)}. Порог риска не задан.`;
  }
  const ratioPct = (upper / thr) * 100;
  return `Формула риска: p90 / порог = ${formatNum(upper, 2)} / ${formatNum(thr, 2)} = ${formatNum(ratioPct, 1)}%`;
};

const representativeForecastPoints = computed(() => {
  const rows = Array.isArray(primaryForecastPoints.value) ? primaryForecastPoints.value : [];
  const bestByMetric = new Map();

  rows.forEach((row) => {
    const metricCode = String(row?.metric_code || '').trim();
    if (!metricCode) return;

    const ratio = riskRatioByRow(row);
    const riskScore = Number.isFinite(Number(ratio)) ? Number(ratio) : -1;
    const tsScore = timestampValue(row?.target_ts || row?.created_at);

    const current = bestByMetric.get(metricCode);
    if (!current) {
      bestByMetric.set(metricCode, { row, riskScore, tsScore });
      return;
    }

    if (riskScore > current.riskScore + 1e-9) {
      bestByMetric.set(metricCode, { row, riskScore, tsScore });
      return;
    }

    if (Math.abs(riskScore - current.riskScore) <= 1e-9 && tsScore >= current.tsScore) {
      bestByMetric.set(metricCode, { row, riskScore, tsScore });
    }
  });

  return [...bestByMetric.values()]
    .map((item) => item.row)
    .sort((a, b) => metricLabel(a.metric_code).localeCompare(metricLabel(b.metric_code), 'ru'));
});

const primaryAlphaValue = (row) => {
  const alpha = Number(row?.alpha);
  if (!Number.isFinite(alpha)) return '—';
  if (row?.model_kind === 'ensemble') return `${alpha.toFixed(3)} / ${(1 - alpha).toFixed(3)}`;
  return alpha.toFixed(3);
};

const primaryAlphaTooltip = (row) => {
  const alpha = Number(row?.alpha);
  if (!Number.isFinite(alpha)) return 'Нет данных по alpha';
  if (row?.model_kind === 'ensemble') {
    const method = row?.labels?.alpha_selection?.selection_method || 'unknown';
    const methodLabel = ({
      automatic_metric_weight: 'автоматически по истории ошибок',
      automatic_segment_weight: 'автоматически по последним совместимым ошибкам в сегменте горизонта',
      default_prior: 'по базовому приоритету',
      manual_profile_override: 'фиксированный вес из профиля',
      winner_bias_recent_compatible_error: 'смещение в пользу лучшей модели по последним совместимым ошибкам',
      sarima_only: 'только SARIMA',
      lstm_only: 'только LSTM',
    })[method] || method;
    return `Вес SARIMA: ${alpha.toFixed(3)}, вес LSTM: ${(1 - alpha).toFixed(3)}. Метод выбора: ${methodLabel}.`;
  }
  return `Уровень интервального прогноза: ${alpha.toFixed(3)}`;
};

const filteredForecastPoints = computed(() => {
  const rows = representativeForecastPoints.value;
  if (!isOpsPreset.value) return rows;
  return rows.filter((row) => {
    const level = riskLevelByRow(row);
    return level === 'medium' || level === 'high' || level === 'critical';
  });
});

const forecastRowClass = (row) => {
  const level = riskLevelByRow(row);
  if (level === 'critical') return 'row-risk-critical';
  if (level === 'high') return 'row-risk-high';
  if (level === 'medium') return 'row-risk-medium';
  return '';
};

const downsampleSeries = (rows, maxPoints = MAX_SPARKLINE_POINTS) => {
  if (rows.length <= maxPoints) return rows;
  const step = Math.ceil(rows.length / maxPoints);
  const sampled = [];
  for (let i = 0; i < rows.length; i += step) sampled.push(rows[i]);
  if (sampled[sampled.length - 1] !== rows[rows.length - 1]) sampled.push(rows[rows.length - 1]);
  return sampled.slice(-maxPoints);
};

const buildSparklinePath = (values) => {
  if (!Array.isArray(values) || values.length < 2) return '';
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const isFlat = maxV === minV;
  const range = isFlat ? 1 : (maxV - minV);

  return values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * SPARKLINE_WIDTH;
    const y = isFlat
      ? SPARKLINE_HEIGHT / 2
      : SPARKLINE_HEIGHT - ((value - minV) / range) * (SPARKLINE_HEIGHT - 3) - 1.5;
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
};

const sparklinePath = (metricCode) => metricTrendMap.value[metricCode]?.path || '';
const sparklineTooltip = (metricCode) => {
  const entry = metricTrendMap.value[metricCode];
  if (!entry || !entry.count) return `${metricLabel(metricCode)}: нет данных за выбранный период`;
  return `${metricLabel(metricCode)}: ${entry.count} точек, последнее значение ${formatNum(entry.lastValue)} ${metricUnit(metricCode)}`;
};

const fetchRawSeriesRows = async (metricCode, limit = 50000, anchorTs = null) => {
  if (!selectedDeviceId.value || !metricCode) return [];

  let endTs = Number(anchorTs);
  if (!Number.isFinite(endTs) || endTs <= 0) {
    const latestParams = new URLSearchParams();
    latestParams.set('device', String(selectedDeviceId.value));
    latestParams.set('code', metricCode);
    latestParams.set('ordering', '-timestamp');
    latestParams.set('limit', '1');
    const latestRes = await apiClient.get(`metrics-raw/?${latestParams.toString()}`);
    const latestRows = unwrap(latestRes);
    const latestRow = latestRows[0];
    endTs = timestampValue(latestRow?.timestamp);
  }
  if (!Number.isFinite(endTs) || endTs <= 0) return [];

  const startIso = isoFromTimestamp(endTs - (Number(chartWindowMinutes.value) || 0) * 60000);
  const endIso = isoFromTimestamp(endTs);
  if (!startIso || !endIso) return [];

  const params = new URLSearchParams();
  params.set('device', String(selectedDeviceId.value));
  params.set('code', metricCode);
  params.set('date_from', startIso);
  params.set('date_to', endIso);
  params.set('ordering', 'timestamp');
  params.set('limit', String(limit));
  const res = await apiClient.get(`metrics-raw/?${params.toString()}`);
  return unwrap(res)
    .map((row) => ({ timestamp: row.timestamp, value: Number(row.value) }))
    .filter((row) => Number.isFinite(timestampValue(row.timestamp)) && Number.isFinite(row.value));
};

const loadMetricTrendSeries = async () => {
  metricTrendMap.value = {};
  if (!selectedDeviceId.value) return;

  const codes = [...new Set(
    [
      ...forecastPoints.value,
      ...lstmForecastPoints.value,
      ...ensembleForecastPoints.value,
    ].map((item) => item.metric_code).filter(Boolean)
  )];
  if (!codes.length) return;

  const entries = await Promise.all(codes.map(async (metricCode) => {
    try {
      const forecastBounds = getChartForecastBounds(metricCode);
      const rows = await fetchRawSeriesRows(metricCode, 50000, forecastBounds?.minTs || null);
      const sampled = downsampleSeries(rows);
      const values = sampled.map((row) => row.value);
      return [
        metricCode,
        {
          count: rows.length,
          lastValue: rows.length ? rows[rows.length - 1].value : null,
          latestTs: rows.length ? rows[rows.length - 1].timestamp : null,
          path: buildSparklinePath(values),
        },
      ];
    } catch {
      return [metricCode, { count: 0, lastValue: null, latestTs: null, path: '' }];
    }
  }));

  metricTrendMap.value = Object.fromEntries(entries);
};

const relativeFreshness = (value) => {
  if (!value) return 'нет данных';
  const ts = typeof value === 'number' ? value : timestampValue(value);
  if (!Number.isFinite(ts) || ts <= 0) return 'нет данных';
  const diffMin = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (diffMin <= 1) return 'только что';
  if (diffMin < 60) return `${diffMin} мин назад`;
  const hours = Math.floor(diffMin / 60);
  const mins = diffMin % 60;
  if (hours < 24) return `${hours} ч ${mins} мин назад`;
  const days = Math.floor(hours / 24);
  return `${days} д ${hours % 24} ч назад`;
};

const loadDevices = async () => {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = unwrap(res);
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch {
    devices.value = [];
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить список устройств', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
};

const loadLatestRun = async () => {
  latestRun.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.get(`forecast-runs/latest/?serial=${encodeURIComponent(selectedSerial.value)}&model_kind=sarima`);
    latestRun.value = res.data;
  } catch {
    latestRun.value = null;
  }
};

const loadLatestLstmRun = async () => {
  latestLstmRun.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.get(`forecast-runs/latest/?serial=${encodeURIComponent(selectedSerial.value)}&model_kind=lstm`);
    latestLstmRun.value = res.data;
  } catch {
    latestLstmRun.value = null;
  }
};

const loadLatestEnsembleRun = async () => {
  latestEnsembleRun.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.get(`forecast-runs/latest/?serial=${encodeURIComponent(selectedSerial.value)}&model_kind=ensemble`);
    latestEnsembleRun.value = res.data;
  } catch {
    latestEnsembleRun.value = null;
  }
};

const loadLatestLstmQueueJob = async () => {
  latestLstmQueueJob.value = null;
  if (!selectedSerial.value) return;
  try {
    const params = new URLSearchParams();
    if (latestLstmRun.value?.id) params.set('run_id', String(latestLstmRun.value.id));
    else params.set('serial', selectedSerial.value);
    const res = await apiClient.get(`forecast-queue-jobs/latest/?${params.toString()}`);
    latestLstmQueueJob.value = res.data;
  } catch {
    latestLstmQueueJob.value = null;
  }
};

const loadLatestState = async () => {
  latestState.value = null;
  if (!selectedSerial.value) return;

  const stateCandidates = [
    { kind: 'ensemble', run: latestEnsembleRun.value },
    { kind: 'lstm', run: latestLstmRun.value },
    { kind: 'sarima', run: latestRun.value },
  ]
    .filter((item) => item.run?.status === 'success' && item.run?.id)
    .sort((a, b) => timestampValue(b.run?.created_at) - timestampValue(a.run?.created_at));

  for (const candidate of stateCandidates) {
    try {
      const url = `state-estimates/latest/?serial=${encodeURIComponent(selectedSerial.value)}&horizon=${encodeURIComponent(selectedHorizon.value)}&run=${encodeURIComponent(candidate.run.id)}&model_kind=${encodeURIComponent(candidate.kind)}`;
      const res = await apiClient.get(url);
      latestState.value = res.data;
      return;
    } catch {
      // continue
    }
  }
};

const loadForecastPoints = async () => {
  forecastPoints.value = [];
  if (!selectedDeviceId.value || !latestRun.value?.id) return;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('run', String(latestRun.value.id));
    params.set('model_kind', 'sarima');
    params.set('ordering', '-target_ts');
    const res = await apiClient.get(`forecast-points/?${params.toString()}`);
    forecastPoints.value = unwrap(res);
  } catch {
    forecastPoints.value = [];
  }
};

const loadLstmForecastPoints = async () => {
  lstmForecastPoints.value = [];
  if (!selectedDeviceId.value || !latestLstmRun.value?.id) return;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('run', String(latestLstmRun.value.id));
    params.set('model_kind', 'lstm');
    params.set('ordering', '-target_ts');
    const res = await apiClient.get(`forecast-points/?${params.toString()}`);
    lstmForecastPoints.value = unwrap(res);
  } catch {
    lstmForecastPoints.value = [];
  }
};

const loadEnsembleForecastPoints = async () => {
  ensembleForecastPoints.value = [];
  if (!selectedDeviceId.value || !latestEnsembleRun.value?.id) return;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('run', String(latestEnsembleRun.value.id));
    params.set('model_kind', 'ensemble');
    params.set('ordering', '-target_ts');
    const res = await apiClient.get(`forecast-points/?${params.toString()}`);
    ensembleForecastPoints.value = unwrap(res);
  } catch {
    ensembleForecastPoints.value = [];
  }
};

const loadMetricScatter = async () => {
  rawScatterPoints.value = [];
  if (!selectedDeviceId.value || !selectedMetricCode.value) return;
  chartLoading.value = true;
  try {
    const forecastBounds = getChartForecastBounds(selectedMetricCode.value);
    const rows = await fetchRawSeriesRows(selectedMetricCode.value, 50000, forecastBounds?.minTs || null);
    rawScatterPoints.value = rows
      .map((row) => ({ x: timestampValue(row.timestamp), y: Number(row.value) }))
      .filter((p) => Number.isFinite(p.x) && p.x > 0 && Number.isFinite(p.y));
  } catch {
    rawScatterPoints.value = [];
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить точки для графика', life: 3500 });
  } finally {
    chartLoading.value = false;
  }
};

const loadOrchestratorDefaults = async () => {
  try {
    const res = await apiClient.get('forecast-runs/orchestrator_defaults/');
    const beta = Number(res?.data?.ensemble_beta);
    const ws = Number(res?.data?.ensemble_weights?.sarima);
    const wl = Number(res?.data?.ensemble_weights?.lstm);

    if (Number.isFinite(beta)) ensembleBeta.value = Math.max(0, beta);
    if (Number.isFinite(ws)) ensembleSarimaWeight.value = Math.max(0, ws);
    if (Number.isFinite(wl)) ensembleLstmWeight.value = Math.max(0, wl);
  } catch {
    // keep local defaults
  }
};

const loadAll = async () => {
  loading.value = true;
  try {
    await Promise.all([loadLatestRun(), loadLatestLstmRun(), loadLatestEnsembleRun()]);
    await Promise.all([
      loadLatestState(),
      loadForecastPoints(),
      loadLstmForecastPoints(),
      loadEnsembleForecastPoints(),
      loadLatestLstmQueueJob(),
    ]);
    await refreshChartData();
    syncLstmAutoPolling();
  } finally {
    loading.value = false;
  }
};

const refreshChartData = async () => {
  await loadMetricScatter();
  await loadMetricTrendSeries();
};

const refreshAll = async () => {
  await loadDevices();
  await loadAll();
};

const stopWorkflowStream = () => {
  if (workflowStreamController) {
    workflowStreamController.abort();
    workflowStreamController = null;
  }
  workflowStreamActive.value = false;
};

const handleWorkflowStreamEvent = async (event) => {
  if (!event || typeof event !== 'object') return;
  workflowStreamSnapshot.value = event;
  workflowStreamLastEvent.value = String(event.event || 'progress');
  if (event.status) workflowStreamStatus.value = String(event.status);

  if (event.event === 'poll_error') {
    workflowStreamError.value = String(event.poll_error || 'Ошибка опроса realtime');
  }
  if (event.event === 'done') {
    workflowStreamActive.value = false;
    workflowFinishTs.value = new Date().toISOString();
    workflowUiStep.value = 4;
    if (event.status === 'completed') {
      toast.add({ severity: 'success', summary: 'Готово', detail: 'Прогнозирование завершено', life: 3200 });
    } else if (event.status === 'failed') {
      toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Прогнозирование завершилось с ошибкой', life: 4200 });
    }
    await loadAll();
  }
  if (event.event === 'timeout') {
    workflowStreamActive.value = false;
    workflowStreamStatus.value = 'timeout';
    workflowFinishTs.value = new Date().toISOString();
    workflowUiStep.value = 4;
    toast.add({ severity: 'warn', summary: 'Таймаут', detail: 'Realtime-стрим достиг лимита ожидания', life: 4200 });
    await loadAll();
  }
};

const startWorkflowStream = async ({ mode, sarimaRunId = null, lstmRunId = null, ensembleRunId = null }) => {
  stopWorkflowStream();
  workflowStreamError.value = '';
  workflowStreamSnapshot.value = null;
  workflowStreamStatus.value = 'running';
  workflowStreamLastEvent.value = '';
  workflowStreamActive.value = true;

  const token = localStorage.getItem('auth_token');
  if (!token) {
    workflowStreamActive.value = false;
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Нет токена авторизации для realtime потока', life: 4200 });
    return;
  }

  const params = new URLSearchParams();
  params.set('mode', mode);
  if (selectedSerial.value) params.set('serial', selectedSerial.value);
  if (sarimaRunId) params.set('sarima_run_id', String(sarimaRunId));
  if (lstmRunId) params.set('lstm_run_id', String(lstmRunId));
  if (ensembleRunId) params.set('ensemble_run_id', String(ensembleRunId));
  params.set('poll_interval_sec', String(Math.max(1, Number(lstmPollIntervalSec.value) || 2)));
  params.set('max_wait_sec', '900');

  workflowStreamController = new AbortController();
  try {
    const response = await fetch(`/api/forecast-runs/workflow_stream/?${params.toString()}`, {
      method: 'GET',
      headers: { Authorization: `Token ${token}` },
      signal: workflowStreamController.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`workflow stream http ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    let keepReading = true;
    while (keepReading) {
      const { done, value } = await reader.read();
      if (done) {
        keepReading = false;
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf('\n');
      while (idx >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) {
          try {
            const event = JSON.parse(line);
            // eslint-disable-next-line no-await-in-loop
            await handleWorkflowStreamEvent(event);
          } catch {
            // ignore malformed chunk
          }
        }
        idx = buffer.indexOf('\n');
      }
    }
  } catch (e) {
    if (e?.name !== 'AbortError') {
      workflowStreamActive.value = false;
      workflowStreamStatus.value = 'failed';
      workflowStreamError.value = e?.message || 'Ошибка realtime потока';
      workflowFinishTs.value = new Date().toISOString();
      workflowUiStep.value = 4;
      toast.add({ severity: 'error', summary: 'Realtime stream', detail: workflowStreamError.value, life: 4200 });
      await loadAll();
    }
  } finally {
    workflowStreamController = null;
    workflowStreamActive.value = false;
  }
};

const normalizeEnsembleWeights = () => {
  const s = Math.max(0, Number(ensembleSarimaWeight.value) || 0);
  const l = Math.max(0, Number(ensembleLstmWeight.value) || 0);
  const total = s + l;
  if (total <= 0) return { sarima: 0.5, lstm: 0.5 };
  return { sarima: s / total, lstm: l / total };
};

const runBaseline = async () => {
  let started = false;
  runningBaseline.value = true;
  stopWorkflowStream();
  workflowStreamStatus.value = 'running';
  workflowStartTs.value = new Date().toISOString();
  workflowFinishTs.value = null;
  try {
    const payload = {
      lookback_days: baselineLookbackDays.value,
      freq: baselineFreq.value,
      horizons: launchHorizonCsv.value,
      save_stl_components: baselineSaveStl.value,
      seasonality_mode: baselineSeasonalityMode.value,
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;

    const res = await apiClient.post('forecast-runs/run_baseline/', payload);
    const runIds = Array.isArray(res?.data?.run_ids) ? res.data.run_ids : [];
    const sarimaRunId = runIds.length ? Number(runIds[0]) : null;
    const failed = Number(res?.data?.failed_runs || 0);
    if (failed > 0) {
      toast.add({
        severity: 'warn',
        summary: 'Внимание',
        detail: `SARIMA прогноз завершен с ошибками: ${failed}`,
        life: 3800,
      });
    } else {
      toast.add({ severity: 'success', summary: 'Готово', detail: 'SARIMA прогноз выполнен', life: 3000 });
    }
    await startWorkflowStream({
      mode: 'sarima',
      sarimaRunId,
    });
    started = true;
    workflowFinishTs.value = new Date().toISOString();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить SARIMA прогноз';
    workflowStreamStatus.value = 'failed';
    workflowFinishTs.value = new Date().toISOString();
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningBaseline.value = false;
  }
  return started;
};

const runLstmRemote = async () => {
  let started = false;
  runningLstm.value = true;
  stopWorkflowStream();
  workflowStreamStatus.value = 'running';
  workflowStartTs.value = new Date().toISOString();
  workflowFinishTs.value = null;
  try {
    const payload = {
      lookback_days: lstmLookbackDays.value,
      freq: lstmFreq.value,
      horizons: launchHorizonCsv.value,
      no_wait: true,
      max_retries: lstmMaxRetries.value,
      poll_interval_sec: lstmPollIntervalSec.value,
      max_wait_sec: 120,
      lstm_options: buildLstmOptionsPayload(),
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;

    const res = await apiClient.post('forecast-runs/run_lstm_remote/', payload);
    const runIds = Array.isArray(res?.data?.run_ids) ? res.data.run_ids : [];
    const lstmRunId = runIds.length ? Number(runIds[0]) : null;

    toast.add({
      severity: 'success',
      summary: 'Задача отправлена',
      detail: 'LSTM прогноз поставлен в очередь и будет обработан через backend',
      life: 3200,
    });

    await startWorkflowStream({
      mode: 'lstm',
      lstmRunId,
    });
    started = true;
    workflowFinishTs.value = new Date().toISOString();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось запустить LSTM прогноз';
    workflowStreamStatus.value = 'failed';
    workflowFinishTs.value = new Date().toISOString();
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningLstm.value = false;
  }
  return started;
};

const runOrchestrated = async () => {
  let started = false;
  runningOrchestrator.value = true;
  stopWorkflowStream();
  workflowStreamStatus.value = 'running';
  workflowStartTs.value = new Date().toISOString();
  workflowFinishTs.value = null;
  try {
    const weights = normalizeEnsembleWeights();
    const payload = {
      sarima_lookback_days: baselineLookbackDays.value,
      sarima_freq: baselineFreq.value,
      save_stl_components: baselineSaveStl.value,
      sarima_seasonality_mode: baselineSeasonalityMode.value,
      lstm_lookback_days: lstmLookbackDays.value,
      lstm_freq: lstmFreq.value,
      horizons: launchHorizonCsv.value,
      wait_for_lstm: false,
      max_retries: lstmMaxRetries.value,
      poll_interval_sec: lstmPollIntervalSec.value,
      max_wait_sec: 120,
      ensemble_beta: Number(ensembleBeta.value) || 0,
      ensemble_sarima_weight: weights.sarima,
      ensemble_lstm_weight: weights.lstm,
      lstm_options: buildLstmOptionsPayload(),
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;

    const res = await apiClient.post('forecast-runs/run_orchestrated/', payload);
    const paired = Array.isArray(res?.data?.paired_runs) ? res.data.paired_runs : [];
    const pair = paired[0] || null;
    const baselineRunIds = Array.isArray(res?.data?.baseline?.run_ids) ? res.data.baseline.run_ids : [];
    const lstmRunIds = Array.isArray(res?.data?.lstm?.run_ids) ? res.data.lstm.run_ids : [];
    const ensembleRunIds = Array.isArray(res?.data?.ensemble?.ensemble_run_ids) ? res.data.ensemble.ensemble_run_ids : [];

    const sarimaRunId = Number(pair?.sarima_run_id || baselineRunIds[0] || 0) || null;
    const lstmRunId = Number(pair?.lstm_run_id || lstmRunIds[0] || 0) || null;
    const ensembleRunId = Number(ensembleRunIds[0] || 0) || null;

    toast.add({
      severity: 'success',
      summary: 'Оркестр запущен',
      detail: 'SARIMA выполнен, LSTM поставлен в очередь, итоговый прогноз соберется после завершения LSTM',
      life: 3600,
    });

    await startWorkflowStream({
      mode: 'full',
      sarimaRunId,
      lstmRunId,
      ensembleRunId,
    });
    started = true;
    workflowFinishTs.value = new Date().toISOString();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось запустить оркестр SARIMA + LSTM';
    workflowStreamStatus.value = 'failed';
    workflowFinishTs.value = new Date().toISOString();
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningOrchestrator.value = false;
  }
  return started;
};

const clearLstmPollTimer = () => {
  if (lstmPollTimer) {
    clearTimeout(lstmPollTimer);
    lstmPollTimer = null;
  }
};

const pollOrchestrated = async (silent = false) => {
  if ((!latestLstmRun.value?.id && !selectedSerial.value) || pollingLstm.value) return;
  pollingLstm.value = true;
  try {
    await apiClient.post('forecast-runs/poll_orchestrated/', {
      run_id: latestLstmRun.value?.id,
      serial: selectedSerial.value || undefined,
      limit: 20,
      poll_interval_sec: lstmPollIntervalSec.value,
    });

    await Promise.all([loadLatestLstmRun(), loadLatestLstmQueueJob(), loadLatestEnsembleRun()]);
    await Promise.all([loadLstmForecastPoints(), loadEnsembleForecastPoints(), loadLatestState()]);
    syncLstmAutoPolling();

    if (!silent && latestEnsembleRun.value?.status === 'success') {
      workflowFinishTs.value = new Date().toISOString();
      toast.add({ severity: 'success', summary: 'Готово', detail: 'Оркестр завершен, итоговый прогноз собран', life: 3200 });
    }
    if (!silent && (normalizeLstmStatus() === 'failed' || latestEnsembleRun.value?.status === 'failed')) {
      toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Оркестр завершился с ошибкой', life: 4200 });
    }
  } catch (e) {
    if (!silent) {
      const detail = e?.response?.data?.detail || 'Не удалось опросить статус оркестра';
      toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
    }
  } finally {
    pollingLstm.value = false;
  }
};

const pollLstmRemote = async (silent = false) => {
  if (!latestLstmRun.value?.id || pollingLstm.value) return;
  pollingLstm.value = true;
  try {
    await apiClient.post('forecast-runs/poll_lstm_remote/', {
      run_id: latestLstmRun.value.id,
      limit: 20,
      poll_interval_sec: lstmPollIntervalSec.value,
    });

    await Promise.all([loadLatestLstmRun(), loadLatestLstmQueueJob(), loadLatestEnsembleRun()]);
    await Promise.all([loadLstmForecastPoints(), loadEnsembleForecastPoints(), loadLatestState()]);
    syncLstmAutoPolling();

    if (!silent && normalizeLstmStatus() === 'completed') {
      workflowFinishTs.value = new Date().toISOString();
      toast.add({ severity: 'success', summary: 'Готово', detail: 'LSTM прогноз завершен', life: 3000 });
    }
    if (!silent && normalizeLstmStatus() === 'failed') {
      toast.add({ severity: 'error', summary: 'Ошибка', detail: 'LSTM прогноз завершился с ошибкой', life: 4200 });
    }
  } catch (e) {
    if (!silent) {
      const detail = e?.response?.data?.detail || 'Не удалось опросить статус LSTM';
      toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
    }
  } finally {
    pollingLstm.value = false;
  }
};

const scheduleLstmPoll = (delayMs = 4000) => {
  clearLstmPollTimer();
  if (!lstmAutoPolling.value) return;
  lstmPollTimer = setTimeout(async () => {
    await pollCurrentWorkflow(true);
    if (lstmAutoPolling.value) scheduleLstmPoll(delayMs);
  }, delayMs);
};

const syncLstmAutoPolling = () => {
  if (workflowStreamActive.value) {
    lstmAutoPolling.value = false;
    clearLstmPollTimer();
    return;
  }
  const status = normalizeLstmStatus();
  const shouldPoll = !!selectedSerial.value && !!latestLstmRun.value?.id && (status === 'queued' || status === 'running');
  lstmAutoPolling.value = shouldPoll;
  if (shouldPoll) scheduleLstmPoll(3500);
  else clearLstmPollTimer();
};

const pollCurrentWorkflow = async (silent = false) => {
  if (!canPollWorkflow.value) return;
  if (workflowMode.value === 'full' || isLatestLstmOrchestrated.value || lastWorkflowRequestedType.value === 'full') {
    await pollOrchestrated(silent);
  } else {
    await pollLstmRemote(silent);
  }
};

const setWorkflowMode = (mode) => {
  workflowMode.value = mode;
  if (mode === 'full') {
    lastWorkflowRequestedType.value = 'full';
    return;
  }
  if (partialMethod.value) lastWorkflowRequestedType.value = partialMethod.value;
};

const ensureWorkflowRunnable = () => {
  if (!selectedSerial.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала выберите устройство', life: 2500 });
    return false;
  }
  if (workflowMode.value === 'partial' && !partialMethod.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'В частичном режиме выберите один метод (SARIMA или LSTM)', life: 3200 });
    return false;
  }
  return true;
};

const executeWorkflow = async () => {
  if (!ensureWorkflowRunnable()) return false;

  workflowStreamSnapshot.value = null;
  workflowStreamError.value = '';
  workflowStreamLastEvent.value = '';
  workflowFinishTs.value = null;

  if (workflowMode.value === 'full') {
    lastWorkflowRequestedType.value = 'full';
    return runOrchestrated();
  }

  if (partialMethod.value === 'sarima') {
    lastWorkflowRequestedType.value = 'sarima';
    return runBaseline();
  }

  lastWorkflowRequestedType.value = 'lstm';
  return runLstmRemote();
};

const startWorkflowFromStep2 = async () => {
  if (workflowBusy.value || workflowStreamActive.value) return;
  if (!ensureWorkflowRunnable()) return;

  workflowUiStep.value = 3;
  const started = await executeWorkflow();
  if (!started && !workflowStreamActive.value) workflowUiStep.value = 4;
};

const restartWorkflow = async () => {
  if (workflowBusy.value || workflowStreamActive.value) return;
  if (!ensureWorkflowRunnable()) {
    workflowUiStep.value = 1;
    return;
  }

  workflowUiStep.value = 3;
  const started = await executeWorkflow();
  if (!started && !workflowStreamActive.value) workflowUiStep.value = 4;
};

watch(selectedDeviceId, () => {
  stopWorkflowStream();
  loadAll();
});

watch(selectedHorizon, () => {
  loadLatestState();
});

watch([selectedMetricCode, chartWindowMinutes, chartForecastHorizon], () => {
  loadMetricScatter();
  loadMetricTrendSeries();
});

watch([lstmPollIntervalSec, selectedSerial], () => {
  syncLstmAutoPolling();
});

watch([launchHorizons, lstmFreq], () => {
  syncRecommendedLstmParams();
}, { deep: true });

watch(partialMethod, () => {
  if (workflowMode.value === 'partial' && partialMethod.value) {
    lastWorkflowRequestedType.value = partialMethod.value;
  }
});

watch(forecastUiMode, (value) => {
  localStorage.setItem(FORECAST_UI_MODE_KEY, value);
});

onMounted(async () => {
  syncRecommendedLstmParams({ force: true });
  await loadDevices();
  await loadOrchestratorDefaults();
  await loadAll();
});

onUnmounted(() => {
  clearLstmPollTimer();
  stopWorkflowStream();
});
</script>

<style scoped>
.filters-grid {
  display: grid;
  grid-template-columns: minmax(260px, 2fr) minmax(180px, 1fr) minmax(260px, 1.4fr);
  gap: 1rem;
  align-items: end;
}

.field-block label {
  display: block;
  margin-bottom: 0.35rem;
  color: #475569;
  font-size: 0.86rem;
  font-weight: 600;
}

.run-icons-row {
  min-height: 2.6rem;
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.55rem 0.7rem;
  flex-wrap: wrap;
  background: #ffffff;
}

.run-icon-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: #334155;
  font-weight: 700;
}

.task-widget-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.7rem;
}

.task-widget-item {
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  background: #fff;
  padding: 0.65rem 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.32rem;
}

.task-widget-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.task-widget-title {
  color: #0f172a;
  font-size: 0.82rem;
  font-weight: 700;
}

.task-widget-meta {
  color: #64748b;
  font-size: 0.76rem;
  line-height: 1.35;
}

.run-dot-red {
  color: #dc2626;
}

.run-dot-yellow {
  color: #eab308;
}

.run-dot-green {
  color: #16a34a;
}

.run-dot-gray {
  color: #94a3b8;
}

.state-card-shell {
  border: 1px solid #e6edf7;
}

.state-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.state-head-subtitle {
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.82rem;
}

.state-head-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.35rem;
}

.state-head-meta {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  color: #64748b;
  font-size: 0.8rem;
}

.state-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
}

.state-mini {
  border-radius: 12px;
  border: 1px solid #dbe6f2;
  background: #f8fafc;
  padding: 0.65rem 0.8rem;
}

.state-mini.active {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 1px rgba(14, 165, 233, 0.2);
  background: #f0f9ff;
}

.state-mini-title {
  color: #334155;
  font-size: 0.8rem;
  font-weight: 700;
}

.state-mini-value {
  color: #0f172a;
  font-size: 1rem;
  font-weight: 800;
  margin-top: 0.25rem;
}

.state-summary {
  border-radius: 12px;
  border: 1px solid #dbe6f2;
  padding: 0.7rem 0.85rem;
  background: #f8fbff;
}

.state-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0.75rem;
}

.state-summary-card {
  border-radius: 14px;
  border: 1px solid #dbe6f2;
  padding: 0.8rem 0.9rem;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  color: #334155;
  font-size: 0.84rem;
}

.state-summary-card strong {
  color: #0f172a;
  font-size: 0.98rem;
}

.summary-main {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  color: #334155;
  font-size: 0.86rem;
}

.summary-title {
  color: #0f172a;
  font-weight: 700;
}

.risk-drivers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}

.driver-card {
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  background: #ffffff;
  padding: 0.7rem;
}

.driver-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.driver-title {
  font-size: 0.86rem;
  font-weight: 700;
  color: #0f172a;
}

.driver-meta {
  margin-top: 0.35rem;
  color: #64748b;
  font-size: 0.78rem;
}

.risk-track {
  margin-top: 0.45rem;
  height: 7px;
  border-radius: 999px;
  background: #dbeafe;
  overflow: hidden;
}

.risk-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
}

.risk-fill-solid {
  transition: width 0.2s ease;
}

.workflow-card {
  border: 1px solid #dbe6f2;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcff 100%);
}

.workflow-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.workflow-status {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
}

.workflow-body {
  min-height: 12rem;
}

.wizard-step-title {
  color: #0f172a;
  font-size: 0.95rem;
  font-weight: 800;
}

.wizard-step-subtitle {
  color: #64748b;
  font-size: 0.8rem;
  margin-top: 0.18rem;
}

.workflow-mode-row,
.partial-method-row,
.workflow-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.workflow-step-start {
  display: flex;
  flex-direction: column;
}

.workflow-step1-row {
  width: 100%;
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}

.workflow-step1-actions {
  margin-top: 0.75rem !important;
}

.partial-check-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.partial-check-item {
  min-height: 2.5rem;
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  background: #ffffff;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.45rem 0.7rem;
  color: #334155;
  font-size: 0.84rem;
  font-weight: 600;
}

.workflow-steps {
  display: grid;
  gap: 0.55rem;
}

.workflow-step {
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  background: #fff;
  padding: 0.55rem 0.7rem;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.6rem;
}

.step-index {
  width: 1.4rem;
  height: 1.4rem;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  background: #e2e8f0;
  color: #334155;
}

.step-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: #0f172a;
}

.step-desc {
  font-size: 0.74rem;
  color: #64748b;
}

.step-status {
  font-size: 0.75rem;
  font-weight: 700;
}

.step-done {
  border-color: #86efac;
  background: #f0fdf4;
}

.step-done .step-index {
  background: #16a34a;
  color: #fff;
}

.step-done .step-status {
  color: #166534;
}

.step-current {
  border-color: #7dd3fc;
  background: #f0f9ff;
}

.step-current .step-index {
  background: #0ea5e9;
  color: #fff;
}

.step-current .step-status {
  color: #0369a1;
}

.step-failed {
  border-color: #fca5a5;
  background: #fef2f2;
}

.step-failed .step-index {
  background: #dc2626;
  color: #fff;
}

.step-failed .step-status {
  color: #991b1b;
}

.step-pending .step-status {
  color: #64748b;
}

.workflow-grid {
  display: grid;
  gap: 0.85rem;
}

.full-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.partial-grid {
  grid-template-columns: minmax(260px, 420px);
}

.setting-panel {
  border: 1px solid #dbe6f2;
  border-radius: 14px;
  padding: 0.8rem;
  background: #ffffff;
}

.setting-title {
  color: #0f172a;
  font-size: 0.9rem;
  font-weight: 800;
}

.setting-desc {
  color: #64748b;
  font-size: 0.78rem;
  margin-top: 0.2rem;
}

.seasonality-toggle-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.seasonality-toggle-btn {
  flex: 1 1 220px;
}

.seasonality-info-card {
  border: 1px solid #dbe6f2;
  border-radius: 12px;
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
  padding: 0.7rem 0.8rem;
}

.seasonality-info-title {
  color: #0f172a;
  font-size: 0.84rem;
  font-weight: 800;
}

.seasonality-info-text {
  color: #64748b;
  font-size: 0.77rem;
  margin-top: 0.2rem;
}

.seasonality-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.65rem;
}

.seasonality-info-block {
  border-radius: 10px;
  border: 1px solid #dbe6f2;
  background: #ffffff;
  padding: 0.6rem 0.7rem;
}

.seasonality-info-block.risk {
  background: #fffaf5;
  border-color: #fed7aa;
}

.seasonality-info-label {
  color: #0f172a;
  font-size: 0.76rem;
  font-weight: 800;
  margin-bottom: 0.35rem;
}

.seasonality-info-list {
  margin: 0;
  padding-left: 1rem;
  color: #475569;
  font-size: 0.76rem;
  display: grid;
  gap: 0.25rem;
}

.switch-inline {
  min-height: 2.6rem;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  color: #334155;
  background: #fff;
}

.run-progress {
  border: 1px dashed #94a3b8;
  border-radius: 12px;
  padding: 0.7rem;
  background: rgba(248, 250, 252, 0.85);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.loader-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: #0ea5e9;
  box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.5);
  animation: pulse 1.2s infinite;
}

.loader-title {
  color: #0f172a;
  font-size: 0.86rem;
  font-weight: 700;
}

.loader-subtitle {
  color: #64748b;
  font-size: 0.78rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.65rem;
}

.workflow-restart {
  display: flex;
  justify-content: flex-start;
}

.summary-item {
  border-radius: 10px;
  border: 1px solid #dbe6f2;
  background: #ffffff;
  padding: 0.55rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.summary-label {
  color: #64748b;
  font-size: 0.74rem;
}

.chart-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.8rem;
}

.freshness-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.15rem;
}

.chart-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.8rem;
  align-items: end;
}

.series-switches {
  min-height: 2.5rem;
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0.35rem;
  background: #fff;
}

.action-button {
  display: flex;
  align-items: end;
}

.chart-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  padding: 0.7rem;
}

.scatter-chart {
  height: 21rem;
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

.table-freshness {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.8rem;
}

.sparkline-cell {
  min-width: 126px;
  max-width: 150px;
  height: 2.2rem;
  display: flex;
  align-items: center;
}

.sparkline-svg {
  width: 100%;
  height: 100%;
}

.sparkline-axis {
  stroke: rgba(148, 163, 184, 0.35);
  stroke-width: 1;
  fill: none;
}

.sparkline-line {
  stroke-width: 1.8;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sparkline-empty {
  color: #94a3b8;
  font-weight: 600;
  font-size: 0.9rem;
  line-height: 1;
}

.risk-cell {
  display: inline-block;
  border-radius: 8px;
  padding: 0.1rem 0.45rem;
  font-weight: 600;
}

.risk-cell-critical {
  color: #991b1b;
  background: #fee2e2;
}

.risk-cell-high {
  color: #9a3412;
  background: #ffedd5;
}

.risk-cell-medium {
  color: #92400e;
  background: #fef3c7;
}

.risk-cell-low {
  color: #166534;
  background: #dcfce7;
}

.risk-cell-none {
  color: #475569;
  background: #e2e8f0;
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

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.25s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.45);
  }
  70% {
    box-shadow: 0 0 0 12px rgba(14, 165, 233, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(14, 165, 233, 0);
  }
}

@media (max-width: 1180px) {
  .filters-grid {
    grid-template-columns: 1fr;
  }

  .freshness-stack,
  .workflow-status {
    align-items: flex-start;
  }
}

@media (max-width: 760px) {
  .state-head,
  .workflow-head {
    flex-direction: column;
    align-items: stretch;
  }

  .state-head-actions {
    align-items: stretch;
  }

  .scatter-chart {
    height: 16rem;
  }
}
</style>
