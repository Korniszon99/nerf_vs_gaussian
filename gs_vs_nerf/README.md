# GS vs NeRF (Django + Nerfstudio)

MVP aplikacji do porownania czasu i metryk jakosci dla:
- `vanilla-nerf`
- `vanilla-gaussian-splatting`

Aplikacja przechowuje datasety, zdjecia, orientacje kamer, runy eksperymentow, metryki i artefakty. Zawiera tez podstawowy viewer 3D (`three.js`) do podgladu chmur punktow `.ply`.

## Funkcje

- modele: `Dataset`, `ImageFrame`, `CameraPose`, `ExperimentRun`, `Metric`, `Artifact`
- uruchamianie Nerfstudio przez `ns-train` (async z `ThreadPoolExecutor`)
- zapis stdout/stderr, czasu wykonania i metryk (`psnr`, `ssim`, `lpips` + `duration_sec`)
- automatyczne wykrywanie artefaktow (`.ply`, `.splat`, `.ckpt`, `.pt`, `.mp4`, `.json`)
- dashboard i szczegoly runa + podglad point cloud w `three.js`

## Szybki start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Aplikacja jest pod: `http://127.0.0.1:8000/`

## Konfiguracja Nerfstudio

Domyslnie backend uzywa polecenia `ns-train`.
Mozesz podmienic binarke:

```bash
export NERFSTUDIO_BIN=/sciezka/do/ns-train
```

Przykladowa konfiguracja JSON runa:

```json
{
  "max_num_iterations": 5000,
  "downscale_factor": 0.5
}
```

## Runner CLI (tiny harness)

Po utworzeniu runa w UI mozna uruchomic go synchronicznie:

```bash
python manage.py run_experiment <run_id>
```

## Testy

```bash
python manage.py test
```

## Uwagi

- Viewer front-end renderuje tylko `.ply`.
- Dla `.splat` mozna dodac dedykowany renderer (np. webgl plugin do gaussian splatting) albo etap konwersji do `.ply`.
- Aktualny async worker jest in-process (MVP). Do produkcji zalecane `Celery`/`RQ`.

