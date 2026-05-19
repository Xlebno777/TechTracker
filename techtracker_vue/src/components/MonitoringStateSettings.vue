<template>
  <div :class="['state-settings-page', isEmbedded ? 'p-0' : 'p-4']">
    <Toast />

    <PageHeader
      v-if="!isEmbedded"
      title="Настройки модели состояния"
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: настройки модели состояния"
      help-intro="Здесь настраивается, как система переводит прогнозные метрики в вероятности состояний S0, S1 и S2."
      :help-steps="helpSteps"
      help-note="Если сомневаетесь, меняйте сначала только пороги метрик и уровни чувствительности, а затем уже веса S0/S1/S2."
      @refresh="refreshAll"
    />

    <FilterPanel class="mb-3" title="Быстрые действия">
      <div class="quick-actions mt-2">
        <Button
          icon="pi pi-cog"
          label="Создать базовый профиль"
          :loading="loadingBootstrap"
          @click="bootstrapDefaults"
        />
        <Tag
          :value="activeProfileTag"
          :severity="activeProfile ? 'success' : 'warning'"
        />
      </div>
    </FilterPanel>

    <div class="settings-grid mb-3">
      <div class="card p-3">
        <div class="card-head">
          <div>
            <h4 class="m-0">Профиль</h4>
            <p class="text-500 mt-1 mb-0">Профиль определяет набор порогов и коэффициентов, которые используются при расчете S0/S1/S2.</p>
          </div>
          <Tag :value="profileForm.is_active ? 'Активный' : 'Черновик'" :severity="profileForm.is_active ? 'success' : 'secondary'" />
        </div>

        <div class="form-inline mt-3">
          <div class="field-block">
            <label>Название профиля</label>
            <InputText v-model.trim="profileForm.name" class="w-full" placeholder="Например: Осторожный профиль" />
          </div>
          <div class="field-block field-block--small">
            <label>Версия</label>
            <InputNumber v-model="profileForm.version" :min="1" class="w-full" />
          </div>
          <div class="field-block field-block--switch">
            <label>Сделать активным после сохранения</label>
            <InputSwitch v-model="profileForm.is_active" />
          </div>
        </div>

        <div class="field-block mt-3">
          <label>Комментарий</label>
          <Textarea
            v-model="profileForm.notes"
            rows="3"
            class="w-full"
            placeholder="Коротко опишите, для чего этот профиль: более строгий, мягкий, для тестов и т.д."
          />
        </div>

        <div class="actions-row mt-3">
          <Button icon="pi pi-save" label="Сохранить профиль" :loading="savingProfile" @click="saveProfile" />
          <Button icon="pi pi-plus" label="Новый профиль" text @click="resetForm" />
          <Button
            icon="pi pi-check-circle"
            label="Сделать активным"
            text
            severity="success"
            :disabled="!profileForm.id || profileForm.is_active"
            @click="activateProfile(profileForm.id)"
          />
          <Button
            icon="pi pi-trash"
            label="Удалить"
            text
            severity="danger"
            :disabled="!profileForm.id"
            @click="deleteProfile"
          />
        </div>
      </div>

      <div class="card p-3">
        <div class="card-head">
          <div>
            <h4 class="m-0">Пороговые значения метрик</h4>
            <p class="text-500 mt-1 mb-0">Если метрика приближается к порогу или превышает его, система сильнее смещается в сторону S1/S2.</p>
          </div>
        </div>

        <div class="threshold-list mt-3">
          <div v-for="(row, idx) in thresholdRows" :key="`${row.metric_code || 'custom'}-${idx}`" class="threshold-row">
            <div class="threshold-main">
              <label class="threshold-label">Метрика</label>
              <InputText
                v-if="!row.builtin"
                v-model.trim="row.metric_code"
                class="w-full"
                placeholder="metric_code"
              />
              <div v-else class="threshold-static">
                <strong>{{ row.label }}</strong>
                <span class="text-500">{{ row.metric_code }}</span>
              </div>
            </div>
            <div class="threshold-value">
              <label class="threshold-label">Порог</label>
              <InputNumber
                v-model="row.threshold"
                mode="decimal"
                :min="0"
                :minFractionDigits="0"
                :maxFractionDigits="2"
                class="w-full"
              />
            </div>
            <div class="threshold-unit">
              <label class="threshold-label">Ед.</label>
              <div class="threshold-static">{{ row.unit || '—' }}</div>
            </div>
            <div class="threshold-actions">
              <Button
                v-if="!row.builtin"
                icon="pi pi-trash"
                text
                severity="danger"
                rounded
                @click="removeThresholdRow(idx)"
              />
            </div>
          </div>
        </div>

        <div class="actions-row mt-3">
          <Button icon="pi pi-plus" label="Добавить свою метрику" text @click="addThresholdRow" />
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="card-head">
        <div>
          <h4 class="m-0">Источники прогноза по метрикам</h4>
          <p class="text-500 mt-1 mb-0">
            Здесь задаётся, участвует ли каждая метрика в SARIMA и LSTM, и будет ли alpha для оркестра считаться автоматически или вручную.
          </p>
        </div>
      </div>

      <div class="forecast-controls-grid mt-3">
        <div class="forecast-editor-card">
          <div class="field-block">
            <label>Выбранная метрика</label>
            <Dropdown
              v-model="selectedForecastMetricCode"
              :options="forecastMetricOptions"
              optionLabel="label"
              optionValue="value"
              placeholder="Выберите метрику"
              class="w-full"
            />
          </div>

          <div v-if="selectedForecastMetricRow" class="forecast-editor-panel mt-3">
            <div class="forecast-editor-head">
              <div>
                <strong>{{ selectedForecastMetricRow.label }}</strong>
                <div class="text-500">{{ selectedForecastMetricRow.metric_code }}</div>
              </div>
              <Tag :value="selectedForecastMetricModeLabel" :severity="selectedForecastMetricModeSeverity" />
            </div>

            <div class="forecast-toggle-grid mt-3">
              <div class="field-block">
                <label>SARIMA участвует</label>
                <div class="switch-inline">
                  <InputSwitch
                    :modelValue="selectedForecastMetricRow.sarima_enabled"
                    @update:modelValue="(value) => updateForecastControl(selectedForecastMetricRow.metric_code, 'sarima_enabled', value)"
                  />
                  <span>{{ selectedForecastMetricRow.sarima_enabled ? 'Да' : 'Нет' }}</span>
                </div>
                <small class="text-500">Если отключить, SARIMA не будет строить прогноз по этой метрике.</small>
              </div>

              <div class="field-block">
                <label>LSTM участвует</label>
                <div class="switch-inline">
                  <InputSwitch
                    :modelValue="selectedForecastMetricRow.lstm_enabled"
                    @update:modelValue="(value) => updateForecastControl(selectedForecastMetricRow.metric_code, 'lstm_enabled', value)"
                  />
                  <span>{{ selectedForecastMetricRow.lstm_enabled ? 'Да' : 'Нет' }}</span>
                </div>
                <small class="text-500">Если отключить, удалённый LSTM не будет получать эту метрику.</small>
              </div>
            </div>

            <div class="field-block mt-3">
              <label>Режим alpha</label>
              <div class="alpha-mode-toggle-row mt-2">
                <Button
                  label="Авто"
                  :outlined="selectedForecastMetricRow.alpha_mode !== 'auto'"
                  :severity="selectedForecastMetricRow.alpha_mode === 'auto' ? 'primary' : 'secondary'"
                  @click="setForecastAlphaMode(selectedForecastMetricRow.metric_code, 'auto')"
                />
                <Button
                  label="Фиксированный"
                  :outlined="selectedForecastMetricRow.alpha_mode !== 'manual'"
                  :severity="selectedForecastMetricRow.alpha_mode === 'manual' ? 'primary' : 'secondary'"
                  @click="setForecastAlphaMode(selectedForecastMetricRow.metric_code, 'manual')"
                />
              </div>
              <small class="text-500">
                Авто: оркестр сам выбирает вес по истории ошибок. Фиксированный: вес SARIMA задаётся вручную, вес LSTM равен 1 - alpha.
              </small>
            </div>

            <div v-if="selectedForecastMetricRow.alpha_mode === 'manual'" class="field-block mt-3">
              <label>Вес SARIMA в оркестре: {{ formatForecastAlpha(selectedForecastMetricRow.manual_alpha_sarima) }}</label>
              <input
                class="alpha-range"
                type="range"
                min="0"
                max="100"
                step="1"
                :value="Math.round((selectedForecastMetricRow.manual_alpha_sarima || 0) * 100)"
                @input="updateForecastAlphaFromRange(selectedForecastMetricRow.metric_code, $event)"
              />
              <div class="alpha-range-labels">
                <span>SARIMA 0% / LSTM 100%</span>
                <span>SARIMA 50% / LSTM 50%</span>
                <span>SARIMA 100% / LSTM 0%</span>
              </div>
              <small class="text-500">{{ selectedForecastMetricAlphaHint }}</small>
            </div>

            <div v-if="selectedForecastMetricRow.lstm_enabled" class="mt-3">
              <div class="field-block">
                <label>Долгий тренд LSTM</label>
                <Dropdown
                  :modelValue="selectedForecastMetricRow.trend_long_mode"
                  :options="trendLongModeOptions"
                  optionLabel="label"
                  optionValue="value"
                  class="w-full"
                  @update:modelValue="(value) => updateForecastControl(selectedForecastMetricRow.metric_code, 'trend_long_mode', value)"
                />
                <small class="text-500">
                  Определяет, как LSTM продолжает долгий рост: мягко к среднему или с опорой на верхний устойчивый уровень.
                </small>
              </div>

              <div class="forecast-toggle-grid mt-3">
                <div class="field-block">
                  <label>Переход тренда (шагов)</label>
                  <InputNumber
                    :modelValue="selectedForecastMetricRow.trend_transition_steps"
                    :min="0"
                    :max="10000"
                    class="w-full"
                    @update:modelValue="(value) => updateForecastControl(selectedForecastMetricRow.metric_code, 'trend_transition_steps', value)"
                  />
                  <small class="text-500">0 = авто. Чем больше шагов, тем дольше модель сохраняет краткосрочный рост перед переходом к долгому тренду.</small>
                </div>

                <div class="field-block">
                  <label>Вес верхнего конверта: {{ formatForecastAlpha(selectedForecastMetricRow.trend_envelope_weight) }}</label>
                  <input
                    class="alpha-range"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    :value="Math.round((selectedForecastMetricRow.trend_envelope_weight || 0) * 100)"
                    @input="updateForecastAlphaFromRange(selectedForecastMetricRow.metric_code, $event, 'trend_envelope_weight')"
                  />
                  <small class="text-500">0 = ориентироваться только на усреднённый долгий тренд. 1 = сильнее удерживать верхний устойчивый уровень.</small>
                </div>

                <div class="field-block">
                  <label>Сила bias-correction: {{ formatForecastAlpha(selectedForecastMetricRow.bias_correction_strength) }}</label>
                  <input
                    class="alpha-range"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    :value="Math.round((selectedForecastMetricRow.bias_correction_strength || 0) * 100)"
                    @input="updateForecastAlphaFromRange(selectedForecastMetricRow.metric_code, $event, 'bias_correction_strength')"
                  />
                  <small class="text-500">Плюс помогает поднять систематически заниженный прогноз. Для CPU, памяти и температуры лучше держать умеренно, без агрессивного подъёма.</small>
                </div>
              </div>
            </div>

            <div class="forecast-hint-box mt-3">
              <strong>{{ selectedForecastMetricSummary.title }}</strong>
              <div class="text-500 mt-1">{{ selectedForecastMetricSummary.text }}</div>
            </div>
          </div>
        </div>

        <div class="forecast-summary-card">
          <DataTable
            :value="forecastMetricRows"
            dataKey="metric_code"
            stripedRows
            selectionMode="single"
            :selection="selectedForecastMetricRow"
            @rowSelect="onForecastMetricRowSelect"
          >
            <Column field="label" header="Метрика" />
            <Column header="SARIMA">
              <template #body="{ data }">
                <Tag :value="data.sarima_enabled ? 'Вкл.' : 'Выкл.'" :severity="data.sarima_enabled ? 'success' : 'danger'" />
              </template>
            </Column>
            <Column header="LSTM">
              <template #body="{ data }">
                <Tag :value="data.lstm_enabled ? 'Вкл.' : 'Выкл.'" :severity="data.lstm_enabled ? 'success' : 'danger'" />
              </template>
            </Column>
            <Column header="alpha">
              <template #body="{ data }">
                {{ data.alpha_mode === 'manual' ? formatForecastAlpha(data.manual_alpha_sarima) : 'Авто' }}
              </template>
            </Column>
          </DataTable>
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="card-head">
        <div>
          <h4 class="m-0">Правила оркестра SARIMA + LSTM</h4>
          <p class="text-500 mt-1 mb-0">
            Здесь задаётся, как оркестр выбирает alpha: только по последним совместимым поколениям, по каким сегментам делится горизонт и нужно ли нормировать ошибку по масштабу метрики.
          </p>
        </div>
      </div>

      <div class="coeff-grid mt-3">
        <div class="field-block">
          <label>Version-aware alpha</label>
          <div class="switch-inline">
            <InputSwitch
              :modelValue="orchestratorControlsModel.alpha_version_aware"
              @update:modelValue="(value) => updateOrchestratorControl('alpha_version_aware', value)"
            />
            <span>{{ orchestratorControlsModel.alpha_version_aware ? 'Только последние совместимые поколения' : 'Весь архив ошибок' }}</span>
          </div>
          <small class="text-500">Если включено, оркестр не смешивает старые поколения SARIMA/LSTM с текущей версией модели.</small>
        </div>

        <div class="field-block">
          <label>Нормировать ошибку по масштабу метрики</label>
          <div class="switch-inline">
            <InputSwitch
              :modelValue="orchestratorControlsModel.normalize_errors_by_scale"
              @update:modelValue="(value) => updateOrchestratorControl('normalize_errors_by_scale', value)"
            />
            <span>{{ orchestratorControlsModel.normalize_errors_by_scale ? 'Да' : 'Нет' }}</span>
          </div>
          <small class="text-500">Помогает сравнивать качество моделей честно на CPU, температуре и сетевых метриках с разным масштабом.</small>
        </div>

        <div class="field-block">
          <label>Сколько последних совместимых запусков учитывать</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.compatible_history_runs"
            @update:modelValue="(value) => updateOrchestratorControl('compatible_history_runs', value)"
            :min="1"
            :max="50"
            class="w-full"
          />
          <small class="text-500">Чем меньше число, тем быстрее оркестр подстраивается под новое поколение модели.</small>
        </div>

        <div class="field-block">
          <label>Ошибок на сегмент</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.history_limit_per_segment"
            @update:modelValue="(value) => updateOrchestratorControl('history_limit_per_segment', value)"
            :min="1"
            :max="200"
            class="w-full"
          />
          <small class="text-500">Сколько исторических ошибок максимум брать для расчёта alpha внутри одного сегмента горизонта.</small>
        </div>

        <div class="field-block">
          <label>Окно оценки масштаба ошибки (дней)</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.error_scale_lookback_days"
            @update:modelValue="(value) => updateOrchestratorControl('error_scale_lookback_days', value)"
            :min="1"
            :max="3650"
            class="w-full"
          />
          <small class="text-500">За сколько последних дней смотреть реальный ряд, чтобы нормировать ошибку по типичному масштабу метрики.</small>
        </div>

        <div class="field-block">
          <label>Порог явного победителя</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.winner_margin"
            @update:modelValue="(value) => updateOrchestratorControl('winner_margin', value)"
            mode="decimal"
            :min="1"
            :max="10"
            :step="0.05"
            :minFractionDigits="2"
            :maxFractionDigits="2"
            class="w-full"
          />
          <small class="text-500">Если одна модель лучше другой хотя бы в {{ orchestratorControlsModel.winner_margin.toFixed(2) }} раза, оркестр смещает alpha в её сторону.</small>
        </div>

        <div class="field-block">
          <label>Вес победителя</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.winner_weight"
            @update:modelValue="(value) => updateOrchestratorControl('winner_weight', value)"
            mode="decimal"
            :min="0.5"
            :max="1"
            :step="0.01"
            :minFractionDigits="2"
            :maxFractionDigits="2"
            class="w-full"
          />
          <small class="text-500">Это не winner-takes-all: точка всё равно считается честным blending, но с большим весом лучшей модели.</small>
        </div>
      </div>

      <div class="coeff-grid mt-3">
        <div class="field-block">
          <label>Граница сегмента 1 (часы)</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.segment_boundaries_hours[0]"
            @update:modelValue="(value) => updateOrchestratorBoundary(0, value)"
            :min="1"
            :max="10000"
            class="w-full"
          />
          <small class="text-500">Сегмент ближнего прогноза. Обычно 24 часа.</small>
        </div>

        <div class="field-block">
          <label>Граница сегмента 2 (часы)</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.segment_boundaries_hours[1]"
            @update:modelValue="(value) => updateOrchestratorBoundary(1, value)"
            :min="1"
            :max="10000"
            class="w-full"
          />
          <small class="text-500">Сегмент среднего горизонта. Обычно 168 часов = 7 дней.</small>
        </div>

        <div class="field-block">
          <label>Граница сегмента 3 (часы)</label>
          <InputNumber
            :modelValue="orchestratorControlsModel.segment_boundaries_hours[2]"
            @update:modelValue="(value) => updateOrchestratorBoundary(2, value)"
            :min="1"
            :max="10000"
            class="w-full"
          />
          <small class="text-500">Сегмент длинного горизонта. Обычно 720 часов = 30 дней.</small>
        </div>
      </div>

      <div class="forecast-hint-box mt-3">
        <strong>Текущая схема сегментации</strong>
        <div class="text-500 mt-1">
          Оркестр считает alpha отдельно для сегментов: {{ orchestratorBoundaryLabel }}. На длинном горизонте точка теперь всегда считается как blending, без режима winner-takes-all.
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="card-head">
        <div>
          <h4 class="m-0">Коэффициенты модели состояния</h4>
          <p class="text-500 mt-1 mb-0">
            Модель считает набор признаков риска, переводит их в оценки S0/S1/S2 и затем нормирует вероятности через softmax.
          </p>
        </div>
      </div>

      <div class="coeff-group-grid mt-3">
        <div v-for="group in coefficientGroups" :key="group.title" class="coeff-group-card">
          <div class="coeff-group-head">
            <h5 class="m-0">{{ group.title }}</h5>
            <small class="text-500">{{ group.description }}</small>
          </div>
          <div class="coeff-grid mt-3">
            <div v-for="field in group.fields" :key="field.key" class="field-block">
              <label>{{ field.label }}</label>
              <InputNumber
                :modelValue="readCoefficient(group, field)"
                @update:modelValue="(value) => writeCoefficient(group, field, value)"
                mode="decimal"
                :min="field.min"
                :max="field.max"
                :step="field.step || 0.01"
                :minFractionDigits="field.fractionDigits ?? 2"
                :maxFractionDigits="field.fractionDigits ?? 3"
                class="w-full"
              />
              <small class="text-500">{{ field.help }}</small>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card p-3">
      <div class="card-head">
        <div>
          <h4 class="m-0">Сохранённые профили</h4>
          <p class="text-500 mt-1 mb-0">Можно хранить несколько версий и переключать активный профиль без изменения кода.</p>
        </div>
      </div>

      <DataTable
        :value="profiles"
        dataKey="id"
        stripedRows
        class="mt-3"
        selectionMode="single"
        :selection="selectedProfileRow"
        @rowSelect="onProfileRowSelect"
      >
        <Column field="name" header="Профиль" />
        <Column field="version" header="Версия" />
        <Column header="Статус">
          <template #body="{ data }">
            <Tag :value="data.is_active ? 'Активный' : 'Отключен'" :severity="data.is_active ? 'success' : 'secondary'" />
          </template>
        </Column>
        <Column field="created_by_username" header="Автор" />
        <Column header="Обновлён">
          <template #body="{ data }">{{ formatDateTime(data.updated_at) }}</template>
        </Column>
        <Column header="">
          <template #body="{ data }">
            <Button
              icon="pi pi-check"
              text
              rounded
              severity="success"
              :disabled="data.is_active"
              @click.stop="activateProfile(data.id)"
            />
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { computed, defineProps, onMounted, reactive, ref } from 'vue';
import Button from 'primevue/button';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import InputText from 'primevue/inputtext';
import Tag from 'primevue/tag';
import Textarea from 'primevue/textarea';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import apiClient from '@/api';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import { useConfirmAction } from '@/composables/useConfirmAction';

