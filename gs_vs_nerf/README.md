# GS vs NeRF (Django + Nerfstudio)

MVP aplikacji do porownania czasu i metryk jakosci dla:
- `vanilla-nerf`
- `vanilla-gaussian-splatting`

Aplikacja przechowuje datasety, zdjecia, orientacje kamer, runy eksperymentow, metryki i artefakty. Zawiera tez podstawowy viewer 3D (`three.js`) do podgladu chmur punktow `.ply`.

## Funkcje

- modele: `Dataset`, `ImageFrame`, `CameraPose`, `ExperimentRun`, `Metric`, `Artifact`
- uruchamianie Nerfstudio przez `ns-train`
- zapis stdout/stderr, czasu wykonania i metryk (`psnr`, `ssim`, `lpips` + `duration_sec`)
- automatyczne wykrywanie artefaktow (`.ply`, `.splat`, `.ckpt`, `.pt`, `.mp4`, `.json`)
- dashboard i szczegoly runa + podglad point cloud w `three.js`

## Wymagania

- Python 3.10.x (zalecane na Windows dla kompatybilności z `av`/Nerfstudio)
- Conda / Anaconda albo Miniconda
- `pip`, `setuptools`, `wheel`, `cython` w aktualnych wersjach
- Nerfstudio z dostępnym poleceniem `ns-train`
- Windows PowerShell lub Linux/macOS shell

## Przygotowanie srodowiska (Windows + Conda)

Najpewniejsza konfiguracja dla tego projektu na Windows to **Conda z Pythonem 3.10**.

1. Otworz **Anaconda Prompt** albo **Anaconda PowerShell Prompt**.
2. Przejdz do katalogu projektu `gs_vs_nerf`.
3. Utworz i aktywuj nowe srodowisko.
4. Zainstaluj zaleznosci Django i dopiero potem Nerfstudio.

```powershell
cd C:\Users\User\PycharmProjects\nerf_vs_gaussian\gs_vs_nerf
conda create -n gs-nerf python=3.10 -y
conda activate gs-nerf
python -m pip install -U pip setuptools wheel cython
pip install -r requirements.txt
```

Jesli chcesz instalowac Nerfstudio lokalnie w tym samym srodowisku, zrob to po aktywacji env:

```powershell
pip install --only-binary=:all: av
pip install nerfstudio
```

Jesli `av` nadal probuje budowac sie ze zrodel i pada, upewnij sie, ze:
- aktywne jest srodowisko `conda` z Pythonem 3.10
- `pip`, `setuptools`, `wheel` i `cython` sa zaktualizowane
- instalujesz Nerfstudio w tym samym env, w ktorym uruchamiasz Django

### Integracja z PyCharm

W PyCharm nie trzeba recznie dodawac Anacondy do PATH. Lepiej ustawic interpreter projektu na srodowisko Conda:

1. `File -> Settings -> Project -> Python Interpreter`
2. `Add Interpreter`
3. `Conda Environment`
4. wybierz `Existing environment` lub `New environment`
5. wskaż interpreter z katalogu env, np. `C:\Users\User\anaconda3\envs\gs-nerf\python.exe`

Po tym terminal w PyCharm moze uzywac tego samego env, jesli aktywujesz je komenda:

```powershell
conda activate gs-nerf
```

## Jak zainstalowac Nerfstudio i uzyskac `ns-train`

Nerfstudio najlepiej instalowac **po zalozeniu i aktywacji** srodowiska Conda.

```powershell
conda activate gs-nerf
pip install nerfstudio
ns-train --help
```

Jesli komenda `ns-train` nie jest znaleziona:
- sprawdz, czy aktywowane jest wlasciwe env
- sprawdz `where ns-train`
- jesli trzeba, ustaw w projekcie zmienna `NERFSTUDIO_BIN` na pelna sciezke do `ns-train.exe`

Przyklad dla PowerShell:

```powershell
$env:NERFSTUDIO_BIN = "C:\sciezka\do\ns-train.exe"
```

## Szybki start (Windows PowerShell + Conda)

Uruchamiaj komendy z katalogu `gs_vs_nerf` (tam sa `manage.py` i `requirements.txt`).

```powershell
conda activate gs-nerf
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Aplikacja jest pod: `http://127.0.0.1:8000/`

## Szybki start (Linux/macOS)

