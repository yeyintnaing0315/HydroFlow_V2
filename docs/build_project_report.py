"""Build the HydroFlow V2 project book (docx, then pdf when a converter exists).

Numbers in the chapters come from the served model metadata:
ml/models/bago_flood_model_metadata.json and
ml/models/bago_flood_model_logistic_metadata.json.
The earlier twelve-feature repair is described only as a prior study.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips

ROOT = Path(__file__).resolve().parents[1]
DOCS = Path(__file__).resolve().parent
DOCX_PATH = DOCS / "HydroFlow_V2_Project_Report.docx"
PDF_PATH = DOCS / "HydroFlow_V2_Project_Report.pdf"
CONTENT_PATH = DOCS / "HydroFlow_V2_Project_Content.md"
CONTENT_DOCX_PATH = DOCS / "HydroFlow_V2_Project_Content.docx"

HGB_TEST = {
    "precision": "0.0113",
    "recall": "0.6364",
    "f1": "0.0222",
    "pr_auc": "0.0085",
    "roc_auc": "0.8684",
    "accuracy": "0.9235",
    "threshold": "0.05",
    "rows": "8,052",
    "flood_rows": "11",
    "tn": "7,429",
    "fp": "612",
    "fn": "4",
    "tp": "7",
}
HGB_VALIDATION = {
    "precision": "0.0701",
    "recall": "0.2874",
    "f1": "0.1127",
    "pr_auc": "0.0624",
    "roc_auc": "0.8222",
    "accuracy": "0.9059",
    "rows": "8,030",
    "flood_rows": "167",
    "tn": "7,226",
    "fp": "637",
    "fn": "119",
    "tp": "48",
}
LOGISTIC_TEST = {
    "precision": "0.0025",
    "recall": "0.0909",
    "f1": "0.0048",
    "pr_auc": "0.0063",
    "roc_auc": "0.7950",
    "accuracy": "0.9490",
    "threshold": "0.87",
    "tn": "7,640",
    "fp": "401",
    "fn": "10",
    "tp": "1",
}


def _entry(sno: str, chapter: str, title: str, level: int, paragraphs: list[str], tables: list | None = None):
    return {
        "sno": sno,
        "chapter": chapter,
        "title": title,
        "level": level,
        "paragraphs": paragraphs,
        "tables": tables or [],
        "probe": re.sub(r"\s+", " ", paragraphs[0])[:70],
    }


def report_entries() -> list[dict]:
    return [
        _entry(
            "1",
            "—",
            "Acknowledgment",
            1,
            [
                "The author thanks the project guide for supervision, technical comment, and the time given to reviewing this work. The teaching staff and the computing facilities of the institution made the prototype possible.",
                "Colleagues who discussed the rainfall records, the township maps, and the limits of an academic prototype improved the clarity of the result. Families and friends provided the patience required to finish the book.",
                "The names of the guide, the candidate, the degree, and the institution are left in brackets on the cover because they are not recorded in the HydroFlow V2 source tree. They should be written in before submission.",
            ],
        ),
        _entry(
            "2",
            "—",
            "Abstract",
            1,
            [
                "Flood response in Bago Region needs an early view of where heavy rain and rising river discharge may coincide with communities that later appear in relief records. HydroFlow V2 is an academic prototype for twenty-three townships. It joins a flood-occurrence score, a short assistance illustration, and a camera count of relief goods.",
                "The served flood classifier is a histogram gradient boosting model with fifteen hydrometeorological features. The candidate saved in the model file is hgb-depth3. Its decision threshold of 0.05 is chosen on a chronological validation block, and the final test block is left untouched. On 8,052 test township-days, of which 11 are flood days, the model records precision 0.0113, recall 0.6364, F1 0.0222, and precision-recall area 0.0085.",
                "A class-weighted logistic regression uses the same fifteen features and the same split. It is retained as an interpretable baseline. The prediction service loads the histogram model, not the logistic file. A rule that always predicts no flood is accurate on this sparse test block, so accuracy is reported beside precision and recall and is not treated as evidence of skill.",
                "The interface has a home view, a flood-outlook map, a resource-allocation view, and an inventory view. Assistance counts use fixed planning ratios. Routes are drawn from township centroids. The prototype demonstrates an end-to-end workflow. It is not validated for public warnings, caseload estimates, or dispatch.",
            ],
        ),
        _entry(
            "3",
            "—",
            "Table of Contents",
            1,
            [
                "Front matter is numbered in roman numerals. Chapters are numbered in arabic numerals from 1. The Page column uses those printed numbers.",
            ],
        ),
        _entry(
            "4",
            "Chapter 1",
            "Introduction",
            1,
            [
                "Bago Region sits on a low floodplain where monsoon rain and river discharge can rise together. A township office that plans relief still has to look across weather, past flood days, population, stock, and the road to the next township. HydroFlow V2 is a single academic workspace for that inspection.",
                "The unit of analysis for the flood model is a township-day. The label is the observed relief flood flag stored with the daily table. The model file states that no synthetic flood rows were added. A positive label means a flood day present in the available relief records. It is not a complete hydrological inventory of every inundated field.",
            ],
        ),
        _entry(
            "5",
            "1.1",
            "Purpose of the Project",
            2,
            [
                "The purpose of the project is to show a correct path from stored and live hydrometeorological inputs to a township flood score, a short planning illustration, and a count of relief goods. The path is meant for study and demonstration.",
                "The served score comes from a saved scikit-learn histogram gradient boosting classifier. The application loads that file and does not retrain when a user opens the map. A second file, a class-weighted logistic regression, is kept so the same features and the same untouched test block can be read in a linear form.",
                "The purpose stops at the academic prototype. Outputs on the screen are labeled as prototype results. They are not an instruction to issue a public warning or to dispatch a truck.",
            ],
        ),
        _entry(
            "6",
            "1.2",
            "Objectives of the Project",
            2,
            [
                "The first objective is to train and serve a flood-occurrence model on a chronological split of Bago township-days, with the test block held out from fitting, calibration, and threshold selection.",
                "The second objective is to keep an interpretable logistic baseline on the same fifteen features, so model selection can be explained with precision, recall, F1, and precision-recall area rather than with accuracy alone.",
                "The third objective is to place that score in a working system: a FastAPI service, a React map, a resource-allocation screen, and an inventory screen that can count foods, clothing, kitchenware, and utilities from a photograph or a video.",
                "The fourth objective is to state the limits in the same book as the scores. Rainfall in the training table is reanalysis. River discharge is modeled GloFAS discharge. Impact counts used for planning are illustrations tied to relief records, census context, or the flood score.",
            ],
        ),
        _entry(
            "7",
            "1.3",
            "Problem Definition",
            2,
            [
                "Given a township and a date, the flood problem is to estimate whether that township-day matches the relief flood flag, using only inputs that can be assembled from rainfall, modeled discharge, temperature, humidity, wind, location, and the day of the year.",
                "The class is rare. The served metadata records 39,534 township-days with complete features and drops 638 rows for missing features. The validation block has 8,030 rows and 167 flood rows. The test block has 8,052 rows and 11 flood rows. A classifier can look accurate by predicting no flood on almost every day.",
                "A second problem sits beside the score. After a high or severe day, a planner still needs a picture of people and households, a three-day package of shelter, food, and water, a route between township centroids, and a count of what is already in store. HydroFlow V2 treats those as linked screens, not as a claim that the counts are a field assessment.",
            ],
        ),
        _entry(
            "8",
            "1.4",
            "Existing System and Limitations",
            2,
            [
                "Before this prototype, the practical tools were separate. Weather and discharge came from public archives. Flood days and impact counts lived in relief workbooks. Population context lived in the census extract. Stock was a paper or spreadsheet count. A map, a model, and a route were not one workflow.",
                "An operational forecasting chain that uses machine learning still depends on maintained forecasts, exposure, and local verification [1]. A general review of flood prediction with machine learning collects tree ensembles, linear classifiers, and neural networks as separate families [2]. Those systems depend on labels and measurements that this project does not have for every township-day.",
                "The limitation that shapes HydroFlow V2 is the label itself. Relief flags are incomplete, positives are concentrated in time, and the untouched test block contains only eleven flood days. An earlier twelve-feature logistic repair, kept as a separate study, removed retrospective soil fields so that a future date could be scored, and its flood F1 was about 0.029. That experiment is not the model loaded by the current prediction service. The service loads the fifteen-feature histogram model described in later chapters.",
            ],
        ),
        _entry(
            "9",
            "1.5",
            "Organization of the Project",
            2,
            [
                "Chapter 2 reviews flood prediction, imbalanced evaluation, leakage, humanitarian planning quantities, and camera detection of relief goods. Chapter 3 describes the two flood classifiers, the application services, the preparation of relief and inventory data, the fifteen numeric features, storage, the external inputs, the controls on leakage and claims, request handling, and the workflow.",
                "Chapter 4 states the scope, the source files, preprocessing, the technical stack, and how the service and the interface are implemented. Chapter 5 reports the untouched test scores, compares the logistic baseline with the served histogram model, describes the screens, and records how testing is organized. Chapter 6 summarizes the work, lists the limits, and names extensions that would require new labels and an independent review.",
            ],
        ),
        _entry(
            "10",
            "Chapter 2",
            "Literature Review",
            1,
            [
                "Machine learning for flood prediction is reviewed as a family of methods rather than as a single accepted model [2]. Tree ensembles, logistic models, and neural networks all appear in that literature. Random forests are a standard ensemble baseline in the wider machine-learning literature [3]. An earlier comparison sat beside a random-forest score, and this project does not serve a random forest. The served model belongs to the gradient boosting family introduced for additive stagewise fitting [4], in the histogram form provided by scikit-learn [5].",
                "Rainfall-runoff studies have also used long short-term memory networks when long gauged series exist [6]. HydroFlow V2 does not serve a recurrent network. The daily table is a township panel with a sparse relief flag, and the evaluation design in this book is a single chronological holdout rather than a sequence model trained on gauge traces.",
                "Operational flood forecasting with machine learning has been demonstrated where forecasts, exposure, and verification are maintained as a service [1]. Global river discharge from GloFAS is a modeled field, produced by a hydrological chain forced with meteorological reanalysis, and it is not a reading from a local staff gauge [7]. HydroFlow V2 uses that modeled discharge, together with Open-Meteo rainfall [8] and NASA POWER meteorology for temperature, humidity, and wind [9]. Copernicus elevation is used as map context. It is a surface model and includes canopy and buildings [10]. It is not one of the fifteen model inputs.",
                "Leakage is the use of information that would not be known at the time of prediction [11]. The training script for the served model keeps the saved chronological split, checks that training dates end before validation and that validation ends before the test, and writes a flag that the test block was not used for training, calibration, or the threshold. Rolling rainfall totals are computed inside each township. Discharge inputs are lagged by one day so the discharge features do not copy the same-day value.",
                "When positives are rare, a precision-recall curve is more informative than accuracy or a receiver-operating curve used alone [12]. The test block here has eleven flood days in 8,052 rows. The metadata also records a majority-class accuracy of 0.9986 for a prediction of no flood on every test row. Chapter 5 therefore leads with precision, recall, F1, and precision-recall area.",
                "Humanitarian planning has published minimum quantities for water, food, and shelter in the Sphere handbook [13]. The software multiplies expected people and households by fixed ratios: one shelter kit per household, three food rations per person across three days, and fifteen litres of drinking water per person per day. Those ratios are planning multipliers in the prototype. They are not a field assessment and they are not a claim that a distribution meets the handbook.",
                "Counting relief goods from a camera is a detection problem. The original detection framework locates objects in one pass [14]. The training runs in this project use the Ultralytics implementation [15]. Four detectors are trained separately for foods, clothing, kitchenware, and utilities. The catalog class fund is not given a detector.",
            ],
        ),
        _entry(
            "11",
            "Chapter 3",
            "Methodology and Techniques",
            1,
            [
                "This chapter states the methods that turn a Bago township-day into a flood class, a risk band, an assistance illustration, and a stock count. The prediction service loads one flood artifact, a histogram gradient boosting classifier saved as hgb-depth3. A class-weighted logistic regression is trained on the same rows and the same fifteen features so Chapter 5 has a linear baseline. Assistance figures, routes, and inventory counts follow their own rules.",
                "The unit of analysis is the township-day. The label is the relief flood flag on the validated daily table: a flood day that appears in the available relief records. The flag is an incomplete indicator. The metadata records that no synthetic flood rows were added. The served artifact names twenty-two townships: Bago, Daik-U, Htantabin, Kawa, Kyauktaga, Madauk, Minhla, Monyo, Okpho, Oktwin, Pantaung, Pyay, Pyu, Shwedaung, Shwegyin, Taungoo, Thanatpin, Thayarwady, Thegon, Waw, Yedashe, and Zigon.",
                "After feature construction, 39,534 rows have every served input and the flood flag. Six hundred and thirty-eight rows are dropped because a required feature is missing. The chronological assignment is the saved file data/processed/split_assignments.csv. The validation block holds 8,030 rows, including 167 flood days. The test block holds 8,052 rows, including 11 flood days. The trainer uses that file. It does not redraw the split at fit time.",
            ],
        ),
        _entry(
            "12",
            "3.1",
            "Machine-Learning Approaches for Flood Occurrence",
            2,
            [
                "Both flood classifiers answer the same question: does the township-day carry the relief flood flag. Both see the fifteen columns in section 3.4 and the same chronological assignment of rows to train, validation, and test. For the histogram model, preprocessing is the feature construction in the training script. Rows that still miss any required column, or that miss the flag, are removed. For the logistic model, a median imputer and a standard scaler are fitted on the training rows only and stored inside the pipeline.",
                "Histogram candidates are compared by validation average precision, the area under the precision-recall curve. That curve is the selection metric because flood days are rare, so accuracy would favour a prediction of no flood on every row. After one candidate is kept, an isotonic calibrator is fit on its validation scores. The decision threshold for either classifier is then the point on the grid from 0.01 to 0.99, in steps of 0.01, that maximizes flood-class F1 on the validation block. The test block is scored only after that threshold is frozen. That order is the method behind the tables in Chapter 5.",
            ],
        ),
        _entry(
            "13",
            "3.1.1",
            "Class-Weighted Logistic Regression (interpretable baseline)",
            3,
            [
                "The baseline is sklearn.linear_model.LogisticRegression with balanced class weights, the liblinear solver, and a maximum of 2,000 iterations. Balanced weights raise the influence of the rare flood class during fitting, because a township panel contains far more non-flood days than flood days. Numeric columns pass through a median imputer and a standard scaler. The imputer, the scaler, and the classifier are saved as one scikit-learn pipeline. The imputer statistics and the scaler mean and scale come from the training block only.",
                "The decision threshold is the validation threshold that maximizes flood-class F1. The saved threshold is 0.87. The metadata marks the file as secondary and names hist_gradient_boosting as the primary model. Coefficients remain available for inspection because the classifier is linear in the scaled features. A reader can see the direction and relative size of each input after standardization. The prediction service resolves ml/models/bago_flood_model.joblib. It does not load the logistic file when it scores a township-day.",
            ],
        ),
        _entry(
            "14",
            "3.1.2",
            "Histogram Gradient Boosting (served flood model)",
            3,
            [
                "The served classifier is sklearn.ensemble.HistGradientBoostingClassifier. Histogram gradient boosting bins each numeric feature and grows an additive sequence of trees on those bins. Each candidate uses a learning rate of 0.05, a maximum of 300 iterations, an L2 penalty of 1.0, early stopping, and random_state 42. Three candidates are fit on the training block only. The first, hgb-depth3, has maximum depth 3 and at least 20 samples in a leaf. The second, hgb-depth3-balanced, uses the same tree size with balanced class weight. The third, hgb-depth4, has maximum depth 4 and at least 10 samples in a leaf. The candidate with the highest validation precision-recall area is kept. The saved name is hgb-depth3.",
                "An isotonic calibrator is fitted on the raw validation probabilities of that candidate. The calibrator is sklearn.isotonic.IsotonicRegression with outputs clipped to the unit interval. It maps the tree scores onto empirical frequencies observed on the validation block. The F1 search for the threshold then runs on the calibrated validation probabilities and selects 0.05. Test probabilities are produced only after that choice. The metadata flag test_used_for_training_calibration_or_threshold is false. The trees and the calibrator are stored together and loaded as one object.",
                "The fifteen inputs are the one-day, three-day, seven-day, fourteen-day, and thirty-day rainfall totals; temperature; relative humidity; wind speed; latitude; longitude; the sine and cosine of the day of the year; the previous day's modeled discharge; and the three-day mean of lagged discharge. The metadata also lists soil moisture, runoff, a seven-day CHIRPS rainfall total, a HAND fraction below two metres, a 100-year depth grid, and a built-up floodplain fraction. Those names are recorded as extended fields. They are not columns of the classifier that the service loads.",
            ],
        ),
        _entry(
            "15",
            "3.2",
            "Application Services and External Data Clients",
            2,
            [
                "The HTTP service is a FastAPI application run by Uvicorn. Separate routers cover health, hydrology and the flood score, prediction timelines, allocation plans, inventory, operations, and a replay of archived days. At startup the process loads the flood artifact once. A score is refused when the joblib file or the JSON metadata is missing, or when the artifact has no probability method. The service returns an unavailable-model error in that case. It does not invent a probability from an untrained default.",
                "External clients fill values the local table does not already hold for a live day. Open-Meteo supplies rainfall. GloFAS modeled discharge is read through the Open-Meteo flood interface. NASA POWER supplies retrospective temperature, humidity, and wind for the training join and for historical charts. OpenTopography supplies Copernicus GLO-30 elevation for the selected point. That elevation is shown as terrain context. It includes canopy and buildings, and it is not one of the fifteen model inputs. Driving geometry, when the public routing service answers, comes from OSRM. If that call does not return a road path, the allocation code keeps a straight-line fallback and can also record a flood-aware corridor. Stops on those routes are township centroids. Keys for services that require them stay in the environment. They are not written into source listings or API responses.",
            ],
        ),
        _entry(
            "16",
            "3.3",
            "Relief, Census, and Inventory Data Preparation",
            2,
            [
                "The daily flood table is validated before features are built. Validation checks the schema, the binary flood flag, duplicate township-date keys, coordinates, and non-negative rainfall and discharge. Invalid dates, non-binary labels, and missing required fields are rejected. The approved daily file is the source. The processed copy used for training is data/processed/validated_daily.csv. The label column remains the relief flag. Precomputed rolling columns that may already sit in a source workbook are rebuilt inside the training script. The trainer does not trust those earlier columns.",
                "The 2024 Bago census extract supplies population by sex, urban and rural residence where the workbook publishes it, age groups for the region and the districts, and household size and dwelling type. Age groups are published for the region and the districts. They are not published for every township. The service reads a structured JSON copy of the extract. Census figures are reference context on the allocation screen. They are not columns in the fifteen-feature flood model.",
                "Inventory images are prepared separately for each detector. Foods cover rice, oil, and canned fish. Clothing covers T-shirts, men's longyi, and women's longyi. Kitchenware covers bowl, knife, mug, spoon, soap, water dipper, plate, and pot. Utilities cover bed net, blanket, towel, and box. The catalog class fund is entered by hand in Myanmar kyat and has no detector. Class names in each image set match the item codes the scan screen expects, so a confirmed box can be written to the matching stock row.",
            ],
        ),
        _entry(
            "17",
            "3.4",
            "Feature Construction and Numeric Representation",
            2,
            [
                "Feature construction sorts the daily table by township and date and computes every window inside one township. Rainfall from one township does not enter the rolling sum of another. Rainfall windows are rolling sums. The one-day feature is the rainfall on the current day. The three-day, seven-day, fourteen-day, and thirty-day features are trailing sums that include the current day. Each window requires a full set of days. A short series at the start of a township leaves the window missing. Rows that still miss any of the fifteen inputs, or that miss the flood flag, are dropped. The served metadata records 638 such rows and 39,534 complete rows.",
                "Modeled discharge is shifted by one day inside the township before it is used. The one-day discharge feature is that shifted value. The three-day discharge feature is the mean of the shifted series over three days, and that mean also requires three observations. The same-day discharge value therefore stays out of both discharge columns. Seasonality is the sine and cosine of the day of the year on a 365.25-day circle, so the monsoon position is available to a linear model and to a tree model without treating the last day of December as numerically next to the first day of January. Latitude and longitude are the township coordinates stored on the daily row.",
                "Temperature, humidity, and wind are joined from the NASA POWER cache. Humidity is RH2M from data/external/nasa_power_daily.csv. Temperature and wind are T2M and WS2M. Cache values at or below −999 are treated as missing. The training script may fill a NASA gap from the Open-Meteo archive. The saved metadata records zero values filled from that archive, so the served file was built from NASA meteorology on the rows that remained. Household counts and affected-people counts are impact fields observed after an event. They are targets of the planning illustration in section 3.8. They are excluded from the flood feature list.",
            ],
            tables=[
                (
                    ["Feature", "Construction"],
                    [
                        ["rainfall_1d_mm", "Same-day rainfall total"],
                        ["rainfall_3d_mm", "Three-day rolling rainfall sum, current day included"],
                        ["rainfall_7d_mm", "Seven-day rolling rainfall sum, current day included"],
                        ["rainfall_14d_mm", "Fourteen-day rolling rainfall sum, current day included"],
                        ["rainfall_30d_mm", "Thirty-day rolling rainfall sum, current day included"],
                        ["temperature_c", "NASA POWER 2 m temperature"],
                        ["relative_humidity_pct", "NASA POWER relative humidity"],
                        ["wind_speed_m_s", "NASA POWER 2 m wind speed"],
                        ["latitude, longitude", "Township coordinates"],
                        ["day_of_year_sin, day_of_year_cos", "Seasonal position on a 365.25-day circle"],
                        ["discharge_lag_1d_m3s", "Modeled discharge shifted by one day"],
                        ["discharge_lag_3d_mean_m3s", "Three-day mean of the lagged discharge"],
                    ],
                )
            ],
        ),
        _entry(
            "18",
            "3.5",
            "Application Database and Processed Data Store",
            2,
            [
                "Two kinds of storage are kept apart. Model files, the validated daily CSV, the split assignment, the census extract, and the offline hydrology cache stay on the filesystem. The API reads ml/models/bago_flood_model.joblib and bago_flood_model_metadata.json by path. An environment setting can point the service at another artifact path. Those files are not inserted into the application database. A change to the model is a change of files, followed by a reload of the process.",
                "The application database holds operational records: locations, allocation plans, alerts, and inventory rows. Local development uses SQLite through the default database URL. The Docker stack uses PostgreSQL 16 with PostGIS for the same role. A second SQLite file, data/offline/flood_sources.sqlite, can hold merged hydrology for hindcast dates so the map can read stored rainfall and discharge without a live call. Source CSVs and detector weights remain on disk beside that database.",
                "Lookups are by township and by date. The database answers those lookups and keeps the rows the interface writes, including confirmed stock and a selected delivery plan. The flood decision remains a classifier over the fifteen numeric columns described in section 3.4.",
            ],
        ),
        _entry(
            "19",
            "3.6",
            "Multi-Source Hydrometeorological Inputs",
            2,
            [
                "No single archive supplies every column. Rainfall in the training table is Open-Meteo reanalysis already stored on the validated daily file. Discharge is GloFAS river discharge stored from the Open-Meteo flood interface. GloFAS discharge is a modeled field from a hydrological chain. It is not a reading from a local staff gauge. Humidity is NASA POWER RH2M. Temperature and wind are NASA POWER T2M and WS2M. Each source is joined on township and date, and the feature names in section 3.4 are the names the classifier expects.",
                "For a live outlook the feature builder assembles the same fifteen names. Where a retrospective NASA value exists it is preferred for temperature, humidity, and wind. Short gaps in the local hydrology cache can be carried forward from the last stored rainfall, discharge, or meteorology so the screen can still draw a day. A carried-forward value is the last stored neighbour for that series. The screen remains a prototype view of that assembled row.",
                "Elevation from Copernicus GLO-30 is requested for the selected point and shown as terrain context. The 2024 census extract is requested as population, age, and dwelling context. Neither source is appended to the fifteen flood features. A map layer can therefore change without changing the columns the histogram model receives.",
            ],
        ),
        _entry(
            "20",
            "3.7",
            "Leakage Control and Claim Limits",
            2,
            [
                "The split file is the authority for which rows may be fit. The trainer merges it onto the engineered table and stops if a train, validation, or test block is missing. It also stops when training dates do not fall entirely before validation, or when validation dates do not fall entirely before the test. Thresholds and the isotonic calibrator see validation rows only. The published test metrics are computed with that frozen threshold. The metadata records that the test block was not used for training, calibration, or the threshold.",
                "Same-day rainfall sits on the same calendar day as the relief flag. It is a feature of the recorded day. It is contemporaneous with a historical label, and it is not a forecast lead. Discharge features are lagged by one day inside the township, which keeps the same-day discharge value out of those two columns. Rolling sums use the current row and earlier rows of that township only. Impact counts stay out of the flood feature list. Census totals stay out of the flood feature list. A future mutation of weather on a later date must leave the features of an earlier date unchanged. That is the leakage check the feature design is written to satisfy.",
                "Claim limits are part of the method. The API description states that the service is an academic flood-risk prototype and is not an operational warning desk. The risk bands in section 3.8 come from a documented formula. They are a display rule beside the classifier. Assistance priority taken from households and affected people uses the retrospective score households plus affected people divided by five. The bands are none at zero, low above zero, moderate from 100, high from 500, and severe from 2,000. That score uses counts available after an event. Chapter 5 reports agreement with the relief flag on the held-out block. It does not report an operational probability of inundation.",
            ],
        ),
        _entry(
            "21",
            "3.8",
            "Request Handling and Response Generation",
            2,
            [
                "A prediction request names a township and a date. The service builds the fifteen features, checks that each required name is present, and calls predict_proba on the loaded histogram model. The flood class is positive when the calibrated probability is at least the saved threshold of 0.05. The response carries the probability, the class, the threshold, and the model version read from the metadata, so a reader can see which file produced the score.",
                "The academic risk score is a bounded sum. It adds 1.25 times rainfall in millimetres, 0.04 times modeled discharge in cubic metres per second, and 10 times the flood probability, then limits the result to the range from 0 to 100. Bands on that score are low below 25, moderate below 50, high below 75, and severe from 75. A separate display band groups the probability itself: low below 0.25, moderate below 0.50, high below 0.75, and very high from 0.75. The very-high band is drawn with the severe colour. These bands explain the colour on the map. Precision and recall on the held-out test are reported in Chapter 5.",
                "An assistance request checks sources in a fixed order. It prefers a relief-workbook impact for that township and date when one exists. Otherwise it reads an archived simulation day when that day is marked as a flood day. Otherwise it scales a relief baseline by the flood probability. When the relief baseline for people or for households is empty, the scale uses eight percent of the matching 2024 census total. The headcount is capped at the township population. If the risk band is high or severe and the scaled count is still zero while a baseline exists, the fallback uses 55 percent of the baseline for a high band and 85 percent for a severe band. Shelter kits equal the expected households, because the planning ratio is one kit per household. Three-day food rations equal three times the expected people. Drinking water equals 15 litres per person per day across three days, which is 45 litres per person for the package. Assistance priority applies the retrospective severity rule to those expected counts. A learned two-stage help artifact is used only when that file is present on disk. It is absent from the artifact directory of this tree, so the screens follow the workbook, archive, or scaled-baseline path, and the response version string names which path was used.",
                "Inventory detection accepts an image or a video, runs the detector for the requested goods class, and returns boxes. Stock changes only after the user confirms those boxes. Fund amounts are typed in. They are not detected from a photograph. Allocation can then compare route options for the township centroids and store the selected plan, including the route method that produced the line.",
            ],
        ),
        _entry(
            "22",
            "3.9",
            "Proposed System Workflow",
            2,
            [
                "The workflow is a sequence of stored files and request-time calls. It is the path a user walks from the home screen to a flood day, a plan, and a stock count.",
                "First the daily table is validated and the fifteen features are built inside each township. Second the histogram candidates are fit on the training dates, one candidate is chosen on validation average precision, the calibrator and the threshold are fit on validation, and the test block is scored and stored in metadata. The logistic pipeline is fit on the same split and saved beside the served file. Third the API loads the histogram artifact. Fourth a map request builds features for the selected township and date and returns the probability, the class, and the risk band. Fifth an allocation request turns workbook, archive, or scaled census figures into a three-day package and a route among centroids. Sixth an inventory request counts visible goods and, after confirmation, updates stock.",
            ],
        ),
        _entry(
            "23",
            "Chapter 4",
            "System Design and Implementation",
            1,
            [
                "The implementation is divided into a machine-learning tree, a FastAPI service, a React interface, and Docker packaging. Training writes files. The service reads files and answers HTTP. The interface renders those answers and labels prototype inputs.",
            ],
        ),
        _entry(
            "24",
            "4.1",
            "Overview of the Proposed System",
            2,
            [
                "HydroFlow V2 has four screens: Home, Flood Prediction, Resource Allocation, and Inventory Management. The flood screen is a Leaflet map of Bago districts and townships, a timeline, forecast cards, a hazard panel, historical weather, and recorded flood history. The allocation screen lists township plans, compares routes, and can open a print preview. The inventory screen scans a photograph or a video and confirms counts into a regional stock list.",
                "The backend process exposes health, hydrology, prediction, allocation, inventory, operations, and simulation routes. High-level prediction paths include a timeline, map scores, and a region forecast, together with the earlier predict and outlook calls. Allocation covers stores, plans, confirmation, and dispatch records. Inventory covers detection, the catalog, and stock entries.",
            ],
        ),
        _entry(
            "25",
            "4.2",
            "Scope of the Project",
            2,
            [
                "The geographical scope is twenty-three townships in Bago Region: Bago, Daik-U, Htantabin, Kawa, Kyauktaga, Madauk, Minhla, Monyo, Okpho, Oktwin, Pantaung, Pyay, Pyu, Shwedaung, Shwegyin, Taungoo, Thanatpin, Thayarwady, Thegon, Waw, Yedashe, and Zigon. The flood model scores a township-day. It does not draw a street-level inundation polygon as its learned output.",
                "The functional scope covers the served histogram model, the logistic comparison file, the risk heuristic, the assistance illustration, centroid routes, and four goods detectors. Official warning products and job records exist as operational endpoints for provenance and replay. They do not convert the prototype into an agency warning desk.",
                "Out of scope are public dissemination, measured gauge height, a complete flood inventory, and any use of the scores as a sole basis for evacuation or procurement. An extension that needs those functions also needs new labels and an authority outside this codebase.",
            ],
        ),
        _entry(
            "26",
            "4.3",
            "Dataset Description",
            2,
            [
                "The flood dataset is a panel of township-days. After feature construction, 39,534 rows have every served input and the flood flag. The chronological validation block holds 8,030 of them, including 167 flood days. The chronological test block holds 8,052, including 11 flood days. The label text stored with the model is an observed relief flood flag, with no synthetic flood rows added.",
                "Detection datasets are separate image collections under the inventory raw tree, built into YOLO layouts for foods, clothing, kitchenware, and utilities. Their metrics in Chapter 5 are the last recorded training epoch in each detector history. They are not rows of the flood table.",
            ],
        ),
        _entry(
            "27",
            "4.3.1",
            "Source Data Files",
            3,
            [
                "The validated daily table is data/processed/validated_daily.csv. The chronological assignment is data/processed/split_assignments.csv. NASA humidity is data/external/nasa_power_daily.csv, with temperature and wind caches beside it. The census workbook is the 2024 Bago extract, and the service reads the structured JSON copy. Township centroids and administrative names come from the admin boundary files used by the map.",
                "The served flood weights are ml/models/bago_flood_model.joblib with bago_flood_model_metadata.json. The logistic comparison is bago_flood_model_logistic.joblib with its metadata. Detector weights, when promoted, live under ml/models/object_detect for foods, clothing, kitchenware, and utilities, each with a training_history.csv copied from the training log.",
                "Offline hydrology for hindcast dates can be read from data/offline/flood_sources.sqlite. Relief workbooks remain the source of the flood flag and of impact counts when a planning date matches a workbook row.",
            ],
        ),
        _entry(
            "28",
            "4.3.2",
            "Data Preprocessing",
            3,
            [
                "Preprocessing for the flood model is deterministic and township-wise, as Chapter 3 describes. Rows with a missing feature or a missing flag are removed rather than filled inside the histogram trainer. The logistic pipeline is the exception that imputes the median, and it imputes from the training block only.",
                "The split is not redrawn at serving time. Both models consume the saved assignment. A check in the trainer rejects a file whose training dates do not fall entirely before validation, or whose validation dates do not fall entirely before the test.",
                "Image preprocessing follows the detector trainer: class lists are built from the raw photo folders, names are aligned to item codes, and the training entry point records precision, recall, and mean average precision for each epoch. Promotion copies the chosen weights into the model directory the API resolves first.",
            ],
        ),
        _entry(
            "29",
            "4.4",
            "Technical Stack and Configuration",
            2,
            [
                "The service is Python with FastAPI and Uvicorn. Tables in memory use pandas. The flood models use scikit-learn and are stored with joblib. The application database uses SQLAlchemy, with SQLite locally and PostgreSQL through psycopg in Docker. Image detection uses OpenCV and Ultralytics. Tests use pytest.",
                "The interface is React 19 with TypeScript and Vite. Maps use Leaflet. Plan sheets can be exported with the PDF helpers in the frontend. Interface tests use Vitest. The browser build is served on port 8080 in Docker and on the Vite port during local development.",
                "Docker Compose defines three services. The database image is PostGIS 16. The API container depends on a healthy database and reads the validated daily file from a read-only mount. The frontend container depends on a healthy API and publishes port 8080. API keys and the database URL are environment settings. The compose file supplies a development database password for the local stack; a deployment outside this prototype would replace it.",
            ],
            tables=[
                (
                    ["Layer", "Role in this prototype"],
                    [
                        ["Python, FastAPI, Uvicorn", "HTTP service and request validation"],
                        ["pandas, scikit-learn, joblib", "Features, classifiers, saved artifacts"],
                        ["SQLAlchemy, SQLite, PostgreSQL/PostGIS", "Operational records"],
                        ["OpenCV, Ultralytics", "Relief-goods detection"],
                        ["React, TypeScript, Vite, Leaflet", "Map and planning screens"],
                        ["Docker Compose", "Database, API, and frontend"],
                    ],
                )
            ],
        ),
        _entry(
            "30",
            "4.5",
            "System Implementation",
            2,
            [
                "Training of the served flood model is the script that reads the validated daily table, joins NASA meteorology, engineers the fifteen columns, and writes the joblib and the metadata. The logistic script states that it scores the held-out block once and does not replace the histogram file. The API path resolves ml/models/bago_flood_model.joblib unless an environment path overrides it.",
                "On startup the API initializes the operational database and ensures a demonstration stock so the inventory screen is not empty. CORS allows the local Vite origin and the Docker origin on port 8080. Each router returns typed responses. A missing model becomes an unavailable-model error rather than a silent score of zero from an untrained default, except where an assistance path explicitly records a fallback version name.",
                "The flood screen requests calendar bounds, map scores, and a timeline. The allocation screen creates a plan, compares route options for a township row, and stores the selected option. Route methods recorded in the service include an OSRM road path, a straight-line fallback, and a flood-aware corridor. Stops are township centroids, so the line is an illustration of order and distance, not a site survey.",
                "The inventory service maps detector class names onto item codes, resolves weights from the promoted directory, and can confirm a detection into a stock entry. Video detection uses the same class list. The user confirms a count before it is treated as stock on hand.",
            ],
        ),
        _entry(
            "31",
            "Chapter 5",
            "Results and Discussion",
            1,
            [
                "This chapter reports the scores stored with the served model and with the logistic comparison, then describes what the screens show. Detection histories are reported in their own table because they measure boxes on images, not flood days.",
            ],
        ),
        _entry(
            "32",
            "5.1",
            "Introduction",
            2,
            [
                "All flood figures in this chapter are taken from the JSON metadata written when the models were trained. They are not a fresh fit performed for the book. The test block was not used to train, to calibrate, or to pick the threshold. Validation figures are included so the threshold choice is visible, and they are labeled as validation.",
                "The test set contains eleven flood days. With so few positives, a change of one true positive moves recall by about nine percentage points. The tables are therefore a description of this holdout, not a stable estimate of performance on a future monsoon.",
            ],
        ),
        _entry(
            "33",
            "5.2",
            "System Output and Functional Results",
            2,
            [
                "A successful health check shows that the API process is up. A flood request returns a probability, a binary class at the saved threshold, the threshold itself, and the model version. For the served file that version name resolves to the histogram model. Map scores colour townships from the same response family. Historical weather and flood history are context panels. They replay stored rows and are not an extra trained model.",
                "An allocation result lists expected people and households, an assistance priority, shelter kits, three-day food rations, and drinking water, together with a route method. When the numbers come from a workbook row, the version string says so. When they come from the flood probability and a baseline, the version string records that fallback. An inventory result lists class counts and boxes. Stock changes after the user confirms.",
                "These outputs are functional in the sense that the screens and the service implement them. Functional here does not mean that the flood class is precise. The next sections give the holdout counts that bound that claim.",
            ],
        ),
        _entry(
            "34",
            "5.3",
            "Logistic Regression Baseline versus Served Histogram Gradient Boosting",
            2,
            [
                "Both models see 8,052 untouched test rows and the same eleven flood days. The histogram model uses threshold 0.05. The logistic model uses threshold 0.87. The histogram model records precision 0.0113, recall 0.6364, F1 0.0222, precision-recall area 0.0085, and ROC area 0.8684. The logistic model records precision 0.0025, recall 0.0909, F1 0.0048, precision-recall area 0.0063, and ROC area 0.7950.",
                "The confusion counts make the same comparison concrete. The histogram model marks 7 of the 11 flood days and also marks 612 non-flood days as flood, with 4 flood days missed and 7,429 non-flood days left negative. The logistic model marks 1 of the 11 flood days and marks 401 non-flood days as flood, with 10 flood days missed and 7,640 non-flood days left negative.",
                "Accuracy is 0.9235 for the histogram model and 0.9490 for the logistic model. A prediction of no flood on every test row reaches accuracy 0.9986. The logistic model is closer to that rule because its threshold is high and its recall is one flood day in eleven. The histogram model recovers more of the eleven days and pays for that recall with more false alarms. Precision-recall area, which was also the criterion that chose the histogram candidate, is higher for the served model than for the logistic baseline on this block.",
                "On the validation block, which was used to choose the histogram threshold, the served model sees 8,030 rows and 167 flood days. At threshold 0.05 it records precision 0.0701, recall 0.2874, F1 0.1127, and precision-recall area 0.0624, with 48 true positives and 637 false positives. Validation is easier than the test block because the positives are more numerous. It is not a substitute for the untouched test.",
            ],
            tables=[
                (
                    ["Model", "Threshold", "Precision", "Recall", "F1", "PR-AUC", "ROC-AUC"],
                    [
                        ["Histogram gradient boosting", "0.05", "0.0113", "0.6364", "0.0222", "0.0085", "0.8684"],
                        ["Logistic regression", "0.87", "0.0025", "0.0909", "0.0048", "0.0063", "0.7950"],
                    ],
                ),
                (
                    ["Model", "True negative", "False positive", "False negative", "True positive"],
                    [
                        ["Histogram gradient boosting", "7,429", "612", "4", "7"],
                        ["Logistic regression", "7,640", "401", "10", "1"],
                    ],
                ),
            ],
        ),
        _entry(
            "35",
            "5.4",
            "Graphical User Interface",
            2,
            [
                "The shell is a single page with four destinations. Home introduces the workspace. Flood Prediction centres a Leaflet map and places the timeline, summary cards, forecast cards, hazard depth, and historical context beside it. Resource Allocation lists township rows for a plan, opens a comparison of route options, draws the selected path, and can preview a printable sheet. Inventory Management shows catalog categories, a scan action for a still image or a video, and the stock that remains after confirmation.",
                "The map uses township boundaries and centroids already served by the API. Colours follow the risk and probability bands defined in the service. Text on the planning views names the prototype role of the counts. The route line is the geometry returned for the chosen method. A user can switch among the screens without a second login step because the prototype has no accounts.",
            ],
        ),
        _entry(
            "36",
            "5.5",
            "System Testing and Model Evaluation",
            2,
            [
                "Evaluation of the flood classifiers is the chronological protocol in Chapter 3. Fit on train, select the histogram candidate and both thresholds on validation, and publish the test metrics from the metadata. The majority-class accuracy is stored next to those metrics so a high accuracy cannot be misread.",
                "Software tests cover the service and the interface. Backend tests exercise health, prediction, assistance fallbacks, allocation, and the mapping from detector names to item codes. Machine-learning tests cover the feature and training helpers under the ml tree. Frontend tests render the dashboards and the allocation interactions with Vitest. The commands live in the verification note: pytest for the Python trees, and npm test plus a production build for the interface.",
                "Detector evaluation in this book is the final epoch written in each training_history.csv. Those columns are the validation precision, recall, and mean average precision logged during training. They are not an untouched flood test, and they are not a count of goods in a warehouse audit.",
            ],
            tables=[
                (
                    ["Detector", "Final epoch", "Precision", "Recall", "mAP50", "mAP50-95"],
                    [
                        ["Foods", "52", "0.831", "0.912", "0.875", "0.704"],
                        ["Clothing", "41", "0.910", "0.882", "0.965", "0.656"],
                        ["Kitchenware", "80", "0.936", "0.958", "0.942", "0.756"],
                        ["Utilities", "71", "0.846", "0.898", "0.887", "0.737"],
                    ],
                )
            ],
        ),
        _entry(
            "37",
            "5.6",
            "Results Analysis",
            2,
            [
                "The served model finds seven of the eleven test flood days. That recall is the strongest flood-class result in the comparison, and the precision of 0.0113 means that a positive mark is usually a non-flood day. A planner who treated every positive mark as a confirmed flood would be responding to hundreds of quiet days. The prototype therefore shows the probability and the band, and the book keeps the false-positive count beside the true-positive count.",
                "The logistic baseline is more specific in the weak sense that it raises fewer false alarms, and it misses ten of the eleven flood days. Its higher accuracy follows from predicting the majority class more often. For a rare relief flag, that accuracy repeats the base rate. The precision-recall area remains below 0.01 for both models on the test block, which is the quantitative statement that ranking quality on this holdout is poor.",
                "The validation block, with 167 flood days, supports a higher F1 for the served model than the test block does. The drop from validation F1 0.1127 to test F1 0.0222 is consistent with a shift in how rare and how placed the later positives are. Eleven test positives cannot identify which township drives the drop. The training notes already suppress township test metrics when a township has fewer than five test flood days, and no township in this design has five.",
                "The detector table is stronger than the flood table, and it answers a different question. Kitchenware, clothing, foods, and utilities all end training with validation mAP50 above 0.87 on the logged epoch. A high mAP50 means the boxes agreed with the labeled images in that training run. It says nothing about the relief flood flag.",
            ],
        ),
        _entry(
            "38",
            "5.7",
            "Model Selection and Justification",
            2,
            [
                "The served flood model is the histogram candidate hgb-depth3 because it won the validation precision-recall comparison among the three candidates the trainer fit, and because the saved logistic comparison also records the histogram model as the better of the two on precision-recall area. The logistic pipeline remains in the tree as the interpretable baseline. It is the model a reader can inspect through scaled coefficients. It is not the file the prediction path loads.",
                "The threshold 0.05 is low because flood-class F1 on the validation block preferred it. A higher threshold would resemble the logistic operating point: fewer alarms and fewer of the rare flood days. The book reports the operating point that the training rule actually saved.",
                "An earlier twelve-feature logistic study removed NASA soil wetness and humidity so those retrospective fields would not be required on an outlook date. Its untouched-test flood F1 was about 0.029. That study used a different feature list from the fifteen columns in the current metadata. It is cited here so the two results are not exchanged. The justification for serving the histogram file is the fifteen-feature comparison above, together with the fact that the API path points at that file.",
                "No detector replaces the flood model. Goods detection is selected per catalog class because each training set has its own item list. Fund remains a manual catalog entry.",
            ],
        ),
        _entry(
            "39",
            "5.8",
            "Advantages of the Proposed System",
            2,
            [
                "The prototype puts the township map, the flood score, the three-day illustration, the route, and the stock count in one interface backed by one service. A reader can see which file produced the score because the response carries the model version and the metadata carries the threshold and the test counts.",
                "The evaluation design is visible. The split is chronological. The test flag is stored. The majority-class accuracy is stored. The logistic baseline uses the same rows, so the gain in recall is measured against a stated alternative rather than against an unpublished run.",
                "Local files allow the map to read stored hydrology and the census extract when a live provider is slow or absent, within the limits of those files. Demonstration stock lets the inventory path be reviewed without a prior warehouse import. These are advantages for study and for a supervised demonstration.",
            ],
        ),
        _entry(
            "40",
            "Chapter 6",
            "Conclusion and Future Scope",
            1,
            [
                "HydroFlow V2 is a complete academic path from a Bago daily table to a served flood score and a set of planning screens. The path is documented with the holdout counts that bound its skill.",
            ],
        ),
        _entry(
            "41",
            "6.1",
            "Summary of the Project",
            2,
            [
                "The project builds and serves a histogram gradient boosting classifier for a relief flood flag on twenty-three townships. Fifteen features cover rainfall windows, NASA meteorology, coordinates, seasonality, and lagged modeled discharge. The saved candidate is hgb-depth3. The threshold is 0.05. On the untouched test block the model reaches recall 0.6364 and precision 0.0113, with 7 true positives and 612 false positives out of 11 flood days and 8,052 rows.",
                "A class-weighted logistic regression on the same features is the baseline, with threshold 0.87, recall 0.0909, and precision 0.0025. The interface adds an assistance illustration, centroid routes, and four goods detectors. The book records the last-epoch detection scores separately from the flood scores.",
            ],
        ),
        _entry(
            "42",
            "6.2",
            "Limitations",
            2,
            [
                "The relief flag is an incomplete label. Precision on the untouched test is 0.0113. Eleven test flood days cannot support a township ranking or an operational probability. The scores are not independently calibrated for public warning. Isotonic calibration was fit on the validation block and was not given a later calibration set.",
                "GloFAS discharge is modeled discharge, not a gauge height. Rainfall in the training table is reanalysis. Carried-forward hydrology fills gaps with the last stored value. Copernicus elevation includes canopy and buildings and is display context only. Census age groups are not published for every township.",
                "Assistance counts are illustrations from a workbook row, an archived day, or a baseline scaled by the flood score and capped by population. The fixed ratios are not a needs assessment. Routes follow township centroids. Alerts stored by the application are prototype records. Detector scores come from training logs. The class fund is not detected. The earlier twelve-feature result must not be quoted as the score of the file the API loads.",
            ],
        ),
        _entry(
            "43",
            "6.3",
            "Future Extensions",
            2,
            [
                "The data extension that would change the flood scores is a set of independently verified flood labels for later years, with event dates and township provenance kept, followed by a new untouched time block. Synthetic positives would not serve that purpose.",
                "A scientific extension is to pair the relief flag with gauged stages and a local rainfall network, and to publish reliability of the probabilities on a block that was not used for the threshold. A planning extension is to replace centroid illustrations with surveyed sites and stock that has been counted outside the demonstration seed. Any of those steps still leaves public use dependent on review by the authorities who issue warnings.",
            ],
        ),
        _entry(
            "44",
            "—",
            "References",
            1,
            [
                "[1] Nevo, S. et al., 2022. Flood forecasting with machine learning models in an operational framework. Hydrology and Earth System Sciences, 26, pp.4013–4032.",
                "[2] Mosavi, A., Ozturk, P. and Chau, K.W., 2018. Flood prediction using machine learning models: Literature review. Water, 10(11), p.1536.",
                "[3] Breiman, L., 2001. Random forests. Machine Learning, 45(1), pp.5–32.",
                "[4] Friedman, J.H., 2001. Greedy function approximation: a gradient boosting machine. Annals of Statistics, 29(5), pp.1189–1232.",
                "[5] Pedregosa, F. et al., 2011. Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, pp.2825–2830.",
                "[6] Kratzert, F., Klotz, D., Brenner, C., Schulz, K. and Herrnegger, M., 2018. Rainfall–runoff modelling using Long Short-Term Memory (LSTM) networks. Hydrology and Earth System Sciences, 22, pp.6005–6022.",
                "[7] Harrigan, S., Zsoter, E., Alfieri, L., Prudhomme, C., Salamon, P., Wetterhall, F., Barnard, C., Cloke, H. and Pappenberger, F., 2020. GloFAS-ERA5 operational global river discharge reanalysis 1979–present. Earth System Science Data, 12, pp.2043–2060.",
                "[8] Open-Meteo, n.d. Weather and flood APIs. Available at: https://open-meteo.com/.",
                "[9] NASA Langley Research Center, n.d. Prediction of Worldwide Energy Resources (POWER). Available at: https://power.larc.nasa.gov/.",
                "[10] European Space Agency, n.d. Copernicus DEM. Copernicus Data Space Ecosystem.",
                "[11] Kaufman, S., Rosset, S., Perlich, C. and Stitelman, O., 2012. Leakage in data mining: Formulation, detection, and avoidance. ACM Transactions on Knowledge Discovery from Data, 6(4), pp.1–21.",
                "[12] Saito, T. and Rehmsmeier, M., 2015. The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets. PLoS ONE, 10(3), e0118432.",
                "[13] Sphere Association, 2018. The Sphere Handbook: Humanitarian Charter and Minimum Standards in Humanitarian Response. 4th ed. Geneva: Sphere Association.",
                "[14] Redmon, J., Divvala, S., Girshick, R. and Farhadi, A., 2016. You Only Look Once: Unified, real-time object detection. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition, pp.779–788.",
                "[15] Jocher, G., Chaurasia, A. and Qiu, J., 2023. Ultralytics YOLO. Available at: https://github.com/ultralytics/ultralytics.",
            ],
        ),
    ]


def _set_run_font(run, size: int = 12, bold: bool = False, italic: bool = False) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = RGBColor(0, 0, 0)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        r_fonts.set(qn(attr), "Times New Roman")


def _shade(cell, color: str) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), color)
    shd.set(qn("w:val"), "clear")


def _set_cell_border(cell) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right"):
        element = tc_borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            tc_borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), "000000")


def _paragraph(doc: Document, text: str, *, size: int = 12, bold: bool = False, center: bool = False, space_after: int = 8, space_before: int = 0, indent: bool = False):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.space_after = Pt(space_after)
    paragraph.paragraph_format.space_before = Pt(space_before)
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    if indent and not center:
        paragraph.paragraph_format.first_line_indent = Cm(1.0)
    run = paragraph.add_run(text)
    _set_run_font(run, size=size, bold=bold)
    return paragraph


def _heading(doc: Document, text: str, level: int) -> None:
    paragraph = doc.add_heading(text, level=level)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = Pt(16 if level == 1 else 12)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.15
    paragraph.paragraph_format.keep_with_next = True
    for run in paragraph.runs:
        _set_run_font(run, size={1: 16, 2: 14, 3: 12}[level], bold=True)


def _add_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(header)
        _set_run_font(run, size=11, bold=True)
        _shade(cell, "D9E2F3")
        _set_cell_border(cell)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            cell = table.rows[row_index + 1].cells[col_index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(value)
            _set_run_font(run, size=11)
            _set_cell_border(cell)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)


def _page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run2 = paragraph.add_run()
    run2._r.append(instr)
    run3 = paragraph.add_run()
    run3._r.append(separate)
    run3._r.append(end)
    for item in (run, run2, run3):
        _set_run_font(item, size=11)


def _set_page_numbering(section, fmt: str | None, start: int | None) -> None:
    section.footer.is_linked_to_previous = False
    section.header.is_linked_to_previous = False
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.text = ""
    if fmt is None:
        return
    sect_pr = section._sectPr
    pg_num = sect_pr.find(qn("w:pgNumType"))
    if pg_num is None:
        pg_num = OxmlElement("w:pgNumType")
        sect_pr.append(pg_num)
    pg_num.set(qn("w:fmt"), fmt)
    if start is not None:
        pg_num.set(qn("w:start"), str(start))
    _page_field(footer)


def _configure_page(section) -> None:
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.4)


def _apply_normal_style(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    r_pr = normal.element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        r_fonts.set(qn(attr), "Times New Roman")


def _contents_table(doc: Document, entries: list[dict], pages: dict[str, str]) -> None:
    headers = ["S.No", "Chapter", "Title", "Page"]
    table = doc.add_table(rows=1 + len(entries), cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    widths = (Cm(1.6), Cm(3.2), Cm(9.4), Cm(2.0))
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(header)
        _set_run_font(run, size=12, bold=True)
        _shade(cell, "D9E2F3")
        _set_cell_border(cell)
    for row_index, entry in enumerate(entries):
        values = [entry["sno"], entry["chapter"], entry["title"], pages.get(entry["sno"], "—")]
        aligns = [
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.LEFT,
            WD_ALIGN_PARAGRAPH.CENTER,
        ]
        for col_index, value in enumerate(values):
            cell = table.rows[row_index + 1].cells[col_index]
            cell.text = ""
            cell.width = widths[col_index]
            paragraph = cell.paragraphs[0]
            paragraph.alignment = aligns[col_index]
            run = paragraph.add_run(value)
            _set_run_font(run, size=11, bold=entry["level"] == 1 and entry["chapter"].startswith("Chapter"))
            _set_cell_border(cell)
    doc.add_paragraph()


def _write_cover(doc: Document) -> None:
    _paragraph(doc, "PROJECT REPORT", size=18, bold=True, center=True, space_before=72, space_after=12)
    _paragraph(doc, "On", size=14, center=True, space_after=12)
    _paragraph(
        doc,
        "HydroFlow V2: Flood Outlook and Humanitarian Planning for Bago Region, Myanmar",
        size=16,
        bold=True,
        center=True,
        space_after=18,
    )
    _paragraph(doc, "Submitted", size=12, center=True, space_after=0)
    _paragraph(doc, "In partial fulfilment", size=12, center=True, space_after=0)
    _paragraph(doc, "For the award of the Degree of", size=12, center=True, space_after=12)
    _paragraph(doc, "[Degree programme]", size=12, bold=True, center=True, space_after=12)
    _paragraph(doc, "[Institution]", size=12, center=True, space_after=18)
    _paragraph(doc, "Guided By: [Name of the project guide]", size=12, center=True, space_after=12)
    _paragraph(doc, "Submitted By:", size=12, center=True, space_after=0)
    _paragraph(doc, "[Name of the candidate]", size=12, bold=True, center=True, space_after=0)
    _paragraph(doc, "[Institution and address]", size=12, center=True, space_after=18)
    _paragraph(doc, "November 2026", size=12, center=True, space_after=0)


def build_document(pages: dict[str, str] | None = None) -> Document:
    pages = pages or {}
    entries = report_entries()
    doc = Document()
    _apply_normal_style(doc)
    section = doc.sections[0]
    _configure_page(section)
    _set_page_numbering(section, None, None)
    _write_cover(doc)

    front = doc.add_section()
    _configure_page(front)
    _set_page_numbering(front, "lowerRoman", 1)

    for entry in entries:
        if entry["sno"] == "4":
            body = doc.add_section()
            _configure_page(body)
            _set_page_numbering(body, "decimal", 1)
        if entry["chapter"].startswith("Chapter"):
            _paragraph(doc, entry["chapter"], size=14, bold=True, center=True, space_before=6, space_after=0)
            _heading(doc, entry["title"], 1)
        elif entry["chapter"] == "—":
            _heading(doc, entry["title"], 1)
        else:
            _heading(doc, f"{entry['chapter']}  {entry['title']}", entry["level"])
        if entry["title"] == "Table of Contents":
            for paragraph in entry["paragraphs"]:
                _paragraph(doc, paragraph, indent=False)
            _contents_table(doc, entries, pages)
            continue
        for paragraph in entry["paragraphs"]:
            _paragraph(doc, paragraph, indent=True)
        for headers, rows in entry["tables"]:
            _add_table(doc, headers, rows)
    return doc


def _to_roman(value: int) -> str:
    numerals = [
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ]
    result = ""
    for number, glyph in numerals:
        while value >= number:
            result += glyph
            value -= number
    return result


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def printed_pages_from_pdf(pdf_path: Path, entries: list[dict]) -> dict[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_text = [_compact(page.extract_text() or "") for page in reader.pages]
    probes = {entry["sno"]: _compact(entry["probe"])[:48] for entry in entries}
    missing = [sno for sno, probe in probes.items() if not any(probe in text for text in page_text)]
    if missing:
        titles = {entry["sno"]: entry["title"] for entry in entries}
        detail = ", ".join(f"{sno} {titles[sno]}" for sno in missing)
        raise SystemExit(f"Page probes missing from the PDF: {detail}")
    front_start = next(index for index, text in enumerate(page_text) if probes["1"] in text)
    body_start = next(index for index, text in enumerate(page_text) if probes["4"] in text)
    found: dict[str, str] = {}
    for sno, probe in probes.items():
        physical = next(index for index, text in enumerate(page_text) if probe in text)
        if physical < body_start:
            found[sno] = _to_roman(physical - front_start + 1)
        else:
            found[sno] = str(physical - body_start + 1)
    return found


def convert_to_pdf(docx_path: Path, pdf_path: Path) -> bool:
    if pdf_path.exists():
        pdf_path.unlink()
    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    candidates = [
        soffice,
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for program in candidates:
        if not program or not Path(program).exists() and shutil.which(program or "") is None:
            if not program or not Path(program).exists():
                continue
        command = [
            program,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_path.parent),
            str(docx_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if completed.returncode == 0 and pdf_path.exists():
            return True
    word_candidates = [
        shutil.which("winword"),
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
    ]
    if any(path and Path(path).exists() for path in word_candidates):
        script = f"""
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {{
  $doc = $word.Documents.Open('{docx_path}', $false, $true, $false)
  $doc.ExportAsFixedFormat('{pdf_path}', 17)
}} finally {{
  if ($doc -ne $null) {{ $doc.Close($false) }}
  $word.Quit()
}}
"""
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if completed.returncode != 0 or not pdf_path.exists():
            print(completed.stdout, file=sys.stderr)
            print(completed.stderr, file=sys.stderr)
        return completed.returncode == 0 and pdf_path.exists()
    return False


def assert_book(entries: list[dict]) -> None:
    from docx import Document as OpenDocument

    doc = OpenDocument(str(DOCX_PATH))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    lowered = text.lower()
    for banned in ("langchain", "retrieval-augmented", "vector database"):
        if banned in lowered:
            raise SystemExit(f"Banned phrase present: {banned}")
    if re.search(r"\brag\b", lowered):
        raise SystemExit("Banned phrase present: RAG")
    required = [
        "Acknowledgment",
        "Abstract",
        "Table of Contents",
        "Purpose of the Project",
        "Literature Review",
        "Class-Weighted Logistic Regression (interpretable baseline)",
        "Histogram Gradient Boosting (served flood model)",
        "Application Services and External Data Clients",
        "Source Data Files",
        "Logistic Regression Baseline versus Served Histogram Gradient Boosting",
        "0.0113",
        "0.6364",
        "0.0222",
        "0.0085",
        "0.0025",
        "0.0909",
        "0.0048",
        "0.0063",
        "twelve-feature",
        "hgb-depth3",
        "References",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f"Missing book text: {missing}")
    titles = [entry["title"] for entry in entries]
    if titles[0] != "Acknowledgment" or titles[-1] != "References":
        raise SystemExit("Contents order does not match the skeleton")
    if len(entries) != 44:
        raise SystemExit(f"Expected 44 contents rows, found {len(entries)}")


def verify_saved_book() -> None:
    entries = report_entries()
    pages = printed_pages_from_pdf(PDF_PATH, entries)
    document = Document(str(DOCX_PATH))
    contents = document.tables[0]
    mismatches = []
    for entry in entries:
        printed = contents.rows[int(entry["sno"])].cells[3].text.strip()
        actual = pages[entry["sno"]]
        if printed != actual:
            mismatches.append((entry["sno"], entry["title"], printed, actual))
    assert_book(entries)
    if mismatches:
        for sno, title, printed, actual in mismatches:
            print(f"shift {sno} {title}: contents {printed}, pdf {actual}")
        raise SystemExit(f"{len(mismatches)} contents pages differ from the PDF")
    print(f"Verified {DOCX_PATH.name} and {PDF_PATH.name}: {len(entries)} sections, pages agree")


def _content_entries() -> list[dict]:
    skipped = {"Table of Contents"}
    entries = []
    for entry in report_entries():
        if entry["title"] in skipped:
            continue
        paragraphs = [
            paragraph
            for paragraph in entry["paragraphs"]
            if "left in brackets on the cover" not in paragraph
            and "numbered in roman numerals" not in paragraph
        ]
        if paragraphs:
            copied = dict(entry)
            copied["paragraphs"] = paragraphs
            entries.append(copied)
    return entries


def write_content_files() -> None:
    entries = _content_entries()
    lines = [
        "# HydroFlow V2: Flood Outlook and Humanitarian Planning for Bago Region, Myanmar",
        "",
    ]
    document = Document()
    _apply_normal_style(document)
    _configure_page(document.sections[0])
    _paragraph(
        document,
        "HydroFlow V2: Flood Outlook and Humanitarian Planning for Bago Region, Myanmar",
        size=16,
        bold=True,
        center=True,
        space_after=12,
    )
    for entry in entries:
        if entry["chapter"].startswith("Chapter"):
            heading = f"{entry['chapter']}: {entry['title']}"
            lines.extend([f"## {heading}", ""])
            _heading(document, heading, 1)
        elif entry["chapter"] == "—":
            lines.extend([f"## {entry['title']}", ""])
            _heading(document, entry["title"], 1)
        else:
            heading = f"{entry['chapter']} {entry['title']}"
            marker = "####" if entry["level"] >= 3 else "###"
            lines.extend([f"{marker} {heading}", ""])
            _heading(document, heading, min(entry["level"], 3))
        for paragraph in entry["paragraphs"]:
            lines.extend([paragraph, ""])
            _paragraph(document, paragraph, indent=True)
        for headers, rows in entry["tables"]:
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in rows:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
            _add_table(document, headers, rows)
    CONTENT_PATH.write_text("\n".join(lines), encoding="utf-8")
    document.save(CONTENT_DOCX_PATH)
    print(f"Wrote {CONTENT_PATH}")
    print(f"Wrote {CONTENT_DOCX_PATH}")


def main() -> None:
    entries = report_entries()
    document = build_document({})
    document.save(DOCX_PATH)
    pages: dict[str, str] = {}
    if convert_to_pdf(DOCX_PATH, PDF_PATH):
        for _ in range(4):
            confirmed = printed_pages_from_pdf(PDF_PATH, entries)
            if confirmed == pages:
                break
            pages = confirmed
            document = build_document(pages)
            document.save(DOCX_PATH)
            if not convert_to_pdf(DOCX_PATH, PDF_PATH):
                raise SystemExit("PDF export failed while filling page numbers")
        else:
            confirmed = printed_pages_from_pdf(PDF_PATH, entries)
            if confirmed != pages:
                raise SystemExit("Printed page numbers did not settle")
    else:
        print("No Word or LibreOffice converter found. The docx contents table has no printed page numbers.", file=sys.stderr)
    assert_book(entries)
    print(f"Wrote {DOCX_PATH}")
    if PDF_PATH.exists():
        print(f"Wrote {PDF_PATH}")
    if pages:
        print("Contents pages:")
        for entry in entries:
            print(f"  {entry['sno']:>2}  {pages.get(entry['sno'], '—'):>4}  {entry['title']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_saved_book()
    elif len(sys.argv) > 1 and sys.argv[1] == "content":
        write_content_files()
    else:
        main()