const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
});
const isEmbedded = computed(() => Boolean(props.embedded));

const toast = useToast();
const { confirmAction } = useConfirmAction();

const helpSteps = [
  'Базово настройте пороги метрик: CPU, память, температура, задержка.',
  'В блоке источников прогноза задайте, какие метрики участвуют в SARIMA и LSTM, и где alpha выбирается автоматически, а где фиксируется вручную.',
  'В блоке правил оркестра задайте, считать ли alpha только по последним совместимым поколениям, на какие сегменты делить горизонт и нужно ли нормировать ошибку по масштабу метрики.',
  'Дальше настройте веса признаков: агрегат риска, марковский риск S2, топ-метрики, температура, износ и задержки.',
  'Если система слишком часто уходит в S1/S2, уменьшайте веса для S2 и повышайте softmax temperature.',
  'Если система слишком поздно реагирует, повышайте веса для S2 и снижайте пороги проблемных метрик.',
  'Сохраняйте новую версию профиля, а затем переключайте её как активную.',
  'После изменения профиля запустите новый прогноз и проверьте, как изменились вероятности S0/S1/S2 на странице прогнозов.',
];

const defaultScoreWeights = () => ({
  s0: {
    bias: 0.20,
    metric_aggregate_risk: 1.90,
    markov_p_s2: 1.20,
    top1_risk: 1.50,
    top3_risk: 1.10,
    temperature_risk: 0.80,
    wear_risk: 0.90,
    latency_risk: 0.60,
  },
  s1: {
    bias: 0.30,
    metric_aggregate_risk: 1.40,
    markov_p_s2: 0.80,
    top1_risk: 0.90,
    top3_risk: 1.20,
    temperature_risk: 0.80,
    wear_risk: 0.70,
    latency_risk: 0.70,
  },
  s2: {
    bias: 0.10,
    metric_aggregate_risk: 2.20,
    markov_p_s2: 1.80,
    top1_risk: 1.60,
    top3_risk: 1.20,
    temperature_risk: 1.20,
    wear_risk: 1.40,
    latency_risk: 0.80,
  },
});