```bash
cd gs_vs_nerf
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Konfiguracja Nerfstudio

Backend uruchamia `ns-train` przez service runner.

Na Windows:

```powershell
$env:NERFSTUDIO_BIN = "C:\sciezka\do\ns-train.exe"
```

Na Linux/macOS:

```bash
export NERFSTUDIO_BIN=/sciezka/do/ns-train
```

Jeśli nie ustawisz `NERFSTUDIO_BIN`, backend zwykle probuje uzyc domyslnego `ns-train` z `PATH`.

## Oczekiwany layout datasetu pod pipeline

`ExperimentRun` wywoluje komende w stylu:

```text
ns-train <pipeline_type> --data <Dataset.data_path> --output-dir <...>
```

Dlatego `Dataset.data_path` musi wskazywac katalog datasetu kompatybilny z Nerfstudio.

Zalecany uklad (COLMAP):

```text
gs_vs_nerf/
  data/
    ilza/
      images/
        IMG_0001.tif
        IMG_0002.tif
        ...
      sparse/
        0/
          cameras.bin
          images.bin
          points3D.bin
```

Uwagi praktyczne:
- Uzywaj prostych nazw plikow bez spacji i bez polskich znakow.
- Dla datasetu `Iłża` obrazy sa w formacie `.tif` i taki layout jest wspierany.
- Nazwy obrazow w `images.bin` musza odpowiadac fizycznym plikom w `images/`.

## Dostosowanie datasetu `Iłża`

Masz obecnie katalog `gs_vs_nerf/Iłża/` z obrazami `.tif` i `0/` z plikami COLMAP.

Rekomendowane kroki:
1. Przenies dane do katalogu roboczego, np. `gs_vs_nerf/data/ilza/`.
2. Umiesc obrazy w `data/ilza/images/`.
3. Umiesc rekonstrukcje COLMAP w `data/ilza/sparse/0/`.
4. Ujednolic nazwy plikow (usun spacje, literowki, nietypowe znaki).
5. W panelu Django ustaw `Dataset.data_path` na absolutna sciezke do `data/ilza`.

Przyklad docelowej wartosci:

```text
C:\Users\User\PycharmProjects\nerf_vs_gaussian\gs_vs_nerf\data\ilza
```

## Konfiguracja runa w Django

Podczas tworzenia `ExperimentRun`:
- `pipeline_type`: `vanilla-nerf` lub `vanilla-gaussian-splatting`
- opcjonalne `config_json`, np.:

```json
{
  "max_num_iterations": 5000,
  "downscale_factor": 0.5
}
```

Runner mapuje te pola na argumenty CLI:
- `max_num_iterations` -> `--max-num-iterations`
- `downscale_factor` -> `--pipeline.datamanager.camera-res-scale-factor`
- `dataparser_type` (opcjonalnie) -> `--pipeline.datamanager.dataparser-type`

Runner automatycznie dobiera parser danych:
- jeśli wykryje `sparse/0/` w datasetcie, ustawia `--pipeline.datamanager.dataparser-type nerfstudio-data` (COLMAP),
- jeśli nie wykryje COLMAP, dataset musi mieć layout Blender (`transforms_train.json`, `transforms_test.json`, `transforms_val.json`) — w przeciwnym razie run zostanie odrzucony na walidacji.

## Runner CLI

Po utworzeniu runa w UI mozna uruchomic go przez management command:

```powershell
python manage.py run_experiment <run_id>
```

## Testy

```powershell
python manage.py test
```

## Troubleshooting

- `conda` not recognized: uruchom **Anaconda Prompt** albo **Anaconda PowerShell Prompt**; w zwyklym PowerShell wpisz `conda activate gs-nerf` dopiero po poprawnej inicjalizacji Condy.
- `source` not recognized: w PowerShell aktywuj srodowisko przez `conda activate gs-nerf`, nie przez `source`.
- `requirements.txt not found`: wejdz do katalogu `gs_vs_nerf` przed `pip install -r requirements.txt`.
- `ns-train not found`: ustaw `NERFSTUDIO_BIN` albo dodaj Nerfstudio do `PATH`.
- Run failuje zaraz po starcie: sprawdz czy `Dataset.data_path` wskazuje poprawny katalog i czy layout datasetu jest zgodny z sekcja powyzej.
- "Brak zdjęć w katalogu" przy importzie: system szuka `images/` wewnątrz folderu. Jeśli go nie ma, przeszukuje sam folder. Upewnij się, że zdjęcia są w jednym z tych miejsc.
- Import pomija pliki: sprawdź, czy rozszerzenia są obsługiwane (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.gif`) i czy nazwy są ASCII (bez polskich znaków).

## Uwagi

- Viewer front-end renderuje tylko `.ply`.
- Dla `.splat` mozna dodac dedykowany renderer albo etap konwersji do `.ply`.
- Aktualny worker jest in-process (MVP); do produkcji zalecane `Celery` lub `RQ`.
