#!/bin/bash
#
# End to end pileup chain for the 2026 low pileup certification JSON.
#
# Two things make this era different from the ones the other scripts were written for:
#
#  * Collisions26 has no official PileUp/ directory under
#    /eos/user/c/cmsdqm/www/CAF/certification/, so the per-LS pileup JSON that
#    pileupCalc.py needs is produced here from brilcalc --xing.
#
#  * The certification JSON is not a single pileup point. 98% of the recorded
#    luminosity sits at PU ~ 5, but the same runs also contain lumisections from
#    PU ~ 1 up to PU ~ 48, and four runs ramp the pileup within the run. The
#    split is therefore done per lumisection, not per run, and the histograms
#    are produced for the whole JSON and separately for each pileup band.
#
# Note on the MC: every event in the RunIII2026LowPUSummer26 campaign has
# Pileup_nTrueInt == 5.0 exactly, so it cannot be reweighted on the true pileup.
# The usable weights are the --calcMode observed ones against Pileup_nPU.
#
# Run from the repository root after `source activate_environment.sh`.
set -e

: "${LUMIENV:?source activate_environment.sh first}"

LOWPU_JSON=/cvmfs/cms-griddata.cern.ch/cat/metadata/DC/Collisions26/latest/Cert_Collisions2026_lowPU.json
MC_DATASET=/DYto2Mu-4Jets_Bin-MLL-50_TuneCP5_13p6TeV_madgraphMLM-pythia8/RunIII2026LowPUSummer26NanoAODv15-DRLowPU_Miniv6LowPU_Nanov15LowPU_160X_mcRun3_2026_lowPU_v3-v2/NANOAODSIM
OUT=$LUMIENV/output/2026_lowPU
PILEUP_JSON=$LUMIENV/Data/pileup_JSON-2026_lowPU.txt
NORMTAG=BRIL                     # normtag_PHYSICS.json stops in 2024, BRIL covers 2026
XSECS="66000 69200 72400 71800 75300 78800"
BANDS="0-1,2-3,4-6,7-15,16-30,31-100"
BAND_EDGES=1.5,3.5,6.5,15.5,30.5
BAND_NAMES="pu1 pu2 pu5 pu11 pu23 pu41"
PU5_MAX=20                       # the pu5 profiles are capped at PU 20

mkdir -p "$OUT"

echo "### 1/8 per-LS luminosity and pileup"
source /cvmfs/cms-bril.cern.ch/cms-lumi-pog/brilws-docker/brilws-env > /dev/null
BRILCALC="singularity -s exec --env PYTHONPATH=/home/bril/.local/lib/python3.10/site-packages /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-cloud/brilws-docker:latest brilcalc"
[ -f "$OUT/lowPU_byls.csv" ] || $BRILCALC lumi --byls \
    --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_$NORMTAG.json \
    -i $LOWPU_JSON -o "$OUT/lowPU_byls.csv"

echo "### 2/8 average pileup per run"
python3 "$LUMIENV/Pileup/plot_avgpu_per_run.py" "$OUT/lowPU_byls.csv" \
    --output "$OUT/avgpu_per_run" \
    --title "CMS 2026 low pileup certification (Cert_Collisions2026_lowPU.json)" \
    --note "brilcalc avgpu, normtag $NORMTAG. brilcalc uses a ~80 mb minimum bias cross section; the reweighting histograms use 69200-78800 ub." \
    --pu-bands $BAND_EDGES --band-labels $(echo $BAND_NAMES | tr ' ' ',')

echo "### 3/8 splitting the certification JSON into pileup bands"
python3 "$LUMIENV/CommonTools/avgpu_per_run.py" "$OUT/lowPU_byls.csv" \
    --split-pu --pu-bands "$BANDS" --split-dir "$OUT" --split-prefix lowPU

echo "### 4/8 per-LS pileup JSON (slow, brilcalc --xing over every run, several GB of CSV)"
if [ ! -f "$PILEUP_JSON" ]; then
    python3 "$LUMIENV/Pileup/produce_pileupJSON.py" \
        --lumijson $LOWPU_JSON --output "$PILEUP_JSON" --normtag $NORMTAG
else
    echo "reusing $PILEUP_JSON"
fi