const metricCatalog = [
  { metric_code: 'cpu_load_total', label: 'Загрузка CPU', unit: '%' },
  { metric_code: 'mem_usage_percent', label: 'Использование памяти', unit: '%' },
  { metric_code: 'ping_latency_gateway', label: 'Ping до шлюза', unit: 'ms' },
  { metric_code: 'system_temperature', label: 'Температура системы', unit: 'C' },
  { metric_code: 'storcli_drive_temperature', label: 'Температура диска RAID', unit: 'C' },
  { metric_code: 'storcli_predictive_failure_count', label: 'Predictive Failure Count', unit: 'count' },
];

const forecastMetricCatalog = [
  { metric_code: 'cpu_load_total', label: 'Загрузка CPU', unit: '%' },
  { metric_code: 'mem_usage_percent', label: 'Использование памяти', unit: '%' },
  { metric_code: 'net_bytes_sent', label: 'Трафик исходящий', unit: 'KB/s' },
  { metric_code: 'net_bytes_recv', label: 'Трафик входящий', unit: 'KB/s' },
  { metric_code: 'ping_latency_gateway', label: 'Ping до шлюза', unit: 'ms' },
  { metric_code: 'system_temperature', label: 'Температура системы', unit: 'C' },
  { metric_code: 'storcli_drive_temperature', label: 'Температура диска RAID', unit: 'C' },
  { metric_code: 'storcli_predictive_failure_count', label: 'Predictive Failure Count', unit: 'count' },
];

