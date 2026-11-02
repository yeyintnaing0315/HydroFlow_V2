# Chapter 3 — Methodology and Techniques

This chapter states the methods that turn a Bago township-day into a flood class, a risk band, an assistance illustration, and a stock count. The prediction service loads one flood artifact: a histogram gradient boosting classifier saved as `hgb-depth3`, wrapped by an isotonic calibrator. A class-weighted logistic regression is trained on the same rows and the same fifteen features so the results chapter has a linear baseline. Assistance figures, routes, and inventory counts follow their own rules. No project source file was changed in order to write this chapter. The figures below are the ones stored with the loaded artifacts.

The unit of analysis is the township-day. The label is the relief flood flag on the validated daily table: a flood day that appears in the available relief records. The flag is an incomplete indicator. The metadata records that no synthetic flood rows were added. The served artifact names twenty-two townships: Bago, Daik-U, Htantabin, Kawa, Kyauktaga, Madauk, Minhla, Monyo, Okpho, Oktwin, Pantaung, Pyay, Pyu, Shwedaung, Shwegyin, Taungoo, Thanatpin, Thayarwady, Thegon, Waw, Yedashe, and Zigon.

After feature construction, 39,534 rows have every served input and the flood flag. Six hundred and thirty-eight rows are dropped because a required feature or the flag is missing. The chronological assignment is the saved file `data/processed/split_assignments.csv`. The validation block holds 8,030 rows, including 167 flood days. The test block holds 8,052 rows, including 11 flood days. The trainer uses that file. It does not redraw the split at fit time.

## 3.1 Machine-Learning Approaches for Flood Occurrence

Flood occurrence is treated as supervised binary classification. Each example is one township-day. The input is a vector of fifteen numeric features, written x. The label y is 1 when that township-day carries the relief flood flag and 0 otherwise. A classifier estimates the conditional probability p(x) = P(y = 1 | x). A later rule turns that probability into a class: the day is called a flood day when p(x) is at least a threshold τ. The two models in this section estimate p(x) in different ways. They share the same fifteen features, the same saved chronological split, and the same rule for choosing τ. The comparison therefore concerns the form of the probability model.

The label is rare. The validation block has 167 flood days in 8,030 rows, and the untouched test block has 11 flood days in 8,052 rows. Under ordinary 0–1 loss, a rule that predicts the more common class is favoured whenever the estimated flood probability stays below one half. Accuracy, (true positives + true negatives) / N, is then dominated by the true negatives. The metadata records a majority-class accuracy of 0.9986 on the test block for a prediction of no flood on every row. Accuracy is stored so that a high value can be read against that baseline. It is not the quantity used to choose a model or a threshold [12].

For a rare positive class, the useful counts are the true positives (TP), false positives (FP), and false negatives (FN). Precision is TP / (TP + FP). Recall is TP / (TP + FN). The F1 score is their harmonic mean,

F1 = 2 · TP / (2 · TP + FP + FN).

F1 is high only when both precision and recall are high. Average precision is the area under the precision–recall curve obtained by sweeping τ. It summarises the ranking of flood days above non-flood days and does not depend on one chosen threshold [12]. Histogram candidates are therefore compared by validation average precision. After a candidate is kept, τ is chosen on the same validation block by maximising F1. The search uses the grid 0.01, 0.02, …, 0.99. The test block is scored only after that choice is frozen.

The split is chronological because a township-day is not an independent draw from a fixed population. Rainfall, discharge, and the relief flag are ordered in time. A random split would place later monsoon days in the training block and earlier days in the test block, so the reported score would describe interpolation inside one period. The saved assignment keeps every training date before every validation date, and every validation date before every test date. Model fitting sees the training dates. Candidate choice, probability calibration, and the threshold see the validation dates. The test dates are the first block on which the frozen rule is reported.

For the histogram model, a row that still lacks any of the fifteen inputs, or that lacks the flag, is removed before fitting. For the logistic model, a median imputer and a standard scaler are fitted on the training rows only and stored in the same pipeline as the classifier. A separate study pipeline under `ml/hydroflow_ml` fits another logistic model on a shorter feature list and can redraw a 60/20/20 date split. That pipeline is not the file the prediction service loads.

