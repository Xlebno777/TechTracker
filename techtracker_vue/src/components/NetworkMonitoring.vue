<template>
  <div class="network-monitoring p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Сетевой мониторинг</h2>
        <p class="text-500 m-0">Пути, матрица доступности и инциденты</p>
      </div>
      <div class="flex align-items-center gap-2">
        <Button icon="pi pi-refresh" label="Обновить" text @click="refreshActiveTab" />
      </div>
    </div>

    <div class="tab-switch mb-3">
      <Button :outlined="activeTab !== 'paths'" label="Пути" @click="activeTab = 'paths'" />
      <Button :outlined="activeTab !== 'automap'" label="Автокарта" @click="activeTab = 'automap'" />
      <Button :outlined="activeTab !== 'matrix'" label="Матрица" @click="activeTab = 'matrix'" />
      <Button :outlined="activeTab !== 'scan'" label="Сканирование" @click="activeTab = 'scan'" />
      <Button :outlined="activeTab !== 'incidents'" label="Инциденты" @click="activeTab = 'incidents'" />
      <Button :outlined="activeTab !== 'derived_alerts'" label="Метрики и тревоги" @click="activeTab = 'derived_alerts'" />
    </div>

    <div v-if="activeTab === 'paths'">
      <div class="card p-3 mb-3">
        <div class="grid">
          <div class="col-12 md:col-4">
            <label class="block mb-2">Поиск</label>
            <InputText v-model="pathFilter.search" placeholder="Источник / назначение" class="w-full" />
          </div>
          <div class="col-12 md:col-3">
            <label class="block mb-2">Состояние</label>
            <Dropdown v-model="pathFilter.state" :options="stateOptions" optionLabel="label" optionValue="value" showClear class="w-full" />
          </div>
          <div class="col-12 md:col-3">
            <label class="block mb-2">Включен</label>
            <Dropdown v-model="pathFilter.enabled" :options="enabledOptions" optionLabel="label" optionValue="value" showClear class="w-full" />
          </div>
          <div class="col-12 md:col-2 flex align-items-end">
            <Button label="Создать путь" icon="pi pi-plus" class="w-full" @click="openCreatePath" />
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <h4 class="m-0 mb-2">Мастер создания путей</h4>
        <div class="path-master-grid">
          <div class="path-master-item item-template">
            <label class="block mb-2">Шаблон</label>
            <Dropdown v-model="templateForm.template" :options="templateOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
          <div class="path-master-item item-interval">
            <label class="block mb-2">Интервал</label>
            <InputNumber v-model="templateForm.defaults.interval_sec" :min="5" :max="3600" suffix=" c" class="w-full" />
          </div>
          <div class="path-master-item item-timeout">
            <label class="block mb-2">Timeout</label>
            <InputNumber v-model="templateForm.defaults.timeout_sec" :min="1" :max="120" suffix=" c" class="w-full" />
          </div>
          <div class="path-master-item item-fail-recover">
            <label class="block mb-2">Fail/Recover</label>
            <div class="fail-recover-grid">
              <InputNumber v-model="templateForm.defaults.fail_threshold" :min="1" :max="20" class="w-full" />
              <InputNumber v-model="templateForm.defaults.recover_threshold" :min="1" :max="20" class="w-full" />
            </div>
          </div>
          <div class="path-master-item item-generate">
            <Button label="Сгенерировать" icon="pi pi-sparkles" class="w-full" @click="runTemplate" />
          </div>
        </div>
        <div v-if="templateForm.template === 'custom'" class="path-master-grid custom-devices-grid mt-2">
          <div class="path-master-item">
            <label class="block mb-2">Источники</label>
            <MultiSelect
              v-model="templateForm.src_device_ids"
              :options="deviceOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full"
              filter
              display="chip"
            />
          </div>
          <div class="path-master-item">
            <label class="block mb-2">Назначения (с IP)</label>
            <MultiSelect
              v-model="templateForm.dst_device_ids"
              :options="deviceOptionsWithIp"
              optionLabel="label"
              optionValue="value"
              class="w-full"
              filter
              display="chip"
            />
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="bulk-toolbar">
          <div class="bulk-group bulk-group-actions">
            <span class="text-600 font-medium">Массовые действия ({{ selectedPaths.length }})</span>
            <Button label="Вкл" size="small" @click="bulkEnable(true)" :disabled="!selectedPaths.length" />
            <Button label="Выкл" size="small" severity="secondary" @click="bulkEnable(false)" :disabled="!selectedPaths.length" />
          </div>
          <div class="bulk-group bulk-interval-group">
            <InputNumber v-model="bulkInterval" :min="5" :max="3600" suffix=" c" class="bulk-input" />
            <Button
              label="Применить интервал"
              size="small"
              severity="secondary"
              class="bulk-interval-btn"
              @click="bulkSetInterval"
              :disabled="!selectedPaths.length"
            />
          </div>
          <div class="bulk-group bulk-group-probe">
            <Button label="Проверить выбранные" size="small" severity="help" @click="probeSelected" :disabled="!selectedPaths.length" />
            <Button label="Проверить все" size="small" severity="help" outlined @click="probeAll" />
          </div>
        </div>
      </div>

      <DataTable
        :value="filteredPaths"
        v-model:selection="selectedPaths"
        dataKey="id"
        :loading="loadingPaths"
        class="table-compact"
        paginator
        :rows="15"
        stripedRows
        responsiveLayout="scroll"
      >
        <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>
        <Column field="src_device_name" header="Источник" sortable />
        <Column field="dst_device_name" header="Назначение" sortable />
        <Column field="dst_ip" header="IP назначения" />
        <Column field="last_state" header="Состояние" sortable>
          <template #body="{ data }">
            <Tag :value="stateLabel(data.last_state)" :severity="stateSeverity(data.last_state)" />
          </template>
        </Column>
        <Column header="Эффективность">
          <template #body="{ data }">
            <div class="eff-cell">
              <div>24ч: {{ formatPercent(data.uptime_24h_pct) }}</div>
              <div>7д: {{ formatPercent(data.uptime_7d_pct) }}</div>
            </div>
          </template>
        </Column>
        <Column header="Инциденты">
          <template #body="{ data }">
            <div class="eff-cell">
              <div>24ч: {{ data.outage_count_24h ?? 0 }}</div>
              <div>7д: {{ data.outage_count_7d ?? 0 }}</div>
            </div>
          </template>
        </Column>
        <Column field="last_latency_ms" header="RTT (ms)">
          <template #body="{ data }">{{ formatNum(data.last_latency_ms, 1) }}</template>
        </Column>
        <Column field="last_packet_loss_pct" header="Loss (%)">
          <template #body="{ data }">{{ formatNum(data.last_packet_loss_pct, 1) }}</template>
        </Column>
        <Column header="Последний outage (сек)">
          <template #body="{ data }">{{ data.last_outage_duration_sec ?? '—' }}</template>
        </Column>
        <Column header="Действия" style="width: 11rem">
          <template #body="{ data }">
            <div class="flex gap-1">
              <Button icon="pi pi-pencil" text rounded @click="openEditPath(data)" />
              <Button icon="pi pi-play" text rounded severity="help" @click="probePath(data.id)" />
              <Button icon="pi pi-trash" text rounded severity="danger" @click="removePath(data)" />
            </div>
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="activeTab === 'automap'">
      <div class="card p-3 mb-3">
        <div class="grid">
          <div class="col-12 md:col-4">
            <label class="block mb-2">Поиск</label>
            <InputText
              v-model="mapFilter.search"
              placeholder="Имя узла / IP / serial / путь"
              class="w-full"
            />
          </div>
          <div class="col-12 md:col-2">
            <label class="block mb-2">Состояние ребра</label>
            <Dropdown
              v-model="mapFilter.state"
              :options="mapStateOptions"
              optionLabel="label"
              optionValue="value"
              showClear
              class="w-full"
            />
          </div>
          <div class="col-12 md:col-2">
            <label class="block mb-2">Окно для rebuild</label>
            <Dropdown
              v-model="mapWindowHours"
              :options="mapWindowOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full"
            />
          </div>
          <div class="col-12 md:col-2 flex align-items-end">
            <div class="flex align-items-center gap-2">
              <InputSwitch v-model="mapFilter.includeDisabled" />
              <span class="text-600">Показывать выключенные</span>
            </div>
          </div>
          <div class="col-12 md:col-2 flex align-items-end">
            <Button
              label="Пересобрать карту"
              icon="pi pi-cog"
              class="w-full"
              :loading="loadingMap"
              @click="rebuildNetworkMap"
            />
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="map-summary-row">
          <div class="map-summary-item">
            <div class="summary-label">Снимок</div>
            <div class="summary-value">#{{ mapSnapshot?.id || '—' }}</div>
          </div>
          <div class="map-summary-item">
            <div class="summary-label">Узлы</div>
            <div class="summary-value">{{ mapSnapshot?.node_count ?? 0 }}</div>
          </div>
          <div class="map-summary-item">
            <div class="summary-label">Ребра</div>
            <div class="summary-value">{{ mapSnapshot?.edge_count ?? 0 }}</div>
          </div>
          <div class="map-summary-item">
            <div class="summary-label">Статус сборки</div>
            <Tag :value="(mapSnapshot?.status || 'unknown').toUpperCase()" :severity="mapStatusSeverity(mapSnapshot?.status)" />
          </div>
          <div class="map-summary-item">
            <div class="summary-label">Обновлено</div>
            <div class="summary-value">{{ fmtTime(mapSnapshot?.generated_at) }}</div>
          </div>
          <div class="map-summary-item">
            <div class="summary-label">Сборка (ms)</div>
            <div class="summary-value">{{ mapSnapshot?.build_duration_ms ?? '—' }}</div>
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="map-canvas-wrap">
          <svg viewBox="0 0 1200 700" class="map-canvas" preserveAspectRatio="xMidYMid meet">
            <g v-for="edge in mapGraph.edges" :key="edge.id">
              <line
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                :stroke="mapEdgeColor(edge.state)"
                :stroke-opacity="mapEdgeOpacity(edge)"
                :stroke-width="mapEdgeWidth(edge)"
                stroke-linecap="round"
                @mouseenter="onMapEdgeMouseEnter(edge, $event)"
                @mousemove="onMapEdgeMouseMove(edge, $event)"
                @mouseleave="onMapEdgeMouseLeave"
              />
            </g>
            <g v-for="node in mapGraph.nodes" :key="node.id">
              <circle
                :cx="node.x"
                :cy="node.y"
                :r="mapNodeRadius(node)"
                :fill="mapNodeFill(node)"
                :stroke="mapNodeStroke(node)"
                :stroke-width="mapNodeStrokeWidth(node)"
                :opacity="mapNodeOpacity(node)"
                class="map-node-circle"
                @mouseenter="onMapNodeMouseEnter(node, $event)"
                @mousemove="onMapNodeMouseMove(node, $event)"
                @mouseleave="onMapNodeMouseLeave"
                @click="onMapNodeClick(node)"
              />
              <text
                :x="node.x"
                :y="node.y + 4"
                text-anchor="middle"
                class="map-node-short"
                :opacity="mapNodeOpacity(node)"
              >
                {{ node.shortName }}
              </text>
              <text
                :x="node.x"
                :y="node.y + 34"
                text-anchor="middle"
                class="map-node-label"
                :opacity="mapNodeOpacity(node)"
              >
                {{ node.label }}
              </text>
            </g>
          </svg>
          <div
            v-if="mapTooltip.visible"
            class="map-tooltip"
            :style="{ left: `${mapTooltip.x}px`, top: `${mapTooltip.y}px` }"
          >
            <div class="map-tooltip-title">{{ mapTooltip.title }}</div>
            <div v-for="(line, idx) in mapTooltip.lines" :key="idx" class="map-tooltip-line">{{ line }}</div>
          </div>
        </div>
      </div>

      <div class="card p-3">
        <h4 class="m-0 mb-2">Ребра автокарты</h4>
        <DataTable
          :value="filteredMapEdges"
          :loading="loadingMap"
          class="table-compact"
          paginator
          :rows="15"
          stripedRows
          responsiveLayout="scroll"
        >
          <Column field="src_name" header="Источник" />
          <Column field="dst_name" header="Назначение" />
          <Column field="dst_ip" header="IP">
            <template #body="{ data }">{{ data.dst_ip || '—' }}</template>
          </Column>
          <Column field="state" header="Состояние">
            <template #body="{ data }">
              <Tag :value="stateLabel(data.state)" :severity="stateSeverity(data.state)" />
            </template>
          </Column>
          <Column field="enabled" header="Вкл">
            <template #body="{ data }">
              <Tag :value="data.enabled ? 'Да' : 'Нет'" :severity="data.enabled ? 'success' : 'secondary'" />
            </template>
          </Column>
          <Column field="confidence_pct" header="Confidence %">
            <template #body="{ data }">{{ formatNum(data.confidence_pct, 1) }}</template>
          </Column>
          <Column field="latency_ms" header="RTT (ms)">
            <template #body="{ data }">{{ formatNum(data.latency_ms, 1) }}</template>
          </Column>
          <Column field="packet_loss_pct" header="Loss %">
            <template #body="{ data }">{{ formatNum(data.packet_loss_pct, 1) }}</template>
          </Column>
          <Column field="outage_count_24h" header="Outage 24ч" />
        </DataTable>
      </div>
    </div>

    <div v-if="activeTab === 'matrix'" class="card p-3">
      <div class="flex justify-content-between align-items-center mb-2">
        <h4 class="m-0">PING-матрица</h4>
        <div class="flex align-items-center gap-2">
          <label class="text-600">Показывать выключенные пути</label>
          <InputSwitch v-model="matrixIncludeDisabled" @change="loadMatrix" />
        </div>
      </div>
      <div class="matrix-wrap">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Источник \ Назначение</th>
              <th v-for="dst in matrix.destinations" :key="dst.id">{{ dst.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrix.rows" :key="row.src_device_id">
              <td class="src-cell">{{ row.src_device_name }}</td>
              <td
                v-for="cell in row.cells"
                :key="`${row.src_device_id}-${cell.dst_device_id}`"
                :class="['matrix-cell', matrixCellClass(cell)]"
                @click="openCellHistory(cell)"
              >
                <div v-if="cell.path_id">
                  <div class="cell-main">{{ stateLabel(cell.state) }}</div>
                  <div class="cell-sub">{{ formatNum(cell.latency_ms, 1) }} ms</div>
                  <div class="cell-sub">{{ formatPercent(cell.uptime_24h_pct) }}</div>
                </div>
                <div v-else>—</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="activeTab === 'scan'">
      <div class="card p-3 mb-3">
        <div class="grid">
          <div class="col-12 md:col-4">
            <label class="block mb-2">Подсеть (CIDR)</label>
            <Dropdown
              v-model="scanCidr"
              :options="scanSuggestions"
              optionLabel="label"
              optionValue="value"
              editable
              placeholder="Например: 10.250.0.0/24"
              class="w-full"
            />
          </div>
          <div class="col-12 md:col-2">
            <label class="block mb-2">Timeout ping</label>
            <InputNumber v-model="scanTimeoutMs" :min="100" :max="5000" suffix=" ms" class="w-full" />
          </div>
          <div class="col-12 md:col-6 flex align-items-end gap-2">
            <Button label="Сканировать" icon="pi pi-search" @click="runNetworkScan" :loading="scanLoading" />
            <Button label="Сети хоста" icon="pi pi-sync" text @click="loadScanSuggestions" :loading="scanSuggestionsLoading" />
            <Button
              label="Добавить выбранные в базу"
              icon="pi pi-plus"
              severity="success"
              @click="importScannedDevices"
              :disabled="!selectedScanned.length"
            />
            <div class="flex align-items-center gap-2 ml-auto">
              <InputSwitch v-model="showOnlyNewScanned" />
              <span class="text-600 text-sm">Только новые (не в БД)</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="flex flex-wrap gap-3 text-600">
          <span>Подсеть: <b>{{ scanStats.cidr || '—' }}</b></span>
          <span>Хостов проверено: <b>{{ scanStats.host_count || 0 }}</b></span>
          <span>Доступно: <b>{{ scanStats.alive_count || 0 }}</b></span>
          <span>IP обновлено по MAC: <b>{{ scanStats.ip_updated_count || 0 }}</b></span>
          <span>Выбрано: <b>{{ selectedScanned.length }}</b></span>
        </div>
      </div>

      <DataTable
        :value="filteredScannedDevices"
        v-model:selection="selectedScanned"
        dataKey="ip_address"
        :loading="scanLoading"
        paginator
        :rows="15"
        stripedRows
        responsiveLayout="scroll"
      >
        <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>
        <Column field="name" header="Название" />
        <Column field="ip_address" header="IP" />
        <Column field="mac_address" header="MAC">
          <template #body="{ data }">{{ data.mac_address || '—' }}</template>
        </Column>
        <Column field="serial_number" header="Серийный">
          <template #body="{ data }">{{ data.serial_number || '—' }}</template>
        </Column>
        <Column field="latency_ms" header="RTT (ms)">
          <template #body="{ data }">{{ data.latency_ms ?? '—' }}</template>
        </Column>
        <Column header="В БД">
          <template #body="{ data }">
            <Tag
              :value="data.existing_device_id ? `Да (${data.existing_device_name || data.existing_serial_number || data.existing_device_id})` : 'Нет'"
              :severity="data.existing_device_id ? 'warning' : 'success'"
            />
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="activeTab === 'incidents'" class="card p-3">
      <div class="grid mb-2">
        <div class="col-12 md:col-3">
          <label class="block mb-2">Период</label>
          <Dropdown v-model="incidentFilter.period" :options="periodOptions" optionLabel="label" optionValue="value" class="w-full" @change="loadOutages" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Статус</label>
          <Dropdown v-model="incidentFilter.active" :options="activeOptions" optionLabel="label" optionValue="value" class="w-full" @change="loadOutages" />
        </div>
      </div>
      <DataTable :value="outages" :loading="loadingOutages" class="table-compact" paginator :rows="15" stripedRows responsiveLayout="scroll">
        <Column field="path_src" header="Источник" />
        <Column field="path_dst" header="Назначение" />
        <Column field="path_dst_ip" header="IP" />
        <Column field="started_at" header="Начало">
          <template #body="{ data }">{{ fmtTime(data.started_at) }}</template>
        </Column>
        <Column field="ended_at" header="Конец">
          <template #body="{ data }">{{ data.ended_at ? fmtTime(data.ended_at) : 'Активен' }}</template>
        </Column>
        <Column field="duration_sec" header="Длительность (сек)" />
        <Column field="fail_count" header="Ошибки" />
        <Column field="is_active" header="Статус">
          <template #body="{ data }">
            <Tag :value="data.is_active ? 'Активен' : 'Закрыт'" :severity="data.is_active ? 'danger' : 'success'" />
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="activeTab === 'derived_alerts'">
      <div class="grid mb-3">
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Critical</div>
            <div class="text-3xl font-bold text-red-600">{{ alertSummary.critical || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">High</div>
            <div class="text-3xl font-bold text-orange-500">{{ alertSummary.high || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Medium</div>
            <div class="text-3xl font-bold text-yellow-600">{{ alertSummary.medium || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Low</div>
            <div class="text-3xl font-bold text-teal-600">{{ alertSummary.low || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Всего тревог</div>
            <div class="text-3xl font-bold text-900">{{ alertSummary.total || 0 }}</div>
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="flex flex-wrap align-items-center gap-2">
          <Button label="Пересчитать + проверить правила" icon="pi pi-cog" @click="evaluateAlerts(true)" :loading="loadingDerived" />
          <Button label="Проверить правила" severity="secondary" outlined @click="evaluateAlerts(false)" :loading="loadingDerived" />
          <Button label="Сбросить дефолтные правила" severity="help" outlined @click="seedDefaultRules" />
          <span class="text-500 ml-2">Обновлено: {{ fmtTime(alertSummary.generated_at) }}</span>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
          <h4 class="m-0">Правила тревог</h4>
          <div class="flex gap-2">
            <Button label="Добавить правило" icon="pi pi-plus" @click="openCreateRuleDialog" />
          </div>
        </div>
        <DataTable :value="alertRules" :loading="loadingDerived" class="table-compact rules-table" stripedRows responsiveLayout="scroll">
          <Column field="order" header="Порядок" style="min-width: 7rem">
            <template #body="{ data }">
              <InputNumber v-model="data.order" :min="1" :max="10000" class="w-full" />
            </template>
          </Column>
          <Column field="code" header="Код" style="min-width: 12rem">
            <template #body="{ data }">
              <InputText v-model="data.code" class="w-full" />
            </template>
          </Column>
          <Column field="name" header="Название" style="min-width: 15rem">
            <template #body="{ data }">
              <InputText v-model="data.name" class="w-full" />
            </template>
          </Column>
          <Column field="description" header="Описание" style="min-width: 15rem">
            <template #body="{ data }">
              <InputText v-model="data.description" class="w-full" />
            </template>
          </Column>
          <Column field="metric_code" header="Метрика" style="min-width: 12rem">
            <template #body="{ data }">
              <Dropdown v-model="data.metric_code" :options="metricCodeOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="window" header="Окно" style="min-width: 8rem">
            <template #body="{ data }">
              <Dropdown v-model="data.window" :options="windowOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="comparison" header="Сравнение" style="min-width: 8rem">
            <template #body="{ data }">
              <Dropdown v-model="data.comparison" :options="comparisonOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="threshold_value" header="Порог" style="min-width: 8rem">
            <template #body="{ data }">
              <InputNumber v-model="data.threshold_value" :minFractionDigits="0" :maxFractionDigits="2" class="w-full" />
            </template>
          </Column>
          <Column field="severity" header="Severity" style="min-width: 9rem">
            <template #body="{ data }">
              <Dropdown v-model="data.severity" :options="severityOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="enabled" header="Enabled" style="min-width: 7rem">
            <template #body="{ data }">
              <InputSwitch v-model="data.enabled" />
            </template>
          </Column>
          <Column header="Действия" style="min-width: 8rem">
            <template #body="{ data }">
              <div class="flex gap-1">
                <Button icon="pi pi-save" text rounded @click="saveRule(data)" />
                <Button icon="pi pi-trash" text rounded severity="danger" @click="removeRule(data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </div>

      <div class="card p-3 mb-3">
        <h4 class="m-0 mb-2">Derived метрики путей</h4>
        <DataTable :value="derivedRows" :loading="loadingDerived" class="table-compact" stripedRows paginator :rows="15" responsiveLayout="scroll">
          <Column field="src_device_name" header="Источник" />
          <Column field="dst_device_name" header="Назначение" />
          <Column field="dst_ip" header="IP" />
          <Column field="net_path_uptime_24h" header="Uptime 24ч (%)"><template #body="{ data }">{{ formatNum(data.net_path_uptime_24h, 2) }}</template></Column>
          <Column field="net_path_uptime_7d" header="Uptime 7д (%)"><template #body="{ data }">{{ formatNum(data.net_path_uptime_7d, 2) }}</template></Column>
          <Column field="net_path_outage_count_24h" header="Outage 24ч" />
          <Column field="net_path_latency_p95_24h" header="Latency p95 (ms)"><template #body="{ data }">{{ formatNum(data.net_path_latency_p95_24h, 1) }}</template></Column>
          <Column field="net_path_latency_jitter_1h" header="Jitter 1ч (ms)"><template #body="{ data }">{{ formatNum(data.net_path_latency_jitter_1h, 1) }}</template></Column>
          <Column field="net_path_packet_loss_avg_24h" header="Loss avg 24ч (%)"><template #body="{ data }">{{ formatNum(data.net_path_packet_loss_avg_24h, 2) }}</template></Column>
        </DataTable>
      </div>

      <div class="card p-3">
        <div class="flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
          <h4 class="m-0">Активные тревоги</h4>
          <div class="flex gap-2">
            <Dropdown
              v-model="alertsFilter.severity"
              :options="alertsSeverityOptions"
              optionLabel="label"
              optionValue="value"
              class="alert-filter"
            />
            <InputText v-model="alertsFilter.search" placeholder="Поиск по пути/правилу" class="alert-filter" />
          </div>
        </div>
        <DataTable :value="filteredActiveAlerts" :loading="loadingDerived" class="table-compact" stripedRows paginator :rows="15" responsiveLayout="scroll">
          <Column field="severity" header="Severity">
            <template #body="{ data }"><Tag :value="data.severity" :severity="severityTag(data.severity)" /></template>
          </Column>
          <Column field="rule_name" header="Правило" />
          <Column field="src_device_name" header="Источник" />
          <Column field="dst_device_name" header="Назначение" />
          <Column field="metric_code" header="Метрика" />
          <Column header="Текущее"><template #body="{ data }">{{ formatNum(data.metric_value, 2) }}</template></Column>
          <Column header="Порог"><template #body="{ data }">{{ data.comparison }} {{ formatNum(data.threshold_value, 2) }}</template></Column>
          <Column field="message" header="Описание" />
        </DataTable>
      </div>
    </div>

    <Dialog
      v-model:visible="pathDialogVisible"
      modal
      :header="editingPathId ? 'Редактировать путь' : 'Создать путь'"
      :style="{ width: 'var(--dialog-width-lg)', maxWidth: 'var(--dialog-max-width)' }"
      :breakpoints="{ '1400px': '78vw', '1200px': '84vw', '960px': '92vw', '640px': '96vw' }"
    >
      <div class="grid p-fluid">
        <div class="col-12 md:col-6">
          <label class="block mb-2">Источник</label>
          <Dropdown v-model="pathForm.src_device" :options="deviceOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Назначение</label>
          <Dropdown v-model="pathForm.dst_device" :options="deviceOptionsWithIp" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-6 lg:col-3">
          <label class="block mb-2">Интервал</label>
          <InputNumber v-model="pathForm.interval_sec" :min="5" :max="3600" suffix=" c" class="w-full" />
        </div>
        <div class="col-12 md:col-6 lg:col-3">
          <label class="block mb-2">Timeout</label>
          <InputNumber v-model="pathForm.timeout_sec" :min="1" :max="120" suffix=" c" class="w-full" />
        </div>
        <div class="col-12 md:col-6 lg:col-3">
          <label class="block mb-2">Пакеты</label>
          <InputNumber v-model="pathForm.packet_count" :min="1" :max="10" class="w-full" />
        </div>
        <div class="col-12 md:col-6 lg:col-3 flex flex-column justify-content-end">
          <label class="block mb-2">Вкл</label>
          <InputSwitch v-model="pathForm.enabled" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Порог fail</label>
          <InputNumber v-model="pathForm.fail_threshold" :min="1" :max="20" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Порог recover</label>
          <InputNumber v-model="pathForm.recover_threshold" :min="1" :max="20" class="w-full" />
        </div>
      </div>
      <template #footer>
        <Button label="Отмена" severity="secondary" text @click="pathDialogVisible = false" />
        <Button label="Сохранить" icon="pi pi-check" @click="savePath" />
      </template>
    </Dialog>

    <Dialog
      v-model:visible="historyDialogVisible"
      modal
      header="История пути"
      :style="{ width: 'var(--dialog-width-lg)', maxWidth: 'var(--dialog-max-width)' }"
      :breakpoints="{ '1600px': '86vw', '1200px': '92vw', '960px': '95vw', '640px': '96vw' }"
    >
      <div v-if="historyPath">
        <div class="text-700 mb-3">{{ historyPath.src_device }} -> {{ historyPath.dst_device }}</div>
        <div class="grid">
          <div class="col-12">
            <Chart type="line" :data="historyCharts.reachability" :options="historyChartOptions.reachability" class="h-16rem" />
          </div>
          <div class="col-12 md:col-6">
            <Chart type="line" :data="historyCharts.latency" :options="historyChartOptions.latency" class="h-16rem" />
          </div>
          <div class="col-12 md:col-6">
            <Chart type="line" :data="historyCharts.loss" :options="historyChartOptions.loss" class="h-16rem" />
          </div>
        </div>
      </div>
    </Dialog>

    <Dialog
      v-model:visible="ruleDialogVisible"
      modal
      header="Добавить правило тревоги"
      :style="{ width: 'var(--dialog-width-lg)', maxWidth: 'var(--dialog-max-width)' }"
      :breakpoints="{ '1400px': '86vw', '1200px': '90vw', '960px': '94vw', '640px': '96vw' }"
    >
      <div class="grid p-fluid">
        <div class="col-12 md:col-6">
          <label class="block mb-2">Код</label>
          <InputText v-model="ruleForm.code" placeholder="Например: latency_high_custom" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Название</label>
          <InputText v-model="ruleForm.name" placeholder="Человекочитаемое имя" class="w-full" />
        </div>
        <div class="col-12">
          <label class="block mb-2">Описание</label>
          <InputText v-model="ruleForm.description" placeholder="Что означает тревога" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Метрика</label>
          <Dropdown v-model="ruleForm.metric_code" :options="metricCodeOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Окно</label>
          <Dropdown v-model="ruleForm.window" :options="windowOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Сравнение</label>
          <Dropdown v-model="ruleForm.comparison" :options="comparisonOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Порог</label>
          <InputNumber v-model="ruleForm.threshold_value" :maxFractionDigits="2" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Порядок</label>
          <InputNumber v-model="ruleForm.order" :min="1" :max="10000" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Severity</label>
          <Dropdown v-model="ruleForm.severity" :options="severityOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-3 flex flex-column justify-content-end">
          <label class="block mb-2">Enabled</label>
          <InputSwitch v-model="ruleForm.enabled" />
        </div>
      </div>
      <template #footer>
        <Button label="Отмена" severity="secondary" text @click="ruleDialogVisible = false" />
        <Button label="Создать" icon="pi pi-check" @click="createRule" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import MultiSelect from 'primevue/multiselect';
import InputText from 'primevue/inputtext';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Dialog from 'primevue/dialog';
import Toast from 'primevue/toast';
import Chart from 'primevue/chart';
import { useToast } from 'primevue/usetoast';

const toast = useToast();
const activeTab = ref('paths');
const autoTimer = ref(null);

const loadingPaths = ref(false);
const loadingOutages = ref(false);
const loadingDerived = ref(false);
const loadingMap = ref(false);
const scanLoading = ref(false);
const scanSuggestionsLoading = ref(false);

const paths = ref([]);
const devices = ref([]);
const outages = ref([]);
const selectedPaths = ref([]);
const scannedDevices = ref([]);
const selectedScanned = ref([]);
const scanSuggestions = ref([]);
const scanCidr = ref('');
const scanTimeoutMs = ref(600);
const showOnlyNewScanned = ref(true);
const scanStats = ref({
  cidr: '',
  host_count: 0,
  alive_count: 0,
  ip_updated_count: 0,
});
const alertRules = ref([]);
const derivedRows = ref([]);
const activeAlerts = ref([]);
const mapSnapshot = ref(null);
const mapNodes = ref([]);
const mapEdges = ref([]);
const mapSelectedNodeKey = ref(null);
const mapHoveredNodeKey = ref(null);
const mapHoveredEdgeId = ref(null);
const mapTooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  lines: [],
});
const alertSummary = ref({
  critical: 0,
  high: 0,
  medium: 0,
  low: 0,
  total: 0,
  generated_at: null,
});
const alertsFilter = ref({
  severity: '',
  search: '',
});
const mapFilter = ref({
  search: '',
  state: null,
  includeDisabled: true,
});
const mapWindowHours = ref(24);

const pathDialogVisible = ref(false);
const editingPathId = ref(null);
const pathForm = ref({
  src_device: null,
  dst_device: null,
  enabled: true,
  interval_sec: 60,
  timeout_sec: 3,
  packet_count: 1,
  fail_threshold: 3,
  recover_threshold: 2,
});

const pathFilter = ref({
  search: '',
  state: null,
  enabled: null,
});

const bulkInterval = ref(60);

const templateForm = ref({
  template: 'servers_to_gateways',
  src_device_ids: [],
  dst_device_ids: [],
  defaults: {
    interval_sec: 60,
    timeout_sec: 3,
    packet_count: 1,
    fail_threshold: 3,
    recover_threshold: 2,
    enabled: true,
  },
});

const stateOptions = [
  { label: 'UP', value: 'up' },
  { label: 'DOWN', value: 'down' },
  { label: 'UNKNOWN', value: 'unknown' },
];
const mapStateOptions = [
  { label: 'UP', value: 'up' },
  { label: 'DOWN', value: 'down' },
  { label: 'UNKNOWN', value: 'unknown' },
];
const mapWindowOptions = [
  { label: '1 час', value: 1 },
  { label: '6 часов', value: 6 },
  { label: '24 часа', value: 24 },
  { label: '72 часа', value: 72 },
  { label: '7 дней', value: 168 },
];
const enabledOptions = [
  { label: 'Включен', value: true },
  { label: 'Выключен', value: false },
];
const templateOptions = [
  { label: 'Серверы -> Шлюзы', value: 'servers_to_gateways' },
  { label: 'Серверы -> Маршрутизаторы', value: 'servers_to_routers' },
  { label: 'Маршрутизаторы -> Шлюзы', value: 'routers_to_gateways' },
  { label: 'Custom', value: 'custom' },
];

const matrixIncludeDisabled = ref(false);
const matrix = ref({ sources: [], destinations: [], rows: [] });
const historyDialogVisible = ref(false);
const historyPath = ref(null);
const historyCharts = ref({
  reachability: { labels: [], datasets: [] },
  latency: { labels: [], datasets: [] },
  loss: { labels: [], datasets: [] },
});
const createHistoryOptions = (yOverrides = {}) => ({
  maintainAspectRatio: false,
  animation: false,
  plugins: {
    legend: { display: true, labels: { boxWidth: 16 } },
  },
  scales: {
    x: {
      ticks: {
        maxRotation: 25,
        minRotation: 25,
        autoSkip: true,
        maxTicksLimit: 10,
      },
      grid: { display: false },
    },
    y: {
      beginAtZero: true,
      ...yOverrides,
    },
  },
});
const historyChartOptions = ref({
  reachability: createHistoryOptions({ min: 0, max: 1, ticks: { stepSize: 1 } }),
  latency: createHistoryOptions(),
  loss: createHistoryOptions({ min: 0, max: 100 }),
});

const ruleDialogVisible = ref(false);
const ruleForm = ref({
  code: '',
  name: '',
  description: '',
  metric_code: 'net_path_down_flag_current',
  window: 'current',
  comparison: 'eq',
  threshold_value: 1,
  severity: 'high',
  enabled: true,
  order: 100,
});

const incidentFilter = ref({
  period: '24h',
  active: '',
});
const periodOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: 'Все', value: 'all' },
];
const activeOptions = [
  { label: 'Все', value: '' },
  { label: 'Только активные', value: 'true' },
  { label: 'Только закрытые', value: 'false' },
];
const metricCodeOptions = [
  { label: 'Путь DOWN (current)', value: 'net_path_down_flag_current' },
  { label: 'Uptime 24ч', value: 'net_path_uptime_24h' },
  { label: 'Uptime 7д', value: 'net_path_uptime_7d' },
  { label: 'Outage count 24ч', value: 'net_path_outage_count_24h' },
  { label: 'Outage count 7д', value: 'net_path_outage_count_7d' },
  { label: 'Latency p95 24ч', value: 'net_path_latency_p95_24h' },
  { label: 'Latency jitter 1ч', value: 'net_path_latency_jitter_1h' },
  { label: 'Packet loss avg 24ч', value: 'net_path_packet_loss_avg_24h' },
];
const windowOptions = [
  { label: 'Current', value: 'current' },
  { label: '1h', value: '1h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
];
const comparisonOptions = [
  { label: '>', value: 'gt' },
  { label: '>=', value: 'gte' },
  { label: '<', value: 'lt' },
  { label: '<=', value: 'lte' },
  { label: '=', value: 'eq' },
  { label: '!=', value: 'ne' },
];
const severityOptions = [
  { label: 'Low', value: 'low' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
  { label: 'Critical', value: 'critical' },
];
const alertsSeverityOptions = [
  { label: 'Все severity', value: '' },
  ...severityOptions,
];

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const deviceOptions = computed(() => devices.value.map((d) => ({
  label: `${d.name} (${d.serial_number})`,
  value: d.id,
})));
const deviceOptionsWithIp = computed(() => devices.value
  .filter((d) => !!d.ip_address)
  .map((d) => ({ label: `${d.name} (${d.ip_address})`, value: d.id })));

const mapNodeKey = (node) => (node?.device ? `dev:${node.device}` : `node:${node?.id}`);
const edgeNodeKey = (edge, side) => {
  const deviceId = side === 'src' ? edge?.src_device : edge?.dst_device;
  const edgeId = edge?.id;
  if (deviceId) return `dev:${deviceId}`;
  return side === 'src' ? `src:${edgeId}` : `dst:${edgeId}`;
};

const filteredMapEdges = computed(() => {
  const search = (mapFilter.value.search || '').trim().toLowerCase();
  return mapEdges.value.filter((edge) => {
    if (!mapFilter.value.includeDisabled && !edge.enabled) return false;
    if (mapFilter.value.state && edge.state !== mapFilter.value.state) return false;
    if (!search) return true;
    const haystack = `${edge.src_name || ''} ${edge.dst_name || ''} ${edge.dst_ip || ''}`.toLowerCase();
    return haystack.includes(search);
  });
});

const filteredMapNodes = computed(() => {
  const allNodes = mapNodes.value;
  const search = (mapFilter.value.search || '').trim().toLowerCase();
  const hasEdgeLevelFilter = Boolean(mapFilter.value.state) || !mapFilter.value.includeDisabled;
  if (!search && !hasEdgeLevelFilter) {
    return allNodes;
  }

  const matchedNodeKeys = new Set();
  for (const node of allNodes) {
    const haystack = `${node.device_name || ''} ${node.ip_address || ''} ${node.serial_number || ''}`.toLowerCase();
    if (search && haystack.includes(search)) {
      matchedNodeKeys.add(mapNodeKey(node));
    }
  }

  const edgeNodeKeys = new Set();
  for (const edge of filteredMapEdges.value) {
    edgeNodeKeys.add(edgeNodeKey(edge, 'src'));
    edgeNodeKeys.add(edgeNodeKey(edge, 'dst'));
  }

  return allNodes.filter((node) => {
    const key = mapNodeKey(node);
    if (matchedNodeKeys.has(key)) return true;
    if (edgeNodeKeys.has(key)) return true;
    return false;
  });
});

const mapGraph = computed(() => {
  const width = 1200;
  const height = 700;
  const nodes = filteredMapNodes.value;
  const nodePos = new Map();
  const total = nodes.length;
  const radius = Math.max(110, Math.min(width, height) * 0.36);
  const centerX = width / 2;
  const centerY = height / 2;

  nodes.forEach((node, idx) => {
    const angle = total <= 1 ? -Math.PI / 2 : (-Math.PI / 2) + (2 * Math.PI * idx / total);
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    nodePos.set(mapNodeKey(node), { x, y });
  });

  const graphEdges = filteredMapEdges.value
    .map((edge) => {
      const srcKey = edgeNodeKey(edge, 'src');
      const dstKey = edgeNodeKey(edge, 'dst');
      const from = nodePos.get(srcKey);
      const to = nodePos.get(dstKey);
      if (!from || !to) return null;
      return {
        id: edge.id,
        srcKey,
        dstKey,
        src_name: edge.src_name,
        dst_name: edge.dst_name,
        dst_ip: edge.dst_ip,
        state: edge.state,
        enabled: edge.enabled,
        latency_ms: edge.latency_ms,
        packet_loss_pct: edge.packet_loss_pct,
        confidence_pct: edge.confidence_pct,
        outage_count_24h: edge.outage_count_24h,
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
      };
    })
    .filter(Boolean);

  const graphNodes = nodes.map((node) => {
    const key = mapNodeKey(node);
    const pos = nodePos.get(key) || { x: centerX, y: centerY };
    const raw = node.device_name || node.ip_address || node.serial_number || `Node ${node.id}`;
    const shortName = raw.length > 10 ? `${raw.slice(0, 10)}…` : raw;
    return {
      id: node.id,
      key,
      status: node.status,
      device_type_name: node.device_type_name,
      ip_address: node.ip_address,
      serial_number: node.serial_number,
      last_seen: node.last_seen,
      label: raw,
      shortName,
      x: pos.x,
      y: pos.y,
    };
  });

  return { width, height, nodes: graphNodes, edges: graphEdges };
});

const mapSelectedConnectedNodeKeys = computed(() => {
  const selected = mapSelectedNodeKey.value;
  const keys = new Set();
  if (!selected) return keys;
  keys.add(selected);
  for (const edge of mapGraph.value.edges) {
    if (edge.srcKey === selected || edge.dstKey === selected) {
      keys.add(edge.srcKey);
      keys.add(edge.dstKey);
    }
  }
  return keys;
});

const filteredPaths = computed(() => {
  return paths.value.filter((p) => {
    const stateOk = !pathFilter.value.state || p.last_state === pathFilter.value.state;
    const enabledOk = pathFilter.value.enabled === null || p.enabled === pathFilter.value.enabled;
    const search = (pathFilter.value.search || '').toLowerCase().trim();
    const searchOk = !search || `${p.src_device_name} ${p.dst_device_name} ${p.dst_ip || ''}`.toLowerCase().includes(search);
    return stateOk && enabledOk && searchOk;
  });
});
const filteredActiveAlerts = computed(() => {
  return activeAlerts.value.filter((item) => {
    const severityOk = !alertsFilter.value.severity || item.severity === alertsFilter.value.severity;
    const search = (alertsFilter.value.search || '').toLowerCase().trim();
    if (!search) return severityOk;
    const haystack = `${item.rule_name || ''} ${item.src_device_name || ''} ${item.dst_device_name || ''} ${item.message || ''}`.toLowerCase();
    return severityOk && haystack.includes(search);
  });
});
const filteredScannedDevices = computed(() => {
  if (!showOnlyNewScanned.value) return scannedDevices.value;
  return scannedDevices.value.filter((item) => !item.existing_device_id);
});

const stateLabel = (state) => {
  if (state === 'up') return 'UP';
  if (state === 'down') return 'DOWN';
  if (state === 'none') return 'NONE';
  return 'UNKNOWN';
};
const stateSeverity = (state) => {
  if (state === 'up') return 'success';
  if (state === 'down') return 'danger';
  if (state === 'none') return 'secondary';
  return 'warning';
};
const mapStatusSeverity = (status) => {
  if (status === 'ok') return 'success';
  if (status === 'error') return 'danger';
  return 'warning';
};
const mapEdgeColor = (state) => {
  if (state === 'up') return '#16a34a';
  if (state === 'down') return '#dc2626';
  if (state === 'unknown') return '#f59e0b';
  return '#94a3b8';
};
const mapNodeFill = (node) => {
  const typeName = (node?.device_type_name || '').toLowerCase();
  if (typeName.includes('сервер') || typeName.includes('server')) return '#e0f2fe';
  if (typeName.includes('маршрут') || typeName.includes('router') || typeName.includes('шлюз')) return '#ede9fe';
  if (node?.status === 'active') return '#dcfce7';
  if (node?.status === 'in_repair') return '#fef3c7';
  return '#e2e8f0';
};
const isEdgeConnectedToSelected = (edge) => {
  const selected = mapSelectedNodeKey.value;
  if (!selected) return true;
  return edge.srcKey === selected || edge.dstKey === selected;
};
const mapEdgeOpacity = (edge) => {
  if (mapSelectedNodeKey.value) {
    return isEdgeConnectedToSelected(edge) ? (edge.enabled ? 0.96 : 0.62) : 0.12;
  }
  if (mapHoveredEdgeId.value) {
    return mapHoveredEdgeId.value === edge.id ? 1 : (edge.enabled ? 0.45 : 0.25);
  }
  return edge.enabled ? 0.85 : 0.35;
};
const mapEdgeWidth = (edge) => {
  let width = edge.state === 'down' ? 3 : 2;
  if (mapHoveredEdgeId.value === edge.id) width += 1.4;
  if (mapSelectedNodeKey.value && isEdgeConnectedToSelected(edge)) width += 1;
  return width;
};
const mapNodeStroke = (node) => {
  if (mapSelectedNodeKey.value === node.key) return '#0f172a';
  if (mapHoveredNodeKey.value === node.key) return '#0f172a';
  if (mapSelectedNodeKey.value && mapSelectedConnectedNodeKeys.value.has(node.key)) return '#334155';
  return '#0f172a';
};
const mapNodeStrokeWidth = (node) => {
  if (mapSelectedNodeKey.value === node.key) return 3;
  if (mapHoveredNodeKey.value === node.key) return 2.4;
  if (mapSelectedNodeKey.value && mapSelectedConnectedNodeKeys.value.has(node.key)) return 2;
  return 1.2;
};
const mapNodeRadius = (node) => {
  if (mapSelectedNodeKey.value === node.key) return 24;
  if (mapHoveredNodeKey.value === node.key) return 22;
  return 20;
};
const mapNodeOpacity = (node) => {
  if (!mapSelectedNodeKey.value) return 1;
  return mapSelectedConnectedNodeKeys.value.has(node.key) ? 1 : 0.35;
};
const updateMapTooltip = (event, title, lines) => {
  if (!event) return;
  const safeLines = Array.isArray(lines) ? lines.filter((line) => !!line) : [];
  let x = (event.clientX || 0) + 14;
  let y = (event.clientY || 0) + 14;
  if (typeof window !== 'undefined') {
    const maxX = Math.max(20, window.innerWidth - 320);
    const maxY = Math.max(20, window.innerHeight - 180);
    x = Math.min(x, maxX);
    y = Math.min(y, maxY);
  }
  mapTooltip.value = {
    visible: true,
    x,
    y,
    title: title || '',
    lines: safeLines,
  };
};
const hideMapTooltip = () => {
  mapTooltip.value.visible = false;
};
const onMapNodeMouseEnter = (node, event) => {
  mapHoveredNodeKey.value = node.key;
  updateMapTooltip(event, node.label, [
    `IP: ${node.ip_address || '—'}`,
    `S/N: ${node.serial_number || '—'}`,
    `Статус: ${node.status || '—'}`,
    `Последняя активность: ${fmtTime(node.last_seen)}`,
  ]);
};
const onMapNodeMouseMove = (node, event) => {
  updateMapTooltip(event, node.label, [
    `IP: ${node.ip_address || '—'}`,
    `S/N: ${node.serial_number || '—'}`,
    `Статус: ${node.status || '—'}`,
    `Последняя активность: ${fmtTime(node.last_seen)}`,
  ]);
};
const onMapNodeMouseLeave = () => {
  mapHoveredNodeKey.value = null;
  if (!mapHoveredEdgeId.value) hideMapTooltip();
};
const onMapNodeClick = (node) => {
  mapSelectedNodeKey.value = mapSelectedNodeKey.value === node.key ? null : node.key;
};
const onMapEdgeMouseEnter = (edge, event) => {
  mapHoveredEdgeId.value = edge.id;
  updateMapTooltip(event, `${edge.src_name} → ${edge.dst_name}`, [
    `Состояние: ${stateLabel(edge.state)}`,
    `RTT: ${formatNum(edge.latency_ms, 1)} ms`,
    `Loss: ${formatNum(edge.packet_loss_pct, 1)} %`,
    `Confidence: ${formatNum(edge.confidence_pct, 1)} %`,
    `Outage 24ч: ${edge.outage_count_24h ?? 0}`,
  ]);
};
const onMapEdgeMouseMove = (edge, event) => {
  updateMapTooltip(event, `${edge.src_name} → ${edge.dst_name}`, [
    `Состояние: ${stateLabel(edge.state)}`,
    `RTT: ${formatNum(edge.latency_ms, 1)} ms`,
    `Loss: ${formatNum(edge.packet_loss_pct, 1)} %`,
    `Confidence: ${formatNum(edge.confidence_pct, 1)} %`,
    `Outage 24ч: ${edge.outage_count_24h ?? 0}`,
  ]);
};
const onMapEdgeMouseLeave = () => {
  mapHoveredEdgeId.value = null;
  if (!mapHoveredNodeKey.value) hideMapTooltip();
};

watch(
  () => mapGraph.value.nodes.map((node) => node.key),
  (keys) => {
    if (mapSelectedNodeKey.value && !keys.includes(mapSelectedNodeKey.value)) {
      mapSelectedNodeKey.value = null;
    }
    if (mapHoveredNodeKey.value && !keys.includes(mapHoveredNodeKey.value)) {
      mapHoveredNodeKey.value = null;
    }
  }
);

const fmtTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value));
  } catch (e) {
    return value;
  }
};
const formatNum = (value, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
};
const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}%`;
};

const validatePathForm = () => {
  if (!pathForm.value.src_device || !pathForm.value.dst_device) {
    return 'Нужно выбрать источник и назначение.';
  }
  if (pathForm.value.src_device === pathForm.value.dst_device) {
    return 'Источник и назначение не могут совпадать.';
  }
  const dst = devices.value.find((d) => d.id === pathForm.value.dst_device);
  if (!dst || !dst.ip_address) {
    return 'У назначения должен быть IP-адрес.';
  }
  if (pathForm.value.timeout_sec > pathForm.value.interval_sec) {
    return 'Timeout должен быть меньше или равен интервалу.';
  }
  return '';
};

const loadDevices = async () => {
  const res = await apiClient.get('devices/?ordering=name');
  devices.value = unwrap(res);
};

const loadPaths = async () => {
  loadingPaths.value = true;
  try {
    const res = await apiClient.get('network-paths/');
    paths.value = unwrap(res);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить пути', life: 4000 });
  } finally {
    loadingPaths.value = false;
  }
};

const loadMatrix = async () => {
  try {
    const res = await apiClient.get(`network-paths/matrix/?include_disabled=${matrixIncludeDisabled.value ? '1' : '0'}`);
    matrix.value = res.data || { sources: [], destinations: [], rows: [] };
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить матрицу', life: 4000 });
  }
};

const loadOutages = async () => {
  loadingOutages.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-started_at');
    if (incidentFilter.value.period === '24h') params.set('since_hours', '24');
    if (incidentFilter.value.period === '7d') params.set('since_days', '7');
    if (incidentFilter.value.active !== '') params.set('is_active', incidentFilter.value.active);
    const res = await apiClient.get(`network-outages/?${params.toString()}`);
    outages.value = unwrap(res);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить инциденты', life: 4000 });
  } finally {
    loadingOutages.value = false;
  }
};

const loadScanSuggestions = async () => {
  scanSuggestionsLoading.value = true;
  try {
    const res = await apiClient.get('devices/network_scan_suggestions/');
    const cidrs = Array.isArray(res.data?.cidrs) ? res.data.cidrs : [];
    scanSuggestions.value = cidrs.map((value) => ({ label: value, value }));
    if (!scanCidr.value && scanSuggestions.value.length) {
      scanCidr.value = scanSuggestions.value[0].value;
    }
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: e?.response?.data?.detail || 'Не удалось получить подсети',
      life: 3500,
    });
  } finally {
    scanSuggestionsLoading.value = false;
  }
};

const runNetworkScan = async () => {
  scanLoading.value = true;
  selectedScanned.value = [];
  try {
    const res = await apiClient.post('devices/network_scan/', {
      cidr: scanCidr.value || null,
      timeout_ms: scanTimeoutMs.value || 600,
    });
    scannedDevices.value = Array.isArray(res.data?.results) ? res.data.results : [];
    scanStats.value = {
      cidr: res.data?.cidr || scanCidr.value || '',
      host_count: res.data?.host_count || 0,
      alive_count: res.data?.alive_count || 0,
      ip_updated_count: res.data?.ip_updated_count || 0,
    };
    if ((res.data?.ip_updated_count || 0) > 0) {
      toast.add({
        severity: 'info',
        summary: 'IP обновлены',
        detail: `Обновлено IP по MAC: ${res.data.ip_updated_count}`,
        life: 3000,
      });
    }
  } catch (e) {
    scannedDevices.value = [];
    scanStats.value = {
      cidr: '',
      host_count: 0,
      alive_count: 0,
      ip_updated_count: 0,
    };
    const detail = e?.response?.data?.detail || 'Не удалось выполнить сканирование';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    scanLoading.value = false;
  }
};

const importScannedDevices = async () => {
  if (!selectedScanned.value.length) {
    return;
  }
  try {
    const payload = selectedScanned.value
      .filter((item) => !item.existing_device_id)
      .map((item) => ({
        name: item.name,
        ip_address: item.ip_address,
        mac_address: item.mac_address,
        serial_number: item.serial_number,
      }));

    if (!payload.length) {
      toast.add({ severity: 'warn', summary: 'Нет данных', detail: 'Все выбранные устройства уже есть в базе.', life: 3000 });
      return;
    }

    const res = await apiClient.post('devices/import_scanned/', { devices: payload });
    toast.add({
      severity: 'success',
      summary: 'Импорт завершен',
      detail: `Создано: ${res.data?.created || 0}, пропущено: ${res.data?.skipped || 0}`,
      life: 3500,
    });
    await Promise.all([loadDevices(), runNetworkScan()]);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось добавить устройства';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
};

const loadAlertRules = async () => {
  try {
    const res = await apiClient.get('network-alert-rules/?ordering=order,code');
    alertRules.value = unwrap(res);
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: e?.response?.data?.detail || 'Не удалось загрузить правила тревог',
      life: 4000,
    });
  }
};

const loadDerivedSnapshot = async () => {
  try {
    const res = await apiClient.get('network-paths/derived/');
    derivedRows.value = Array.isArray(res.data) ? res.data : [];
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: e?.response?.data?.detail || 'Не удалось загрузить derived-метрики',
      life: 4000,
    });
  }
};

const severityTag = (severity) => {
  if (severity === 'critical') return 'danger';
  if (severity === 'high') return 'warning';
  if (severity === 'medium') return 'info';
  return 'success';
};

const openCreateRuleDialog = () => {
  ruleForm.value = {
    code: '',
    name: '',
    description: '',
    metric_code: 'net_path_down_flag_current',
    window: 'current',
    comparison: 'eq',
    threshold_value: 1,
    severity: 'high',
    enabled: true,
    order: 100,
  };
  ruleDialogVisible.value = true;
};

const createRule = async () => {
  const payload = {
    code: (ruleForm.value.code || '').trim(),
    name: (ruleForm.value.name || '').trim(),
    description: (ruleForm.value.description || '').trim(),
    metric_code: ruleForm.value.metric_code,
    window: ruleForm.value.window,
    comparison: ruleForm.value.comparison,
    threshold_value: Number(ruleForm.value.threshold_value),
    severity: ruleForm.value.severity,
    enabled: !!ruleForm.value.enabled,
    order: Number(ruleForm.value.order || 100),
  };
  if (!payload.code || !payload.name) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Код и название обязательны.', life: 3200 });
    return;
  }
  if (Number.isNaN(payload.threshold_value)) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Порог должен быть числом.', life: 3200 });
    return;
  }
  try {
    await apiClient.post('network-alert-rules/', payload);
    ruleDialogVisible.value = false;
    await loadAlertRules();
    toast.add({ severity: 'success', summary: 'Создано', detail: `Правило: ${payload.code}`, life: 2600 });
  } catch (e) {
    const detail = typeof e?.response?.data === 'object'
      ? JSON.stringify(e.response.data)
      : (e?.response?.data?.detail || 'Не удалось создать правило');
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
};

const evaluateAlerts = async (recompute = true) => {
  loadingDerived.value = true;
  try {
    const res = await apiClient.post('network-paths/evaluate_alerts/', {
      recompute,
      ensure_defaults: false,
    });
    const payload = res.data || {};
    alertSummary.value = payload.summary || {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      total: 0,
      generated_at: null,
    };
    activeAlerts.value = Array.isArray(payload.alerts) ? payload.alerts : [];
    if (Array.isArray(payload.rows) && payload.rows.length) {
      derivedRows.value = payload.rows;
    }
    toast.add({
      severity: 'success',
      summary: recompute ? 'Метрики пересчитаны' : 'Проверка завершена',
      detail: `Активных тревог: ${alertSummary.value.total || 0}`,
      life: 2800,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить проверку тревог';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    loadingDerived.value = false;
  }
};

const seedDefaultRules = async () => {
  try {
    const res = await apiClient.post('network-alert-rules/seed_defaults/', { overwrite: true });
    await loadAlertRules();
    toast.add({
      severity: 'success',
      summary: 'Правила обновлены',
      detail: `created=${res.data?.created || 0}, updated=${res.data?.updated || 0}, skipped=${res.data?.skipped || 0}`,
      life: 3200,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сбросить дефолтные правила';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  }
};

const saveRule = async (rule) => {
  const payload = {
    code: (rule.code || '').trim(),
    name: (rule.name || '').trim(),
    description: (rule.description || '').trim(),
    metric_code: rule.metric_code,
    window: rule.window,
    comparison: rule.comparison,
    threshold_value: Number(rule.threshold_value),
    severity: rule.severity,
    enabled: !!rule.enabled,
    order: Number(rule.order || 100),
  };
  if (!payload.code || !payload.name || Number.isNaN(payload.threshold_value)) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Заполните код/название/порог корректно.', life: 3200 });
    return;
  }
  try {
    await apiClient.patch(`network-alert-rules/${rule.id}/`, payload);
    toast.add({ severity: 'success', summary: 'Сохранено', detail: `Правило: ${payload.code}`, life: 2200 });
  } catch (e) {
    const detail = typeof e?.response?.data === 'object'
      ? JSON.stringify(e.response.data)
      : (e?.response?.data?.detail || 'Не удалось сохранить правило');
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 3800 });
  }
};

const removeRule = async (rule) => {
  if (!window.confirm(`Удалить правило "${rule.name || rule.code}"?`)) return;
  try {
    await apiClient.delete(`network-alert-rules/${rule.id}/`);
    await loadAlertRules();
    await evaluateAlerts(false);
    toast.add({ severity: 'success', summary: 'Удалено', detail: `Правило: ${rule.code}`, life: 2400 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось удалить правило';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 3800 });
  }
};

const loadDerivedTab = async () => {
  loadingDerived.value = true;
  try {
    await Promise.all([
      loadAlertRules(),
      loadDerivedSnapshot(),
    ]);
    const res = await apiClient.post('network-paths/evaluate_alerts/', {
      recompute: false,
      ensure_defaults: false,
    });
    const payload = res.data || {};
    alertSummary.value = payload.summary || alertSummary.value;
    activeAlerts.value = Array.isArray(payload.alerts) ? payload.alerts : [];
    if (Array.isArray(payload.rows) && payload.rows.length) {
      derivedRows.value = payload.rows;
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить тревоги';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    loadingDerived.value = false;
  }
};

const loadNetworkMap = async () => {
  loadingMap.value = true;
  try {
    const res = await apiClient.get('network-map/current/');
    const payload = res.data || {};
    mapSnapshot.value = payload;
    mapNodes.value = Array.isArray(payload.nodes) ? payload.nodes : [];
    mapEdges.value = Array.isArray(payload.edges) ? payload.edges : [];
    mapHoveredNodeKey.value = null;
    mapHoveredEdgeId.value = null;
    hideMapTooltip();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить автокарту';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    loadingMap.value = false;
  }
};

const rebuildNetworkMap = async () => {
  loadingMap.value = true;
  try {
    const res = await apiClient.post('network-map/rebuild/', {
      window_hours: mapWindowHours.value,
      include_data: true,
    });
    const payload = res.data || {};
    mapSnapshot.value = payload;
    mapNodes.value = Array.isArray(payload.nodes) ? payload.nodes : [];
    mapEdges.value = Array.isArray(payload.edges) ? payload.edges : [];
    mapHoveredNodeKey.value = null;
    mapHoveredEdgeId.value = null;
    hideMapTooltip();
    toast.add({
      severity: 'success',
      summary: 'Автокарта обновлена',
      detail: `Узлов: ${payload.node_count || 0}, ребер: ${payload.edge_count || 0}`,
      life: 2800,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.response?.data?.error || 'Не удалось пересобрать автокарту';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    loadingMap.value = false;
  }
};

const refreshActiveTab = async () => {
  if (activeTab.value === 'paths') {
    await loadPaths();
  } else if (activeTab.value === 'automap') {
    await loadNetworkMap();
  } else if (activeTab.value === 'matrix') {
    await loadMatrix();
  } else if (activeTab.value === 'scan') {
    await runNetworkScan();
  } else if (activeTab.value === 'derived_alerts') {
    await loadDerivedTab();
  } else {
    await loadOutages();
  }
};

const openCreatePath = () => {
  editingPathId.value = null;
  pathForm.value = {
    src_device: null,
    dst_device: null,
    enabled: true,
    interval_sec: 60,
    timeout_sec: 3,
    packet_count: 1,
    fail_threshold: 3,
    recover_threshold: 2,
  };
  pathDialogVisible.value = true;
};

const openEditPath = (path) => {
  editingPathId.value = path.id;
  pathForm.value = {
    src_device: path.src_device,
    dst_device: path.dst_device,
    enabled: path.enabled,
    interval_sec: path.interval_sec,
    timeout_sec: path.timeout_sec,
    packet_count: path.packet_count,
    fail_threshold: path.fail_threshold,
    recover_threshold: path.recover_threshold,
  };
  pathDialogVisible.value = true;
};

const savePath = async () => {
  const validationError = validatePathForm();
  if (validationError) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: validationError, life: 3500 });
    return;
  }

  try {
    if (editingPathId.value) {
      await apiClient.patch(`network-paths/${editingPathId.value}/`, pathForm.value);
    } else {
      await apiClient.post('network-paths/', pathForm.value);
    }
    pathDialogVisible.value = false;
    await loadPaths();
    await loadMatrix();
  } catch (e) {
    const detail = e?.response?.data?.detail || JSON.stringify(e?.response?.data || {}) || 'Не удалось сохранить путь';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
};

const removePath = async (path) => {
  if (!window.confirm(`Удалить путь ${path.src_device_name} -> ${path.dst_device_name}?`)) return;
  try {
    await apiClient.delete(`network-paths/${path.id}/`);
    await loadPaths();
    await loadMatrix();
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось удалить путь', life: 4000 });
  }
};

const selectedIds = computed(() => selectedPaths.value.map((p) => p.id));

const bulkEnable = async (enabled) => {
  try {
    const res = await apiClient.post('network-paths/bulk_update/', { ids: selectedIds.value, enabled });
    await loadPaths();
    await loadMatrix();
    toast.add({ severity: 'success', summary: 'OK', detail: `Обновлено: ${res.data.updated}`, life: 2500 });
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Массовое обновление не удалось', life: 4000 });
  }
};

const bulkSetInterval = async () => {
  if (!bulkInterval.value || bulkInterval.value < 5) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Интервал должен быть >= 5 секунд', life: 3000 });
    return;
  }
  try {
    const res = await apiClient.post('network-paths/bulk_update/', { ids: selectedIds.value, interval_sec: bulkInterval.value });
    await loadPaths();
    toast.add({ severity: 'success', summary: 'OK', detail: `Обновлено: ${res.data.updated}`, life: 2500 });
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось применить интервал', life: 4000 });
  }
};

const probeAll = async () => {
  try {
    await apiClient.post('network-paths/probe/', { respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe не выполнен', life: 4000 });
  }
};

const probeSelected = async () => {
  try {
    await apiClient.post('network-paths/probe/', { path_ids: selectedIds.value, respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe выбранных не выполнен', life: 4000 });
  }
};

const probePath = async (pathId) => {
  try {
    await apiClient.post('network-paths/probe/', { path_id: pathId, respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe пути не выполнен', life: 4000 });
  }
};

const runTemplate = async () => {
  if (templateForm.value.template === 'custom') {
    if (!templateForm.value.src_device_ids.length || !templateForm.value.dst_device_ids.length) {
      toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Для custom нужно выбрать источники и назначения', life: 3000 });
      return;
    }
  }
  try {
    const res = await apiClient.post('network-paths/generate_template/', {
      template: templateForm.value.template,
      src_device_ids: templateForm.value.src_device_ids,
      dst_device_ids: templateForm.value.dst_device_ids,
      defaults: templateForm.value.defaults,
      update_existing: false,
    });
    await Promise.all([loadPaths(), loadMatrix()]);
    toast.add({
      severity: 'success',
      summary: 'Шаблон применен',
      detail: `created=${res.data.created}, updated=${res.data.updated}, skipped=${res.data.skipped}`,
      life: 3500,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось применить шаблон';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  }
};

const matrixCellClass = (cell) => {
  if (!cell.path_id) return 'cell-none';
  if (cell.state === 'up') return 'cell-up';
  if (cell.state === 'down') return 'cell-down';
  return 'cell-unknown';
};

const formatLabel = (timestamp) => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (v) => String(v).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())} ${pad(date.getDate())}:${pad(date.getMonth() + 1)}:${date.getFullYear()}`;
};

const buildRange = (values, { minFloor = 0, maxCap = null } = {}) => {
  if (!values.length) return {};
  const numeric = values.map((v) => Number(v)).filter((v) => Number.isFinite(v));
  if (!numeric.length) return {};
  const minValue = Math.min(...numeric);
  const maxValue = Math.max(...numeric);
  if (minValue === maxValue) {
    const delta = Math.max(1, Math.abs(maxValue) * 0.1);
    const min = Math.max(minFloor, minValue - delta);
    const max = maxValue + delta;
    return maxCap === null ? { min, max } : { min, max: Math.min(max, maxCap) };
  }
  const padding = (maxValue - minValue) * 0.1;
  const min = Math.max(minFloor, minValue - padding);
  const max = maxValue + padding;
  return maxCap === null ? { min, max } : { min, max: Math.min(max, maxCap) };
};

const openCellHistory = async (cell) => {
  if (!cell.path_id) return;
  try {
    const res = await apiClient.get(`network-paths/${cell.path_id}/history/?since_hours=168`);
    const data = res.data || {};
    historyPath.value = { src_device: data.src_device, dst_device: data.dst_device };
    const reachable = data.series?.reachable || [];
    const latency = data.series?.latency_ms || [];
    const loss = data.series?.packet_loss_pct || [];

    historyCharts.value.reachability = {
      labels: reachable.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Reachable', data: reachable.map((p) => p.value), borderColor: '#2563eb', fill: false, tension: 0.2 }],
    };
    historyCharts.value.latency = {
      labels: latency.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Latency ms', data: latency.map((p) => p.value), borderColor: '#10b981', fill: false, tension: 0.2 }],
    };
    historyCharts.value.loss = {
      labels: loss.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Loss %', data: loss.map((p) => p.value), borderColor: '#ef4444', fill: false, tension: 0.2 }],
    };
    historyChartOptions.value = {
      reachability: createHistoryOptions({ min: 0, max: 1, ticks: { stepSize: 1 } }),
      latency: createHistoryOptions(buildRange(latency.map((p) => p.value), { minFloor: 0 })),
      loss: createHistoryOptions(buildRange(loss.map((p) => p.value), { minFloor: 0, maxCap: 100 })),
    };
    historyDialogVisible.value = true;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить историю ячейки', life: 4000 });
  }
};

watch(activeTab, async (tab) => {
  if (tab === 'paths') await loadPaths();
  if (tab === 'automap') await loadNetworkMap();
  if (tab === 'matrix') await loadMatrix();
  if (tab === 'scan') await runNetworkScan();
  if (tab === 'incidents') await loadOutages();
  if (tab === 'derived_alerts') await loadDerivedTab();
});

onMounted(async () => {
  await Promise.all([loadDevices(), loadPaths(), loadScanSuggestions()]);
  autoTimer.value = setInterval(() => {
    if (activeTab.value === 'paths') loadPaths();
    if (activeTab.value === 'automap') loadNetworkMap();
    if (activeTab.value === 'matrix') loadMatrix();
    if (activeTab.value === 'incidents') loadOutages();
    if (activeTab.value === 'derived_alerts') loadDerivedTab();
  }, 60000);
});

onBeforeUnmount(() => {
  if (autoTimer.value) clearInterval(autoTimer.value);
});
</script>

<style scoped>
.tab-switch {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.4rem;
  border-radius: 12px;
  background: #eef2ff;
}
.tab-switch :deep(.p-button) {
  min-height: 2.2rem;
  font-weight: 600;
}
.path-master-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: end;
}
.path-master-item {
  grid-column: span 12;
  min-width: 0;
}
.item-template,
.item-interval {
  grid-column: span 3;
}
.item-timeout,
.item-fail-recover,
.item-generate {
  grid-column: span 2;
}
.item-generate {
  display: flex;
  align-items: flex-end;
}
.custom-devices-grid .path-master-item {
  grid-column: span 6;
}
.fail-recover-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}
.path-master-grid :deep(.p-dropdown),
.path-master-grid :deep(.p-multiselect),
.path-master-grid :deep(.p-inputnumber),
.path-master-grid :deep(.p-inputnumber-input) {
  width: 100%;
}
.bulk-toolbar {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: end;
}
.bulk-group {
  min-width: 0;
}
.bulk-group-actions {
  grid-column: span 4;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.bulk-interval-group {
  grid-column: span 4;
  display: grid;
  grid-template-columns: minmax(11rem, 1fr) auto;
  gap: 0.5rem;
  align-items: end;
}
.bulk-group-probe {
  grid-column: span 4;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  justify-content: flex-end;
}
.bulk-input {
  width: 100%;
  min-width: 0;
}
.bulk-interval-btn {
  align-self: end;
  white-space: nowrap;
}
.metric-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.map-summary-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.75rem;
}
.map-summary-item {
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  min-height: 4.25rem;
}
.summary-label {
  color: #64748b;
  font-size: 0.78rem;
  margin-bottom: 0.24rem;
}
.summary-value {
  color: #0f172a;
  font-weight: 600;
  font-size: 0.92rem;
}
.map-canvas-wrap {
  position: relative;
  width: 100%;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background:
    radial-gradient(circle at 20% 18%, rgba(56, 189, 248, 0.08), transparent 36%),
    radial-gradient(circle at 84% 78%, rgba(16, 185, 129, 0.08), transparent 32%),
    #ffffff;
  overflow: hidden;
}
.map-canvas {
  width: 100%;
  min-height: 34rem;
  display: block;
}
.map-node-circle {
  cursor: pointer;
  transition: r 0.15s ease, stroke-width 0.15s ease, opacity 0.15s ease;
}
.map-node-short {
  font-size: 0.72rem;
  fill: #0f172a;
  font-weight: 700;
  pointer-events: none;
}
.map-node-label {
  font-size: 0.7rem;
  fill: #334155;
  pointer-events: none;
}
.map-tooltip {
  position: fixed;
  z-index: 1000;
  max-width: 19rem;
  background: rgba(15, 23, 42, 0.95);
  color: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(2, 6, 23, 0.35);
  padding: 0.52rem 0.65rem;
  pointer-events: none;
}
.map-tooltip-title {
  font-size: 0.78rem;
  font-weight: 700;
  margin-bottom: 0.2rem;
}
.map-tooltip-line {
  font-size: 0.74rem;
  color: #e2e8f0;
  line-height: 1.24;
}
.network-monitoring :deep(.card) {
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}
.network-monitoring :deep(.p-datatable .p-datatable-thead > tr > th) {
  white-space: nowrap;
  font-size: 0.82rem;
  padding: 0.62rem 0.6rem;
}
.network-monitoring :deep(.p-datatable .p-datatable-tbody > tr > td) {
  vertical-align: middle;
  font-size: 0.85rem;
  padding: 0.56rem 0.6rem;
}
.table-compact :deep(.p-inputtext),
.table-compact :deep(.p-dropdown),
.table-compact :deep(.p-inputnumber-input) {
  min-height: 2rem;
}
.rules-table :deep(.p-inputnumber),
.rules-table :deep(.p-dropdown),
.rules-table :deep(.p-inputtext) {
  width: 100%;
}
.alert-filter {
  min-width: 12rem;
}
.eff-cell {
  font-size: 0.84rem;
  color: #475569;
  line-height: 1.3;
}
.matrix-wrap {
  overflow: auto;
}
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 4px;
  min-width: 900px;
}
.matrix-table th,
.matrix-table td {
  padding: 0.55rem;
  text-align: center;
  border-radius: 8px;
}
.src-cell {
  text-align: left;
  background: #f8fafc;
  font-weight: 600;
}
.matrix-cell {
  cursor: pointer;
  transition: transform 0.15s ease;
  min-width: 170px;
  min-height: 86px;
}
.matrix-cell:hover {
  transform: translateY(-1px);
}
.cell-main {
  font-weight: 600;
  font-size: 0.8rem;
}
.cell-sub {
  font-size: 0.72rem;
  opacity: 0.9;
}
.cell-up {
  background: rgba(34, 197, 94, 0.18);
  color: #14532d;
}
.cell-down {
  background: rgba(239, 68, 68, 0.18);
  color: #7f1d1d;
}
.cell-unknown {
  background: rgba(245, 158, 11, 0.22);
  color: #78350f;
}
.cell-none {
  background: #e2e8f0;
  color: #475569;
}
.network-monitoring :deep(.p-dialog .p-dialog-content) {
  overflow-x: hidden;
}