echo "### 5/8 data pileup histograms"
# 1.0 wide bins for the usual Pileup_nTrueInt convention, and 0.1 wide because at
# PU ~ 5 the standard binning leaves only about ten filled bins. Pileup_nPU is an
# integer, so the observed mode is only produced in 1.0 wide bins.
hists() {  # $1 lumijson, $2 tag, $3 maxPileupBin
    local MAX=$3
    for XS in $XSECS; do
        python3 "$LUMIENV/Pileup/produce_pileupHist.py" --year 2026 --lumijson "$1" --tag "$2" \
            --minBiasXsec $XS --maxPileupBin $MAX --numPileupBins $MAX \
            --normtag $NORMTAG --output-path "$OUT/"
        python3 "$LUMIENV/Pileup/produce_pileupHist.py" --year 2026 --lumijson "$1" --tag "$2" \
            --minBiasXsec $XS --maxPileupBin $MAX --numPileupBins $((MAX * 10)) \
            --normtag $NORMTAG --output-path "$OUT/"
        python3 "$LUMIENV/Pileup/produce_pileupHist.py" --year 2026 --lumijson "$1" --tag "$2" \
            --minBiasXsec $XS --maxPileupBin $MAX --numPileupBins $MAX --calcMode observed \
            --normtag $NORMTAG --output-path "$OUT/"
    done
}
hists $LOWPU_JSON lowPU 100
for BAND in $BAND_NAMES; do
    [ "$BAND" = "pu5" ] && MAX=$PU5_MAX || MAX=100
    hists "$OUT/lowPU_$BAND.json" "lowPU_$BAND" $MAX
done

echo "### 6/8 MC pileup references"
# The MC pileup profile is fixed at digitisation, so each branch is read once at the
# finest binning and the coarser and narrower versions are made with rebin_pileupHist.py.
# The dataset is hosted at T2_CH_CERN, so on lxplus /eos/cms is far faster than the
# global redirector: 12 minutes rather than several hours.
mc_read() {  # $1 branch, $2 output stem, $3 nbins
    [ -f "$OUT/$2_mc_reference.root" ] || python3 "$LUMIENV/Pileup/produce_pileupWeight.py" \
        --pileup_dt "$OUT/pileup_2026_lowPU_69200ub.root" \
        --calculate_mc --mc_dataset $MC_DATASET --mc_branch "$1" \
        --numPileupBins $3 --maxPileupBin 100 --save_mc --file_prefix /eos/cms \
        --output "$OUT/$2.root"
    rm -f "$OUT/$2.root"
}
mc_read Pileup_nTrueInt pileup_mc_2026_lowPU_1000bins 1000
mc_read Pileup_nPU      pileup_mc_nPU_2026_lowPU      100

R="$LUMIENV/Pileup/rebin_pileupHist.py"
python3 $R "$OUT/pileup_mc_2026_lowPU_1000bins_mc_reference.root" "$OUT/pileup_mc_2026_lowPU_100bins_mc_reference.root"       --rebin 10
python3 $R "$OUT/pileup_mc_2026_lowPU_1000bins_mc_reference.root" "$OUT/pileup_mc_2026_lowPU_200bins_max20_mc_reference.root" --xmax $PU5_MAX
python3 $R "$OUT/pileup_mc_2026_lowPU_1000bins_mc_reference.root" "$OUT/pileup_mc_2026_lowPU_20bins_max20_mc_reference.root"  --rebin 10 --xmax $PU5_MAX
python3 $R "$OUT/pileup_mc_nPU_2026_lowPU_mc_reference.root"      "$OUT/pileup_mc_nPU_2026_lowPU_max20_mc_reference.root"     --xmax $PU5_MAX

