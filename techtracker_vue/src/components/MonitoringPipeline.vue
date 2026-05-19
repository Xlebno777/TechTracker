<template>
  <div class="pipeline-page p-4 page-shell">
    <Toast />

    <PageHeader
      title="Полный цикл прогнозирования"
      subtitle="Единый центр управления: от сбора метрик до итогового решения СППР."
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: полный цикл системы"
      help-intro="Эта страница запускает оркестр прогнозирования и собирает в одном месте итог по состоянию, риску, рекомендациям и подтвержденной точности."
      :help-steps="pipelineHelpSteps"
      help-note="Детальная аналитика по каждому блоку остаётся на отдельных страницах, но оперативный итог теперь можно читать здесь."
      @refresh="refreshAll({ withDevices: true })"
    />

    <FilterPanel
      class="mb-3"
      title="Параметры запуска"
      description="Выберите устройство, горизонт прогноза и режим расчёта."
    >
      <div class="filters-grid launch-grid">
        <div class="field-block field-block--wide">
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

        <div class="field-block field-block--wide">
          <label>Горизонты прогноза</label>
          <div class="forecast-pill-grid">
            <button
              v-for="option in horizonOptions"
              :key="option.value"
              type="button"
              class="forecast-pill"
              :class="{ 'forecast-pill--active': selectedForecastHorizons.includes(option.value) }"
              @click="toggleForecastHorizon(option.value)"
            >
              <i class="pi" :class="selectedForecastHorizons.includes(option.value) ? 'pi-check-square' : 'pi-stop'" />
              <span>{{ option.label }}</span>
            </button>
          </div>
        </div>

        <div class="field-block">
          <label>Горизонт риска</label>
          <Dropdown
            v-model="selectedDecisionHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>

        <div class="field-block">
          <label>Режим СППР</label>
          <Dropdown
            v-model="selectedDecisionMode"
            :options="decisionModeOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
      </div>

      <div class="launch-summary-card mt-3">
        <div class="launch-summary-card__head">
          <div class="section-title-row">
            <strong>Будет выполнено сейчас</strong>
            <InfoHint
              title="Что входит в полный цикл"
              :lines="[
                'Сначала запускается оркестр SARIMA + LSTM по выбранным горизонтам.',
                'После этого система строит оценку состояния S0/S1/S2.',
                'Затем рассчитывается риск отказа на выбранном горизонте.',
                'В конце СППР выбирает действие с минимальными ожидаемыми потерями.'
              ]"
            />
          </div>
          <Tag :value="launchSummaryTag" :severity="launchSummaryTagSeverity" />
        </div>
        <div class="launch-summary-card__main">{{ launchSummaryLabel }}</div>
        <div class="launch-summary-card__meta">
          <span>Горизонты прогноза: {{ selectedForecastHorizonLabels.length ? selectedForecastHorizonLabels.join(', ') : 'не выбраны' }}</span>
          <span>{{ launchLastRunText }}</span>
          <span>{{ launchStatusText }}</span>
          <span>Источник точности: {{ launchAccuracySourceText }}</span>
        </div>
      </div>

      <div class="launch-actions-row mt-3">
        <Button
          icon="pi pi-play"
          label="Запустить полный цикл"
          class="launch-actions-row__primary"
          :loading="runningFullCycle"
          :disabled="!canRunCycle"
          @click="launchFullCycle"
        />
        <div class="launch-actions-row__secondary">
          <Button
            icon="pi pi-check-square"
            label="Точность"
            outlined
            :loading="runningEvaluation"
            :disabled="!selectedSerial"
            @click="runAccuracyEvaluation"
          />
          <Button
            icon="pi pi-file-pdf"
            label="PDF"
            outlined
            severity="secondary"
            :loading="downloadingPipelineReport"
            :disabled="!selectedSerial"
            @click="downloadPipelineReport"
          />
          <Button
            icon="pi pi-sliders-v"
            label="Настройки"
            text
            @click="router.push({ name: 'Settings', query: { tab: 'forecast-state' } })"
          />
        </div>
      </div>

      <div class="launch-profile-row mt-3">
        <div class="launch-profile-row__head">
          <span class="launch-profile-row__label">Профиль запуска: стандартный</span>
          <InfoHint
            title="Технический профиль запуска"
            :lines="[
              'SARIMA: lookback 60 дней, частота 1ч, STL + возврат сезонности.',
              'LSTM: lookback 60 дней, частота 1ч, удалённый сервис.',
              'Риск: рассчитывается по последнему успешному прогнозу на выбранном горизонте.',
              'Точность: читается из последней подтвержденной evaluation-сессии.'
            ]"
          />
        </div>
        <div class="launch-profile-row__details">
          SARIMA: 60 д / 1ч / STL + вернуть сезонность •
          LSTM: 60 д / 1ч / удалённый сервис •
          Риск: авто по последнему успешному прогнозу
        </div>
      </div>
    </FilterPanel>

    <div v-if="!selectedDeviceId && !loadingDevices" class="card p-3 mb-3">
      <EmptyStateCard
        icon="pi pi-sitemap"
        title="Устройство не выбрано"
        description="Выберите устройство в верхнем блоке, чтобы система могла собрать цепочку: метрики -> прогноз -> риск -> СППР."
      />
    </div>

    <template v-else>
      <div class="hero-grid mb-3">
        <section class="card p-3 hero-card hero-card--workflow">
          <div class="hero-card__head">
            <div>
              <div class="section-title-row">
                <h4 class="m-0">Центр запуска полного цикла</h4>
                <InfoHint
                  title="Что делает этот блок"
                  :lines="[
                    '1. Запускает оркестр SARIMA + LSTM по выбранному устройству и горизонтам.',
                    '2. После завершения прогноза автоматически считает риск отказа.',
                    '3. Затем запускает СППР и получает итоговую рекомендацию.',
                    '4. Оценка точности прогноза читается из последней подтвержденной верификации с фактическими данными.'
                  ]"
                />
              </div>
              <div class="hero-card__subtitle">Операционный статус конвейера в реальном времени.</div>
            </div>
            <Tag :value="workflowStatusLabel" :severity="workflowStatusSeverity" />
          </div>

          <div class="workflow-timeline mt-3">
            <template v-for="(step, index) in workflowTimelineSteps" :key="step.key">
              <button
                type="button"
                class="workflow-node"
                :class="[
                  `workflow-node--${step.state}`,
                  { 'workflow-node--active': activeWorkflowStage?.key === step.key },
                ]"
                @click="selectWorkflowStage(step.key)"
              >
                <span class="workflow-node__index">{{ step.index }}</span>
                <div class="workflow-node__body">
                  <strong>{{ step.title }}</strong>
                  <span>{{ step.badge }}</span>
                </div>
              </button>
              <div v-if="index < workflowTimelineSteps.length - 1" class="workflow-node__connector" aria-hidden="true">
                <i class="pi pi-arrow-right"></i>
              </div>
            </template>
          </div>

          <div v-if="activeWorkflowStage" class="workflow-focus-card mt-3">
            <div class="workflow-focus-card__head">
              <div>
                <div class="workflow-focus-card__eyebrow">Выбранный этап</div>
                <strong>{{ activeWorkflowStage.title }}</strong>
              </div>
              <Tag :value="activeWorkflowStage.badge" :severity="activeWorkflowStage.severity" />
            </div>

            <div class="workflow-focus-card__summary">{{ activeWorkflowStage.summary }}</div>

            <div class="workflow-focus-card__facts">
              <span>{{ activeWorkflowStage.valueLine }}</span>
              <span>{{ activeWorkflowStage.statusLine }}</span>
            </div>

            <div v-if="activeWorkflowStage.techDetails.length" class="workflow-focus-card__actions">
              <Button
                text
                size="small"
                :icon="workflowStageTechExpanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"
                :label="workflowStageTechExpanded ? 'Скрыть технические детали' : 'Показать технические детали'"
                @click="workflowStageTechExpanded = !workflowStageTechExpanded"
              />
            </div>

            <div v-if="workflowStageTechExpanded && activeWorkflowStage.techDetails.length" class="workflow-tech-box">
              <div v-for="line in activeWorkflowStage.techDetails" :key="line" class="workflow-tech-box__line">
                {{ line }}
              </div>
            </div>
          </div>

          <div class="workflow-kpi-grid mt-3">
            <div class="mini-kpi">
              <span>Текущий этап</span>
              <strong>{{ workflowCurrentStepLabel }}</strong>
            </div>
            <div class="mini-kpi">
              <span>Длительность</span>
              <strong>{{ workflowDurationLabel }}</strong>
            </div>
            <div class="mini-kpi">
              <span>Метрик обработано</span>
              <strong>{{ workflowSummary.metricsProcessed }}</strong>
            </div>
            <div class="mini-kpi">
              <span>Точек прогноза</span>
              <strong>{{ workflowSummary.pointsCreated }}</strong>
            </div>
          </div>

          <div class="workflow-feed mt-3">
            <div class="workflow-feed__head">
              <strong>Лента выполнения</strong>
              <div class="workflow-feed__head-actions">
                <span>{{ workflowFeed.length }} событий</span>
                <Button
                  v-if="workflowFeed.length"
                  text
                  size="small"
                  :icon="workflowFeedExpanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"
                  :label="workflowFeedExpanded ? 'Скрыть' : 'Показать'"
                  @click="workflowFeedExpanded = !workflowFeedExpanded"
                />
              </div>
            </div>
            <div v-if="workflowFeed.length" class="workflow-feed__list">
              <div v-for="entry in visibleWorkflowFeed" :key="entry.id" class="workflow-feed__item" :class="`workflow-feed__item--${entry.tone}`">
                <span class="workflow-feed__time">{{ formatTime(entry.at) }}</span>
                <span class="workflow-feed__text">{{ entry.text }}</span>
              </div>
            </div>
            <div v-else class="workflow-feed__empty">После запуска здесь появятся этапы выполнения и итоговые сообщения системы.</div>
          </div>
        </section>

        <section class="card p-3 hero-card hero-card--summary">
          <div class="hero-card__head">
            <div>
              <div class="section-title-row">
                <h4 class="m-0">Краткий итог по системе</h4>
                <InfoHint
                  title="Как читать краткий итог"
                  :lines="[
                    'Эти карточки нужны для быстрого чтения состояния системы без перехода на отдельные страницы.',
                    'Точность прогноза берётся не из текущего запуска, а из последней подтвержденной верификации, где уже есть фактические значения.',
                    'Риск и рекомендация относятся к текущему выбранному устройству и горизонту.'
                  ]"
                />
              </div>
              <div class="hero-card__subtitle">Главный ответ системы: что делать сейчас и почему.</div>
            </div>
          </div>

          <div class="decision-hero-card mt-3">
            <div class="decision-hero-card__head">
              <div>
                <div class="decision-hero-card__eyebrow">Что делать сейчас</div>
                <strong>{{ decisionHeroTitle }}</strong>
              </div>
              <div class="decision-hero-card__tags">
                <Tag :value="decisionHeroRiskTag" :severity="decisionHeroRiskSeverity" />
                <Tag :value="decisionModeShortLabel" severity="info" />
              </div>
            </div>

            <div class="decision-hero-card__sentence">{{ decisionHumanNarrative }}</div>
          </div>

          <div class="summary-chain mt-3">
            <div v-for="(item, index) in summaryChainItems" :key="item.key" class="summary-chain__item">
              <span class="summary-chain__label">{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.note }}</small>
              <div v-if="index < summaryChainItems.length - 1" class="summary-chain__arrow" aria-hidden="true">
                <i class="pi pi-arrow-right"></i>
              </div>
            </div>
          </div>

          <div class="overview-grid mt-3">
            <div v-for="card in summarySupportCards" :key="card.key" class="overview-card">
              <div class="overview-card__head">
                <span>{{ card.title }}</span>
                <Tag v-if="card.tag" :value="card.tag" :severity="card.severity" />
              </div>
              <strong>{{ card.value }}</strong>
              <span>{{ card.note }}</span>
            </div>
          </div>
        </section>
      </div>

      <section class="card p-3 mb-3 scheme-card">
        <div class="table-head">
          <div class="section-title-row">
            <h4 class="m-0">Структурно-функциональная схема</h4>
            <InfoHint
              title="Логика движения данных"
              :lines="[
                'Система получает сырые метрики от агента мониторинга.',
                'Далее строится прогноз по двум веткам: SARIMA и удалённый LSTM, затем оркестр собирает итоговый прогноз.',
                'Из прогнозных точек строится оценка состояния S0/S1/S2 и интегральный риск отказа.',
                'СППР использует риск и потери действий, чтобы выбрать практическую рекомендацию.',
                'Верификация прогноза и экономического эффекта замыкает цикл и нужна для диссертационной оценки качества.'
              ]"
            />
          </div>
          <span class="text-500 text-sm">От «сбор метрик» до «что делать сейчас»</span>
        </div>

        <div class="pipeline-scheme mt-3">
          <template v-for="(node, idx) in schemeNodes" :key="node.key">
            <div class="scheme-node" :class="`scheme-node--${node.state}`">
              <div class="scheme-node__icon"><i :class="node.icon"></i></div>
              <div class="scheme-node__body">
                <span class="scheme-node__title">{{ node.title }}</span>
                <strong>{{ node.value }}</strong>
                <small>{{ node.note }}</small>
              </div>
            </div>
            <div v-if="idx < schemeNodes.length - 1" class="scheme-arrow">
              <i class="pi pi-arrow-right"></i>
            </div>
          </template>
        </div>

        <div class="feedback-loop mt-3">
          <div class="feedback-loop__title">Контур обратной связи</div>
          <div class="feedback-loop__body">
            Верификация точности прогноза и оценка экономического эффекта возвращают информацию назад в систему,
            чтобы корректировать параметры моделей, веса интеграции и правила СППР.
          </div>
        </div>
      </section>

      <section class="card p-3 mb-3 mini-chart-panel">
        <div class="table-head">
          <div>
            <div class="section-title-row">
              <h4 class="m-0">Мини-графики последнего run</h4>
              <InfoHint
                title="Как читать мини-графики"
                :lines="[
                  'Каждая карточка показывает хвост фактической истории и прогнозные точки последнего доминирующего run.',
                  'Синяя линия — недавние реальные значения, оранжевая — прогноз y_hat, светлая область — интервал p10-p90.',
                  'Для компактности выводятся только самые важные метрики: сначала лидеры риска, затем резервные метрики прогноза.',
                  'Это быстрый визуальный контроль: растёт ли нагрузка, сглажен ли прогноз и насколько широк интервал неопределённости.'
                ]"
              />
            </div>
            <div class="text-500 text-sm">{{ miniChartSectionNote }}</div>
          </div>
          <div class="mini-chart-panel__meta">
            <Tag v-if="latestSuccessfulForecastRun" :value="humanModel(latestSuccessfulForecastRun.model_kind)" severity="info" />
            <Tag :value="humanHorizon(selectedDecisionHorizon)" severity="secondary" />
          </div>
        </div>

        <div v-if="loadingMiniCharts" class="mini-chart-panel__loading mt-3">
          Загружаю компактные ряды последнего run...
        </div>
        <div v-else-if="miniCharts.length" class="mini-chart-grid mt-3">
          <article v-for="chart in miniCharts" :key="chart.metric_code" class="mini-trend-card">
            <div class="mini-trend-card__head">
              <div class="mini-trend-card__title-wrap">
                <strong>{{ chart.metric_label }}</strong>
                <span>{{ chart.summary }}</span>
              </div>
              <Tag v-if="chart.risk_tag" :value="chart.risk_tag" :severity="chart.risk_severity" />
            </div>

            <svg class="mini-trend-card__svg" viewBox="0 0 320 110" preserveAspectRatio="none" aria-hidden="true">
              <path class="mini-trend-card__axis" d="M10 94.5 L310 94.5" />
              <path v-if="chart.band_path" :d="chart.band_path" class="mini-trend-card__band" />
              <path v-if="chart.history_path" :d="chart.history_path" class="mini-trend-card__history" />
              <path v-if="chart.forecast_path" :d="chart.forecast_path" class="mini-trend-card__forecast" />
            </svg>

            <div class="mini-trend-card__legend">
              <span><i class="mini-dot mini-dot--history"></i>История</span>
              <span><i class="mini-dot mini-dot--forecast"></i>Прогноз</span>
              <span><i class="mini-dot mini-dot--band"></i>p10-p90</span>
            </div>

            <div class="mini-trend-card__footer">
              <span>{{ chart.points_label }}</span>
              <span>{{ chart.last_label }}</span>
            </div>
          </article>
        </div>
        <div v-else class="mt-3">
          <EmptyStateCard
            icon="pi pi-wave-pulse"
            title="Мини-графики пока недоступны"
            description="Нужен успешный прогнозный run с точками на выбранном горизонте и хвост истории по этим метрикам."
          />
        </div>
      </section>

      <div class="details-grid mb-3">
        <section class="card p-3 detail-card">
          <div class="table-head">
            <div class="section-title-row">
              <h4 class="m-0">Прогноз и состояние</h4>
              <InfoHint
                title="Что показывает этот блок"
                :lines="[
                  'Слева направо идут последние запуски SARIMA, LSTM и итогового оркестра.',
                  'Ниже показывается последняя оценка состояния S0/S1/S2 для выбранного горизонта.',
                  'Если оркестр уже завершён, именно он считается основным прогнозом для дальнейшего риска.'
                ]"
              />
            </div>
            <Button text size="small" icon="pi pi-external-link" label="Открыть страницу прогнозов" @click="router.push({ name: 'MonitoringForecast' })" />
          </div>

          <div class="model-run-list mt-3">
            <div v-for="item in forecastRunRows" :key="item.key" class="model-run-row">
              <div>
                <strong>{{ item.title }}</strong>
                <div class="text-500 text-sm">{{ item.note }}</div>
              </div>
              <div class="model-run-row__meta">
                <Tag :value="item.statusLabel" :severity="item.severity" />
                <span>{{ item.at }}</span>
              </div>
            </div>
          </div>

          <div v-if="latestState" class="state-compact-grid mt-3">
            <div class="state-compact-card">
              <span>S0</span>
              <strong>{{ formatPercent(latestState.p_s0) }}</strong>
            </div>
            <div class="state-compact-card">
              <span>S1</span>
              <strong>{{ formatPercent(latestState.p_s1) }}</strong>
            </div>
            <div class="state-compact-card">
              <span>S2</span>
              <strong>{{ formatPercent(latestState.p_s2) }}</strong>
            </div>
            <div class="state-compact-card state-compact-card--accent">
              <span>Итоговое состояние</span>
              <strong>{{ stateLabel(latestState.state) }}</strong>
              <small>Уверенность {{ formatPercent(latestState.confidence) }}</small>
            </div>
          </div>
          <div v-else class="mt-3">
            <EmptyStateCard
              icon="pi pi-chart-scatter"
              title="Оценка состояния ещё не получена"
              description="Сначала нужен успешный прогноз и рассчитанные state-estimates для выбранного горизонта."
            />
          </div>
        </section>

        <section class="card p-3 detail-card">
          <div class="table-head">
            <div class="section-title-row">
              <h4 class="m-0">Подтверждённая точность прогноза</h4>
              <InfoHint
                title="Важно для чтения точности"
                :lines="[
                  'Точность прогноза нельзя честно оценить сразу после запуска: нужен уже наступивший факт.',
                  'Поэтому здесь показывается последняя подтвержденная evaluation-сессия по выбранному устройству.',
                  'RMSE/Pinball/PICP/Winkler — это научные метрики качества, рассчитанные на фактических значениях.'
                ]"
              />
            </div>
            <Button text size="small" icon="pi pi-external-link" label="Открыть страницу оценки" @click="router.push({ name: 'MonitoringEvaluation' })" />
          </div>

          <div v-if="latestEvaluation" class="accuracy-summary mt-3">
            <div class="accuracy-summary__head">
              <div>
                <strong>Последняя подтвержденная верификация</strong>
                <div class="text-500 text-sm">{{ formatDateTime(latestEvaluation.generated_at) }} • {{ relativeFreshness(latestEvaluation.generated_at) }}</div>
              </div>
              <Tag :value="accuracyStatusTag" :severity="accuracyStatusSeverity" />
            </div>

            <div class="accuracy-kpi-grid mt-3">
              <div class="mini-kpi">
                <span>Покрытие фактом</span>
                <strong>{{ forecastCoverageLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Лучшая связка по RMSE</span>
                <strong>{{ bestRmseLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Лучшая связка по Pinball</span>
                <strong>{{ bestPinballLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Средний PICP80</span>
                <strong>{{ avgPicpLabel }}</strong>
              </div>
            </div>

            <div class="text-note-box mt-3">
              <div><strong>Лучшая интервальная калибровка:</strong> {{ bestCalibrationLabel }}</div>
              <div><strong>Средний эффект СППР:</strong> {{ avgDeltaLabel }} • положительный эффект {{ deltaShareLabel }}</div>
            </div>
          </div>
          <div v-else class="mt-3">
            <EmptyStateCard
              icon="pi pi-check-square"
              title="Подтвержденная точность пока не найдена"
              description="Для выбранного устройства ещё нет evaluation-run с фактическими значениями или не загружена детализация верификации."
            >
              <template #actions>
                <Button size="small" icon="pi pi-play" label="Запустить оценку точности" @click="runAccuracyEvaluation" />
              </template>
            </EmptyStateCard>
          </div>
        </section>

        <section class="card p-3 detail-card">
          <div class="table-head">
            <div class="section-title-row">
              <h4 class="m-0">Оценка риска отказа</h4>
              <InfoHint
                title="Что такое риск на этой странице"
                :lines="[
                  'Риск — это интегральный индекс угрозы отказа на выбранном горизонте, приведённый к шкале 0-100%.',
                  'Он собирается из двух источников: риска по прогнозным метрикам и вероятности перейти в состояние S2.',
                  'Высокий риск не гарантирует отказ, но означает, что ожидать неблагоприятный сценарий уже рационально.'
                ]"
              />
            </div>
            <Button text size="small" icon="pi pi-external-link" label="Открыть страницу риска" @click="router.push({ name: 'MonitoringRisk' })" />
          </div>

          <div v-if="selectedRiskResult" class="risk-summary mt-3">
            <div class="risk-summary__hero">
              <div>
                <span>Общий риск отказа</span>
                <strong>{{ formatPercent(selectedRiskResult.overall_risk) }}</strong>
              </div>
              <Tag :value="riskLabel(selectedRiskResult.overall_risk)" :severity="riskSeverity(selectedRiskResult.overall_risk)" />
            </div>

            <div class="accuracy-kpi-grid mt-3">
              <div class="mini-kpi">
                <span>Надежность</span>
                <strong>{{ formatPercent(selectedRiskResult.reliability) }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Риск по метрикам</span>
                <strong>{{ formatPercent(selectedRiskResult.metric_aggregate_risk) }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Марковский риск S2</span>
                <strong>{{ formatPercent(selectedRiskResult.markov_projected_p_s2) }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Текущее состояние</span>
                <strong>{{ riskStateLabel }}</strong>
              </div>
            </div>

            <div class="metric-risk-list mt-3">
              <div v-for="row in topRiskMetrics" :key="row.metric_code" class="metric-risk-row">
                <div>
                  <strong>{{ metricLabel(row.metric_code) }}</strong>
                  <div class="text-500 text-sm">{{ methodLabel(row.method) }} • p90 {{ formatMetricValue(row.p90, row.metric_code) }}</div>
                </div>
                <div class="metric-risk-row__meta">
                  <span>{{ formatPercent(row.risk) }}</span>
                  <Tag :value="riskLabel(row.risk)" :severity="riskSeverity(row.risk)" />
                </div>
              </div>
            </div>
          </div>
          <div v-else class="mt-3">
            <EmptyStateCard
              icon="pi pi-exclamation-triangle"
              title="Риск пока не рассчитан"
              description="Для выбранного горизонта нет готовой оценки риска. Нужен успешный прогноз и валидная оценка состояния."
            />
          </div>
        </section>

        <section class="card p-3 detail-card">
          <div class="table-head">
            <div class="section-title-row">
              <h4 class="m-0">Итоговое решение СППР</h4>
              <InfoHint
                title="Как читается рекомендация"
                :lines="[
                  'СППР выбирает действие с минимальными ожидаемыми потерями.',
                  'В расчёт входят вероятности состояний, риск-метрики и стоимость альтернативных действий.',
                  'Итог здесь — это не просто текст, а результат формального выбора среди допустимых вариантов.'
                ]"
              />
            </div>
            <Button text size="small" icon="pi pi-external-link" label="Открыть страницу СППР" @click="router.push({ name: 'MonitoringDecision' })" />
          </div>

          <div v-if="latestDecision" class="decision-summary mt-3">
            <div class="decision-summary__hero">
              <div>
                <span>Рекомендованное действие</span>
                <strong>{{ latestDecision.recommended_action_name || 'Нет данных' }}</strong>
                <small>{{ latestDecision.recommended_action_code || '—' }}</small>
              </div>
              <Tag :value="decisionModeLabel(selectedDecisionMode)" :severity="selectedDecisionMode === 'advanced' ? 'warning' : 'info'" />
            </div>

            <div class="accuracy-kpi-grid mt-3">
              <div class="mini-kpi">
                <span>Ожидаемые потери</span>
                <strong>{{ recommendedLossLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Контекст риска</span>
                <strong>{{ decisionRiskContextLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Почему выбрано</span>
                <strong>{{ decisionReasonLabel }}</strong>
              </div>
              <div class="mini-kpi">
                <span>Последний запуск</span>
                <strong>{{ formatDateTime(latestDecision.created_at) }}</strong>
              </div>
            </div>

            <div class="decision-active-metrics mt-3">
              <span>Метрики, которые реально вошли в расчёт:</span>
              <div v-if="decisionActiveMetrics.length" class="decision-chip-wrap">
                <Tag v-for="item in decisionActiveMetrics" :key="item.metric_code" :value="metricLabel(item.metric_code)" severity="info" />
              </div>
              <div v-else class="text-500 text-sm">Backend не передал список активных риск-метрик для этой рекомендации.</div>
            </div>
          </div>
          <div v-else class="mt-3">
            <EmptyStateCard
              icon="pi pi-lightbulb"
              title="Рекомендация СППР пока не рассчитана"
              description="После завершения прогноза и оценки риска система сможет предложить действие с минимальными ожидаемыми потерями."
            />
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import apiClient from '@/api';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import Toast from 'primevue/toast';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import Tag from 'primevue/tag';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import InfoHint from '@/components/ui/InfoHint.vue';

const router = useRouter();
const toast = useToast();
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();

const devices = ref([]);
const loadingDevices = ref(false);
const loadingDashboard = ref(false);
const runningFullCycle = ref(false);
const runningEvaluation = ref(false);
const latestRawMetric = ref(null);
const latestAgentStatus = ref(null);
const latestSarimaRun = ref(null);
const latestLstmRun = ref(null);
const latestEnsembleRun = ref(null);
const latestLstmQueueJob = ref(null);
const latestState = ref(null);
const riskPayload = ref(null);
const latestDecision = ref(null);
const latestEvaluation = ref(null);
const latestEvaluationDetail = ref(null);
const miniCharts = ref([]);
const loadingMiniCharts = ref(false);
const downloadingPipelineReport = ref(false);
const selectedWorkflowStageKey = ref('');
const workflowStageTechExpanded = ref(false);
const workflowFeedExpanded = ref(false);
const selectedDecisionMode = ref('bayes');
const selectedDecisionHorizon = ref('30d');
const selectedForecastHorizons = ref(['24h', '7d', '30d']);
const workflowStreamSnapshot = ref(null);
const workflowStreamStatus = ref('idle');
const workflowStartTs = ref(null);
const workflowFinishTs = ref(null);
const workflowFeed = ref([]);

let workflowStreamController = null;
let bootstrapped = false;
let workflowFeedCounter = 0;
let lastWorkflowMarker = '';

const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});

const horizonOptions = [
  { value: '24h', label: '24 часа' },
  { value: '7d', label: '7 дней' },
  { value: '30d', label: '30 дней' },
];

const decisionModeOptions = [
  { value: 'bayes', label: 'Базовый Bayes' },
  { value: 'advanced', label: 'Расширенный Bayes + AHP' },
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
};

const pipelineHelpSteps = [
  'Выберите устройство и горизонты прогноза в верхнем блоке.',
  'Нажмите «Запустить полный цикл» для запуска SARIMA, удалённого LSTM и итогового оркестра.',
  'После завершения прогноза система автоматически пересчитает риск отказа и СППР.',
  'Блок «Структурно-функциональная схема» показывает, где сейчас находится информация в конвейере.',
  'Карточка точности прогноза использует только подтвержденные evaluation-run, где уже есть фактические значения.',
  'Если нужен полный разбор, переходите по кнопкам в детальные страницы прогнозов, риска, СППР и оценки прогноза.',
];

const deviceOptions = computed(() => (
  devices.value.map((device) => ({
    id: device.id,
    serial: device.serial_number || '',
    label: device.serial_number ? `${device.name} (${device.serial_number})` : device.name,
  }))
));

const selectedDevice = computed(() => (
  deviceOptions.value.find((item) => item.id === selectedDeviceId.value) || null
));

const selectedSerial = computed(() => selectedDevice.value?.serial || '');
const loadingAny = computed(() => loadingDevices.value || loadingDashboard.value || runningFullCycle.value || runningEvaluation.value);
const canRunCycle = computed(() => Boolean(selectedSerial.value) && selectedForecastHorizons.value.length > 0 && !runningFullCycle.value);

const selectedRiskResult = computed(() => {
  const rows = Array.isArray(riskPayload.value?.horizons) ? riskPayload.value.horizons : [];
  return rows.find((row) => row.horizon === selectedDecisionHorizon.value) || rows[0] || null;
});

const evaluationSummary = computed(() => latestEvaluationDetail.value?.manifest?.summary || latestEvaluation.value?.summary || {});
const evaluationInsights = computed(() => latestEvaluationDetail.value?.insights || {});
const evaluationChartData = computed(() => latestEvaluationDetail.value?.chart_data || {});
const decisionActiveMetrics = computed(() => latestDecision.value?.explanation?.risk_context?.active_metrics || []);
const decisionScores = computed(() => Array.isArray(latestDecision.value?.scores) ? latestDecision.value.scores : []);
const recommendedScore = computed(() => decisionScores.value.find((row) => row.is_recommended) || null);

const topRiskMetrics = computed(() => {
  const rows = Array.isArray(selectedRiskResult.value?.metrics) ? selectedRiskResult.value.metrics : [];
  return [...rows]
    .sort((a, b) => Number(b.risk || 0) - Number(a.risk || 0))
    .slice(0, 3);
});

const topRiskMetricLabel = computed(() => {
  const top = topRiskMetrics.value[0];
  if (!top) return 'лидирующая метрика не определена';
  return `лидер: ${metricLabel(top.metric_code)}`;
});

const miniChartSectionNote = computed(() => {
  if (!latestSuccessfulForecastRun.value) {
    return 'После первого успешного прогноза здесь появится компактная визуализация ключевых метрик.';
  }
  return `Источник: ${humanModel(latestSuccessfulForecastRun.value.model_kind)} • run #${latestSuccessfulForecastRun.value.id} • горизонт ${humanHorizon(selectedDecisionHorizon.value)}.`;
});

const selectedForecastHorizonLabels = computed(() => (
  horizonOptions
    .filter((option) => selectedForecastHorizons.value.includes(option.value))
    .map((option) => option.label)
));

const decisionModeShortLabel = computed(() => (
  selectedDecisionMode.value === 'advanced' ? 'Расширенный Bayes + AHP' : 'Базовый Bayes'
));

const launchSummaryLabel = computed(() => (
  `Оркестр SARIMA + LSTM → Оценка состояния → Оценка риска ${humanHorizon(selectedDecisionHorizon.value)} → СППР (${decisionModeShortLabel.value})`
));

const launchLastRunText = computed(() => {
  if (runningFullCycle.value && workflowStartTs.value) {
    return `Новый запуск: ${formatDateTime(workflowStartTs.value)}`;
  }
  if (latestSuccessfulForecastRun.value) {
    return `Последний запуск: ${formatDateTime(latestSuccessfulForecastRun.value.created_at)}`;
  }
  return 'Последний запуск: не найден';
});

const launchStatusText = computed(() => {
  if (runningFullCycle.value) {
    return `Статус: ${workflowStatusLabel.value} • этап: ${workflowCurrentStepLabel.value}`;
  }
  if (latestSuccessfulForecastRun.value) {
    return `Статус: ${runStatusLabel(latestSuccessfulForecastRun.value.status)}`;
  }
  return 'Статус: ожидание запуска';
});

const launchAccuracySourceText = computed(() => (
  latestEvaluation.value ? 'последняя подтвержденная верификация' : 'подтвержденная верификация отсутствует'
));

const launchSummaryTag = computed(() => {
  if (runningFullCycle.value) return 'Выполняется';
  if (latestSuccessfulForecastRun.value) return 'Готово';
  return 'Ожидание';
});

const launchSummaryTagSeverity = computed(() => {
  if (runningFullCycle.value) return 'warning';
  if (latestSuccessfulForecastRun.value) return 'success';
  return 'secondary';
});

const accuracyHasConfirmedMetrics = computed(() => Boolean(evaluationInsights.value?.best_rmse));

const accuracyStatusTag = computed(() => {
  if (!latestEvaluation.value) return 'Нет факта';
  if (!accuracyHasConfirmedMetrics.value) return 'Факт без метрик';
  return 'Подтверждено';
});

const accuracyStatusSeverity = computed(() => {
  if (!latestEvaluation.value) return 'secondary';
  if (!accuracyHasConfirmedMetrics.value) return 'warning';
  return 'success';
});

const decisionHeroTitle = computed(() => (
  latestDecision.value?.recommended_action_name || 'Рекомендация ещё не готова'
));

const decisionHeroRiskTag = computed(() => (
  selectedRiskResult.value ? riskLabel(selectedRiskResult.value.overall_risk) : 'Нет риска'
));

const decisionHeroRiskSeverity = computed(() => (
  selectedRiskResult.value ? riskSeverity(selectedRiskResult.value.overall_risk) : 'secondary'
));

const decisionHumanNarrative = computed(() => {
  if (latestDecision.value && selectedRiskResult.value) {
    return `Система считает, что риск отказа ${riskLabel(selectedRiskResult.value.overall_risk).toLowerCase()}; рекомендуется ${latestDecision.value.recommended_action_name}.`;
  }
  if (selectedRiskResult.value && !latestDecision.value) {
    return `Система считает, что риск отказа ${riskLabel(selectedRiskResult.value.overall_risk).toLowerCase()}, но рекомендация СППР для этого контекста пока не рассчитана.`;
  }
  if (latestSuccessfulForecastRun.value && !selectedRiskResult.value) {
    return 'Прогноз уже построен, но оценка риска отказа ещё не сформирована.';
  }
  return 'Сначала нужен полный цикл прогноза, чтобы система могла связать прогноз, риск и итоговое решение.';
});

const summaryChainItems = computed(() => ([
  {
    key: 'forecast',
    label: 'Прогноз',
    value: dominantForecastLabel.value,
    note: latestSuccessfulForecastRun.value ? formatDateTime(latestSuccessfulForecastRun.value.created_at) : 'ожидание запуска',
  },
  {
    key: 'risk',
    label: 'Риск',
    value: selectedRiskResult.value ? formatPercent(selectedRiskResult.value.overall_risk) : 'не рассчитан',
    note: selectedRiskResult.value ? riskLabel(selectedRiskResult.value.overall_risk) : 'нужен прогноз',
  },
  {
    key: 'decision',
    label: 'Решение',
    value: latestDecision.value?.recommended_action_name || 'нет рекомендации',
    note: latestDecision.value ? decisionModeShortLabel.value : 'СППР ещё не запускалась',
  },
]));

const summarySupportCards = computed(() => ([
  {
    key: 'raw',
    title: 'Свежесть метрик',
    value: rawFreshnessLabel.value,
    note: latestAgentStatus.value?.status ? `Агент: ${agentStatusLabel(latestAgentStatus.value.status)}` : 'Статус агента не найден',
    tag: rawStatusTag.value,
    severity: rawStatusSeverity.value,
  },
  {
    key: 'forecast',
    title: 'Основной прогноз',
    value: dominantForecastLabel.value,
    note: latestSuccessfulForecastRun.value ? `${formatDateTime(latestSuccessfulForecastRun.value.created_at)} • ${relativeFreshness(latestSuccessfulForecastRun.value.created_at)}` : 'Прогноз ещё не построен',
    tag: dominantForecastTag.value,
    severity: dominantForecastSeverity.value,
  },
  {
    key: 'risk',
    title: 'Текущий риск отказа',
    value: selectedRiskResult.value ? formatPercent(selectedRiskResult.value.overall_risk) : '—',
    note: selectedRiskResult.value ? `Лидер: ${metricLabel(topRiskMetrics.value[0]?.metric_code)}` : 'Риск не рассчитан',
    tag: selectedRiskResult.value ? riskLabel(selectedRiskResult.value.overall_risk) : 'Нет данных',
    severity: selectedRiskResult.value ? riskSeverity(selectedRiskResult.value.overall_risk) : 'secondary',
  },
  {
    key: 'accuracy',
    title: 'Подтвержденная точность',
    value: accuracyHasConfirmedMetrics.value ? bestRmseLabel.value : 'Нет подтвержденного RMSE',
    note: latestEvaluation.value ? `Верификация: ${formatDateTime(latestEvaluation.value.generated_at)}` : 'Подтвержденной верификации нет',
    tag: accuracyStatusTag.value,
    severity: accuracyStatusSeverity.value,
  },
]));

const rawFreshnessLabel = computed(() => relativeFreshness(latestRawMetric.value?.timestamp || latestAgentStatus.value?.updated_at || null));
const rawStatusTag = computed(() => {
  if (!latestRawMetric.value && !latestAgentStatus.value) return 'Нет данных';
  const freshness = relativeFreshnessMinutes(latestRawMetric.value?.timestamp || latestAgentStatus.value?.updated_at || null);
  if (freshness === null) return 'Нет данных';
  if (freshness <= 10) return 'Свежие';
  if (freshness <= 60) return 'Устаревают';
  return 'Старые';
});
const rawStatusSeverity = computed(() => {
  if (rawStatusTag.value === 'Свежие') return 'success';
  if (rawStatusTag.value === 'Устаревают') return 'warning';
  if (rawStatusTag.value === 'Старые') return 'danger';
  return 'secondary';
});

const latestSuccessfulForecastRun = computed(() => {
  const rows = [latestEnsembleRun.value, latestLstmRun.value, latestSarimaRun.value]
    .filter((row) => row?.status === 'success')
    .sort((a, b) => timestampValue(b?.created_at) - timestampValue(a?.created_at));
  return rows[0] || null;
});

const dominantForecastLabel = computed(() => {
  const run = latestSuccessfulForecastRun.value;
  if (!run) return 'Нет готового прогноза';
  return `${modelKindLabel(run.model_kind)} • ${humanHorizonList(run.horizon_set)}`;
});

const dominantForecastNote = computed(() => {
  const run = latestSuccessfulForecastRun.value;
  if (!run) return 'Запустите полный цикл, чтобы получить актуальный оркестр и состояние.';
  return `run #${run.id} • ${formatDateTime(run.created_at)} • ${relativeFreshness(run.created_at)}`;
});

const dominantForecastTag = computed(() => runStatusLabel(latestSuccessfulForecastRun.value?.status || null));
const dominantForecastSeverity = computed(() => runStatusSeverity(latestSuccessfulForecastRun.value?.status || null));

const forecastRunRows = computed(() => ([
  buildForecastRunRow('sarima', 'SARIMA baseline', latestSarimaRun.value),
  buildForecastRunRow('lstm', 'Удалённый LSTM', latestLstmRun.value, latestLstmQueueJob.value),
  buildForecastRunRow('ensemble', 'Итоговый оркестр', latestEnsembleRun.value),
]));

const workflowSummary = computed(() => {
  const summary = workflowStreamSnapshot.value?.summary || {};
  return {
    metricsProcessed: displayInt(summary.metrics_processed),
    historyPoints: displayInt(summary.history_points_total),
    pointsCreated: displayInt(summary.points_created),
    statesCreated: displayInt(summary.states_created),
  };
});

const workflowCurrentStepLabel = computed(() => {
  const step = workflowStreamSnapshot.value?.current_step;
  const steps = Array.isArray(workflowStreamSnapshot.value?.steps) ? workflowStreamSnapshot.value.steps : [];
  const found = steps.find((item) => item.key === step?.key);
  return found?.title || 'ожидание запуска';
});

const workflowDurationLabel = computed(() => {
  const snapshotDuration = Number(workflowStreamSnapshot.value?.summary?.duration_sec);
  if (Number.isFinite(snapshotDuration) && snapshotDuration > 0) return formatDuration(snapshotDuration);
  if (workflowStartTs.value) {
    const end = workflowFinishTs.value || new Date().toISOString();
    const diff = Math.max(0, (timestampValue(end) - timestampValue(workflowStartTs.value)) / 1000);
    return formatDuration(diff);
  }
  return '—';
});

const workflowStatusLabel = computed(() => {
  if (workflowStreamStatus.value === 'completed') return 'Цикл завершён';
  if (workflowStreamStatus.value === 'failed') return 'Цикл завершился с ошибкой';
  if (workflowStreamStatus.value === 'timeout') return 'Таймаут цикла';
  if (runningFullCycle.value) return 'Выполняется';
  return 'Ожидание запуска';
});

const workflowStatusSeverity = computed(() => {
  if (workflowStreamStatus.value === 'completed') return 'success';
  if (workflowStreamStatus.value === 'failed') return 'danger';
  if (workflowStreamStatus.value === 'timeout') return 'warning';
  if (runningFullCycle.value) return 'warning';
  return 'secondary';
});

const workflowStepCards = computed(() => {
  const baseSteps = Array.isArray(workflowStreamSnapshot.value?.steps) && workflowStreamSnapshot.value.steps.length
    ? workflowStreamSnapshot.value.steps
    : [
      { key: 'sarima', title: 'SARIMA', description: 'Локальный baseline-прогноз.' },
      { key: 'lstm', title: 'LSTM', description: 'Удалённый расчёт на выделенном ПК.' },
      { key: 'ensemble', title: 'Оркестр', description: 'Сборка итогового прогноза.' },
      { key: 'risk', title: 'Риск', description: 'Интегральная оценка угрозы отказа.' },
      { key: 'decision', title: 'СППР', description: 'Выбор действия с минимальными потерями.' },
    ];

  const currentKey = workflowStreamSnapshot.value?.current_step?.key || null;
  const forecastStatus = workflowStreamStatus.value;

  const rows = baseSteps.map((step, index) => {
    let state = 'pending';
    if (forecastStatus === 'completed') {
      state = 'done';
    } else if (forecastStatus === 'failed' || forecastStatus === 'timeout') {
      if (step.key === currentKey) state = 'failed';
      else if (index < baseSteps.findIndex((item) => item.key === currentKey)) state = 'done';
    } else if (runningFullCycle.value) {
      const currentIndex = baseSteps.findIndex((item) => item.key === currentKey);
      if (currentIndex >= 0) {
        if (index < currentIndex) state = 'done';
        else if (index === currentIndex) state = 'current';
      }
    }
    return {
      ...step,
      index: index + 1,
      state,
      badge: state === 'done' ? 'Готово' : state === 'current' ? 'В работе' : state === 'failed' ? 'Ошибка' : 'Ожидание',
      severity: state === 'done' ? 'success' : state === 'current' ? 'warning' : state === 'failed' ? 'danger' : 'secondary',
      meta: resolveStepMeta(step.key),
    };
  });

  if (!rows.some((item) => item.key === 'risk')) {
    rows.push({
      key: 'risk',
      title: 'Риск',
      description: 'Интегральная оценка угрозы отказа.',
      index: rows.length + 1,
      state: selectedRiskResult.value ? 'done' : 'pending',
      badge: selectedRiskResult.value ? 'Готово' : 'Ожидание',
      severity: selectedRiskResult.value ? 'success' : 'secondary',
      meta: selectedRiskResult.value ? formatPercent(selectedRiskResult.value.overall_risk) : 'ждёт расчёта',
    });
    rows.push({
      key: 'decision',
      title: 'СППР',
      description: 'Выбор итогового действия.',
      index: rows.length + 1,
      state: latestDecision.value ? 'done' : 'pending',
      badge: latestDecision.value ? 'Готово' : 'Ожидание',
      severity: latestDecision.value ? 'success' : 'secondary',
      meta: latestDecision.value?.recommended_action_name || 'ждёт расчёта',
    });
  }

  return rows;
});

const workflowTimelineSteps = computed(() => workflowStepCards.value.filter((step) => (
  ['sarima', 'lstm', 'ensemble', 'risk', 'decision'].includes(step.key)
)));

const defaultWorkflowStageKey = computed(() => {
  const current = workflowStreamSnapshot.value?.current_step?.key;
  if (current && workflowTimelineSteps.value.some((step) => step.key === current)) return current;
  if (latestDecision.value) return 'decision';
  if (selectedRiskResult.value) return 'risk';
  if (latestEnsembleRun.value?.status === 'success') return 'ensemble';
  if (latestLstmRun.value?.status === 'success') return 'lstm';
  if (latestSarimaRun.value?.status === 'success') return 'sarima';
  return workflowTimelineSteps.value[0]?.key || 'sarima';
});

const workflowStageDetails = computed(() => {
  const stepMap = Object.fromEntries(workflowStepCards.value.map((step) => [step.key, step]));
  const sarimaRun = latestSarimaRun.value;
  const lstmRun = latestLstmRun.value;
  const ensembleRun = latestEnsembleRun.value;
  const queue = latestLstmQueueJob.value;
  const risk = selectedRiskResult.value;
  const decision = latestDecision.value;

  return {
    sarima: {
      key: 'sarima',
      title: 'SARIMA',
      badge: stepMap.sarima?.badge || 'Ожидание',
      severity: stepMap.sarima?.severity || 'secondary',
      summary: sarimaRun
        ? 'Локальный статистический baseline строит прогнозные точки по выбранным горизонтам.'
        : 'Локальный baseline-прогноз ещё не запускался для текущего контекста.',
      valueLine: sarimaRun
        ? `Горизонты: ${humanHorizonList(sarimaRun.horizon_set)}`
        : 'Горизонты будут взяты из текущего запуска.',
      statusLine: sarimaRun
        ? `Последнее обновление: ${formatDateTime(sarimaRun.updated_at || sarimaRun.created_at)}`
        : 'Ожидает запуска.',
      techDetails: sarimaRun ? [
        `run #${sarimaRun.id}`,
        `Статус: ${runStatusLabel(sarimaRun.status)}`,
        `Создан: ${formatDateTime(sarimaRun.created_at)}`,
        `Горизонты: ${humanHorizonList(sarimaRun.horizon_set)}`,
      ] : [],
    },
    lstm: {
      key: 'lstm',
      title: 'LSTM',
      badge: stepMap.lstm?.badge || 'Ожидание',
      severity: stepMap.lstm?.severity || 'secondary',
      summary: lstmRun
        ? 'Удалённый сервис LSTM считает нейросетевой прогноз на выделенном ПК.'
        : 'Нейросетевой этап пока не запускался для текущего контекста.',
      valueLine: lstmRun
        ? `Горизонты: ${humanHorizonList(lstmRun.horizon_set)}`
        : 'Будет использовать удалённый вычислительный сервис.',
      statusLine: lstmRun
        ? `Статус: ${runStatusLabel(normalizeLstmStatus(lstmRun, queue))}`
        : 'Ожидает запуска.',
      techDetails: [
        ...(lstmRun ? [
          `run #${lstmRun.id}`,
          `Создан: ${formatDateTime(lstmRun.created_at)}`,
          `Горизонты: ${humanHorizonList(lstmRun.horizon_set)}`,
        ] : []),
        ...(queue?.remote_job_id ? [`remote_job_id=${queue.remote_job_id}`] : []),
      ],
    },
    ensemble: {
      key: 'ensemble',
      title: 'Оркестр',
      badge: stepMap.ensemble?.badge || 'Ожидание',
      severity: stepMap.ensemble?.severity || 'secondary',
      summary: ensembleRun
        ? 'Оркестр объединяет SARIMA и LSTM в итоговый прогнозный ряд.'
        : 'Итоговая интеграция ещё не выполнилась.',
      valueLine: ensembleRun
        ? `Горизонты: ${humanHorizonList(ensembleRun.horizon_set)}`
        : 'Ожидает готовые SARIMA и LSTM.',
      statusLine: ensembleRun
        ? `Последнее обновление: ${formatDateTime(ensembleRun.updated_at || ensembleRun.created_at)}`
        : 'Ожидает запуска.',
      techDetails: ensembleRun ? [
        `run #${ensembleRun.id}`,
        `Статус: ${runStatusLabel(ensembleRun.status)}`,
        `Создан: ${formatDateTime(ensembleRun.created_at)}`,
        `Горизонты: ${humanHorizonList(ensembleRun.horizon_set)}`,
      ] : [],
    },
    risk: {
      key: 'risk',
      title: 'Риск',
      badge: stepMap.risk?.badge || 'Ожидание',
      severity: stepMap.risk?.severity || 'secondary',
      summary: risk
        ? 'Интегральный риск отказа строится из прогнозных метрик и вероятности перехода в S2.'
        : 'Риск ещё не рассчитан для текущего прогноза.',
      valueLine: risk
        ? `Общий риск: ${formatPercent(risk.overall_risk)} • Марков S2: ${formatPercent(risk.markov_projected_p_s2)}`
        : 'Ожидает успешный прогноз и state-estimate.',
      statusLine: risk
        ? `Лидер риска: ${metricLabel(topRiskMetrics.value[0]?.metric_code)}`
        : 'Ожидает расчёта.',
      techDetails: risk ? [
        `Риск по метрикам: ${formatPercent(risk.metric_aggregate_risk)}`,
        `Марковский риск S2: ${formatPercent(risk.markov_projected_p_s2)}`,
        `Общий риск: ${formatPercent(risk.overall_risk)}`,
      ] : [],
    },
    decision: {
      key: 'decision',
      title: 'СППР',
      badge: stepMap.decision?.badge || 'Ожидание',
      severity: stepMap.decision?.severity || 'secondary',
      summary: decision
        ? 'СППР выбирает действие с минимальными ожидаемыми потерями.'
        : 'Итоговая рекомендация ещё не рассчитана.',
      valueLine: decision
        ? `Рекомендация: ${decision.recommended_action_name || '—'}`
        : 'Ожидает риск и допустимые действия.',
      statusLine: decision
        ? `Потери: ${recommendedLossLabel.value}`
        : 'Ожидает расчёта.',
      techDetails: decision ? [
        `run #${decision.id}`,
        `Режим: ${decisionModeShortLabel.value}`,
        `Создан: ${formatDateTime(decision.created_at)}`,
        ...(decision.recommended_action_code ? [`Код действия: ${decision.recommended_action_code}`] : []),
      ] : [],
    },
  };
});

const activeWorkflowStage = computed(() => {
  const key = selectedWorkflowStageKey.value || defaultWorkflowStageKey.value;
  return workflowStageDetails.value[key] || workflowStageDetails.value[defaultWorkflowStageKey.value] || null;
});

const visibleWorkflowFeed = computed(() => (
  workflowFeedExpanded.value ? workflowFeed.value : workflowFeed.value.slice(-3)
));

const schemeNodes = computed(() => ([
  {
    key: 'raw',
    title: 'Сбор метрик',
    icon: 'pi pi-database',
    value: rawFreshnessLabel.value,
    note: latestRawMetric.value ? `Последняя метрика: ${formatDateTime(latestRawMetric.value.timestamp)}` : 'Сырые метрики не найдены',
    state: nodeStateFromFreshness(latestRawMetric.value?.timestamp || latestAgentStatus.value?.updated_at || null),
  },
  {
    key: 'forecast',
    title: 'SARIMA + LSTM + оркестр',
    icon: 'pi pi-chart-scatter',
    value: dominantForecastLabel.value,
    note: dominantForecastNote.value,
    state: latestSuccessfulForecastRun.value ? 'ok' : (runningFullCycle.value ? 'running' : 'idle'),
  },
  {
    key: 'state',
    title: 'Оценка состояния S0/S1/S2',
    icon: 'pi pi-sparkles',
    value: latestState.value ? stateLabel(latestState.value.state) : 'Нет оценки',
    note: latestState.value ? `Уверенность ${formatPercent(latestState.value.confidence)}` : 'State-estimate ещё не найден',
    state: latestState.value ? stateNodeState(latestState.value.state) : 'idle',
  },
  {
    key: 'risk',
    title: 'Оценка риска отказа',
    icon: 'pi pi-exclamation-triangle',
    value: selectedRiskResult.value ? formatPercent(selectedRiskResult.value.overall_risk) : 'Нет риска',
    note: selectedRiskResult.value ? `${riskLabel(selectedRiskResult.value.overall_risk)} • ${topRiskMetricLabel.value}` : 'Риск ещё не рассчитан',
    state: selectedRiskResult.value ? riskNodeState(selectedRiskResult.value.overall_risk) : 'idle',
  },
  {
    key: 'decision',
    title: 'СППР',
    icon: 'pi pi-lightbulb',
    value: latestDecision.value?.recommended_action_name || 'Нет рекомендации',
    note: latestDecision.value ? `Потери ${recommendedLossLabel.value}` : 'Ожидает риск и политику действий',
    state: latestDecision.value ? 'ok' : 'idle',
  },
  {
    key: 'final',
    title: 'Финальное решение',
    icon: 'pi pi-check-circle',
    value: latestDecision.value?.recommended_action_name || 'Ожидание',
    note: latestDecision.value ? decisionReasonLabel.value : 'Что делать сейчас станет ясно после расчёта СППР',
    state: latestDecision.value ? 'ok' : 'idle',
  },
]));

const forecastCoverageLabel = computed(() => percent(evaluationSummary.value?.forecast_coverage));
const bestRmseLabel = computed(() => {
  const best = evaluationInsights.value?.best_rmse;
  if (!best) return 'Нет подтвержденного RMSE';
  return `${humanModel(best.model_kind)} / ${humanHorizon(best.horizon)} • ${num(best.rmse, 3)}`;
});
const bestPinballLabel = computed(() => {
  const best = evaluationInsights.value?.best_pinball;
  if (!best) return 'Нет подтвержденного Pinball';
  return `${humanModel(best.model_kind)} / ${humanHorizon(best.horizon)} • ${num(best.pinball_avg, 3)}`;
});
const bestCalibrationLabel = computed(() => {
  const best = evaluationInsights.value?.best_interval_calibration;
  if (!best) return 'Нет данных';
  return `${humanModel(best.model_kind)} / ${humanHorizon(best.horizon)} • ACE80 ${percent(best.ace80)} • PICP80 ${percent(best.picp80)}`;
});
const avgPicpLabel = computed(() => {
  const rows = Array.isArray(evaluationChartData.value?.forecast_interval_calibration_by_model_horizon)
    ? evaluationChartData.value.forecast_interval_calibration_by_model_horizon
    : [];
  const values = rows.map((row) => Number(row?.picp80)).filter((value) => Number.isFinite(value));
  if (!values.length) return 'Нет данных';
  return percent(values.reduce((acc, value) => acc + value, 0) / values.length);
});
const avgDeltaLabel = computed(() => money(evaluationSummary.value?.delta_r?.delta_r_mean));
const deltaShareLabel = computed(() => percent(evaluationSummary.value?.delta_r?.share_positive));

const riskStateLabel = computed(() => {
  const state = selectedRiskResult.value?.projected_state || selectedRiskResult.value?.current_state || {};
  const pS0 = Number(state?.s0 ?? 0);
  const pS1 = Number(state?.s1 ?? 0);
  const pS2 = Number(state?.s2 ?? 0);
  if (pS2 >= pS1 && pS2 >= pS0) return 'S2 - Предаварийное';
  if (pS1 >= pS0) return 'S1 - Деградация';
  return 'S0 - Норма';
});

const recommendedLossLabel = computed(() => money(recommendedScore.value?.expected_loss));
const decisionRiskContextLabel = computed(() => {
  const risk = Number(latestDecision.value?.risk_snapshot?.overall_risk);
  if (!Number.isFinite(risk)) return 'нет risk_snapshot';
  return `${formatPercent(risk)} • S2 ${formatPercent(latestDecision.value?.risk_snapshot?.p_s2)}`;
});
const decisionReasonLabel = computed(() => {
  if (!recommendedScore.value) return 'итоговый score ещё не сформирован';
  if (recommendedScore.value?.explanation?.allowed === false) return 'вариант ограничен условиями';
  return latestDecision.value?.mode === 'advanced'
    ? 'минимальные потери с учётом Bayes + AHP'
    : 'минимальные ожидаемые потери по Bayes';
});

function unwrap(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function timestampValue(value) {
  const ts = Number(new Date(value).getTime());
  return Number.isFinite(ts) ? ts : 0;
}

function formatDateTime(value) {
  const ts = timestampValue(value);
  if (!ts) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(ts));
}

function formatTime(value) {
  const ts = timestampValue(value);
  if (!ts) return '—';
  return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(ts));
}

function relativeFreshness(value) {
  const diffMin = relativeFreshnessMinutes(value);
  if (diffMin === null) return 'нет данных';
  if (diffMin <= 1) return 'только что';
  if (diffMin < 60) return `${diffMin} мин назад`;
  const hours = Math.floor(diffMin / 60);
  const mins = diffMin % 60;
  if (hours < 24) return `${hours} ч ${mins} мин назад`;
  const days = Math.floor(hours / 24);
  return `${days} д ${hours % 24} ч назад`;
}

function relativeFreshnessMinutes(value) {
  const ts = timestampValue(value);
  if (!ts) return null;
  return Math.max(0, Math.round((Date.now() - ts) / 60000));
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total < 60) return `${total} сек`;
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes < 60) return `${minutes} мин ${secs} сек`;
  const hours = Math.floor(minutes / 60);
  return `${hours} ч ${minutes % 60} мин`;
}

function num(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function money(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`;
}

function percent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

function formatPercent(value) {
  return percent(value);
}

function humanHorizon(value) {
  if (value === '24h') return '24 часа';
  if (value === '7d') return '7 дней';
  if (value === '30d') return '30 дней';
  return value || '—';
}

function humanHorizonList(value) {
  const text = String(value || '').trim();
  if (!text) return 'горизонты не заданы';
  return text.split(',').map((item) => humanHorizon(item.trim())).join(', ');
}

function humanModel(value) {
  if (value === 'ensemble') return 'Оркестр';
  if (value === 'sarima') return 'SARIMA';
  if (value === 'lstm') return 'LSTM';
  return value || '—';
}

function modelKindLabel(value) {
  return humanModel(value);
}

function runStatusLabel(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'success' || value === 'completed') return 'Успех';
  if (value === 'failed') return 'Ошибка';
  if (value === 'running' || value === 'polling' || value === 'submitting' || value === 'submitted') return 'В работе';
  if (value === 'queued' || value === 'pending' || value === 'retry_wait') return 'В очереди';
  return 'Нет данных';
}

function runStatusSeverity(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'success' || value === 'completed') return 'success';
  if (value === 'failed') return 'danger';
  if (value === 'running' || value === 'polling' || value === 'submitting' || value === 'submitted') return 'warning';
  if (value === 'queued' || value === 'pending' || value === 'retry_wait') return 'info';
  return 'secondary';
}

function stateLabel(value) {
  if (value === 's0') return 'S0 - Норма';
  if (value === 's1') return 'S1 - Деградация';
  if (value === 's2') return 'S2 - Предаварийное';
  return 'Нет оценки';
}

function riskLabel(value) {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'Критический';
  if (raw >= 0.65) return 'Высокий';
  if (raw >= 0.40) return 'Средний';
  return 'Низкий';
}

function riskSeverity(value) {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'danger';
  if (raw >= 0.65) return 'warning';
  if (raw >= 0.40) return 'info';
  return 'success';
}

function decisionModeLabel(value) {
  return value === 'advanced' ? 'Bayes + AHP' : 'Bayes';
}

function toggleForecastHorizon(horizon) {
  const current = new Set(selectedForecastHorizons.value);
  if (current.has(horizon)) current.delete(horizon);
  else current.add(horizon);
  selectedForecastHorizons.value = horizonOptions
    .map((option) => option.value)
    .filter((value) => current.has(value));
}

function selectWorkflowStage(key) {
  selectedWorkflowStageKey.value = key;
  workflowStageTechExpanded.value = false;
}

function metricLabel(code) {
  const key = String(code || '').trim().toLowerCase();
  return metricMap[key]?.label || key || 'Метрика';
}

function metricUnit(code) {
  const key = String(code || '').trim().toLowerCase();
  return metricMap[key]?.unit || '';
}

function formatMetricValue(value, code) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const unit = metricUnit(code);
  const digits = unit === 'count' ? 2 : 1;
  return `${n.toFixed(digits)}${unit ? ` ${unit}` : ''}`;
}

function methodLabel(value) {
  const method = String(value || '').toLowerCase();
  if (method === 'weibull') return 'Вейбулл';
  if (method === 'exceedance') return 'Превышение порога';
  if (method === 'wear') return 'Износ';
  return value || '—';
}

function agentStatusLabel(value) {
  const status = String(value || '').toLowerCase();
  if (status === 'ok') return 'ok';
  if (status === 'warning') return 'warning';
  if (status === 'error') return 'error';
  return status || '—';
}

function displayInt(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 });
}

function nodeStateFromFreshness(value) {
  const minutes = relativeFreshnessMinutes(value);
  if (minutes === null) return 'idle';
  if (minutes <= 10) return 'ok';
  if (minutes <= 60) return 'warn';
  return 'danger';
}

function stateNodeState(value) {
  if (value === 's2') return 'danger';
  if (value === 's1') return 'warn';
  if (value === 's0') return 'ok';
  return 'idle';
}

function riskNodeState(value) {
  const raw = Number(value || 0);
  if (raw >= 0.85) return 'danger';
  if (raw >= 0.4) return 'warn';
  return 'ok';
}

function buildForecastRunRow(key, title, run, queueJob = null) {
  const queueStatus = key === 'lstm' ? normalizeLstmStatus(run, queueJob) : null;
  const effectiveStatus = key === 'lstm' && queueStatus ? queueStatus : run?.status;
  return {
    key,
    title,
    note: run ? `run #${run.id} • ${humanHorizonList(run.horizon_set)}${queueJob?.remote_job_id ? ` • remote_job_id=${queueJob.remote_job_id}` : ''}` : 'Запуск ещё не найден',
    statusLabel: runStatusLabel(effectiveStatus),
    severity: runStatusSeverity(effectiveStatus),
    at: run ? formatDateTime(run.updated_at || run.created_at) : '—',
  };
}

function normalizeLstmStatus(run, queueJob) {
  const queueStatus = String(queueJob?.status || '').toLowerCase();
  if (queueStatus === 'success') return 'completed';
  if (queueStatus === 'failed') return 'failed';
  if (queueStatus === 'queued' || queueStatus === 'retry_wait') return 'queued';
  if (queueStatus === 'submitting' || queueStatus === 'submitted' || queueStatus === 'polling') return 'running';

  const runStatus = String(run?.status || '').toLowerCase();
  if (runStatus === 'success') return 'completed';
  if (runStatus === 'failed') return 'failed';
  if (runStatus === 'running') return 'running';
  if (runStatus === 'pending') return 'queued';
  return 'none';
}

const MINI_CHART_INNER_LEFT = 10;
const MINI_CHART_INNER_RIGHT = 310;
const MINI_CHART_INNER_TOP = 12;
const MINI_CHART_INNER_BOTTOM = 94;

function downsampleRows(rows, maxPoints = 96) {
  if (!Array.isArray(rows) || rows.length <= maxPoints) return Array.isArray(rows) ? rows : [];
  const step = Math.ceil(rows.length / maxPoints);
  const sampled = [];
  for (let index = 0; index < rows.length; index += step) {
    sampled.push(rows[index]);
  }
  if (sampled[sampled.length - 1] !== rows[rows.length - 1]) {
    sampled.push(rows[rows.length - 1]);
  }
  return sampled.slice(-maxPoints);
}

function createPath(points, totalCount, minValue, maxValue) {
  if (!Array.isArray(points) || points.length < 2 || totalCount < 2) return '';
  const range = Math.max(1e-6, maxValue - minValue);
  return points.map((point, idx) => {
    const x = MINI_CHART_INNER_LEFT + ((point.index || 0) / (totalCount - 1)) * (MINI_CHART_INNER_RIGHT - MINI_CHART_INNER_LEFT);
    const y = MINI_CHART_INNER_BOTTOM - ((point.value - minValue) / range) * (MINI_CHART_INNER_BOTTOM - MINI_CHART_INNER_TOP);
    return `${idx === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
}

function createBandPath(points, totalCount, minValue, maxValue) {
  if (!Array.isArray(points) || points.length < 2 || totalCount < 2) return '';
  const range = Math.max(1e-6, maxValue - minValue);
  const lower = [];
  const upper = [];
  let firstPoint = null;
  points.forEach((point) => {
    if (!Number.isFinite(point.lower) || !Number.isFinite(point.upper)) return;
    const x = MINI_CHART_INNER_LEFT + ((point.index || 0) / (totalCount - 1)) * (MINI_CHART_INNER_RIGHT - MINI_CHART_INNER_LEFT);
    const yLower = MINI_CHART_INNER_BOTTOM - ((point.lower - minValue) / range) * (MINI_CHART_INNER_BOTTOM - MINI_CHART_INNER_TOP);
    const yUpper = MINI_CHART_INNER_BOTTOM - ((point.upper - minValue) / range) * (MINI_CHART_INNER_BOTTOM - MINI_CHART_INNER_TOP);
    if (!firstPoint) firstPoint = { x, y: yLower };
    lower.push(`L${x.toFixed(2)} ${yLower.toFixed(2)}`);
    upper.unshift(`L${x.toFixed(2)} ${yUpper.toFixed(2)}`);
  });
  if (!firstPoint || !lower.length || !upper.length) return '';
  return `M${firstPoint.x.toFixed(2)} ${firstPoint.y.toFixed(2)} ${lower.join(' ')} ${upper.join(' ')} Z`;
}

function buildMiniChartGeometry(historyRows, forecastRows) {
  const history = downsampleRows(historyRows, 72)
    .map((row, index) => ({ index, value: Number(row.value) }))
    .filter((row) => Number.isFinite(row.value));
  const forecastBase = downsampleRows(forecastRows, 120)
    .map((row) => ({
      y_hat: Number(row.y_hat),
      p10: Number(row.p10),
      p90: Number(row.p90),
    }))
    .filter((row) => Number.isFinite(row.y_hat));
  const forecast = forecastBase.map((row, index) => ({
    index: history.length ? history.length - 1 + index + 1 : index,
    value: row.y_hat,
    lower: Number.isFinite(row.p10) ? row.p10 : row.y_hat,
    upper: Number.isFinite(row.p90) ? row.p90 : row.y_hat,
  }));

  const allValues = [
    ...history.map((row) => row.value),
    ...forecast.map((row) => row.value),
    ...forecast.map((row) => row.lower),
    ...forecast.map((row) => row.upper),
  ].filter((value) => Number.isFinite(value));

  if (!allValues.length) {
    return { historyPath: '', forecastPath: '', bandPath: '' };
  }

  const totalCount = Math.max(2, history.length + Math.max(forecast.length, 1));
  let minValue = Math.min(...allValues);
  let maxValue = Math.max(...allValues);
  if (maxValue <= minValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const margin = Math.max(0.5, (maxValue - minValue) * 0.08);
  minValue -= margin;
  maxValue += margin;

  return {
    historyPath: createPath(history, totalCount, minValue, maxValue),
    forecastPath: createPath(forecast, totalCount, minValue, maxValue),
    bandPath: createBandPath(forecast, totalCount, minValue, maxValue),
  };
}

function historyWindowMinutes(horizon) {
  if (horizon === '24h') return 72 * 60;
  if (horizon === '7d') return 7 * 24 * 60;
  return 14 * 24 * 60;
}

async function loadMiniCharts() {
  miniCharts.value = [];
  loadingMiniCharts.value = false;
  if (!selectedDeviceId.value || !latestSuccessfulForecastRun.value?.id) return;

  loadingMiniCharts.value = true;
  try {
    const params = new URLSearchParams();
    params.set('run', String(latestSuccessfulForecastRun.value.id));
    params.set('horizon', selectedDecisionHorizon.value);
    params.set('ordering', 'target_ts');
    const forecastRes = await apiClient.get(`forecast-points/?${params.toString()}`);
    const forecastRows = unwrap(forecastRes.data)
      .map((row) => ({
        metric_code: row.metric_code,
        target_ts: row.target_ts,
        y_hat: Number(row.y_hat),
        p10: Number(row.p10),
        p90: Number(row.p90),
      }))
      .filter((row) => row.metric_code && Number.isFinite(timestampValue(row.target_ts)) && Number.isFinite(row.y_hat));
    if (!forecastRows.length) return;

    const groupedForecast = forecastRows.reduce((acc, row) => {
      const key = String(row.metric_code || '').trim();
      if (!key) return acc;
      if (!acc[key]) acc[key] = [];
      acc[key].push(row);
      return acc;
    }, {});

    const fallbackMetricCodes = Object.entries(groupedForecast)
      .sort((a, b) => b[1].length - a[1].length || String(a[0]).localeCompare(String(b[0]), 'ru'))
      .map(([metricCode]) => metricCode);
    const metricCodes = [...new Set([
      ...topRiskMetrics.value.map((row) => row.metric_code),
      ...fallbackMetricCodes,
    ])].slice(0, 3);
    const riskMetaMap = new Map(topRiskMetrics.value.map((row) => [row.metric_code, row]));

    const rawEntries = await Promise.all(metricCodes.map(async (metricCode) => {
      const rawParams = new URLSearchParams();
      rawParams.set('device', String(selectedDeviceId.value));
      rawParams.set('code', metricCode);
      rawParams.set('since_minutes', String(historyWindowMinutes(selectedDecisionHorizon.value)));
      rawParams.set('ordering', 'timestamp');
      rawParams.set('limit', '1600');
      try {
        const rawRes = await apiClient.get(`metrics-raw/?${rawParams.toString()}`);
        const rows = unwrap(rawRes.data)
          .map((row) => ({
            timestamp: row.timestamp,
            value: Number(row.value),
          }))
          .filter((row) => Number.isFinite(timestampValue(row.timestamp)) && Number.isFinite(row.value));
        return [metricCode, rows];
      } catch {
        return [metricCode, []];
      }
    }));

    const rawMap = Object.fromEntries(rawEntries);
    miniCharts.value = metricCodes.map((metricCode) => {
      const historyRows = rawMap[metricCode] || [];
      const metricForecastRows = groupedForecast[metricCode] || [];
      const geometry = buildMiniChartGeometry(historyRows, metricForecastRows);
      const riskMeta = riskMetaMap.get(metricCode);
      const lastForecast = metricForecastRows[metricForecastRows.length - 1] || null;
      const lastHistory = historyRows[historyRows.length - 1] || null;
      return {
        metric_code: metricCode,
        metric_label: metricLabel(metricCode),
        summary: `${humanModel(latestSuccessfulForecastRun.value.model_kind)} • ${metricUnit(metricCode) || 'без ед. изм.'}`,
        history_path: geometry.historyPath,
        forecast_path: geometry.forecastPath,
        band_path: geometry.bandPath,
        points_label: `История ${historyRows.length} • прогноз ${metricForecastRows.length}`,
        last_label: lastForecast
          ? `Финал ${formatMetricValue(lastForecast.y_hat, metricCode)}`
          : (lastHistory ? `Последний факт ${formatMetricValue(lastHistory.value, metricCode)}` : 'Нет последней точки'),
        risk_tag: riskMeta ? riskLabel(riskMeta.risk) : '',
        risk_severity: riskMeta ? riskSeverity(riskMeta.risk) : 'secondary',
      };
    }).filter((row) => row.history_path || row.forecast_path);
  } catch {
    miniCharts.value = [];
  } finally {
    loadingMiniCharts.value = false;
  }
}

function pushWorkflowFeed(text, tone = 'info') {
  workflowFeedCounter += 1;
  workflowFeed.value = [
    ...workflowFeed.value.slice(-7),
    { id: workflowFeedCounter, at: new Date().toISOString(), text, tone },
  ];
}

function resetWorkflowVisuals() {
  workflowStreamSnapshot.value = null;
  workflowStreamStatus.value = 'idle';
  workflowStartTs.value = null;
  workflowFinishTs.value = null;
  workflowFeed.value = [];
  workflowFeedCounter = 0;
  lastWorkflowMarker = '';
  selectedWorkflowStageKey.value = '';
  workflowStageTechExpanded.value = false;
  workflowFeedExpanded.value = false;
}

async function loadDevices() {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = unwrap(res.data);
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch {
    devices.value = [];
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить устройства', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
}

async function loadRawSnapshot() {
  latestRawMetric.value = null;
  latestAgentStatus.value = null;
  if (!selectedDeviceId.value) return;

  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('ordering', '-timestamp');
    params.set('limit', '1');
    const res = await apiClient.get(`metrics-raw/?${params.toString()}`);
    latestRawMetric.value = unwrap(res.data)[0] || null;
  } catch {
    latestRawMetric.value = null;
  }

  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('ordering', '-updated_at');
    const res = await apiClient.get(`agent-status/?${params.toString()}`);
    latestAgentStatus.value = unwrap(res.data)[0] || null;
  } catch {
    latestAgentStatus.value = null;
  }
}

async function loadLatestForecastRuns() {
  latestSarimaRun.value = null;
  latestLstmRun.value = null;
  latestEnsembleRun.value = null;
  latestLstmQueueJob.value = null;
  latestState.value = null;
  if (!selectedSerial.value) return;

  const serialParam = encodeURIComponent(selectedSerial.value);
  const [sarimaRes, lstmRes, ensembleRes] = await Promise.allSettled([
    apiClient.get(`forecast-runs/latest/?serial=${serialParam}&model_kind=sarima`),
    apiClient.get(`forecast-runs/latest/?serial=${serialParam}&model_kind=lstm`),
    apiClient.get(`forecast-runs/latest/?serial=${serialParam}&model_kind=ensemble`),
  ]);

  latestSarimaRun.value = sarimaRes.status === 'fulfilled' ? sarimaRes.value.data : null;
  latestLstmRun.value = lstmRes.status === 'fulfilled' ? lstmRes.value.data : null;
  latestEnsembleRun.value = ensembleRes.status === 'fulfilled' ? ensembleRes.value.data : null;

  try {
    const params = new URLSearchParams();
    if (latestLstmRun.value?.id) params.set('run_id', String(latestLstmRun.value.id));
    else params.set('serial', selectedSerial.value);
    const res = await apiClient.get(`forecast-queue-jobs/latest/?${params.toString()}`);
    latestLstmQueueJob.value = res.data;
  } catch {
    latestLstmQueueJob.value = null;
  }

  const candidates = [
    { kind: 'ensemble', run: latestEnsembleRun.value },
    { kind: 'lstm', run: latestLstmRun.value },
    { kind: 'sarima', run: latestSarimaRun.value },
  ]
    .filter((item) => item.run?.status === 'success' && item.run?.id)
    .sort((a, b) => timestampValue(b.run?.created_at) - timestampValue(a.run?.created_at));

  for (const candidate of candidates) {
    try {
      const url = `state-estimates/latest/?serial=${encodeURIComponent(selectedSerial.value)}&horizon=${encodeURIComponent(selectedDecisionHorizon.value)}&run=${encodeURIComponent(candidate.run.id)}&model_kind=${encodeURIComponent(candidate.kind)}`;
      const res = await apiClient.get(url);
      latestState.value = res.data;
      break;
    } catch {
      // continue
    }
  }
}

async function loadRiskSummary({ silent = true } = {}) {
  riskPayload.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.post('risk-assessment/evaluate/', {
      serial: selectedSerial.value,
      horizons: [selectedDecisionHorizon.value],
      preferred_model_kind: 'auto',
      personalized_thresholds: true,
      threshold_lookback_days: 60,
      markov_lookback_days: 120,
      markov_smoothing: 1.0,
      type_blend: 0.35,
      overall_weight_markov: 0.65,
      history_limit: 12,
    });
    riskPayload.value = res.data;
  } catch (e) {
    riskPayload.value = null;
    if (!silent) {
      const detail = e?.response?.data?.detail || 'Не удалось рассчитать риск на обзорной странице';
      toast.add({ severity: 'warn', summary: 'Риск не рассчитан', detail, life: 4200 });
    }
  }
}

async function loadLatestDecision() {
  latestDecision.value = null;
  if (!selectedDeviceId.value) return;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('horizon', selectedDecisionHorizon.value);
    params.set('mode', selectedDecisionMode.value);
    const res = await apiClient.get(`decision-runs/latest/?${params.toString()}`);
    latestDecision.value = res.data;
  } catch {
    latestDecision.value = null;
  }
}

async function loadLatestEvaluation() {
  latestEvaluation.value = null;
  latestEvaluationDetail.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.get(`dissertation-evaluation/latest/?serial=${encodeURIComponent(selectedSerial.value)}`);
    latestEvaluation.value = res.data;
  } catch {
    latestEvaluation.value = null;
    return;
  }

  if (!latestEvaluation.value?.run_id) return;
  try {
    const res = await apiClient.get(`dissertation-evaluation/detail/?run_id=${encodeURIComponent(latestEvaluation.value.run_id)}`);
    latestEvaluationDetail.value = res.data;
  } catch {
    latestEvaluationDetail.value = null;
  }
}

async function refreshAll({ withDevices = false } = {}) {
  loadingDashboard.value = true;
  try {
    if (withDevices) await loadDevices();
    if (!selectedDeviceId.value) {
      miniCharts.value = [];
      return;
    }
    await loadRawSnapshot();
    await loadLatestForecastRuns();
    await loadRiskSummary({ silent: true });
    await Promise.allSettled([
      loadLatestDecision(),
      loadLatestEvaluation(),
    ]);
    await loadMiniCharts();
  } finally {
    loadingDashboard.value = false;
  }
}

function stopWorkflowStream() {
  if (workflowStreamController) {
    workflowStreamController.abort();
    workflowStreamController = null;
  }
}

function createWorkflowMarker(event) {
  return [
    event?.status,
    event?.current_step?.key,
    event?.runs?.sarima?.status,
    event?.runs?.lstm?.status,
    event?.runs?.ensemble?.status,
    event?.queue_job?.status,
    event?.poll_error,
  ].join('|');
}

function resolveStepMeta(stepKey) {
  if (stepKey === 'sarima') {
    const run = latestSarimaRun.value || workflowStreamSnapshot.value?.runs?.sarima;
    return run?.id ? `run #${run.id} • ${humanHorizonList(run.horizon_set)}` : 'локальный baseline';
  }
  if (stepKey === 'lstm') {
    const run = latestLstmRun.value || workflowStreamSnapshot.value?.runs?.lstm;
    const queue = latestLstmQueueJob.value || workflowStreamSnapshot.value?.queue_job;
    if (queue?.remote_job_id) return `remote_job_id=${queue.remote_job_id}`;
    return run?.id ? `run #${run.id} • удалённый расчёт` : 'удалённый ПК';
  }
  if (stepKey === 'ensemble') {
    const run = latestEnsembleRun.value || workflowStreamSnapshot.value?.runs?.ensemble;
    return run?.id ? `run #${run.id} • итоговый прогноз` : 'ожидает интеграции';
  }
  if (stepKey === 'risk') {
    return selectedRiskResult.value ? formatPercent(selectedRiskResult.value.overall_risk) : 'ожидает расчёта';
  }
  if (stepKey === 'decision') {
    return latestDecision.value?.recommended_action_name || 'ожидает расчёта';
  }
  return '—';
}

async function handleWorkflowStreamEvent(event) {
  workflowStreamSnapshot.value = event;
  workflowStreamStatus.value = String(event?.status || workflowStreamStatus.value || 'running');

  const marker = createWorkflowMarker(event);
  if (marker && marker !== lastWorkflowMarker) {
    lastWorkflowMarker = marker;
    const stepKey = event?.current_step?.key;
    const stepTitle = event?.steps?.find?.((item) => item.key === stepKey)?.title || stepKey || 'этап';
    const baseMessage = `${stepTitle}: ${workflowStatusText(event)}`;
    pushWorkflowFeed(baseMessage, workflowTone(event));
    if (event?.poll_error) {
      pushWorkflowFeed(`Ошибка опроса backend: ${event.poll_error}`, 'danger');
    }
  }

  if (event?.event === 'done') {
    workflowFinishTs.value = new Date().toISOString();
    if (event.status === 'completed') {
      pushWorkflowFeed('Прогноз завершён, запускаю расчёт риска.', 'success');
      await loadRawSnapshot();
      await loadLatestForecastRuns();
      await loadRiskSummary({ silent: false });
      if (selectedRiskResult.value) {
        pushWorkflowFeed('Риск рассчитан, запускаю СППР.', 'success');
        await runDecisionRecommendation({ silent: false });
      }
      await loadLatestEvaluation();
      await loadMiniCharts();
      workflowStreamStatus.value = 'completed';
      pushWorkflowFeed('Полный цикл завершён.', 'success');
      toast.add({ severity: 'success', summary: 'Готово', detail: 'Прогноз, риск и СППР успешно обновлены', life: 3200 });
    } else if (event.status === 'failed') {
      workflowStreamStatus.value = 'failed';
      pushWorkflowFeed('Полный цикл завершился с ошибкой.', 'danger');
      toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Оркестр прогнозирования завершился с ошибкой', life: 4200 });
    }
    runningFullCycle.value = false;
  }

  if (event?.event === 'timeout') {
    workflowFinishTs.value = new Date().toISOString();
    workflowStreamStatus.value = 'timeout';
    runningFullCycle.value = false;
    pushWorkflowFeed('Realtime-стрим достиг лимита ожидания.', 'warning');
    toast.add({ severity: 'warn', summary: 'Таймаут', detail: 'Поток выполнения достиг лимита ожидания', life: 4200 });
  }
}

function workflowStatusText(event) {
  const status = String(event?.status || '').toLowerCase();
  if (status === 'completed') return 'этап завершён';
  if (status === 'failed') return 'этап завершился с ошибкой';
  if (status === 'running') return 'выполняется';
  if (status === 'queued') return 'ожидает выполнения';
  return 'состояние обновлено';
}

function workflowTone(event) {
  const status = String(event?.status || '').toLowerCase();
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'running') return 'info';
  if (status === 'queued') return 'warning';
  return 'info';
}

async function startWorkflowStream({ sarimaRunId = null, lstmRunId = null, ensembleRunId = null }) {
  stopWorkflowStream();
  workflowStreamStatus.value = 'running';
  workflowStartTs.value = new Date().toISOString();
  workflowFinishTs.value = null;

  const token = localStorage.getItem('auth_token');
  if (!token) {
    runningFullCycle.value = false;
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Нет токена авторизации для realtime-потока', life: 4200 });
    return;
  }

  const params = new URLSearchParams();
  params.set('mode', 'full');
  params.set('serial', selectedSerial.value);
  if (sarimaRunId) params.set('sarima_run_id', String(sarimaRunId));
  if (lstmRunId) params.set('lstm_run_id', String(lstmRunId));
  if (ensembleRunId) params.set('ensemble_run_id', String(ensembleRunId));
  params.set('poll_interval_sec', '2');
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

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
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
            // ignore malformed line
          }
        }
        idx = buffer.indexOf('\n');
      }
    }
  } catch (e) {
    if (e?.name !== 'AbortError') {
      runningFullCycle.value = false;
      workflowStreamStatus.value = 'failed';
      workflowFinishTs.value = new Date().toISOString();
      pushWorkflowFeed(e?.message || 'Ошибка realtime-потока', 'danger');
      toast.add({ severity: 'error', summary: 'Realtime stream', detail: e?.message || 'Ошибка потока', life: 4200 });
    }
  } finally {
    workflowStreamController = null;
  }
}

async function launchFullCycle() {
  if (!canRunCycle.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Выберите устройство и хотя бы один горизонт', life: 2500 });
    return;
  }

  runningFullCycle.value = true;
  resetWorkflowVisuals();
  pushWorkflowFeed('Запуск полного цикла подготовлен.', 'info');

  try {
    const payload = {
      serial: selectedSerial.value,
      sarima_lookback_days: 60,
      lstm_lookback_days: 60,
      sarima_freq: '1h',
      lstm_freq: '1h',
      horizons: selectedForecastHorizons.value.join(','),
      save_stl_components: true,
      sarima_seasonality_mode: 'stl_restore',
      wait_for_lstm: false,
      poll_interval_sec: 2,
      max_wait_sec: 120,
    };
    const res = await apiClient.post('forecast-runs/run_orchestrated/', payload);
    const paired = Array.isArray(res?.data?.paired_runs) ? res.data.paired_runs : [];
    const pair = paired[0] || null;
    const baselineRunIds = Array.isArray(res?.data?.baseline?.run_ids) ? res.data.baseline.run_ids : [];
    const lstmRunIds = Array.isArray(res?.data?.lstm?.run_ids) ? res.data.lstm.run_ids : [];
    const ensembleRunIds = Array.isArray(res?.data?.ensemble?.ensemble_run_ids) ? res.data.ensemble.ensemble_run_ids : [];

    const sarimaRunId = Number(pair?.sarima_run_id || baselineRunIds[0] || 0) || null;
    const lstmRunId = Number(pair?.lstm_run_id || lstmRunIds[0] || 0) || null;
    const ensembleRunId = Number(ensembleRunIds[0] || 0) || null;

    pushWorkflowFeed('Оркестр SARIMA + LSTM запущен.', 'success');
    await startWorkflowStream({ sarimaRunId, lstmRunId, ensembleRunId });
  } catch (e) {
    runningFullCycle.value = false;
    workflowStreamStatus.value = 'failed';
    workflowFinishTs.value = new Date().toISOString();
    const detail = e?.response?.data?.detail || 'Не удалось запустить полный цикл';
    pushWorkflowFeed(detail, 'danger');
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
}

async function runDecisionRecommendation({ silent = true } = {}) {
  latestDecision.value = null;
  if (!selectedDeviceId.value) return;
  try {
    const payload = {
      device: selectedDeviceId.value,
      horizon: selectedDecisionHorizon.value,
      overall_weight_markov: 0.65,
      risk_metric_min_risk: 0.08,
      risk_metric_min_contribution: 0.03,
      risk_metric_top_k_fallback: 3,
    };
    let endpoint = 'decision-runs/recommend/';
    if (selectedDecisionMode.value === 'advanced') {
      endpoint = 'decision-runs/recommend_advanced/';
      payload.bayes_weight = 0.5;
      payload.ahp_weight = 0.5;
      payload.sensitivity_weights = {};
    }
    const res = await apiClient.post(endpoint, payload);
    latestDecision.value = res.data;
    if (!silent) {
      toast.add({ severity: 'success', summary: 'СППР', detail: 'Рекомендация успешно рассчитана', life: 2600 });
    }
  } catch (e) {
    latestDecision.value = null;
    if (!silent) {
      const detail = e?.response?.data?.detail || 'СППР не смогла рассчитать рекомендацию';
      toast.add({ severity: 'warn', summary: 'СППР', detail, life: 4200 });
    }
  }
}

async function runAccuracyEvaluation() {
  if (!selectedSerial.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала выберите устройство', life: 2500 });
    return;
  }

  runningEvaluation.value = true;
  try {
    await apiClient.post('dissertation-evaluation/run/', {
      serial: selectedSerial.value,
      days_back: 120,
      horizons: selectedForecastHorizons.value.join(','),
      model_kinds: 'sarima,lstm,ensemble',
      baseline_action_code: 'no_action',
      strict_intersection: true,
      enable_stat_tests: true,
      bootstrap_samples: 300,
      bootstrap_block_size: 0,
      tag: 'pipeline_overview',
    });
    await loadLatestEvaluation();
    toast.add({ severity: 'success', summary: 'Оценка прогноза', detail: 'Верификация обновлена', life: 2800 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить верификацию прогноза';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningEvaluation.value = false;
  }
}

async function downloadPipelineReport() {
  if (!selectedSerial.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала выберите устройство', life: 2500 });
    return;
  }

  downloadingPipelineReport.value = true;
  try {
    const res = await apiClient.get('monitoring-system/pipeline-report/', {
      params: {
        serial: selectedSerial.value,
        horizon: selectedDecisionHorizon.value,
        decision_mode: selectedDecisionMode.value,
        forecast_horizons: selectedForecastHorizons.value.join(','),
      },
      responseType: 'blob',
    });
    const blob = new Blob([res.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pipeline_summary_${selectedSerial.value}_${selectedDecisionHorizon.value}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сформировать PDF-отчёт полного цикла';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    downloadingPipelineReport.value = false;
  }
}

watch([selectedDeviceId, selectedDecisionHorizon, selectedDecisionMode], async () => {
  if (!bootstrapped) return;
  await refreshAll();
});

watch(defaultWorkflowStageKey, (value) => {
  if (!value) return;
  if (!selectedWorkflowStageKey.value || !workflowStageDetails.value[selectedWorkflowStageKey.value]) {
    selectedWorkflowStageKey.value = value;
    workflowStageTechExpanded.value = false;
  }
}, { immediate: true });

onMounted(async () => {
  await loadDevices();
  bootstrapped = true;
  await refreshAll();
});

onBeforeUnmount(() => {
  stopWorkflowStream();
});
</script>

<style scoped>
.pipeline-page {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem 1rem;
}

.field-block,
.field-block--wide {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field-block label,
.field-block--wide label {
  font-size: 0.82rem;
  font-weight: 600;
  color: #64748b;
}

.field-block--wide {
  grid-column: span 2;
}

.launch-grid {
  align-items: end;
}

.forecast-pill-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.forecast-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.7rem 1rem;
  border: 1px solid #dbe5ef;
  border-radius: 999px;
  background: #f8fafc;
  color: #334155;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.forecast-pill:hover {
  border-color: #93c5fd;
  background: #f0f9ff;
}

.forecast-pill--active {
  background: #ecfdf5;
  border-color: rgba(16, 185, 129, 0.35);
  color: #065f46;
  box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.08);
}

.launch-summary-card {
  border: 1px solid #dbe5ef;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(248, 250, 252, 0.96) 0%, rgba(255, 255, 255, 0.98) 100%);
  padding: 0.95rem 1rem;
}

.launch-summary-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.launch-summary-card__main {
  margin-top: 0.65rem;
  color: #0f172a;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.45;
}

.launch-summary-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  margin-top: 0.55rem;
  color: #64748b;
  font-size: 0.84rem;
}

.launch-actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.9rem;
}

.launch-actions-row__primary {
  min-width: 15rem;
}

.launch-actions-row__secondary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
}

.launch-profile-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.launch-profile-row__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.launch-profile-row__label {
  color: #0f172a;
  font-weight: 600;
}

.launch-profile-row__details {
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.5;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 1rem;
}

.hero-card {
  min-width: 0;
  border: 1px solid #dbe5ef;
  overflow: hidden;
}

.hero-card--workflow {
  background: linear-gradient(135deg, rgba(236, 254, 255, 0.96) 0%, rgba(255, 255, 255, 0.96) 55%, rgba(240, 253, 244, 0.96) 100%);
}

.hero-card--summary {
  background: linear-gradient(145deg, rgba(248, 250, 252, 0.98) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.hero-card__head,
.table-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.8rem;
}

.hero-card__subtitle {
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.9rem;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.workflow-timeline {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.6rem;
  align-items: center;
}

.workflow-node {
  min-width: 0;
  appearance: none;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 0.9rem;
  border-radius: 16px;
  border: 1px solid #dbe5ef;
  background: rgba(255, 255, 255, 0.88);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease, background-color 0.18s ease;
}

.workflow-node:hover {
  border-color: #93c5fd;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.workflow-node--done {
  border-color: rgba(16, 185, 129, 0.28);
  background: rgba(236, 253, 245, 0.86);
}

.workflow-node--current {
  border-color: rgba(245, 158, 11, 0.3);
  background: rgba(255, 251, 235, 0.9);
}

.workflow-node--failed {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(254, 242, 242, 0.9);
}

.workflow-node--active {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.16), 0 12px 28px rgba(15, 23, 42, 0.08);
}

.workflow-node__index {
  width: 2rem;
  height: 2rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: #0f172a;
  color: #fff;
  font-weight: 700;
  font-size: 0.9rem;
  flex: 0 0 auto;
}

.workflow-node--done .workflow-node__index {
  background: #059669;
}

.workflow-node--current .workflow-node__index {
  background: #d97706;
}

.workflow-node--failed .workflow-node__index {
  background: #dc2626;
}

.workflow-node__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.14rem;
}

.workflow-node__body strong {
  color: #0f172a;
  font-size: 1rem;
  line-height: 1.2;
}

.workflow-node__body span {
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.45;
}

.workflow-node__connector {
  display: grid;
  place-items: center;
  min-width: 1.4rem;
  color: #94a3b8;
}

.workflow-focus-card {
  border: 1px solid #dbe5ef;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.9);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.workflow-focus-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.7rem;
}

.workflow-focus-card__eyebrow,
.decision-hero-card__eyebrow {
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.workflow-focus-card__summary {
  color: #0f172a;
  font-size: 0.98rem;
  line-height: 1.55;
}

.workflow-focus-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  color: #475569;
  font-size: 0.86rem;
}

.workflow-focus-card__actions {
  display: flex;
  justify-content: flex-start;
}

.workflow-tech-box {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  padding: 0.75rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.workflow-tech-box__line {
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  word-break: break-word;
}

.workflow-kpi-grid,
.accuracy-kpi-grid,
.overview-grid,
.state-compact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

.mini-kpi,
.overview-card,
.state-compact-card {
  min-width: 0;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.mini-kpi span,
.overview-card span,
.state-compact-card span {
  color: #64748b;
  font-size: 0.8rem;
}

.mini-kpi strong,
.overview-card strong,
.state-compact-card strong {
  color: #0f172a;
  font-size: 1rem;
}

.overview-card__head,
.accuracy-summary__head,
.risk-summary__hero,
.decision-summary__hero,
.model-run-row,
.metric-risk-row,
.workflow-feed__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
}

.overview-card {
  gap: 0.45rem;
}

.overview-card__head span {
  font-size: 0.82rem;
  font-weight: 600;
}

.overview-card > span {
  line-height: 1.45;
}

.decision-hero-card {
  border: 1px solid #dbe5ef;
  border-radius: 20px;
  background: linear-gradient(145deg, rgba(239, 246, 255, 0.88) 0%, rgba(255, 255, 255, 0.94) 52%, rgba(236, 253, 245, 0.88) 100%);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.decision-hero-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.decision-hero-card__head strong {
  color: #0f172a;
  font-size: 1.28rem;
  line-height: 1.25;
}

.decision-hero-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.decision-hero-card__sentence {
  color: #1e293b;
  font-size: 0.98rem;
  line-height: 1.6;
}

.summary-chain {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.summary-chain__item {
  position: relative;
  min-width: 0;
  border: 1px solid #dbe5ef;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  padding: 0.85rem 0.95rem;
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
}

.summary-chain__label {
  color: #64748b;
  font-size: 0.8rem;
  font-weight: 700;
}

.summary-chain__item strong {
  color: #0f172a;
  font-size: 1rem;
  line-height: 1.35;
}

.summary-chain__item small {
  color: #64748b;
  line-height: 1.45;
}

.summary-chain__arrow {
  position: absolute;
  right: -0.68rem;
  top: calc(50% - 0.55rem);
  width: 1.35rem;
  height: 1.35rem;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #dbe5ef;
  color: #94a3b8;
}

.workflow-feed {
  border: 1px solid #dbe5ef;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.75);
  padding: 0.85rem;
}

.workflow-feed__head span {
  color: #64748b;
  font-size: 0.8rem;
}

.workflow-feed__head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.7rem;
}

.workflow-feed__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.workflow-feed__item {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 0.75rem;
  align-items: start;
  padding: 0.55rem 0.6rem;
  border-radius: 10px;
  background: #f8fafc;
}

.workflow-feed__item--success {
  background: #ecfdf5;
}

.workflow-feed__item--danger {
  background: #fef2f2;
}

.workflow-feed__item--warning {
  background: #fffbeb;
}

.workflow-feed__time {
  color: #64748b;
  font-size: 0.78rem;
}

.workflow-feed__text,
.workflow-feed__empty,
.feedback-loop__body,
.text-note-box {
  color: #334155;
  line-height: 1.55;
}

.mini-chart-panel {
  border: 1px solid #dbe5ef;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.98) 100%);
}

.mini-chart-panel__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.mini-chart-panel__loading {
  color: #64748b;
  font-size: 0.92rem;
}

.mini-chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 0.9rem;
}

.mini-trend-card {
  min-width: 0;
  border: 1px solid #dbe5ef;
  border-radius: 16px;
  padding: 0.9rem;
  background: rgba(255, 255, 255, 0.92);
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.mini-trend-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.65rem;
}

.mini-trend-card__title-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.mini-trend-card__title-wrap strong {
  color: #0f172a;
}

.mini-trend-card__title-wrap span,
.mini-trend-card__legend,
.mini-trend-card__footer {
  color: #64748b;
  font-size: 0.8rem;
}

.mini-trend-card__svg {
  width: 100%;
  height: 7.2rem;
  display: block;
  border-radius: 12px;
  background:
    linear-gradient(to right, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(to top, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    #f8fafc;
  background-size: 20% 100%, 100% 25%, auto;
}

.mini-trend-card__axis {
  fill: none;
  stroke: rgba(148, 163, 184, 0.8);
  stroke-width: 1.1;
}

.mini-trend-card__band {
  fill: rgba(251, 191, 36, 0.18);
  stroke: none;
}

.mini-trend-card__history {
  fill: none;
  stroke: #0ea5e9;
  stroke-width: 2.1;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.mini-trend-card__forecast {
  fill: none;
  stroke: #f97316;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.mini-trend-card__legend,
.mini-trend-card__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem 0.9rem;
}

.mini-dot {
  display: inline-block;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  margin-right: 0.35rem;
  vertical-align: middle;
}

.mini-dot--history {
  background: #0ea5e9;
}

.mini-dot--forecast {
  background: #f97316;
}

.mini-dot--band {
  background: rgba(251, 191, 36, 0.5);
}

.scheme-card {
  border: 1px solid #dbe5ef;
}

.pipeline-scheme {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0.8rem;
}

.scheme-node {
  flex: 1 1 180px;
  min-width: 180px;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.8rem;
  align-items: flex-start;
  padding: 0.95rem;
  border-radius: 16px;
  border: 1px solid #dbe5ef;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.scheme-node--ok {
  border-color: rgba(16, 185, 129, 0.32);
}

.scheme-node--running {
  border-color: rgba(59, 130, 246, 0.34);
  background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
}

.scheme-node--warn {
  border-color: rgba(245, 158, 11, 0.36);
}

.scheme-node--danger {
  border-color: rgba(239, 68, 68, 0.36);
}

.scheme-node--idle {
  border-color: #dbe5ef;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.scheme-node__icon {
  width: 2.4rem;
  height: 2.4rem;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: #0f172a;
  color: #fff;
  font-size: 1rem;
}

.scheme-node__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.scheme-node__title {
  color: #64748b;
  font-size: 0.8rem;
  font-weight: 600;
}

.scheme-node__body strong {
  color: #0f172a;
  line-height: 1.3;
}

.scheme-node__body small {
  color: #64748b;
  line-height: 1.45;
}

.scheme-arrow {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  color: #94a3b8;
  font-size: 1.1rem;
}

.feedback-loop {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  padding: 0.85rem 0.95rem;
  background: #f8fafc;
}

.feedback-loop__title {
  margin-bottom: 0.35rem;
  color: #0f172a;
  font-weight: 700;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.detail-card {
  min-width: 0;
  border: 1px solid #dbe5ef;
}

.model-run-list,
.metric-risk-list {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.model-run-row,
.metric-risk-row {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
  background: #fbfdff;
}

.model-run-row__meta,
.metric-risk-row__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
  color: #64748b;
  font-size: 0.82rem;
}

.state-compact-card--accent {
  background: linear-gradient(145deg, #f0fdfa 0%, #ffffff 100%);
  border-color: rgba(20, 184, 166, 0.28);
}

.accuracy-summary,
.risk-summary,
.decision-summary {
  min-width: 0;
}

.text-note-box {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fbfdff;
  padding: 0.8rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.decision-active-metrics {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  color: #334155;
}

.decision-chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

@media (max-width: 1200px) {
  .hero-grid,
  .details-grid {
    grid-template-columns: 1fr;
  }

  .workflow-timeline {
    grid-template-columns: 1fr;
  }

  .workflow-node__connector,
  .summary-chain__arrow {
    display: none;
  }

  .summary-chain {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .field-block--wide {
    grid-column: span 1;
  }

  .launch-actions-row {
    flex-direction: column;
    align-items: stretch;
  }

  .launch-actions-row__primary,
  .launch-actions-row__secondary {
    width: 100%;
  }

  .launch-actions-row__secondary {
    justify-content: stretch;
  }

  .decision-hero-card__head,
  .workflow-focus-card__head {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 720px) {
  .workflow-feed__item {
    grid-template-columns: 1fr;
  }

  .scheme-arrow {
    display: none;
  }

  .mini-trend-card__svg {
    height: 6.4rem;
  }

  .workflow-kpi-grid,
  .accuracy-kpi-grid,
  .overview-grid,
  .state-compact-grid {
    grid-template-columns: 1fr;
  }

  .workflow-node {
    padding: 0.8rem;
  }
}
</style>
