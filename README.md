# Camera Stream

Сервис запускает `ffmpeg` для RTSP-камер, пишет HLS в общий volume и отдает:

- `GET /player/{camera_id}` через FastAPI
- `/streams/{camera_id}/index.m3u8` и сегменты через nginx

Для HLS-статики лучше использовать nginx: он эффективнее раздает `.m3u8` и `.ts`, умеет корректно выставлять cache headers и не занимает Python-процессы статикой. FastAPI здесь остается тонким слоем для HTML-плеера и управления жизненным циклом `ffmpeg`.

## Запуск

```bash
docker compose up --build
```

Открыть плеер:

```text
http://localhost:8080/player/cam_1
http://localhost:8080/player/cam_10
https://localhost:8443/player/cam_1
https://localhost:8443/player/cam_10
```

## HTTPS без домена

Доверенный Let's Encrypt сертификат через certbot нельзя выпустить без домена:
ACME-проверка должна подтвердить владение DNS-именем. Для запуска по IP compose
поднимает init-контейнер `certbot-selfsigned` на базе образа `certbot/certbot`,
который один раз генерирует self-signed сертификат в volume `certbot-etc`.

По умолчанию сертификат содержит `DNS:camera-stream.local` и `IP:127.0.0.1`.
Для доступа с другого устройства укажите IP сервера:

```bash
HTTPS_CERT_IP=192.168.1.50 docker compose up -d --build
```

После этого плеер будет доступен по адресу:

```text
https://192.168.1.50:8443/player/cam_1
```

Браузер покажет предупреждение о недоверенном сертификате, потому что сертификат
self-signed. Если нужно пересоздать сертификат с другим IP/CN, удалите volume и
поднимите compose заново:

```bash
docker compose down
docker volume rm camera-stream_certbot-etc
HTTPS_CERT_IP=192.168.1.50 docker compose up -d --build
```

Для своего конфига:

```bash
cp config.example.yml config.yml
CAMERAS_CONFIG_FILE=./config.yml docker compose up --build
```

## Настройки

Настройки проекта читаются через `starlette.config.Config` из переменных окружения или `.env`.

| Переменная | По умолчанию |
| --- | --- |
| `CAMERAS_CONFIG` | `config.yml` |
| `HLS_DIR` | `/var/lib/camera-stream/hls` |
| `FFMPEG_PATH` | `ffmpeg` |
| `HLS_SEGMENT_TIME` | `2` |
| `HLS_LIST_SIZE` | `6` |
| `STREAM_RESTART_DELAY` | `5` |

Конфиг камер хранится в YAML:

```yaml
cameras:
  - id: front_door
    name: Front door
    rtsp_url: rtsp://user:password@192.168.1.10:554/stream1
    enabled: true
    transcode: false
```

`transcode: false` — легкий режим, `ffmpeg` делает `-c:v copy`; подходит для слабого сервера, если камера отдает H.264 substream.

`transcode: true` — совместимый режим, `ffmpeg` перекодирует в H.264 через `libx264`; надежнее для браузера, но сильно грузит CPU.