const trendLongModeOptions = [
  { label: 'Мягко к среднему тренду', value: 'mean_regression' },
  { label: 'Смешивать со стабильным верхним уровнем', value: 'upper_envelope_blend' },
  { label: 'Держать верхний уровень как нижнюю границу', value: 'upper_envelope_floor' },
];

const defaultTrendLongMode = (metricCode) => {
  const raw = String(metricCode || '').trim().toLowerCase();
  if (raw === 'cpu_load_total' || raw === 'mem_usage_percent' || raw.includes('temperature')) {
    return 'upper_envelope_floor';
  }
  return 'mean_regression';
};

const defaultTrendEnvelopeWeight = (metricCode) => {
  const raw = String(metricCode || '').trim().toLowerCase();
  if (raw === 'cpu_load_total') return 0.55;
  if (raw === 'mem_usage_percent') return 0.5;
  if (raw.includes('temperature')) return 0.45;
  return 0;
};

const defaultBiasCorrectionStrength = (metricCode) => {
  const raw = String(metricCode || '').trim().toLowerCase();
  if (raw === 'cpu_load_total') return 0.55;
  if (raw === 'mem_usage_percent') return 0.5;
  if (raw.includes('temperature')) return 0.45;
  if (raw === 'storcli_predictive_failure_count' || raw.includes('latency')) return 0.4;
  return 0.25;
};

const defaultForecastMetricControls = () => {
  const controls = Object.fromEntries(
    forecastMetricCatalog.map((item) => [item.metric_code, {
      sarima_enabled: true,
      lstm_enabled: true,
      alpha_mode: 'auto',
      manual_alpha_sarima: 0.5,
      trend_long_mode: defaultTrendLongMode(item.metric_code),
      trend_transition_steps: 0,
      trend_envelope_weight: defaultTrendEnvelopeWeight(item.metric_code),
      bias_correction_strength: defaultBiasCorrectionStrength(item.metric_code),
    }]),
  );
  controls.storcli_predictive_failure_count = {
    sarima_enabled: false,
    lstm_enabled: true,
    alpha_mode: 'manual',
    manual_alpha_sarima: 0.0,
    trend_long_mode: defaultTrendLongMode('storcli_predictive_failure_count'),
    trend_transition_steps: 0,
    trend_envelope_weight: defaultTrendEnvelopeWeight('storcli_predictive_failure_count'),
    bias_correction_strength: defaultBiasCorrectionStrength('storcli_predictive_failure_count'),
  };
  return controls;
};

const defaultOrchestratorControls = () => ({
  alpha_version_aware: true,
  normalize_errors_by_scale: true,
  compatible_history_runs: 6,
  history_limit_per_segment: 18,
  error_scale_lookback_days: 60,
  winner_margin: 1.2,
  winner_weight: 0.85,
  segment_boundaries_hours: [24, 168, 720],
});

