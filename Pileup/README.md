# Pileup Tools

## produce_pileupHist.py

Produces a data pileup ROOT histogram using `brilcalc` (via singularity) and `pileupCalc.py`.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--year` | Yes | Era: `2016`, `2017`, `2018`, `2022`, `2023`, `2024`, `2025`, `2026` |
| `--lumijson` | Yes | Luminosity block JSON (GoldenJSON or DCSOnly) |
| `--pileup-latest` | No | Pileup JSON file. If omitted, looked up from `Data/PileupJSONS.json` via `$LUMIENV` |
| `--trigger` | No | HLT trigger path (without `_v*`) for per-trigger pileup |
| `--minBiasXsec` | No | Minimum bias cross section in µb (default: 69200) |
| `--vary-minBiasXsec` | No | Also produce ±variation histograms (e.g. 3200 for Run 2) |
| `--maxPileupBin` | No | Upper edge of the histogram (default: 100) |
| `--numPileupBins` | No | Number of bins (default: 100). Raise it for low pileup data, where 1.0 wide bins leave only a handful of filled bins |
| `--calcMode` | No | `true` (default) for the true pileup distribution, to reweight `Pileup_nTrueInt`. `observed` Poisson smears it, to reweight `Pileup_nPU` — the only option that works for a sample digitised at a single fixed pileup |
| `--tag` | No | Extra tag in the output file name, e.g. the pileup band the lumijson selects |
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

`pileup_{year}[_{tag}][_{trigger}]_{minBiasXsec}ub[_{numPileupBins}bins][_max{maxPileupBin}][_observed].root` — contains the `pileup` histogram. The optional suffixes only appear when the binning is not the default 1.0 wide, the upper edge is not 100, or the mode is not `true`.

### Choosing `--calcMode`

`true` gives the distribution of the true (Poisson mean) pileup, which is what `Pileup_nTrueInt` holds, and is the usual choice. It only works if the MC actually has a spread in `Pileup_nTrueInt`. Samples generated at a single fixed pileup — the `RunIII2026LowPUSummer26` campaign is one, every event there has `Pileup_nTrueInt == 5.0` — have a delta function there and cannot be reweighted that way at all. For those, use `--calcMode observed`, which Poisson smears the data distribution so that it can be compared to `Pileup_nPU`, the number of interactions actually mixed in, which does have a spread. Since `Pileup_nPU` is an integer, only 1.0 wide bins make sense in `observed` mode.

---

## produce_pileupJSON.py

Produces the per-lumisection pileup JSON that `produce_pileupHist.py` passes to `pileupCalc.py` as `--inputLumiJSON`. Needed for periods with no official file under `/eos/user/c/cmsdqm/www/CAF/certification/<era>/PileUp/` — Collisions26 is one of them.

The chain is `brilcalc lumi --byls --xing` → `makePileupJSON.py`, as described on the [PileupJSONFileforData](https://twiki.cern.ch/twiki/bin/viewauth/CMS/PileupJSONFileforData) twiki. brilcalc is called once per run so the (large) per-BX CSV is written in resumable chunks; a run whose CSV already exists in `--work-dir` is skipped.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--lumijson` | Yes | Luminosity block JSON (GoldenJSON, DCSOnly, a certification JSON) |
| `--output` | Yes | Output pileup JSON file |
| `--work-dir` | No | Directory for the per-run `--xing` CSVs (default: `<output dir>/xing`). Expect several GB |
| `--normtag` | No | `BRIL` or `PHYSICS` (default: `BRIL`). `normtag_PHYSICS.json` stops in 2024 |
| `--ignore-normtag` | No | Skip the normtag argument |
| `--no-threshold` | No | Pass `-n` to `makePileupJSON.py`, disabling the afterglow bunch threshold |
| `--sel-bx` | No | Comma separated list of BXs to use |
| `--force` | No | Re-run brilcalc even for runs whose CSV already exists |

`makePileupJSON.py` drops bunches below 1.2 /µb/LS (HFET, HFOC at low energy 2.0) or 8.0 /µb/LS (HFOC at nominal energy), to keep afterglow out of the pileup calculation. Since PU = 69200 × L_bx / 262144, those thresholds are pileup cuts of about 0.32 and 2.1 — the HFOC one bites on genuinely low pileup data, so check the resulting mean pileup against the `avgpu` column of the brilcalc CSV and rerun with `--no-threshold` if it is biased low.

```bash
python3 Pileup/produce_pileupJSON.py \
  --lumijson /cvmfs/cms-griddata.cern.ch/cat/metadata/DC/Collisions26/latest/Cert_Collisions2026_lowPU.json \
  --output Data/pileup_JSON-2026_lowPU.txt \
  --normtag BRIL
```

