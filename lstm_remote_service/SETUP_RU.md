# Настройка LSTM-ПК под Manjaro/Arch (AMD ROCm + Tailscale)

Документ для вашего сценария: отдельный LSTM-ПК на Manjaro/Arch, доступ к API через Tailscale.

## 1. Важный статус поддержки

- AMD официально в первую очередь таргетирует Ubuntu/RHEL для ROCm.
- На Arch/Manjaro рабочий вариант обычно строится на пакетах дистрибутива (`rocm-*`, `python-pytorch-rocm`).
- Поэтому это практический путь для Arch, но с учетом rolling-release рисков (обновления могут ломать стек).

Если нужна максимальная стабильность на месяцы без сюрпризов, лучше выделить Ubuntu LTS под LSTM.

## 2. Что нужно установить на LSTM-ПК

## 2.1. Обновить систему

```bash
sudo pacman -Syu
```

## 2.2. Установить базовые пакеты

```bash
sudo pacman -S --needed git base-devel python python-pip python-virtualenv tailscale
```

## 2.3. Установить ROCm + PyTorch ROCm

```bash
sudo pacman -S --needed rocm-hip-sdk rocm-opencl-runtime rocminfo rocm-smi-lib python-pytorch-rocm
```

Если на вашей ветке Manjaro какого-то пакета нет, проверьте синхронизацию ветки или используйте AUR/другую ветку. 

## 2.4. Дать доступ к GPU-устройствам

```bash
sudo usermod -aG render,video $USER
```

После этого сделайте logout/login (или reboot), чтобы группы применились.

## 3. Подготовка проекта

## 3.1. Клонировать репозиторий

```bash
git clone <repo_url> TechTracker
cd TechTracker/lstm_remote_service
```

## 3.2. Создать venv с доступом к системному PyTorch ROCm

Важно: `python-pytorch-rocm` установлен через `pacman` в system site-packages.
Чтобы venv видел этот `torch`, используем `--system-site-packages`.

```bash
python -m venv .venv --system-site-packages
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.arch.txt
```

## 3.3. Проверка, что PyTorch видит AMD GPU

```bash
source .venv/bin/activate
python -c "import torch; print('torch', torch.__version__); print('hip', torch.version.hip); print('cuda_available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

Ожидаемо:
- `torch.cuda.is_available() == True`
- устройство: `Radeon RX 7800 XT`

## 4. Настройка Tailscale

## 4.1. Поднять tailscaled

```bash
sudo systemctl enable --now tailscaled
sudo tailscale up
```

## 4.2. Узнать Tailscale IP

```bash
tailscale ip -4
```

Пример: `100.88.10.24`

## 4.3. Проверить доступность с backend

С backend-сервера должен пинговаться Tailscale IP LSTM-ПК.

## 5. Настройка переменных LSTM сервиса

Создать `.env`:

```bash
cp .env.example .env
```

Рекомендуемые параметры для AMD ROCm:

```env
LSTM_API_TOKEN=<СИЛЬНЫЙ_ТОКЕН>
LSTM_MAX_WORKERS=2
LSTM_DEFAULT_EPOCHS=60
LSTM_DEFAULT_LOOKBACK=168
LSTM_DEFAULT_HIDDEN_SIZE=96
LSTM_DEFAULT_LR=0.001
LSTM_DEFAULT_DROPOUT=0.15
LSTM_DEFAULT_WEIGHT_DECAY=0.00001
LSTM_DEFAULT_BATCH_SIZE=64
LSTM_DEFAULT_SEASONALITY_MODE=rolling_profile
LSTM_DEFAULT_SEASONALITY_WINDOW_DAYS=14
LSTM_DEFAULT_LOSS_KIND=quantile
LSTM_DEFAULT_OUTPUT_MODE=direct_multi_horizon
LSTM_DEFAULT_TRAIN_MODE=fit_on_request
LSTM_DEFAULT_TARGET_MODE=anchored_delta
LSTM_DEFAULT_RECENCY_WEIGHTED_LOSS=1
LSTM_DEFAULT_RECENCY_WEIGHT_MIN=0.35
LSTM_DEFAULT_RECENCY_WEIGHT_POWER=2.0
LSTM_MAX_POINTS_PER_METRIC=4000
LSTM_CHECKPOINT_DIR=/home/<user>/TechTracker/lstm_remote_service/artifacts/checkpoints