### 3.1.1 Class-Weighted Logistic Regression (interpretable baseline)

Logistic regression models the log-odds of the flood class as a linear function of the features [16]. If p is the flood probability, the model is

log( p / (1 − p) ) = β0 + β1 x1 + … + β15 x15,

which is the same statement as

p = 1 / ( 1 + exp( −(β0 + β · x) ) ).

The sigmoid function maps any real score onto the interval (0, 1). The decision surface in the original feature space is linear: the set of days with p = τ is a hyperplane. The model can represent a change in level when rainfall or discharge increases, and it can represent seasonality because the sine and cosine of the day of the year are already columns. It cannot represent a threshold interaction, such as “high rainfall matters only when lagged discharge is also high,” unless that product is supplied as its own column. That limit is the reason the logistic file is the baseline and the tree ensemble is the served model.

The coefficients are estimated by minimising a weighted negative log-likelihood, with an L2 penalty on the coefficients. For one row the log-loss is

− [ y log p + (1 − y) log(1 − p) ].

Summed over the training rows, this loss is the negative of the Bernoulli log-likelihood. The implementation is `sklearn.linear_model.LogisticRegression` with the liblinear solver, at most 2,000 iterations, and the library default C = 1 [5], [17]. Liblinear minimises an L2-regularised linear objective. The penalty shrinks large coefficients toward zero, which limits how sharply the linear score can fit idiosyncrasies of the training years.

Class weights change the contribution of each row. With `class_weight="balanced"`, the weight of a class is

w_c = n / (2 · n_c),

where n is the number of training rows and n_c is the number of training rows in class c [5], [18]. The flood class and the non-flood class then contribute the same total weight. Without that reweighting, the many non-flood days would dominate the log-likelihood and the fitted probability would stay near zero. The weight is a fitting device. It does not change the meaning of the label, and it does not by itself produce a probability that matches the base rate of flood days. A probability trained under balanced weights tends to sit higher than the empirical flood frequency. The validation search is then free to place τ well above one half. On this split the selected threshold is 0.87.

Before the linear model is fit, each numeric column is median-imputed and standardised on the training block only. The median imputer replaces a missing training value with the training median of that column, so a later row can still be scored if one field is absent. The standard scaler subtracts the training mean and divides by the training standard deviation. After that transform, β_j is the change in log-odds for an increase of one training standard deviation in feature j, holding the other scaled features fixed. Coefficients of rainfall, discharge, temperature, and the seasonal terms can then be compared with one another. The imputer, the scaler, and the classifier are saved as one pipeline, so serving applies the same training statistics.

The logistic file is marked secondary. Its role is interpretation and comparison. The prediction service loads `ml/models/bago_flood_model.joblib` and does not load `bago_flood_model_logistic.joblib` when it scores a township-day. The comparison script fits this pipeline, writes the secondary file, and leaves the histogram artifact in place.

### 3.1.2 Histogram Gradient Boosting (served flood model)

The served model belongs to the gradient boosting family [4]. An additive predictor is built in stages,

F_m(x) = F_{m−1}(x) + ν · h_m(x),

where h_m is a regression tree and ν is a learning rate between 0 and 1. At stage m the tree is fit to the negative gradient of the training loss at the current prediction F_{m−1}. For binary log-loss, that gradient at a row is the residual y − p, with p obtained from the current score through the sigmoid. Each new tree therefore tries to correct the residuals of the ensemble so far. Friedman’s shrinkage result is the reason ν is kept small: a short step at each stage reduces the chance that one tree memorises the training sample [4]. In this project ν = 0.05, and the number of stages is capped at 300.

A single tree of depth d partitions the feature space into regions and predicts a constant in each region. Depth limits the order of interaction inside one tree. A tree of depth 3 can split on at most three features along one path, so one tree can express a local conjunction such as a rainfall window together with lagged discharge and season. The ensemble is a sum of many such local corrections, so the overall function can be nonlinear and can change its slope in different parts of the feature space. That is the capacity the logistic hyperplane does not have. The cost of that capacity is a less direct reading of a single coefficient.