const coefficientGroups = [
  {
    title: 'Softmax и уверенность',
    description: 'Финальная нормировка вероятностей и доверие к решению модели.',
    fields: [
      { key: 'softmax_temperature', label: 'Softmax temperature', help: 'Чем ниже значение, тем резче модель выбирает одно состояние. Чем выше, тем мягче распределяет вероятности.', min: 0.1, max: 5, step: 0.05 },
      { key: 'risk_ratio_baseline', label: 'Начало роста риска', help: 'После какой доли порога риск метрики начинает заметно расти.', min: 0, max: 2, step: 0.01 },
      { key: 'risk_ratio_scale', label: 'Скорость роста риска', help: 'Чем меньше значение, тем быстрее растёт риск метрики при приближении к порогу.', min: 0.01, max: 2, step: 0.01 },
      { key: 'medium_risk_level', label: 'Граница среднего риска', help: 'Начиная с этого значения метрика считается умеренно проблемной.', min: 0, max: 1, step: 0.01 },
      { key: 'critical_risk_level', label: 'Граница критического риска', help: 'Начиная с этого значения метрика считается критичной.', min: 0, max: 1, step: 0.01 },
    ],
  },
  {
    title: 'Логит S0 (норма)',
    description: 'Эти веса усиливают состояние S0, когда признаки риска низкие.',
    stateKey: 's0',
    fields: [
      { key: 'bias', label: 'Смещение S0', help: 'Базовая поддержка нормального состояния.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'metric_aggregate_risk', label: 'Агрегат риска', help: 'Насколько общий агрегат по метрикам влияет на нормальное состояние.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'markov_p_s2', label: 'Марковский риск S2', help: 'Насколько прогноз перехода в S2 ослабляет нормальное состояние.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top1_risk', label: 'Главная риск-метрика', help: 'Влияние самой опасной метрики.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top3_risk', label: 'Среднее по топ-3', help: 'Влияние трёх главных риск-метрик.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'temperature_risk', label: 'Температурный риск', help: 'Вклад температурных каналов.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'wear_risk', label: 'Риск износа', help: 'Вклад метрик износа и деградации накопителей.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'latency_risk', label: 'Риск задержек', help: 'Вклад сетевых задержек и близких показателей.', min: 0, max: 5, step: 0.01, scope: 'score' },
    ],
  },
  {
    title: 'Логит S1 (деградация)',
    description: 'Эти веса усиливают S1, когда признаки находятся в умеренной зоне.',
    stateKey: 's1',
    fields: [
      { key: 'bias', label: 'Смещение S1', help: 'Базовая склонность замечать деградацию.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'metric_aggregate_risk', label: 'Агрегат риска', help: 'Влияние общего риска по метрикам.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'markov_p_s2', label: 'Марковский риск S2', help: 'Вклад вероятности перехода в S2.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top1_risk', label: 'Главная риск-метрика', help: 'Влияние самой опасной метрики.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top3_risk', label: 'Среднее по топ-3', help: 'Влияние трёх главных риск-метрик.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'temperature_risk', label: 'Температурный риск', help: 'Вклад температурных каналов.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'wear_risk', label: 'Риск износа', help: 'Вклад износа и деградации накопителей.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'latency_risk', label: 'Риск задержек', help: 'Вклад сетевых задержек и похожих сигналов.', min: 0, max: 5, step: 0.01, scope: 'score' },
    ],
  },
  {
    title: 'Логит S2 (предаварийное)',
    description: 'Эти веса усиливают S2, когда признаки риска высокие.',
    stateKey: 's2',
    fields: [
      { key: 'bias', label: 'Смещение S2', help: 'Базовая склонность замечать предаварийное состояние.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'metric_aggregate_risk', label: 'Агрегат риска', help: 'Насколько общий риск по метрикам усиливает S2.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'markov_p_s2', label: 'Марковский риск S2', help: 'Вклад прогноза перехода в S2.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top1_risk', label: 'Главная риск-метрика', help: 'Влияние самой опасной метрики.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'top3_risk', label: 'Среднее по топ-3', help: 'Влияние трёх главных риск-метрик.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'temperature_risk', label: 'Температурный риск', help: 'Вклад температурных каналов.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'wear_risk', label: 'Риск износа', help: 'Вклад признаков износа и деградации накопителей.', min: 0, max: 5, step: 0.01, scope: 'score' },
      { key: 'latency_risk', label: 'Риск задержек', help: 'Вклад задержек и подобных сетевых проблем.', min: 0, max: 5, step: 0.01, scope: 'score' },
    ],
  },
  {
    title: 'Уверенность',
    description: 'Определяет, как быстро растёт confidence расчёта.',
    fields: [
      { key: 'confidence_max', label: 'Максимум уверенности', help: 'Верхний потолок confidence.', min: 0, max: 1, step: 0.01 },
      { key: 'confidence_base', label: 'Базовая уверенность', help: 'Стартовое значение confidence.', min: 0, max: 1, step: 0.01 },
      { key: 'confidence_component_weight', label: 'Вес числа метрик', help: 'Насколько количество учтённых метрик повышает confidence.', min: 0, max: 1, step: 0.01 },
      { key: 'confidence_feature_weight', label: 'Вес доп. признаков', help: 'Влияние внешних подсказок: общий риск, Markov и т.д.', min: 0, max: 1, step: 0.01 },
      { key: 'confidence_margin_weight', label: 'Вес отрыва лидирующего состояния', help: 'Чем сильнее лидер отрывается от остальных, тем выше confidence.', min: 0, max: 1, step: 0.01 },
      { key: 'confidence_component_cap', label: 'Лимит учтённых метрик', help: 'Сколько метрик максимум учитывается в росте confidence.', min: 1, max: 20, step: 1, fractionDigits: 0 },
    ],
  },
];

const loadingProfiles = ref(false);
const loadingActive = ref(false);
const loadingDefaults = ref(false);
const loadingBootstrap = ref(false);
const savingProfile = ref(false);

const profiles = ref([]);
const activeProfile = ref(null);
const defaultsPayload = ref(null);
const selectedProfileRow = ref(null);
const thresholdRows = ref([]);
const selectedForecastMetricCode = ref(forecastMetricCatalog[0]?.metric_code || '');

const loadingAny = computed(() => (
  loadingProfiles.value || loadingActive.value || loadingDefaults.value || loadingBootstrap.value || savingProfile.value
));

const emptyProfile = () => ({
  id: null,
  name: '',
  version: 1,
  is_active: false,
  notes: '',
  thresholds: {},
  forecast_metric_controls: defaultForecastMetricControls(),
  orchestrator_controls: defaultOrchestratorControls(),
  softmax_temperature: 1.0,
  score_weights: defaultScoreWeights(),
  risk_ratio_baseline: 0.75,
  risk_ratio_scale: 0.75,
  medium_risk_level: 0.4,
  critical_risk_level: 0.85,
  overall_hint_weight: 0.25,
  s0_bias: 0.15,
  s0_effective_weight: 0.85,
  s0_avg_weight: 0.45,
  s0_medium_weight: 0.35,
  s0_critical_weight: 0.55,
  s1_bias: 0.10,
  s1_avg_weight: 0.90,
  s1_medium_weight: 0.45,
  s1_markov_weight: 0.10,
  s2_bias: 0.05,
  s2_effective_power: 1.60,
  s2_critical_weight: 0.30,
  s2_medium_weight: 0.15,
  s2_markov_weight: 0.10,
  confidence_max: 0.98,
  confidence_base: 0.36,
  confidence_component_weight: 0.08,
  confidence_feature_weight: 0.07,
  confidence_margin_weight: 0.35,
  confidence_component_cap: 5,
});

const profileForm = reactive(emptyProfile());

const activeProfileTag = computed(() => {
  if (!activeProfile.value?.id) return 'Сохранённый активный профиль пока не выбран';
  return `Активный профиль: ${activeProfile.value.name} v${activeProfile.value.version}`;
});

const rowsFromThresholds = (thresholds = {}) => {
  const knownCodes = new Set(metricCatalog.map((item) => item.metric_code));
  const knownRows = metricCatalog.map((item) => ({
    metric_code: item.metric_code,
    label: item.label,
    unit: item.unit,
    threshold: thresholds[item.metric_code] ?? null,
    builtin: true,
  }));
  const customRows = Object.entries(thresholds || {})
    .filter(([code]) => !knownCodes.has(code))
    .map(([code, value]) => ({
      metric_code: code,
      label: 'Пользовательская метрика',
      unit: '',
      threshold: value,
      builtin: false,
    }));
  return [...knownRows, ...customRows];
};

const serializeThresholdRows = () => {
  const result = {};
  for (const row of thresholdRows.value) {
    const code = String(row.metric_code || '').trim();
    const threshold = Number(row.threshold);
    if (!code || !Number.isFinite(threshold) || threshold <= 0) continue;
    result[code] = threshold;
  }
  return result;
};

const normalizeForecastMetricControls = (payload) => {
  const defaults = defaultForecastMetricControls();
  const raw = payload && typeof payload === 'object' ? payload : {};
  const next = { ...defaults };
  Object.entries(raw).forEach(([metricCode, value]) => {
    const code = String(metricCode || '').trim();
    if (!code || !value || typeof value !== 'object') return;
    const base = next[code] ? { ...next[code] } : {
      sarima_enabled: true,
      lstm_enabled: true,
      alpha_mode: 'auto',
      manual_alpha_sarima: 0.5,
      trend_long_mode: defaultTrendLongMode(code),
      trend_transition_steps: 0,
      trend_envelope_weight: defaultTrendEnvelopeWeight(code),
      bias_correction_strength: defaultBiasCorrectionStrength(code),
    };
    const alphaMode = String(value.alpha_mode || base.alpha_mode || 'auto').toLowerCase() === 'manual' ? 'manual' : 'auto';
    let manualAlpha = Number(value.manual_alpha_sarima);
    if (!Number.isFinite(manualAlpha)) manualAlpha = Number(base.manual_alpha_sarima);
    manualAlpha = Math.min(1, Math.max(0, manualAlpha));
    const trendLongMode = trendLongModeOptions.some((option) => option.value === value.trend_long_mode)
      ? value.trend_long_mode
      : base.trend_long_mode;
    let trendTransitionSteps = Number(value.trend_transition_steps);
    if (!Number.isFinite(trendTransitionSteps)) trendTransitionSteps = Number(base.trend_transition_steps);
    trendTransitionSteps = Math.max(0, Math.round(trendTransitionSteps));
    let trendEnvelopeWeight = Number(value.trend_envelope_weight);
    if (!Number.isFinite(trendEnvelopeWeight)) trendEnvelopeWeight = Number(base.trend_envelope_weight);
    trendEnvelopeWeight = Math.min(1, Math.max(0, trendEnvelopeWeight));
    let biasCorrectionStrength = Number(value.bias_correction_strength);
    if (!Number.isFinite(biasCorrectionStrength)) biasCorrectionStrength = Number(base.bias_correction_strength);
    biasCorrectionStrength = Math.min(1, Math.max(0, biasCorrectionStrength));
    next[code] = {
      sarima_enabled: Boolean(value.sarima_enabled ?? base.sarima_enabled),
      lstm_enabled: Boolean(value.lstm_enabled ?? base.lstm_enabled),
      alpha_mode: alphaMode,
      manual_alpha_sarima: manualAlpha,
      trend_long_mode: trendLongMode,
      trend_transition_steps: trendTransitionSteps,
      trend_envelope_weight: trendEnvelopeWeight,
      bias_correction_strength: biasCorrectionStrength,
    };
  });
  return next;
};

const normalizeOrchestratorControls = (payload) => {
  const base = defaultOrchestratorControls();
  const raw = payload && typeof payload === 'object' ? payload : {};
  const boundariesRaw = Array.isArray(raw.segment_boundaries_hours) ? raw.segment_boundaries_hours : base.segment_boundaries_hours;
  const boundaries = boundariesRaw
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item) && item > 0)
    .map((item) => Math.round(item))
    .sort((a, b) => a - b);
  const uniqueBoundaries = [...new Set(boundaries)];
  return {
    alpha_version_aware: raw.alpha_version_aware !== undefined ? Boolean(raw.alpha_version_aware) : base.alpha_version_aware,
    normalize_errors_by_scale: raw.normalize_errors_by_scale !== undefined ? Boolean(raw.normalize_errors_by_scale) : base.normalize_errors_by_scale,
    compatible_history_runs: Math.min(50, Math.max(1, Math.round(Number(raw.compatible_history_runs ?? base.compatible_history_runs) || base.compatible_history_runs))),
    history_limit_per_segment: Math.min(200, Math.max(1, Math.round(Number(raw.history_limit_per_segment ?? base.history_limit_per_segment) || base.history_limit_per_segment))),
    error_scale_lookback_days: Math.min(3650, Math.max(1, Math.round(Number(raw.error_scale_lookback_days ?? base.error_scale_lookback_days) || base.error_scale_lookback_days))),
    winner_margin: Math.min(10, Math.max(1, Number(raw.winner_margin ?? base.winner_margin) || base.winner_margin)),
    winner_weight: Math.min(1, Math.max(0.5, Number(raw.winner_weight ?? base.winner_weight) || base.winner_weight)),
    segment_boundaries_hours: uniqueBoundaries.length >= 2 ? uniqueBoundaries : [...base.segment_boundaries_hours],
  };
};

const serializeForecastMetricControls = () => {
  const normalized = normalizeForecastMetricControls(profileForm.forecast_metric_controls);
  const result = {};
  Object.entries(normalized).forEach(([metricCode, value]) => {
    result[metricCode] = {
      sarima_enabled: Boolean(value.sarima_enabled),
      lstm_enabled: Boolean(value.lstm_enabled),
      alpha_mode: value.alpha_mode === 'manual' ? 'manual' : 'auto',
      manual_alpha_sarima: Math.min(1, Math.max(0, Number(value.manual_alpha_sarima) || 0)),
      trend_long_mode: trendLongModeOptions.some((option) => option.value === value.trend_long_mode)
        ? value.trend_long_mode
        : defaultTrendLongMode(metricCode),
      trend_transition_steps: Math.max(0, Math.round(Number(value.trend_transition_steps) || 0)),
      trend_envelope_weight: Math.min(1, Math.max(0, Number(value.trend_envelope_weight) || 0)),
      bias_correction_strength: Math.min(1, Math.max(0, Number(value.bias_correction_strength) || 0)),
    };
  });
  return result;
};

const serializeOrchestratorControls = () => {
  const normalized = normalizeOrchestratorControls(profileForm.orchestrator_controls);
  return {
    alpha_version_aware: Boolean(normalized.alpha_version_aware),
    normalize_errors_by_scale: Boolean(normalized.normalize_errors_by_scale),
    compatible_history_runs: Number(normalized.compatible_history_runs),
    history_limit_per_segment: Number(normalized.history_limit_per_segment),
    error_scale_lookback_days: Number(normalized.error_scale_lookback_days),
    winner_margin: Number(normalized.winner_margin),
    winner_weight: Number(normalized.winner_weight),
    segment_boundaries_hours: [...normalized.segment_boundaries_hours],
  };
};

const normalizeScoreWeights = (payload) => {
  const defaults = defaultScoreWeights();
  const raw = payload && typeof payload === 'object' ? payload : {};
  const next = {};
  Object.keys(defaults).forEach((stateKey) => {
    next[stateKey] = { ...defaults[stateKey] };
    const statePayload = raw[stateKey];
    if (!statePayload || typeof statePayload !== 'object') return;
    Object.keys(defaults[stateKey]).forEach((featureKey) => {
      const parsed = Number(statePayload[featureKey]);
      if (Number.isFinite(parsed)) {
        next[stateKey][featureKey] = parsed;
      }
    });
  });
  return next;
};

const applyProfileToForm = (payload, { selectRow = true } = {}) => {
  const next = {
    ...emptyProfile(),
    ...(payload || {}),
  };
  Object.keys(emptyProfile()).forEach((key) => {
    if (key === 'score_weights') {
      profileForm.score_weights = normalizeScoreWeights(next.score_weights);
      return;
    }
    if (key === 'forecast_metric_controls') {
      profileForm.forecast_metric_controls = normalizeForecastMetricControls(next.forecast_metric_controls);
      return;
    }
    if (key === 'orchestrator_controls') {
      profileForm.orchestrator_controls = normalizeOrchestratorControls(next.orchestrator_controls);
      return;
    }
    profileForm[key] = next[key];
  });
  thresholdRows.value = rowsFromThresholds(payload?.thresholds || {});
  ensureSelectedForecastMetric();
  if (selectRow) {
    selectedProfileRow.value = payload?.id ? profiles.value.find((item) => item.id === payload.id) || null : null;
  }
};

const buildDraftFromDefaults = () => {
  const base = {
    ...emptyProfile(),
    ...(defaultsPayload.value || {}),
  };
  base.id = null;
  base.name = '';
  base.version = Math.max(1, ...profiles.value.map((item) => Number(item.version || 0))) + 1;
  base.is_active = !profiles.value.length;
  return base;
};

const formatDateTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return String(value);
  }
};

