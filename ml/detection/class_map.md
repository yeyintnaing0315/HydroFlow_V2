# HydroFlow V2 detection class map

Inventory v2 uses five classes: `fund` (not detected), `foods`, `clothing`, `kitchenware`, and `utilities`. YOLO training is per scannable class; `data.yaml` names must match subclass codes in the catalog.

## Clothing (`clothing`)

| Item code | Inventory name |
| --- | --- |
| `tshirt` | T-shirt |
| `m_longyi` | Men longyi |
| `f_longyi` | Women longyi |

Legacy folder aliases: `male_cloth`, `female_cloth`, `m_cloth`, `f_cloth`.

## Foods (`foods`)

| Item code | Inventory name |
| --- | --- |
| `rice` | Rice |
| `oil` | Oil |
| `canned_fish` | Canned fish |

## Kitchenware (`kitchenware`)

| Item code | Inventory name |
| --- | --- |
| `bowl` | Bowl |
| `knife` | Knife |
| `mug` | Mug |
| `spoon` | Spoon |
| `soap` | Soap |
| `water_dipper` | Water dipper (renamed from `cup`) |
| `plate` | Plate |
| `pot` | Pot |

Legacy weight folder: `utility` (until retrained per class).

## Utilities (`utilities`)

| Item code | Inventory name |
| --- | --- |
| `bednet` | Bed net (renamed from `netbed`) |
| `blanket` | Blanket |
| `towel` | Towel |
| `box` | Box |

## Open Images V7 (weak priors)

| Open Images V7 class | Inventory code |
| --- | --- |
| Bottle | `oil` |
| Bowl | `bowl` |
| Box | `box` |
| Clothing | `tshirt` |
| Dress | `f_longyi` (weak prior only) |
| Coat | `m_longyi` (weak prior only) |
| Knife | `knife` |
| Spoon | `spoon` |
| Coffee cup | map to `water_dipper` when retraining kitchenware |

COCO 2017 priors inside YOLO weights still help bottle, bowl, knife, and spoon.

## Kitchenware YOLOv8 dataset (local)

Build 8-class data from `data/inventory/Raw/Kitchenware`:

```bash
python ml/detection/build_kitchenware_yolo_dataset.py --clean
python ml/train_kitchenware_yolo.py --weights yolov8m.pt --device 0 --batch 4 --epochs 100 --promote
```

Same training via the multi-class script:

```bash
python ml/train_object_detect.py --classes kitchenware --weights yolov8m.pt --epochs 100 --imgsz 640 --device 0 --batch 4 --patience 20 --promote
```

After training, per-epoch metrics are copied to `ml/models/object_detect/kitchenware/training_history.csv` (from Ultralytics `results.csv` under `ml/runs/yolo/run_kitchenware/`). Colab with zip upload: [`Kitchenware_yolov8m_colab_zip.ipynb`](Kitchenware_yolov8m_colab_zip.ipynb).

Output names: `[plate, pot, soap, dipper, mug, bowl, knife, spoon]` in the builder; use `water_dipper` in `data.yaml` when training for the scan UI (see Colab notebook).

## Utilities YOLOv8 dataset (local)

Build 4-class data from `data/inventory/Raw/Utilities` (raw bednet and blanket photos, plus labeled towel and plastic-box Roboflow sets):

```bash
python ml/detection/build_utilities_yolo_dataset.py --clean
python ml/train_object_detect.py --classes utilities --weights yolov8m.pt --epochs 100 --imgsz 640 --device 0 --batch 4 --patience 20 --promote
```

Output: `data/processed/object_detect/utilities/` with names `[bednet, blanket, towel, box]`. Zip for Colab or another PC: `data/processed/object_detect/utilities_yolo_dataset.zip`.

## Clothing YOLOv8 dataset (local)

Build 3-class data from `data/inventory/Raw/Clothing` (raw male/female longyi photos plus labeled T-shirt Roboflow set):

```bash
python ml/detection/build_clothing_yolo_dataset.py --clean
python ml/train_object_detect.py --classes clothing --weights yolov8m.pt --epochs 100 --imgsz 640 --device 0 --batch 4 --patience 20 --promote
```

Output: `data/processed/object_detect/clothing/` with names `[tshirt, m_longyi, f_longyi]`. Zip: `data/processed/object_detect/clothing_yolo_dataset.zip`.