Histogram gradient boosting, as implemented by `sklearn.ensemble.HistGradientBoostingClassifier`, adds a binning approximation in the spirit of LightGBM [5], [19]. Each feature is divided into a fixed set of bins. Split search sums the gradients inside bins rather than sorting every raw value. The tree thresholds fall on bin boundaries. Binning makes the search cheaper and slightly coarsens the feature, which is a form of regularisation. The loss remains the binomial log-loss.

Three candidates are fit on the training rows only. All three use ν = 0.05, at most 300 iterations, an L2 penalty of 1.0 on the leaf values, early stopping, and random seed 42. The leaf penalty discourages large leaf weights when the Hessian of the loss in that leaf is small, which is the usual guard against a leaf that contains little evidence [5]. The candidates differ in capacity:

| Candidate | Maximum depth | Minimum samples in a leaf | Class weight |
| --- | ---: | ---: | --- |
| hgb-depth3 | 3 | 20 | none |
| hgb-depth3-balanced | 3 | 20 | balanced |
| hgb-depth4 | 4 | 10 | none |

The minimum leaf size stops a split that would isolate a handful of days. The depth-4 candidate can represent a higher-order interaction inside one tree, and its smaller leaf size allows finer partitions. The balanced candidate uses the same inverse-frequency weights as section 3.1.1 inside the boosting loss. The unweighted candidates leave the class prior in the loss and rely on the later threshold to trade precision against recall. The candidate with the highest validation average precision is kept. The saved name is `hgb-depth3`, so the served trees are unweighted, of depth at most 3, with at least 20 training rows in a leaf.

Early stopping is internal to the training block. With `early_stopping=True`, the library holds out its default fraction, 0.1, of the rows passed to `fit` and stops when the internal score has not improved for 10 iterations [5]. Those rows are a subset of the training dates. They are not the chronological validation block. The chronological validation block remains available for the three decisions that must be comparable across candidates: average precision, isotonic calibration, and the F1 threshold.

A boosted score is a sum of tree outputs. Even after the sigmoid, that score is not guaranteed to match the empirical flood frequency in each band of scores. Isotonic calibration estimates a non-decreasing map g from the raw score s to a probability [20], [21]. On the validation pairs (s_i, y_i), g minimises the sum of squared errors Σ (y_i − g(s_i))² subject to g(s_1) ≤ g(s_2) ≤ … when the scores are sorted. The pool-adjacent-violators algorithm produces that map. The project uses `IsotonicRegression` with outputs clipped to [0, 1]. Values outside the range of validation scores are clipped as well. The served object stores the trees and g together. `predict_proba` returns 1 − g(s) and g(s). The F1 search then runs on g(s), not on the raw tree score, and selects τ = 0.05.

The low threshold is consistent with a rare event after calibration. Isotonic regression pulls the scores toward the flood frequencies observed on the validation block, and those frequencies are small, so most calibrated probabilities lie near zero. A threshold of 0.05 can still recover flood days that the ranking has placed only slightly above the mass of non-flood days. The class-weighted logistic model, by contrast, inflates the fitted probabilities and then requires τ = 0.87 to make the same F1 trade-off. The two thresholds are not interchangeable, because the two probability scales are not the same.

Calibration and threshold selection share one validation block. The validation F1 is therefore the score of a rule that has already seen those labels twice, once to shape g and once to pick τ. It is the right block for fitting those two steps, and it is not an independent estimate of future performance. The test block is withheld from training, from g, and from the threshold. The metadata flag `test_used_for_training_calibration_or_threshold` is false.

The fifteen inputs of both classifiers are the one-day, three-day, seven-day, fourteen-day, and thirty-day rainfall totals; temperature; relative humidity; wind speed; latitude; longitude; the sine and cosine of the day of the year; the previous day's modeled discharge; and the three-day mean of lagged discharge. The metadata also lists soil moisture, runoff, a seven-day CHIRPS rainfall total, a HAND fraction below two metres, a 100-year depth grid, and a built-up floodplain fraction. Those names are recorded as extended fields. They are not columns of the classifier that the service loads.

Additional sources for this section, to be appended to the reference list:

[16] Cox, D.R., 1958. The regression analysis of binary sequences. Journal of the Royal Statistical Society: Series B, 20(2), pp.215–242.