const ensureSelectedForecastMetric = () => {
  const known = forecastMetricRows.value.map((item) => item.metric_code);
  if (!known.length) {
    selectedForecastMetricCode.value = '';
    return;
  }
  if (!known.includes(selectedForecastMetricCode.value)) {
    selectedForecastMetricCode.value = known[0];
  }
};

const forecastMetricRows = computed(() => {
  const controls = normalizeForecastMetricControls(profileForm.forecast_metric_controls);
  const knownCodes = new Set(forecastMetricCatalog.map((item) => item.metric_code));
  const knownRows = forecastMetricCatalog.map((item) => ({
    ...item,
    ...(controls[item.metric_code] || {}),
  }));
  const customRows = Object.entries(controls)
    .filter(([code]) => !knownCodes.has(code))
    .map(([metric_code, value]) => ({
      metric_code,
      label: metric_code,
      unit: '',
      ...value,
    }));
  return [...knownRows, ...customRows];
});

const forecastMetricOptions = computed(() => (
  forecastMetricRows.value.map((item) => ({
    label: item.label,
    value: item.metric_code,
  }))
));

const selectedForecastMetricRow = computed(() => (
  forecastMetricRows.value.find((item) => item.metric_code === selectedForecastMetricCode.value) || null
));

const selectedForecastMetricModeLabel = computed(() => {
  const row = selectedForecastMetricRow.value;
  if (!row) return 'Нет данных';
  if (!row.sarima_enabled && !row.lstm_enabled) return 'Отключена';
  if (row.alpha_mode === 'manual') return `Фиксированный alpha: ${formatForecastAlpha(row.manual_alpha_sarima)}`;
  return 'Авто alpha';
});

