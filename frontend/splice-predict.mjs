import fs from "node:fs";

const filePath = "D:/Ai_Project/HydroFlow_V1/frontend/src/App.tsx";
const lines = fs.readFileSync(filePath, "utf8").split(/\n/);
const marker = lines.findIndex((line) => line.includes("Model request"));
let start = marker;
while (start > 0 && !lines[start].includes('<article className="panel">')) start -= 1;
const mainEnd = lines.findIndex((line, index) => index > start && line.trim() === "</main>");
if (start < 0 || mainEnd < 0) {
  console.error("markers", start, mainEnd);
  process.exit(1);
}

const block = `          <article className="panel form-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Three times a day</p>
                <h2>Flood prediction</h2>
              </div>
              <span className="source">06:00 · 12:00 · 18:00</span>
            </div>
            <p className="hint">
              Measured at 06:00, 12:00, and 18:00 MMT. One request joins Open-Meteo rainfall, NASA POWER
              temperature, humidity and wind, and GloFAS modeled discharge. The score covers the next 3 days
              and is not an official warning.
            </p>
            <form onSubmit={submitOutlook}>
              <div className="form-grid">
                <label>Start date<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label>
                <label>Township
                  <select
                    value={selectedTownship}
                    onChange={(event) => chooseTownship(event.target.value)}
                    required
                    disabled={!selectedPlace}
                  >
                    {!selectedPlace && <option value="">Loading Bago townships…</option>}
                    {areas.data?.districts.map((district) => (
                      <optgroup key={district.id} label={\`\${district.name_en} District\`}>
                        {district.townships.map((township) => (
                          <option key={township.id} value={township.id}>{township.name_en}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
              </div>
              <button type="submit" disabled={outlook.state === "loading" || !selectedPlace}>
                {outlook.state === "loading" ? "Loading API days…" : "Load API outlook"}
              </button>
            </form>
            {selectedPlace && (
              <p className="place-note">
                {selectedPlace.township.name_en}, {selectedPlace.district.name_en} District ·{" "}
                {selectedPlace.township.latitude.toFixed(4)}, {selectedPlace.township.longitude.toFixed(4)}
              </p>
            )}
            <ElevationNote resource={topography} />
            <StateMessage resource={outlook} empty="Choose a start date to load the API outlook." />
            {outlook.state === "ready" && (
              <p className="place-note">
                Model {outlook.data?.model_version} · {outlook.data?.in_training_set
                  ? "Inside the 14 close-river training townships"
                  : "Outside the 14 close-river training set"}
                {outlook.data?.days[0]?.uncertainty ? \` · \${outlook.data.days[0].uncertainty}\` : ""}
              </p>
            )}
          </article>

          <article className="panel history-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Whole Bago Region</p>
                <h2>5-day region prediction</h2>
              </div>
              <span className="source">Source: /historical</span>
            </div>
            <StateMessage resource={historical} empty="No regional days returned." />
            {historical.state === "ready" && (
              <div className="history-table" role="table" aria-label="Five day Bago Region prediction">
                <div className="history-row region header" role="row">
                  <span>Date</span>
                  <span>Rainfall</span>
                  <span>Temperature</span>
                  <span>Humidity</span>
                </div>
                {regionDays.map((point) => (
                  <div className="history-row region" role="row" key={point.date}>
                    <strong>{point.date}</strong>
                    <span>{valueOrDash(point.precipitation_mm, "mm")}</span>
                    <span>{valueOrDash(point.temperature_c, "°C")}</span>
                    <span>{valueOrDash(point.relative_humidity_pct, "%")}</span>
                  </div>
                ))}
              </div>
            )}
          </article>
`;

const next = [...lines.slice(0, start), ...block.split("\n"), ...lines.slice(mainEnd)];
fs.writeFileSync(filePath, next.join("\n"));
console.log("replaced", start + 1, "through", mainEnd, "total", next.length);