---

## plot_avgpu_per_run.py

Plots the luminosity-weighted average pileup per run from a `brilcalc --byls` CSV. Each run is a point at its lumi-weighted mean per-LS `avgpu`, with a bar for the lumi-weighted 5th–95th percentile and a thin whisker for the full min–max, so runs that ramp the pileup are visible. The lower panel shows the recorded luminosity per run.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `csv` | Yes | Input `brilcalc --byls` CSV |
| `--output` / `-o` | No | Output path without extension (default: `avgpu_per_run`). Writes `.png`, `.pdf` and `.json` |
| `--title` | No | Title annotation |
| `--pu-bands` | No | Comma separated pileup values drawn as reference lines, e.g. the edges used by `avgpu_per_run.py --split-pu` |
| `--band-labels` | No | Names for the regions between those lines, drawn on the right |
| `--x-run-number` | No | Numeric run-number x axis instead of evenly spaced runs |
| `--linear` | No | Linear pileup axis instead of log |

```bash
python3 Pileup/plot_avgpu_per_run.py output/2026_lowPU/lowPU_byls.csv \
  --output output/2026_lowPU/avgpu_per_run \
  --pu-bands 1.5,3.5,6.5,15.5,30.5 --band-labels pu1,pu2,pu5,pu11,pu23,pu41
```

---

## plot_pileupHists.py

Plots the histograms from `produce_pileupHist.py` (`--mode data`) or `produce_pileupWeight.py` (`--mode weights`) as small multiples, one panel per input file. In `--mode weights` each panel gets a data-vs-MC overlay with the data/MC ratio underneath.

| Argument | Required | Description |
|---|---|---|
| `--files` | Yes | Input ROOT files, one panel each |
| `--labels` | No | Comma separated panel labels (default: file basenames) |
| `--mode` | No | `data` (default) or `weights` |
| `--hist` | No | Histogram name in `--mode data` (default: `pileup`) |
| `--output` / `-o` | Yes | Output path without extension |
| `--xmax`, `--ncols`, `--log`, `--title` | No | Axis limit, grid width, log y, figure title |

---

## rebin_pileupHist.py

Rebins and/or truncates a pileup histogram. Filling the MC histogram means reading the whole NanoAOD sample, so it is done once at the finest binning and range needed and the coarser or narrower versions are made from it here instead of by a second pass.

| Argument | Required | Description |
|---|---|---|
| `input` / `output` | Yes | Input and output ROOT files |
| `--rebin` | No | Rebinning factor, must divide the number of bins (default: 1) |
| `--xmax` | No | Truncate the axis to `[0, xmax]`, folding the rest into the overflow. Must fall on a bin edge, so no boundary moves |
| `--hist` | No | Single histogram to process (default: every TH1 in the file) |

```bash
python3 Pileup/rebin_pileupHist.py mc_1000bins.root mc_20bins_max20.root --rebin 10 --xmax 20
```

---

## run_2026_lowPU.sh

Runs the whole chain for `Cert_Collisions2026_lowPU.json`. Run it from the repository root after `source activate_environment.sh`.

1. `brilcalc lumi --byls` over the certification JSON with the `BRIL` normtag.
2. `plot_avgpu_per_run.py` — average pileup per run.
3. `avgpu_per_run.py --split-pu` — six pileup bands (`pu1`, `pu2`, `pu5`, `pu11`, `pu23`, `pu41`), split per lumisection.
4. `produce_pileupJSON.py` — the per-LS pileup JSON, since Collisions26 has no official one.
5. Data histograms for every band at 66000 / 69200 / 72400 and 71800 / 75300 / 78800 µb, in 1.0 and 0.1 wide bins plus the `observed` mode. The `pu5` profiles are capped at PU 20.
6. MC references: `Pileup_nTrueInt` and `Pileup_nPU`, read once each and rebinned/truncated with `rebin_pileupHist.py`.
7. Weights for every combination.
8. `produce_pileupCorrectionlib.py` — the `pu5` observed weights at 75300 µb as a correctionlib file.

Finally the three summary plots.

### Two things to know about this era

**There is no official 2026 pileup JSON.** `/eos/user/c/cmsdqm/www/CAF/certification/Collisions26/` has no `PileUp/` directory, so step 4 builds one. It is registered in `Data/PileupJSONS.json` under `2026`, and `normtag_PHYSICS.json` stops in 2024 so `BRIL` is the only usable normtag.