[17] Fan, R.E., Chang, K.W., Hsieh, C.J., Wang, X.R. and Lin, C.J., 2008. LIBLINEAR: A library for large linear classification. Journal of Machine Learning Research, 9, pp.1871–1874.

[18] He, H. and Garcia, E.A., 2009. Learning from imbalanced data. IEEE Transactions on Knowledge and Data Engineering, 21(9), pp.1263–1284.

[19] Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. and Liu, T.Y., 2017. LightGBM: A highly efficient gradient boosting decision tree. Advances in Neural Information Processing Systems, 30.

[20] Niculescu-Mizil, A. and Caruana, R., 2005. Predicting good probabilities with supervised learning. In: Proceedings of the 22nd International Conference on Machine Learning, pp.625–632.

[21] Zadrozny, B. and Elkan, C., 2002. Transforming classifier scores into accurate multiclass probability estimates. In: Proceedings of the Eighth ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, pp.694–699.

## 3.2 Application Services and External Data Clients

The HTTP service is a FastAPI application. Its description states that the service is an academic flood-risk prototype and is not an operational warning desk. Separate routers cover health, hydrology, prediction, allocation, inventory, operations, and a replay of archived days. At startup the process opens the operational database and ensures a demonstration stock so the inventory screen is not empty. A score is refused when the joblib file or the JSON metadata is missing, or when the artifact has no probability method. The service returns an unavailable-model error in that case. It does not invent a probability from an untrained default.

External clients fill values the local table does not already hold for a live day. Open-Meteo supplies rainfall. GloFAS modeled discharge is read through the Open-Meteo flood interface. NASA POWER supplies retrospective temperature, humidity, and wind for the training join and for historical charts. OpenTopography supplies Copernicus GLO-30 elevation for the selected point. That elevation is shown as terrain context. It includes canopy and buildings, and it is not one of the fifteen model inputs. Driving geometry, when the public routing service answers, comes from OSRM. If that call does not return a road path, the allocation code can keep a flood-aware corridor or a straight-line fallback. Stops on those routes are township centroids. Keys for services that require them stay in the environment. They are not written into source listings or API responses.

## 3.3 Relief, Census, and Inventory Data Preparation

The daily flood table is validated before features are built. Validation checks the schema, the binary flood flag, duplicate township-date keys, coordinates inside valid ranges, and non-negative rainfall and discharge. Invalid dates, non-binary labels, and missing required fields are rejected. The approved daily file is the source. The processed copy used for training is `data/processed/validated_daily.csv`. The label column remains the relief flag. Rolling rainfall and lagged discharge are rebuilt inside the training script. The trainer does not trust precomputed rolling columns that may already sit in a source workbook.

The 2024 Bago census extract supplies population, household counts, and the age and dwelling context the allocation screen can show. Age groups are published for the region and the districts. They are not a column of the flood model. Census figures enter the assistance illustration only when a relief baseline for people or households is empty, and then only as the eight-percent scale described in section 3.8.

Inventory images are prepared separately for each detector. Foods cover rice, oil, and canned fish. Clothing covers T-shirts, men's longyi, and women's longyi. Kitchenware covers bowl, knife, mug, spoon, soap, water dipper, plate, and pot. Utilities cover bed net, blanket, towel, and box. The catalog class fund is entered by hand in Myanmar kyat and has no detector. Class names in each image set are aligned to the item codes the scan screen expects, so a confirmed box can be written to the matching stock row.

## 3.4 Feature Construction and Numeric Representation

Feature construction sorts the daily table by township and date and computes every window inside one township. Rainfall from one township does not enter the rolling sum of another. Rainfall windows are rolling sums. The one-day feature is the rainfall on the current day. The three-day, seven-day, fourteen-day, and thirty-day features are trailing sums that include the current day. Each window requires a full set of days. A short series at the start of a township leaves the window missing, and that row is dropped. The served metadata records 638 dropped rows and 39,534 complete rows.