LSTM_TORCH_DEVICE=cuda
LSTM_TORCH_AMP=0
LSTM_TORCH_GPU_INDEX=0
```

Новые дефолты нужны не “для красоты”, а чтобы модель не занижала уровень прогноза:
- `lookback=168` даёт видеть хотя бы недельный цикл;
- `epochs=60`, `hidden_size=96` дают модели шанс выучить и тренд, и рабочую/ночную сезонность;
- `rolling_profile` считает сезонность по последним неделям, а не по всей старой истории;
- `quantile` сразу учит `p10/p50/p90`, а не достраивает интервалы эвристикой.
- `anchored_delta` заставляет модель продолжать текущее состояние, а не падать к среднему уровню по всей истории.
- recency-weighted loss даёт последним окнам больший вес, чтобы модель сильнее уважала недавний рост/сдвиг режима.

Опции модели в payload (если не передать, берутся дефолты):
- `use_calendar_features=true` — календарные признаки (час/день недели + рабочее окно/обед/бэкап).
- `use_seasonal_residual=true` — LSTM по десезонализированному ряду + возврат сезонного профиля.
- `seasonality_mode=rolling_profile` — сезонность строится по недавнему окну, а не по всей истории.
- `lags=[1,24,168]` — короткий лаг, суточный лаг, недельный лаг.
- `loss_kind=quantile` — прямое обучение интервалов `p10/p50/p90`.
- `output_mode=direct_multi_horizon` — модель сразу предсказывает всю траекторию горизонта.
- `train_mode=fit_on_request|warm_start` — обычное обучение на запросе или дообучение от checkpoint.
- `target_mode=anchored_delta|absolute_level` — прогноз как отклонение от текущего состояния или как абсолютный уровень.
- `recency_weighted_loss=true` — последние окна истории важнее старых.
- `recency_weight_min`, `recency_weight_power` — насколько сильно усиливать последние окна.
- `workday_start`, `workday_end`, `lunch_start`, `lunch_end`, `workday_weekdays`, `backup_start`, `backup_end`, `backup_weekdays`.

Примечание: в PyTorch для ROCm используется API-имя `cuda`.

## 6. Ручной запуск сервиса

```bash
cd /home/<user>/TechTracker/lstm_remote_service
source .venv/bin/activate
set -a
source .env
set +a
uvicorn app.main:app --host 0.0.0.0 --port 8099
```

Проверка локально:

```bash
curl http://127.0.0.1:8099/health
```

## 7. Автозапуск через systemd

Файл `/etc/systemd/system/techtracker-lstm.service`:

```ini
[Unit]
Description=TechTracker LSTM Remote API (Manjaro/Arch)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=<user>
Group=<user>
WorkingDirectory=/home/<user>/TechTracker/lstm_remote_service
EnvironmentFile=/home/<user>/TechTracker/lstm_remote_service/.env
ExecStart=/home/<user>/TechTracker/lstm_remote_service/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8099
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Применить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now techtracker-lstm
sudo systemctl status techtracker-lstm
sudo journalctl -u techtracker-lstm -f
```

## 8. Что настроить на backend-сервере

Используйте Tailscale IP LSTM-ПК:

```env
LSTM_REMOTE_API_BASE_URL=http://100.88.10.24:8099
LSTM_REMOTE_API_TOKEN=<тот_же_токен_что_в_LSTM_API_TOKEN>
LSTM_REMOTE_TIMEOUT_SEC=20
LSTM_REMOTE_VERIFY_SSL=0
```

## 9. Проверка end-to-end

## 9.1. Проверить health с backend

```bash
curl -H "X-API-Key: <token>" http://100.88.10.24:8099/health
```

## 9.2. Поставить job в очередь

```bash
.venv/bin/python manage.py run_forecast_lstm_remote --serial <SERIAL> --no-wait --max-retries 5
```

## 9.3. Обработать очередь

```bash
.venv/bin/python manage.py poll_forecast_lstm_remote --limit 100 --poll-interval-sec 10
```

## 9.4. Убедиться, что использовалась GPU

Проверить `quality.runtime` результата job (`/v1/jobs/{job_id}`):
- `device: "cuda:0"`
- `device_name` содержит `RX 7800 XT`

## 10. Частые проблемы на Manjaro/Arch

1. `torch.cuda.is_available() == False`
- не применились группы `render/video`;
- после обновления сломался стек `rocm`/`python-pytorch-rocm`;
- версия ядра и пакеты ROCm временно несовместимы.

2. `Connection refused` с backend
- сервис `techtracker-lstm` не запущен;
- backend использует неверный Tailscale IP.

3. После больших обновлений системы GPU пропала
- обычный кейс для rolling release; проверьте версии `rocm-*` и `python-pytorch-rocm`, затем перезапуск/перелогин.