const selectedForecastMetricModeSeverity = computed(() => {
  const row = selectedForecastMetricRow.value;
  if (!row) return 'secondary';
  if (!row.sarima_enabled && !row.lstm_enabled) return 'danger';
  if (row.alpha_mode === 'manual') return 'warning';
  return 'success';
});

const formatForecastAlpha = (value) => {
  const alpha = Number(value);
  if (!Number.isFinite(alpha)) return 'SARIMA 50% / LSTM 50%';
  return `SARIMA ${Math.round(alpha * 100)}% / LSTM ${Math.round((1 - alpha) * 100)}%`;
};

const selectedForecastMetricAlphaHint = computed(() => {
  const row = selectedForecastMetricRow.value;
  if (!row) return '';
  const alpha = Number(row.manual_alpha_sarima || 0);
  if (alpha <= 0) return 'Оркестр будет опираться только на LSTM, если прогноз LSTM по этой метрике есть.';
  if (alpha >= 1) return 'Оркестр будет опираться только на SARIMA, если прогноз SARIMA по этой метрике есть.';
  return 'Оркестр смешает оба источника в заданной пропорции. Чем выше alpha, тем больше вклад SARIMA.';
});

const selectedForecastMetricSummary = computed(() => {
  const row = selectedForecastMetricRow.value;
  if (!row) {
    return { title: 'Метрика не выбрана', text: 'Выберите метрику, чтобы настроить её участие в источниках прогноза.' };
  }
  if (!row.sarima_enabled && !row.lstm_enabled) {
    return {
      title: 'Метрика отключена',
      text: 'Ни SARIMA, ни LSTM не будут считать эту метрику. Она не попадёт в оркестр и не будет давать прогнозных точек.',
    };
  }
  if (row.sarima_enabled && !row.lstm_enabled) {
    return {
      title: 'Только SARIMA',
      text: 'Метрика будет считаться локальной SARIMA. Оркестр сможет использовать только SARIMA-прогноз по этой метрике.',
    };
  }
  if (!row.sarima_enabled && row.lstm_enabled) {
    return {
      title: 'Только LSTM',
      text: 'Метрика будет считаться только удалённым LSTM. Это базовый безопасный режим для сложных или нестабильных рядов.',
    };
  }
  if (row.alpha_mode === 'manual') {
    return {
      title: 'Оба источника + ручной alpha',
      text: 'Оба источника строят прогноз, а итоговый вес SARIMA/LSTM берётся из профиля, без авто-подстройки по истории ошибок.',
    };
  }
  return {
    title: 'Оба источника + авто alpha',
    text: 'Оба источника строят прогноз, а оркестр сам выбирает вес SARIMA/LSTM по истории ошибок и текущей устойчивости модели.',
  };
});

const orchestratorControlsModel = computed(() => (
  normalizeOrchestratorControls(profileForm.orchestrator_controls)
));

const orchestratorBoundaryLabel = computed(() => {
  const bounds = orchestratorControlsModel.value.segment_boundaries_hours || [];
  const first = bounds[0] || 24;
  const second = bounds[1] || 168;
  const third = bounds[2] || 720;
  return `0-${first}ч, ${first}-${second}ч, ${second}-${third}ч`;
});

const updateOrchestratorControl = (key, value) => {
  const next = normalizeOrchestratorControls(profileForm.orchestrator_controls);
  next[key] = value;
  profileForm.orchestrator_controls = normalizeOrchestratorControls(next);
};

const updateOrchestratorBoundary = (index, value) => {
  const next = normalizeOrchestratorControls(profileForm.orchestrator_controls);
  const boundaries = [...next.segment_boundaries_hours];
  while (boundaries.length < 3) {
    boundaries.push(defaultOrchestratorControls().segment_boundaries_hours[boundaries.length]);
  }
  const parsed = Math.max(1, Math.round(Number(value) || boundaries[index] || 1));
  boundaries[index] = parsed;
  next.segment_boundaries_hours = boundaries;
  profileForm.orchestrator_controls = normalizeOrchestratorControls(next);
};

const updateForecastControl = (metricCode, key, value) => {
  const code = String(metricCode || '').trim();
  if (!code) return;
  const controls = normalizeForecastMetricControls(profileForm.forecast_metric_controls);
  const current = controls[code] || {
    sarima_enabled: true,
    lstm_enabled: true,
    alpha_mode: 'auto',
    manual_alpha_sarima: 0.5,
    trend_long_mode: defaultTrendLongMode(code),
    trend_transition_steps: 0,
    trend_envelope_weight: defaultTrendEnvelopeWeight(code),
    bias_correction_strength: defaultBiasCorrectionStrength(code),
  };
  let nextValue;
  if (key === 'manual_alpha_sarima' || key === 'trend_envelope_weight' || key === 'bias_correction_strength') {
    nextValue = Math.min(1, Math.max(0, Number(value) || 0));
  } else if (key === 'trend_transition_steps') {
    nextValue = Math.max(0, Math.round(Number(value) || 0));
  } else if (key === 'trend_long_mode') {
    nextValue = trendLongModeOptions.some((option) => option.value === value) ? value : defaultTrendLongMode(code);
  } else {
    nextValue = Boolean(value);
  }
  controls[code] = {
    ...current,
    [key]: nextValue,
  };
  profileForm.forecast_metric_controls = controls;
};

const setForecastAlphaMode = (metricCode, mode) => {
  const code = String(metricCode || '').trim();
  if (!code) return;
  const controls = normalizeForecastMetricControls(profileForm.forecast_metric_controls);
  const current = controls[code] || {
    sarima_enabled: true,
    lstm_enabled: true,
    alpha_mode: 'auto',
    manual_alpha_sarima: 0.5,
    trend_long_mode: defaultTrendLongMode(code),
    trend_transition_steps: 0,
    trend_envelope_weight: defaultTrendEnvelopeWeight(code),
    bias_correction_strength: defaultBiasCorrectionStrength(code),
  };
  controls[code] = {
    ...current,
    alpha_mode: mode === 'manual' ? 'manual' : 'auto',
  };
  profileForm.forecast_metric_controls = controls;
};

const updateForecastAlphaFromRange = (metricCode, event, key = 'manual_alpha_sarima') => {
  const raw = Number(event?.target?.value);
  updateForecastControl(metricCode, key, (Number.isFinite(raw) ? raw : 50) / 100);
};

const onForecastMetricRowSelect = ({ data }) => {
  selectedForecastMetricCode.value = data?.metric_code || '';
};

const readCoefficient = (group, field) => {
  if (field.scope === 'score' && group?.stateKey) {
    return profileForm.score_weights?.[group.stateKey]?.[field.key] ?? 0;
  }
  return profileForm[field.key];
};

const writeCoefficient = (group, field, value) => {
  if (field.scope === 'score' && group?.stateKey) {
    if (!profileForm.score_weights[group.stateKey]) {
      profileForm.score_weights[group.stateKey] = {};
    }
    profileForm.score_weights[group.stateKey][field.key] = value;
    return;
  }
  profileForm[field.key] = value;
};