Modeled discharge is shifted by one day inside the township before it is used. The one-day discharge feature is that shifted value. The three-day discharge feature is the mean of the shifted series over three days, and that mean also requires three observations. The same-day discharge value therefore stays out of both discharge columns. Seasonality is the sine and cosine of the day of the year on a 365.25-day circle, so the monsoon position is available to a linear model and to a tree model without treating the last day of December as numerically next to the first day of January. Latitude and longitude are the township coordinates stored on the daily row.

Temperature, humidity, and wind are joined from the NASA POWER cache. Humidity is RH2M from `data/external/nasa_power_daily.csv`. Temperature and wind are T2M and WS2M. Cache values at or below −999 are treated as missing. The training script may fill a NASA gap from the Open-Meteo archive. The saved metadata records zero values filled from that archive, so the served file was built from NASA meteorology on the rows that remained. Household counts and affected-people counts are impact fields observed after an event. They are targets of the planning illustration in section 3.8. They are excluded from the flood feature list.

| Feature | Construction |
| --- | --- |
| rainfall_1d_mm | Same-day rainfall total |
| rainfall_3d_mm | Three-day rolling rainfall sum, current day included |
| rainfall_7d_mm | Seven-day rolling rainfall sum, current day included |
| rainfall_14d_mm | Fourteen-day rolling rainfall sum, current day included |
| rainfall_30d_mm | Thirty-day rolling rainfall sum, current day included |
| temperature_c | NASA POWER 2 m temperature |
| relative_humidity_pct | NASA POWER relative humidity |
| wind_speed_m_s | NASA POWER 2 m wind speed |
| latitude, longitude | Township coordinates |
| day_of_year_sin, day_of_year_cos | Seasonal position on a 365.25-day circle |
| discharge_lag_1d_m3s | Modeled discharge shifted by one day |
| discharge_lag_3d_mean_m3s | Three-day mean of the lagged discharge |

The live feature builder assembles the same fifteen names. A short gap after the last stored day can be filled forward from the last rainfall, discharge, or meteorology value so the screen can still draw a day. A carried-forward value is the last stored neighbour for that series.

## 3.5 Application Database and Processed Data Store

Two kinds of storage are kept apart. Model files, the validated daily CSV, the split assignment, the census extract, and the offline hydrology cache stay on the filesystem. The API reads `ml/models/bago_flood_model.joblib` and `bago_flood_model_metadata.json` by path. An environment setting can point the service at another artifact path. Those files are not inserted into the application database. A change to the model is a change of files, followed by a reload of the process.

The application database holds operational records: locations, allocation plans, alerts, and inventory rows. Local development uses SQLite through the default database URL. The Docker stack uses PostgreSQL, from the PostGIS 16 image, for the same role. Saved route geometry is stored as GeoJSON text. A second SQLite file, `data/offline/flood_sources.sqlite`, can hold merged hydrology for hindcast dates so the map can read stored rainfall and discharge without a live call. Source CSVs and detector weights remain on disk beside that database.

Lookups are by township and by date. The database answers those lookups and keeps the rows the interface writes, including confirmed stock and a selected delivery plan. The flood decision remains a classifier over the fifteen numeric columns described in section 3.4.

## 3.6 Multi-Source Hydrometeorological Inputs

No single archive supplies every column. Rainfall in the training table is Open-Meteo reanalysis already stored on the validated daily file. Discharge is GloFAS river discharge stored from the Open-Meteo flood interface. GloFAS discharge is a modeled field from a hydrological chain. It is not a reading from a local staff gauge. Humidity is NASA POWER RH2M. Temperature and wind are NASA POWER T2M and WS2M. Each source is joined on township and date, and the feature names in section 3.4 are the names the classifier expects.

For a live outlook the feature builder assembles the same fifteen names. Where a retrospective NASA value exists it is preferred for temperature, humidity, and wind. Short gaps in the local hydrology series can be carried forward, as section 3.4 describes. The screen remains a prototype view of that assembled row.

Elevation from Copernicus GLO-30 is requested for the selected point and shown as terrain context. The 2024 census extract is requested as population, age, and dwelling context. Neither source is appended to the fifteen flood features. A map layer can therefore change without changing the columns the histogram model receives.

## 3.7 Leakage Control and Claim Limits

