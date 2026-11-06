"""
make_figures.py — regenerate the two data figures of the manuscript (Figures 3 and 4) from the release.

  fig3: spatial coverage — (A) station map, (B) top-15 prefectures by station count
  fig4: (A) annual and (B) seasonal mean concentrations of the five pollutants

Inputs : japaq_station_metadata_v1.0.0.csv, japaq_fe_v1.0.0.parquet, japan_prefectures.geojson
Outputs: <out_dir>/pdf/fig3.pdf, fig4.pdf and <out_dir>/jpeg/fig3.jpeg, fig4.jpeg (300 dpi)
Usage  : python validation/make_figures.py <release_dir> <geojson> <out_dir>
"""
import os
import sys
import duckdb
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ART, GEOJSON, OUT = sys.argv[1:4]
FEAT = f"{ART}/japaq_fe_v1.0.0.parquet"
STN = f"{ART}/japaq_station_metadata_v1.0.0.csv"
for d in ("pdf", "jpeg"):
    os.makedirs(f"{OUT}/{d}", exist_ok=True)

c = duckdb.connect()
c.execute("SET threads=32")
st = c.execute(f"""SELECT sid, prefecture_en,
                          TRY_CAST(lat AS DOUBLE) lat, TRY_CAST(lon AS DOUBLE) lon   -- complete station metadata
                   FROM read_csv('{STN}', all_varchar=true)
                   WHERE sid IN (SELECT DISTINCT sid FROM '{FEAT}')""").df()

def save(fig, name):
    fig.savefig(f"{OUT}/pdf/{name}.pdf", bbox_inches="tight")
    fig.savefig(f"{OUT}/jpeg/{name}.jpeg", dpi=300, bbox_inches="tight", pil_kwargs={"quality": 95})
    plt.close(fig)

# ── Figure 3: spatial coverage ──────────────────────────────────────────────────────────
plt.rcParams.update({"font.family": ["Arial", "Liberation Sans"], "pdf.fonttype": 42, "ps.fonttype": 42})  # Arial metrics, matching Figures 1-2
pref = gpd.read_file(GEOJSON)
xy = st.dropna(subset=["lat", "lon"])
top15 = st["prefecture_en"].value_counts().head(15)

fig = plt.figure(figsize=(16, 7.5))
gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.7], wspace=0.42)
axA = fig.add_subplot(gs[0])
pref.plot(ax=axA, facecolor="#EDEDED", edgecolor="#999999", linewidth=0.5, zorder=0)
axA.scatter(xy["lon"], xy["lat"], s=28, c="#B33B3B", alpha=0.55, linewidths=0, zorder=2)
axA.set_xlim(122.5, 146.5)
axA.set_ylim(24, 46)
axA.set_aspect(1.2)
axA.set_xticks([]); axA.set_yticks([])
for sp in axA.spines.values():
    sp.set_linewidth(2.5)


axB = fig.add_subplot(gs[1])
axB.barh(range(len(top15)), top15.values, color="#617FA6", height=0.7)
axB.set_yticks(range(len(top15)))
axB.set_yticklabels(top15.index, fontsize=20)
axB.invert_yaxis()
axB.set_xlabel("Number of stations", fontsize=20)
axB.tick_params(axis="x", labelsize=18, width=1.5, length=6)
axB.tick_params(axis="y", length=0, pad=6)
for sp in ("top", "right", "left"):
    axB.spines[sp].set_visible(False)
axB.spines["bottom"].set_linewidth(2)
# panel letters aligned on one line at the top of each grid column
for letter, cell in (("a", gs[0]), ("b", gs[1])):
    fig.text(cell.get_position(fig).x0 - 0.01, 0.93, letter, fontsize=26, fontweight="bold", ha="left", va="bottom")
save(fig, "fig3")

# ── Figure 4: annual and seasonal means ─────────────────────────────────────────────────
POL = [("pm25", "PM2.5\n(µg/m³)", "#4C9A7A"), ("so2", "SO₂\n(ppm)", "#C8682C"), ("no", "NO\n(ppm)", "#7570B3"),
       ("spm", "SPM\n(mg/m³)", "#D63F8A"), ("ox", "Ox\n(ppm)", "#6FA33A")]
yr = c.execute(f"""SELECT "year", avg(pm25) pm25, avg(so2) so2, avg("no") "no", avg(spm) spm, avg(ox) ox
                   FROM '{FEAT}' WHERE "year" BETWEEN 2018 AND 2025 GROUP BY 1 ORDER BY 1""").df()
se = c.execute(f"""SELECT season, avg(pm25) pm25, avg(so2) so2, avg("no") "no", avg(spm) spm, avg(ox) ox
                   FROM '{FEAT}' GROUP BY 1""").df().set_index("season").loc[["Spring", "Summer", "Autumn", "Winter"]]

fig, axes = plt.subplots(2, 5, figsize=(26, 13), gridspec_kw={"hspace": 0.42, "wspace": 0.42})
for j, (col, title, color) in enumerate(POL):
    a = axes[0, j]
    a.plot(yr["year"], yr[col], "-o", color=color, linewidth=3, markersize=8)
    a.set_title(title, fontsize=17)
    a.set_xticks(yr["year"])
    a.set_xticklabels(yr["year"], rotation=45, fontsize=13)
    a.tick_params(axis="y", labelsize=13)
    a.grid(True, linestyle="--", alpha=0.4)
    b = axes[1, j]
    b.bar(se.index, se[col], color=color, width=0.65)
    b.set_xticks(range(4))
    b.set_xticklabels(se.index, rotation=20, fontsize=13)
    b.tick_params(axis="y", labelsize=13)
    b.grid(True, axis="y", linestyle="--", alpha=0.4)
    for ax in (a, b):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
fig.text(0.07, 0.93, "A", fontsize=30, fontweight="bold")
fig.text(0.07, 0.47, "B", fontsize=30, fontweight="bold")
save(fig, "fig4")

print("stations:", len(st), "with coordinates:", len(xy))
print("top15:", dict(top15))
print(yr.round(5).to_string(index=False))
print(se.round(5).to_string())