const loadProfiles = async () => {
  loadingProfiles.value = true;
  try {
    const res = await apiClient.get('state-inference-profiles/?ordering=-is_active,-updated_at');
    profiles.value = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  } finally {
    loadingProfiles.value = false;
  }
};

const loadDefaults = async () => {
  loadingDefaults.value = true;
  try {
    const res = await apiClient.get('state-inference-profiles/defaults/');
    defaultsPayload.value = res.data;
  } finally {
    loadingDefaults.value = false;
  }
};

const loadActiveProfile = async () => {
  loadingActive.value = true;
  try {
    const res = await apiClient.get('state-inference-profiles/active/');
    activeProfile.value = res.data;
    if (!profileForm.id && !selectedProfileRow.value) {
      applyProfileToForm(res.data, { selectRow: Boolean(res.data?.id) });
    }
  } finally {
    loadingActive.value = false;
  }
};

const refreshAll = async () => {
  await Promise.all([
    loadProfiles(),
    loadDefaults(),
  ]);
  await loadActiveProfile();
  if (!selectedProfileRow.value && !profileForm.id) {
    applyProfileToForm(buildDraftFromDefaults(), { selectRow: false });
  }
};

const resetForm = () => {
  applyProfileToForm(buildDraftFromDefaults(), { selectRow: false });
};

const onProfileRowSelect = ({ data }) => {
  if (!data) return;
  applyProfileToForm(data);
};

const addThresholdRow = () => {
  thresholdRows.value.push({
    metric_code: '',
    label: 'Пользовательская метрика',
    unit: '',
    threshold: null,
    builtin: false,
  });
};

const removeThresholdRow = (idx) => {
  thresholdRows.value.splice(idx, 1);
};

const saveProfile = async () => {
  const payload = {
    ...profileForm,
    thresholds: serializeThresholdRows(),
    forecast_metric_controls: serializeForecastMetricControls(),
    orchestrator_controls: serializeOrchestratorControls(),
    score_weights: normalizeScoreWeights(profileForm.score_weights),
  };
  delete payload.id;
  savingProfile.value = true;
  try {
    let savedId = profileForm.id;
    if (profileForm.id) {
      const res = await apiClient.patch(`state-inference-profiles/${profileForm.id}/`, payload);
      savedId = res.data?.id || savedId;
      toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Профиль модели состояния обновлён.', life: 3000 });
    } else {
      const res = await apiClient.post('state-inference-profiles/', payload);
      savedId = res.data?.id || savedId;
      toast.add({ severity: 'success', summary: 'Создано', detail: 'Новый профиль модели состояния сохранён.', life: 3000 });
    }
    await refreshAll();
    const savedProfile = profiles.value.find((item) => item.id === savedId);
    if (savedProfile) {
      applyProfileToForm(savedProfile);
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: error?.response?.data?.detail || 'Не удалось сохранить профиль модели состояния.',
      life: 5000,
    });
  } finally {
    savingProfile.value = false;
  }
};

const activateProfile = async (profileId) => {
  if (!profileId) return;
  try {
    await apiClient.post(`state-inference-profiles/${profileId}/activate/`, {});
    toast.add({ severity: 'success', summary: 'Активный профиль изменён', detail: 'Новый профиль модели состояния применён.', life: 3000 });
    await refreshAll();
    const picked = profiles.value.find((item) => item.id === profileId);
    if (picked) {
      applyProfileToForm(picked);
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: error?.response?.data?.detail || 'Не удалось активировать профиль.',
      life: 5000,
    });
  }
};

const deleteProfile = async () => {
  if (!profileForm.id) return;
  const ok = await confirmAction({
    header: 'Удаление профиля',
    message: 'Удалить выбранный профиль модели состояния?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  try {
    await apiClient.delete(`state-inference-profiles/${profileForm.id}/`);
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Профиль модели состояния удалён.', life: 3000 });
    resetForm();
    await refreshAll();
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: error?.response?.data?.detail || 'Не удалось удалить профиль.',
      life: 5000,
    });
  }
};

const bootstrapDefaults = async () => {
  loadingBootstrap.value = true;
  try {
    const res = await apiClient.post('state-inference-profiles/bootstrap_defaults/', {});
    toast.add({
      severity: 'success',
      summary: 'Базовый профиль готов',
      detail: `Профиль ${res.data?.name || 'по умолчанию'} создан или обновлён.`,
      life: 3000,
    });
    await refreshAll();
    if (res.data) {
      applyProfileToForm(res.data);
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: error?.response?.data?.detail || 'Не удалось создать базовый профиль.',
      life: 5000,
    });
  } finally {
    loadingBootstrap.value = false;
  }
};

onMounted(async () => {
  await refreshAll();
});
</script>

<style scoped>
.state-settings-page {
  color: #0f172a;
  width: 100%;
  min-width: 0;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  min-width: 0;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: 1rem;
  align-items: start;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  min-width: 0;
}

.form-inline {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
  gap: 0.75rem;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.field-block label {
  font-size: 0.9rem;
  font-weight: 600;
  color: #334155;
}

.field-block--small {
  max-width: none;
}

.field-block--switch {
  justify-content: flex-end;
  min-width: 0;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-width: 0;
}

.threshold-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.threshold-row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(140px, 180px) minmax(72px, 96px) auto;
  gap: 0.75rem;
  align-items: end;
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
  min-width: 0;
}

.threshold-main,
.threshold-value,
.threshold-unit {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.threshold-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: #64748b;
}

.threshold-static {
  min-height: 42px;
  padding: 0.7rem 0.85rem;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  overflow-wrap: anywhere;
}

.threshold-actions {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 42px;
}

.forecast-controls-grid {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.forecast-editor-card,
.forecast-summary-card {
  min-width: 0;
}

.forecast-editor-panel {
  padding: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  min-width: 0;
}

.forecast-editor-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.forecast-toggle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.alpha-mode-toggle-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.alpha-range {
  width: 100%;
  accent-color: #10b981;
}

.alpha-range-labels {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.8rem;
  color: #64748b;
  margin-top: 0.35rem;
  flex-wrap: wrap;
}

.forecast-hint-box {
  padding: 0.9rem 1rem;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.coeff-group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: 1rem;
}

.coeff-group-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  padding: 1rem;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  min-width: 0;
}

.coeff-group-head {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.coeff-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.state-settings-page :deep(.tt-filter-panel__head),
.state-settings-page :deep(.tt-page-header) {
  flex-wrap: wrap;
}

.state-settings-page :deep(.p-inputtext),
.state-settings-page :deep(.p-inputnumber),
.state-settings-page :deep(.p-inputnumber-input),
.state-settings-page :deep(.p-inputtextarea),
.state-settings-page :deep(.p-dropdown) {
  width: 100%;
  min-width: 0;
}

.state-settings-page :deep(.p-datatable-wrapper) {
  overflow: auto;
}

.state-settings-page :deep(.p-datatable-table) {
  min-width: 620px;
}

@media (max-width: 1180px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .forecast-controls-grid {
    grid-template-columns: 1fr;
  }

  .threshold-row {
    grid-template-columns: minmax(0, 1fr) minmax(140px, 180px) minmax(72px, 96px);
  }

  .threshold-actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
  }
}

@media (max-width: 860px) {
  .form-inline {
    grid-template-columns: 1fr;
  }

  .threshold-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .coeff-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .threshold-row {
    grid-template-columns: 1fr;
  }

  .threshold-actions {
    justify-content: flex-start;
  }

  .coeff-group-card,
  .threshold-row {
    padding: 0.8rem;
  }

  .actions-row :deep(.p-button) {
    width: 100%;
    justify-content: center;
  }
}
</style>
