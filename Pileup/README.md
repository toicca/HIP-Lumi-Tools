# Pileup Tools

## produce_pileupHist.py

Produces a data pileup ROOT histogram using `brilcalc` (via singularity) and `pileupCalc.py`.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--year` | Yes | Era: `2016`, `2017`, `2018`, `2022`, `2023`, `2024` |
| `--lumijson` | Yes | Luminosity block JSON (GoldenJSON or DCSOnly) |
| `--pileup-latest` | No | Pileup JSON file. If omitted, looked up from `Data/PileupJSONS.json` via `$LUMIENV` |
| `--trigger` | No | HLT trigger path (without `_v*`) for per-trigger pileup |
| `--minBiasXsec` | No | Minimum bias cross section in µb (default: 69200) |
| `--vary-minBiasXsec` | No | Also produce ±variation histograms (e.g. 3200 for Run 2) |
| `--output-path` | No | Output directory (default: `./`) |
| `--normtag` | No | Normtag to use: `BRIL` or `PHYSICS` (default: `BRIL`) |
| `--ignore-normtag` | No | Skip the normtag argument in the brilcalc call |

### Example — no trigger

```bash
python3 Pileup/produce_pileupHist.py \
  --year 2024 \
  --lumijson /path/to/golden.json \
  --pileup-latest /eos/user/c/cmsdqm/www/CAF/certification/Collisions24/PileUp/pileup_JSON-2024BCDEFGHI_Golden.txt \
  --minBiasXsec 69200 \
  --vary-minBiasXsec 3200 \
  --output-path output/
```

### Example — per trigger

```bash
python3 Pileup/produce_pileupHist.py \
  --year 2024 \
  --lumijson /path/to/golden.json \
  --pileup-latest /eos/user/c/cmsdqm/www/CAF/certification/Collisions24/PileUp/pileup_JSON-2024BCDEFGHI_Golden.txt \
  --trigger HLT_ZeroBias \
  --minBiasXsec 69200 \
  --output-path output/
```

When a trigger is given, the script runs `pileupReCalc_HLTpaths.py` to correct the pileup JSON for the trigger's prescales before calling `pileupCalc.py`.

### Output

`pileup_{year}[_{trigger}]_{minBiasXsec}ub.root` — contains the `pileup` histogram (100 bins, [0, 100]).

---

## produce_pileupWeight.py

Produces pileup weights by dividing the data pileup histogram by the MC pileup histogram.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--pileup_dt` / `--calculate_pileup` | Yes (one) | Data pileup ROOT file, or flag to calculate it |
| `--pileup_mc` / `--calculate_mc` | Yes (one) | MC pileup ROOT file, or flag to calculate from DAS |
| `--output` | Yes | Output ROOT file path |
| `--mc_dataset` | No | DAS dataset query (needed with `--calculate_mc`) |
| `--save_mc` | No | Save the MC pileup histogram to disk |
| `--rdf_filter` | No | RDataFrame filter string for the MC calculation |

### Example

```bash
python3 Pileup/produce_pileupWeight.py \
  --pileup_dt output/pileup_2024_69200ub.root \
  --pileup_mc output/pileup_mc.root \
  --output output/pileup_weights.root
```

### Output

`output.root` contains three histograms:
- `weights` — data/MC ratio (pileup weights to apply to MC events)
- `pileup_data` — normalised data pileup
- `pileup_mc` — normalised MC pileup

Bins where the relative error exceeds 50% are set to weight = 1 (no reweighting).