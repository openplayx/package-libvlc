#!/usr/bin/env bash
# File format playback tests: prepares the samples of formats/manifest.json
# and plays each one through LibVlcBackend in the example host app (macOS).
# These tests are not part of `flutter test` and do not run by default; run
# them when this package changes (see README).
#
# Usage: tool/test_formats.sh [--only ID[,ID|GLOB...]] [--pack] [--device macos]
# Env:   OPX_SAMPLE_CACHE  sample cache (default ~/.cache/openplayx-libvlc-samples)
#        OPX_REPORT_DIR    report directory (default build/formats/<timestamp>)
#        OPX_FORMAT_PACK   material pack for --pack (default ../openplayx-test/formats;
#                          its samples are "pack-<issue>-<ext>", e.g. --only 'pack-*')
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
only="" pack="" device="macos"
while [ $# -gt 0 ]; do
  case "$1" in
    --only) only="$2"; shift 2 ;;
    --pack) pack="${OPX_FORMAT_PACK:-$root/../openplayx-test/formats}"; shift ;;
    --device) device="$2"; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
for tool in flutter ffmpeg ffprobe python3; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 2; }
done
cache="${OPX_SAMPLE_CACHE:-$HOME/.cache/openplayx-libvlc-samples}"
report="${OPX_REPORT_DIR:-$root/build/formats/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$report"
report="$(cd "$report" && pwd)"

echo "== samples ($cache)"
python3 -I "$root/tool/prepare_samples.py" --cache "$cache" --out "$report/samples.json" ${only:+--only "$only"} ${pack:+--pack "$pack"}

# The host app is restarted every $batch samples, and every failed sample is
# then run once more alone: a player can disturb later players in the same
# process (see README, known issues), so the isolated run decides.
batch="${OPX_BATCH:-6}"
python3 -I - "$report" "$batch" <<'PY'
import json, pathlib, sys
report, size = pathlib.Path(sys.argv[1]), int(sys.argv[2])
samples = json.loads((report / "samples.json").read_text())["samples"]
for i in range(0, len(samples), size):
    (report / f"samples-{i // size + 1:02d}.json").write_text(json.dumps({"samples": samples[i:i + size]}))
PY

cd "$root/example"
flutter pub get >/dev/null
run_part() {
  echo "== playback tests ($device): $(basename "$1")"
  flutter test integration_test/formats_test.dart -d "$device" \
    --dart-define=OPX_SAMPLES="$1" \
    --dart-define=OPX_REPORT="$report" 2>&1 | tee -a "$report/flutter.log" |
    grep -E '^[0-9]+:[0-9]+ \+[0-9]+.*: [^ ]+$|Some tests failed|All tests passed' || true
}
for part in "$report"/samples-[0-9]*.json; do run_part "$part"; done

python3 -I - "$report" <<'PY'
import json, pathlib, sys
report = pathlib.Path(sys.argv[1])
samples = {s["id"]: s for s in json.loads((report / "samples.json").read_text())["samples"]}
failed = [r["id"] for f in sorted(report.glob("results-[0-9]*.json"))
          for r in json.loads(f.read_text())["results"] if r.get("result") != "passed"]
ran = {r["id"] for f in report.glob("results-[0-9]*.json") for r in json.loads(f.read_text())["results"]}
failed += [i for i in samples if i not in ran]  # crashed batches
for n, i in enumerate(dict.fromkeys(failed), 1):
    (report / f"samples-retry-{n:02d}.json").write_text(json.dumps({"samples": [samples[i]]}))
PY
for part in "$report"/samples-retry-*.json; do
  [ -e "$part" ] && run_part "$part"
done

status=0

python3 -I "$root/tool/format_report.py" "$report" "$device" || status=1
exit $status
