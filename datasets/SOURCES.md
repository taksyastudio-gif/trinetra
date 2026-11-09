# Trinetra External Dataset Registry & Training Sources

This registry catalogs external and localized datasets for training, evaluation, and benchmark scenarios across Trinetra's assistive vision, navigation, and localized perception models.

---

## 1. Banknote & Currency Recognition

### Nepali Currency Dataset (Authentic & Counterfeit)
- **Source**: [Kaggle - prapannadhungel/nepali-currency-dataset](https://www.kaggle.com/datasets/prapannadhungel/nepali-currency-dataset)
- **Contents**: High-resolution imagery of Nepali banknotes (5, 10, 20, 50, 100, 500, 1000 NPR) featuring both genuine and fake notes.
- **Trinetra Target Module**: `services/vision-engine/app/capabilities/currency.py` & `tools/train_and_export_currency.py`
- **Application**: Banknote denomination identification and counterfeit detection for visually impaired users.
- **Trigger**: Ingest and train on command `"code train it"`.

---

## 2. Computer Vision & Localized Perception

### The Nepali Vehicles Dataset
- **Source**: [GitHub - ishworrsubedii/nepali-vehicles-dataset](https://github.com/ishworrsubedii/nepali-vehicles-dataset) & [sdevkota007/vehicles-nepal-dataset](https://github.com/sdevkota007/vehicles-nepal-dataset)
- **Status**: **Fully Ingested & Trained** (4,797 images: 1,823 two-wheelers, 2,974 four-wheelers).
- **Key Characteristics**: Localized Kathmandu traffic environments with motorcycles, scooters, microbuses, safa tempos, trucks, and buses.
- **Trained Model**: `TrinetraVehicleNet` exported to [`nepali_vehicles.onnx`](file:///d:/trinetra/services/vision-engine/models/vehicles/v1/nepali_vehicles.onnx) (100.2 KB, 96.01% validation accuracy).
- **Trinetra Target Module**: [`app/detection/vehicle_classifier.py`](file:///d:/trinetra/services/vision-engine/app/detection/vehicle_classifier.py)
- **Application**: Real-time localized traffic perception, classifying two-wheelers vs four-wheelers with spoken Nepali/English pedestrian collision warnings.

### Nepali Portraits / Demographics Dataset
- **Source**: [Kaggle - sumansid/nepali-portraits-dataset](https://www.kaggle.com/datasets/sumansid/nepali-portraits-dataset)
- **Contents**: Localized portrait and augmented face data for Nepali demographic features.
- **Trinetra Target Module**: Person awareness and demographic verification.
- **Governance Note**: Must comply with Trinetra's Local-First Privacy Policy (`docs/PRIVACY.md` and `datasets/README.md`) — no biometric storage or unconsented facial surveillance.

---

## 3. Geospatial, Road Quality & Infrastructure

### Nepal Road Surface Data (HDX / HeiGIT)
- **Source**: [Humanitarian Data Exchange (HDX) / HeiGIT](https://data.humdata.org/dataset/nepal-road-surface-data)
- **Contents**: OpenStreetMap road networks enriched with deep learning predictions from Mapillary street-level imagery across Nepal.
- **Attributes**: Road surface types (paved, unpaved, gravel), pavement conditions, and sidewalk layout presence.
- **Trinetra Target Module**: `GroundHazardDetector` (`app/detection/ground_hazard.py`) & offline map caching.
- **Application**: Prior probabilities for tactile surface hazards, drop-offs, and sidewalk walkability.

### Open Data Nepal — Transport Datasets
- **Source**: [Open Data Nepal (Transport Tag)](https://opendatanepal.com/dataset?tags=Transport)
- **Contents**: Historical transport network statistics, road length classifications, and survey data from the Department of Roads (DoR) and Central Bureau of Statistics.
- **Trinetra Target Module**: Spatial path planning and regional hazard profiling.

---

## 4. Behavioral & Pedestrian Traffic Safety (Kathmandu)

### Pedestrian Red Light Violation Behavior Dataset (Kathmandu)
- **Source**: [ScienceDirect (Safety Science / SOTEN)](https://www.sciencedirect.com/science/article/pii/S2590198224000216)
- **Contents**: Videographic tracking data of 1,790 pedestrians (1,253 train / 537 test) at high-density Kathmandu crosswalks.
- **Attributes**: Crossing styles, pedestrian-vehicle conflicts, group crossing behaviors, phone distractions, and compliance metrics.
- **Trinetra Target Module**: `KalmanTracker` trajectory collision prediction & `app/detection/decision.py`.
- **Application**: Predicting chaotic vehicle/pedestrian trajectory conflicts at unsignalized or poorly-regulated Kathmandu crosswalks.

### Pedestrian Level of Service (PLOS) Crosswalk Dataset
- **Source**: Tribhuvan University (TU) Central Library eLibrary
- **Contents**: Empirical crossing metrics in Kathmandu intersections: average walking speeds by demographic, non-compliance rates (up to 98%), crossing delays, and conflict densities.
- **Trinetra Target Module**: Audio alert timing calibration (safe crossing window calculations).

---

## 5. Sign Language & Non-Verbal Communication

### Nepali Sign Language (NSL) Character Dataset
- **Source**: [GitHub - Birat-Poudel/Nepali-Sign-Language-Recognition-and-Translation](https://github.com/Birat-Poudel/Nepali-Sign-Language-Recognition-and-Translation) & [Kaggle - biratpoudelrocks/nepali-sign-language-character-dataset](https://www.kaggle.com/datasets/biratpoudelrocks/nepali-sign-language-character-dataset)
- **Contents**: 1,440 images across 36 Nepali Sign Language classes (Devanagari consonants क to ज्ञ: 40 images per character).
- **Status**: **Fully Ingested & Trained** into `TrinetraNSLNet` (116.8 KB ONNX model, <10ms CPU inference).
- **Trained Model**: [`nepali_sign_language_36.onnx`](file:///d:/trinetra/services/vision-engine/models/signs/v1/nepali_sign_language_36.onnx) & metadata [`nepali_sign_language_36.json`](file:///d:/trinetra/services/vision-engine/models/signs/v1/nepali_sign_language_36.json).
- **Trinetra Target Module**: [`NepaliSignLanguageNeuralClassifier`](file:///d:/trinetra/services/vision-engine/app/detection/sign_interpreter.py).
- **Application**: Translates authentic Nepali Sign Language finger-spelling (क to ज्ञ) directly into spoken Nepali voice synthesis and high-contrast captions.

### Sign Language MNIST Dataset
- **Source**: [Kaggle - datamunge/sign-language-mnist](https://www.kaggle.com/datasets/datamunge/sign-language-mnist)
- **Contents**: 28x28 grayscale images mapped to hand gestures / fingerspelling alphabet classes (A–Z, excluding J & Z requiring temporal motion).
- **Trinetra Target Module**: `SignInterpreter` (`services/vision-engine/app/detection/sign_interpreter.py`)
- **Application**: Training lightweight CNN/ONNX classifier for rapid offline finger-spelling and gesture-to-speech translation, complementing Trinetra's prototype hand gesture dictionary.

