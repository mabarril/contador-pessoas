# Contador de Pessoas 👥

Sistema standalone de contagem automatizada de pessoas via câmera e IA — projetado para rodar em hardware de baixo custo.

## Ambiente e Compatibilidade

O sistema pode rodar nativamente em **Windows**, **Linux** ou via **WSL** (Windows Subsystem for Linux).
*Nota sobre WSL:* O uso de vídeos (`type: "file"`) e streams RTSP (`type: "rtsp"`) funciona sem configurações extras. Para acessar câmeras USB físicas no WSL, pode ser necessário usar ferramentas como o `usbipd-win`.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Web API | FastAPI + Uvicorn |
| Visão | YOLOv8n (ultralytics) + ByteTrack |
| Banco | SQLite + SQLAlchemy async |
| Config | Pydantic v2 + YAML |
| Scheduler | APScheduler |
| Logging | Loguru |
| Frontend | HTML/CSS/JS puro + Chart.js |

## Instalação

```bash
# 1. Instalar dependências
poetry install

# 2. Baixar modelo YOLOv8n (~6 MB)
poetry run python scripts/download_model.py
```

## Configuração

Edite `config.yaml` para adaptar ao seu ambiente:

```yaml
cameras:
  - id: "entrada-principal"
    name: "Entrada Principal"
    type: "usb"          # usb | rtsp | file
    source: 0            # índice USB, URL RTSP, ou caminho de arquivo
    counting_line:
      orientation: "vertical"  # vertical | horizontal
      position: 0.5            # posição da linha (0.0 a 1.0)
      direction_in: "right"    # direção que conta como entrada
```

## Uso

```bash
# Iniciar o servidor
poetry run contador
# ou
poetry run python -m app.main
```

Acesse o dashboard em: **http://localhost:8000**

## Desenvolvimento com arquivo de vídeo

Para testar sem câmera física, use `type: "file"` no config:

```yaml
cameras:
  - id: "teste"
    name: "Vídeo Teste"
    type: "file"
    source: "data/teste.mp4"
```

## Estrutura

```
app/
├── core/           # Config, detector YOLO, logging
├── db/             # ORM models, session, repositórios
├── sources/        # USB, RTSP, File
├── services/       # Counter (line-crossing), CameraManager
├── api/            # FastAPI app, rotas REST, WebSocket
└── tasks/          # APScheduler (relatórios diários)
frontend/           # Dashboard HTML/CSS/JS
models/             # Modelo YOLOv8n.pt (gerado via download_model.py)
data/               # SQLite DB
logs/               # Logs com rotação
scripts/            # Utilitários
```

## API REST

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/cameras/` | Lista câmeras e estado |
| `GET /api/cameras/{id}/state` | Estado de uma câmera |
| `GET /api/cameras/{id}/stream` | Stream MJPEG |
| `GET /api/reports/{id}/today` | Totais do dia |
| `GET /api/reports/{id}/hourly` | Contagens por hora |
| `GET /api/reports/{id}/summaries?days=7` | Resumos diários |
| `WS /ws` | WebSocket tempo real |

## Testes

```bash
poetry run pytest
```