**The certification JSON is not a single pileup point.** 98.1% of the 2120 pb⁻¹ sits at PU ≈ 5, 0.36% at PU 1–3, and the rest is spread from PU 6 to 48. Four runs (402736, 402805, 403166, 403193) ramp the pileup within the run, which is why the split is per lumisection rather than per run.

**The MC cannot be reweighted on the true pileup.** Every event in `RunIII2026LowPUSummer26` has `Pileup_nTrueInt == 5.0` exactly — the campaign was digitised at a single fixed pileup. `Pileup_nPU` does have the expected Poisson spread (0–17, mean 5.005), so the usable weights are the `_observed` ones.

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
| `--numPileupBins` / `--maxPileupBin` | No | MC histogram binning. Defaults to the binning of the data histogram, i.e. whatever `produce_pileupHist.py` produced |
| `--mc_branch` | No | MC branch to histogram (default: `Pileup_nTrueInt`). Use `Pileup_nPU` with a `--calcMode observed` data histogram |
| `--file_prefix` | No | Prefix for the DAS logical file names (default: `root://cms-xrd-global.cern.ch/`). On lxplus, `/eos/cms` is far faster for anything hosted at T2_CH_CERN — minutes rather than hours |
| `--threads` | No | Threads for the MC RDataFrame loop (default: 16) |

The script now refuses to run if the data and MC binnings differ, rather than silently dividing mismatched histograms.

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

---

## produce_pileupCorrectionlib.py

Writes the weights of `produce_pileupWeight.py` as a [correctionlib](https://cms-nanoaod.github.io/correctionlib/) schema v2 JSON file, the format the LUM POG publishes under `/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/`. One correction holds a category over `nominal`/`up`/`down`, each a binning node with `flow: "clamp"`, so the nominal and the two minimum bias cross section variations are read from three separate files.

The ratio is recomputed rather than copied from the `weights` histogram: `produce_pileupWeight.py` scales data and MC to maximum 1 before dividing, while the published convention is data/MC with both normalised to unit area, which differs by a constant `Σmc / Σdata`. Bins where the MC is empty get weight 1, as in the published files.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--nominal` | Yes | Weights file for the nominal cross section, or a bare `pileupCalc.py` histogram together with `--pileup_mc` |
| `--up` / `--down` | No | The same for the varied cross sections, e.g. 78800 / 71800 µb for a 75300 µb nominal. Omit both to write a file with only `nominal` |
| `--pileup_mc` | No | MC reference file. Only needed when the inputs are bare `pileupCalc.py` histograms |
| `--mc_branch` | No | Histogram name in `--pileup_mc` (default: `Pileup_nTrueInt`). Use `Pileup_nPU` for the observed mode |
| `--name` | No | Correction name (default: the output file stem without the `puWeights_` prefix) |
| `--input-name` | No | Name of the pileup input variable (default: `NumTrueInteractions`). Use `NumInteractions` for weights made against `Pileup_nPU` |
| `--description` | No | Description stored with the correction |
| `--version` | No | Correction version (default: 0) |
| `--max-rel-error` | No | Set bins whose relative statistical error exceeds this to weight 1, the way `produce_pileupWeight.py` does (default: 0, no smoothing, which is what the published files do) |
| `--validate` | No | Read the result back with `correctionlib` and print the weights. `correctionlib` is a CMSSW external, so this needs `cmsenv` |
| `--output` | Yes | Output file, gzipped when the name ends in `.gz` as the published files are |

### Example

```bash
python3 Pileup/produce_pileupCorrectionlib.py \
  --nominal output/2026_lowPU/pileup_weights_2026_lowPU_pu5_75300ub_max20_observed.root \
  --up      output/2026_lowPU/pileup_weights_2026_lowPU_pu5_78800ub_max20_observed.root \
  --down    output/2026_lowPU/pileup_weights_2026_lowPU_pu5_71800ub_max20_observed.root \
  --mc_branch Pileup_nPU --input-name NumInteractions \
  --name Collisions26_lowPU_pu5 --validate \
  --output output/2026_lowPU/puWeights_2026_lowPU_pu5_75300ub_observed.json.gz
```

### Output

A gzipped correctionlib file with the binning of the input histograms — 20 unit wide bins over `[0, 20]` for the `pu5` band. Read it with

```python
import correctionlib
cset = correctionlib.CorrectionSet.from_file("puWeights_2026_lowPU_pu5_75300ub_observed.json.gz")
weight = cset["Collisions26_lowPU_pu5"].evaluate(nPU, "nominal")  # or "up" / "down"
```

`flow: "clamp"` means a value outside the histogram range gets the weight of the nearest bin, so an MC event above PU 20 keeps the last bin's weight rather than failing.