The split file is the authority for which rows may be fit. The trainer merges it onto the engineered table and stops if a train, validation, or test block is missing. It also stops when training dates do not fall entirely before validation, or when validation dates do not fall entirely before the test. Thresholds and the isotonic calibrator see validation rows only. The published test metrics are computed with that frozen threshold. The metadata records that the test block was not used for training, calibration, or the threshold.

Same-day rainfall sits on the same calendar day as the relief flag. It is a feature of the recorded day. It is contemporaneous with a historical label, and it is not a forecast lead. Discharge features are lagged by one day inside the township, which keeps the same-day discharge value out of those two columns. Rolling sums use the current row and earlier rows of that township only. Impact counts stay out of the flood feature list. Census totals stay out of the flood feature list.

Claim limits are part of the method. The risk bands in section 3.8 come from a documented formula. They are a display rule beside the classifier. Assistance priority taken from households and affected people uses the retrospective score households plus affected people divided by five. The bands are none at zero, low above zero, moderate from 100, high from 500, and severe from 2,000. That score uses counts available after an event. It is not a learned forecast of severity. Agreement with the relief flag on the held-out block is a description of this label, not an operational probability of inundation.

## 3.8 Request Handling and Response Generation

A prediction request names a township and a date. The service builds the fifteen features, checks that each required name is present, and calls `predict_proba` on the loaded histogram model. The flood class is positive when the calibrated probability is at least the saved threshold of 0.05. The response carries the probability, the class, the threshold, and the model version read from the metadata, so a reader can see which file produced the score. The version name on the served file is `hist_gradient_boosting`.

The academic risk score is a bounded sum. It adds 1.25 times rainfall in millimetres, 0.04 times modeled discharge in cubic metres per second, and 10 times the flood probability, then limits the result to the range from 0 to 100. Bands on that score are low below 25, moderate below 50, high below 75, and severe from 75. A separate display band groups the probability itself: low below 0.25, moderate below 0.50, high below 0.75, and very high from 0.75. The very-high band is drawn with the severe colour. These bands explain the colour on the map. They are not the decision threshold of 0.05.

An assistance request checks sources in a fixed order. It prefers a relief-workbook impact for that township and date when one exists. Otherwise it reads an archived simulation day when that day is marked as a flood day. Otherwise it scales a relief baseline by the flood probability. When the relief baseline for people or for households is empty, the scale uses eight percent of the matching 2024 census total. The headcount is capped at the township population. If the risk band is high or severe and the scaled count is still zero while a baseline exists, the fallback uses 55 percent of the baseline for a high band and 85 percent for a severe band. Shelter kits equal the expected households, because the planning ratio is one kit per household. Three-day food rations equal three times the expected people. Drinking water equals 15 litres per person per day across three days, which is 45 litres per person for the package. Assistance priority applies the retrospective severity rule to those expected counts. A learned two-stage help artifact is used only when `artifacts/flood_help_pipeline.joblib` is present. That file is absent from this tree, so the screens follow the workbook, archive, or scaled-baseline path, and the response version string names which path was used.

Inventory detection accepts an image or a video, runs the detector for the requested goods class, and returns boxes. The accepted classes are clothing, foods, kitchenware, and utilities. Stock changes only after the user confirms those boxes. Fund amounts are typed in. They are not detected from a photograph. Allocation can then compare route options for the township centroids and store the selected plan, including the route method that produced the line. The recorded methods are an OSRM road path, a flood-aware corridor, and a straight-line fallback.

## 3.9 Proposed System Workflow

The workflow is a sequence of stored files and request-time calls.

1. The daily table is validated and the fifteen features are built inside each township.
2. The histogram candidates are fit on the training dates. One candidate is chosen on validation average precision. The calibrator and the threshold are fit on validation. The test block is scored and stored in metadata. The logistic pipeline is fit on the same split and saved beside the served file.
3. The API loads the histogram artifact.
4. A map request builds features for the selected township and date and returns the probability, the class, and the risk band.
5. An allocation request turns workbook, archive, or scaled census figures into a three-day package and a route among centroids.
6. An inventory request counts visible goods and, after confirmation, updates stock.

The result is an academic prototype of that sequence. It is not a public warning, a measured river height, or a field assessment of people and goods.
