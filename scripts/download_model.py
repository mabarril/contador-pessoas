"""
Script auxiliar para baixar o modelo YOLOv8n.
Requer ultralytics instalado.

Uso:
    poetry run python scripts/download_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    models_dir = Path(__file__).parent.parent / "models"
    models_dir.mkdir(exist_ok=True)

    dest = models_dir / "yolov8n.pt"
    if dest.exists():
        print(f"✅ Modelo já existe: {dest}")
        return

    print("📥 Baixando YOLOv8n...")
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")  # faz download automático pro cache do ultralytics
        # Copia do cache local para models/
        import shutil
        source = Path(model.ckpt_path)  # type: ignore[attr-defined]
        shutil.copy(source, dest)
        print(f"✅ Modelo salvo em: {dest}")
    except ImportError:
        print("❌ ultralytics não instalado. Execute: poetry install")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ Erro ao baixar modelo: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