@media (max-width: 1360px) {
  .item-template,
  .item-interval {
    grid-column: span 4;
  }
  .item-timeout,
  .item-fail-recover,
  .item-generate {
    grid-column: span 4;
  }
  .bulk-group-actions {
    grid-column: span 6;
  }
  .bulk-interval-group {
    grid-column: span 6;
    grid-template-columns: minmax(11rem, 1fr) auto;
  }
  .bulk-group-probe {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
  .map-summary-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 992px) {
  .item-template,
  .item-interval,
  .item-timeout,
  .item-fail-recover,
  .item-generate,
  .custom-devices-grid .path-master-item {
    grid-column: span 12;
  }
  .bulk-toolbar {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
  .bulk-group-actions,
  .bulk-interval-group,
  .bulk-group-probe {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
  .bulk-interval-group {
    grid-template-columns: 1fr;
  }
  .bulk-input {
    width: 100%;
    min-width: 0;
  }
  .bulk-interval-btn {
    width: 100%;
  }
  .alert-filter {
    min-width: 100%;
  }
  .map-summary-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .map-canvas {
    min-height: 28rem;
  }
}
@media (max-width: 640px) {
  .fail-recover-grid {
    grid-template-columns: 1fr;
  }
  .map-summary-row {
    grid-template-columns: 1fr;
  }
  .map-canvas {
    min-height: 24rem;
  }
}
</style>