echo "### 7/8 pileup weights"
weights() {  # $1 data suffix, $2 mc file, $3 extra args, $4 band
    for XS in $XSECS; do
        python3 "$LUMIENV/Pileup/produce_pileupWeight.py" \
            --pileup_dt "$OUT/pileup_2026_$4_${XS}ub$1.root" \
            --pileup_mc "$OUT/$2" $3 \
            --output "$OUT/pileup_weights_2026_$4_${XS}ub$1.root"
    done
}
for BAND in lowPU $(for B in $BAND_NAMES; do echo lowPU_$B; done); do
    if [ "$BAND" = "lowPU_pu5" ]; then
        weights "_max20"          pileup_mc_2026_lowPU_20bins_max20_mc_reference.root  ""                       $BAND
        weights "_200bins_max20"  pileup_mc_2026_lowPU_200bins_max20_mc_reference.root ""                       $BAND
        weights "_max20_observed" pileup_mc_nPU_2026_lowPU_max20_mc_reference.root     "--mc_branch Pileup_nPU" $BAND
    else
        weights ""          pileup_mc_2026_lowPU_100bins_mc_reference.root  ""                       $BAND
        weights "_1000bins" pileup_mc_2026_lowPU_1000bins_mc_reference.root ""                       $BAND
        weights "_observed" pileup_mc_nPU_2026_lowPU_mc_reference.root      "--mc_branch Pileup_nPU" $BAND
    fi
done

echo "### 8/8 correctionlib"
# The published pileup weights are a correctionlib file, not a ROOT histogram. Only the
# pu5 band is worth publishing: it carries 98% of the luminosity, and only the observed
# weights are usable because Pileup_nTrueInt is fixed at 5.0 in this MC campaign.
python3 "$LUMIENV/Pileup/produce_pileupCorrectionlib.py" \
    --nominal "$OUT/pileup_weights_2026_lowPU_pu5_75300ub_max20_observed.root" \
    --up      "$OUT/pileup_weights_2026_lowPU_pu5_78800ub_max20_observed.root" \
    --down    "$OUT/pileup_weights_2026_lowPU_pu5_71800ub_max20_observed.root" \
    --mc_branch Pileup_nPU --input-name NumInteractions \
    --name Collisions26_lowPU_pu5 \
    --description "Observed pileup (Pileup_nPU) weights for the PU~5 band of Cert_Collisions2026_lowPU.json, minBiasXsec 75300 ub (up/down: 78800/71800 ub). Pileup_nTrueInt is fixed at 5.0 in RunIII2026LowPUSummer26, so true-pileup reweighting is not possible for this campaign." \
    --validate \
    --output "$OUT/puWeights_2026_lowPU_pu5_75300ub_observed.json.gz"

echo "### plots"
LABELS="all lowPU,pu1 band,pu2 band,pu5 band (max $PU5_MAX),pu11 band,pu23 band,pu41 band"
FINE=""; OBS=""; TRUE=""
for B in lowPU $(for B in $BAND_NAMES; do echo lowPU_$B; done); do
    if [ "$B" = "lowPU_pu5" ]; then FS="_200bins_max20"; OS="_max20_observed"; TS="_max20"
    else FS="_1000bins"; OS="_observed"; TS=""; fi
    FINE="$FINE $OUT/pileup_2026_${B}_75300ub${FS}.root"
    OBS="$OBS $OUT/pileup_weights_2026_${B}_75300ub${OS}.root"
    TRUE="$TRUE $OUT/pileup_weights_2026_${B}_75300ub${TS}.root"
done
python3 "$LUMIENV/Pileup/plot_pileupHists.py" --mode data --ncols 4 --files $FINE --labels "$LABELS" \
    --title "2026 low pileup true pileup distributions, minBiasXsec 75300 ub, 0.1 wide bins" \
    --output "$OUT/pileup_distributions_75300ub"
python3 "$LUMIENV/Pileup/plot_pileupHists.py" --mode weights --ncols 4 --files $OBS --labels "$LABELS" \
    --xlabel "Observed pileup (Pileup_nPU)" \
    --title "2026 low pileup: observed pileup, data vs DYto2Mu LowPUSummer26 Pileup_nPU, and the weights (75300 ub)" \
    --output "$OUT/pileup_weights_observed"
python3 "$LUMIENV/Pileup/plot_pileupHists.py" --mode weights --ncols 4 --files $TRUE --labels "$LABELS" \
    --xlabel "True pileup (Pileup_nTrueInt)" \
    --title "2026 low pileup: Pileup_nTrueInt is fixed at 5.0 in this MC campaign, so true-pileup reweighting is not possible (75300 ub)" \
    --output "$OUT/pileup_weights_true"

echo "Done. Output in $OUT"
