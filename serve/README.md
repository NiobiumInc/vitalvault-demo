# VitalVault — local Full-FHE app

**ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.**

VitalVault runs the **real** 25-marker / 8-panel wellness model under **CKKS fully
homomorphic encryption**, entirely on your own Apple-silicon Mac. There is **no
JavaScript preview, no Toy mode, no verification button, and no fallback**: after
you submit your profile, the app runs `key_generation → encrypt_profile →
compute_wellness → decrypt_report` at **full 128-classic security parameters
(ring 65536, depth 20)** and shows results **only** from the decrypted output.

**No `niobium-client` git submodule is required.** The DSL compiler is vendored
(source-only) at `vendor/fhe_dsl/`, and the native FHE runtime is built locally on
first setup into the git-ignored `vendor/fhe_runtime/` from the exact source
commit pinned in `vendor/runtime.lock`.

## Requirements

| | |
|---|---|
| **OS** | **Apple-silicon macOS (arm64, M1 or newer).** Intel Macs and Linux are not supported by the built runtime (see *Platform*). |
| **RAM** | **16 GB recommended.** 8 GB works but swaps → each FHE run is slower. |
| **Disk** | ~**4 GB** free while running (keys ~1.4 GB + ciphertexts ~1.7 GB per run, in a temp dir wiped afterward), plus a **one-time ~300 MB** source clone + build tree while the runtime is built (removable afterward). The provisioned `vendor/fhe_runtime/` is ~26 MB. |
| **Tools** | Xcode Command Line Tools (`xcode-select --install`), `cmake`, `python3` (3.10+), `git`. No Python packages needed. |
| **Internet** | Required on the **first** run only, to fetch the pinned source. |

## How to run it (clean clone)

```bash
git clone <repo-url>
cd <repo-folder>
./serve/run.sh
```

Then open **http://127.0.0.1:8010/** in a browser.

**Start the bridge from a Terminal and open the localhost URL. Do NOT open
`ui/index.html` directly** — the page needs the local bridge (which runs the FHE
binaries) at the same origin; opening the file alone just shows an error.

### What the first run does

`./serve/run.sh` is idempotent and, on a fresh clone, does three things:

1. **Provision the native FHE runtime** (only if `vendor/fhe_runtime/` is absent).
   This **requires internet**: it shallow-clones the **exact source commit pinned
   in `vendor/runtime.lock`** into `.cache/`, then **builds OpenFHE + FHETCH +
   `fhetch_driver` + the auto-facade locally** and assembles `vendor/fhe_runtime/`.
   **This first build can take a while — roughly 10–30+ minutes depending on your
   hardware** (Mac model, RAM, cores).
2. **Build the VitalVault stage binaries** from the vendored DSL compiler
   (`vendor/fhe_dsl/xcomp`) — ~1–2 minutes.
3. **Serve** the app on `http://127.0.0.1:8010/`.

**Later launches reuse `vendor/fhe_runtime/` and do not rebuild it** — `run.sh`
skips straight to serving (a couple of seconds). Equivalently, once set up you can
start it directly:

```bash
python3 serve/fhe_bridge.py --port 8010     # then open http://127.0.0.1:8010/
```

Enter vitals/labs (or "explore with sample data"). The encrypted pipeline runs
automatically with a live progress view (**Generating keys → Encrypting →
Computing on ciphertext → Decrypting**). **Each Full ring-65536 calculation takes
several minutes** (roughly 3 min on 16 GB, longer on 8 GB); results appear **only**
after the real FHE run succeeds.

### Rebuilding the runtime intentionally

To force a fresh from-source rebuild of `vendor/fhe_runtime/` (e.g. after bumping
the pin in `vendor/runtime.lock`, or to reclaim/repair it):

```bash
./serve/fetch_runtime.sh --build-runtime
```

This also shallow-clones the pinned commit and builds locally (internet required
unless `.cache/` still holds the source). Build parallelism defaults to a
RAM-aware `min(cores, RAM_GB/2)`; override with `NIOBIUM_BUILD_JOBS=N`.

The `.cache/` source+build tree is safe to delete afterward to reclaim disk;
`fetch_runtime.sh` re-clones it if ever needed.

## How it works / privacy

| Stage | Role | Sees secret key? | Sees plaintext? |
|---|---|---|---|
| key_generation | client | yes (creates) | — |
| encrypt_profile | client | — | yes |
| **compute_wellness** | **evaluator** | **no** — `sk.bin` moved out | **no** — `zvec/wmask` moved out |
| decrypt_report | client | yes | yes |

**Exact privacy wording:** the **evaluator (`compute_wellness`) receives only
ciphertext and never sees the secret key or plaintext** — per request, `sk.bin`,
`zvec.bin`, and `wmask.bin` are physically relocated out of its working directory
before it runs. **However, the bridge itself does receive your submitted profile
(plaintext) in order to encrypt it.** Because the bridge runs on *your own
machine*, that plaintext never leaves your computer — but it is not a
zero-knowledge browser. A fully in-browser client (plaintext never leaving the
browser tab) would require compiling the whole stack to **WASM**; that is **not**
done here.

The scores, biological age, per-marker bio-age terms, and follow-up magnitudes
are all produced by the FHE pipeline. Standardization, presence/masking, banding,
the composite blend, and per-marker display are **client-side by design** (this
is the VitalVault trust split, not a second scoring engine). The JavaScript
scoring code in `ui/index.html` is retained **only** as a hidden development
oracle for accuracy checks — it never produces what the user sees.

**Requests are hard-serialized** (one FHE run at a time; a concurrent request
gets HTTP 429).

**Temporary-file cleanup after each run:** plaintext and secret-key files
(`zvec.bin`, `wmask.bin`, `sk.bin`) receive **best-effort overwriting** before
deletion; encrypted ciphertexts and the `.fhetch` trace are deleted normally
(overwriting encrypted data adds no privacy and would stall each run). The
overwriting is **best-effort, not an absolute secure-erasure guarantee**: on
modern storage — especially SSDs — wear-leveling and copy-on-write can retain
residual copies that the filesystem cannot address, so this zeroes the *logical*
contents of the sensitive files rather than guaranteeing physical erasure. The
submitted profile is never written to disk on its own — only the derived
`zvec`/`wmask`, which are among the overwritten files.

## Full-ring (65536, 128-classic) — validated

End-to-end on `full_panel_male` (chrono 45), ring 65536:

| stage | time (16 GB target) | disk |
|---|--:|--:|
| key_generation | ~7 s | keys 1.4 GB (rk 1.32 GB) |
| encrypt_profile | ~7 s | 25+25 ct, ~1.0 GB |
| compute_wellness | ~155 s (up to ~487 s on 8 GB, swapping) | trace 160 MB |
| decrypt_report | ~6 s | — |

Peak memory footprint ~**6.66 GB**. Decrypted result vs the Python/JS oracle:
**biological_age Δ ~4e-3**; panel scores within the degree-13 Chebyshev bound
(≤ 0.076 on the 0–100 scale, on single-marker abs-penalty panels). Ciphertext-only
proof passes (evaluator produced all 8 panels with `sk`/`zvec`/`wmask` withheld).
Verified from a literal clean clone (committed files only) building the runtime
from the pinned source.

## Platform

The built runtime + stage binaries are **Mach-O arm64** and link
`/usr/lib/libSystem.B.dylib` + `/usr/lib/libc++.1.dylib` — **Apple-silicon macOS
only**. They will **not** run on Linux (Mach-O ≠ ELF) or Intel macOS. Porting
elsewhere means building the stack for that platform (the sources are Apache-2.0 /
BSD-2 and the pin is recorded in `vendor/runtime.lock`), which is not wired up
here. The intended path is: **others clone and run on their own Apple-silicon
Macs.**

## Layout

- `vendor/fhe_dsl/` — committed, source-only DSL compiler (`xcomp/`) + docs + license/provenance.
- `vendor/runtime.lock` — pinned source commit + arch (and optional future prebuilt-archive URL/sha256).
- `vendor/fhe_runtime/` — **git-ignored**; the native runtime, provisioned locally by `serve/fetch_runtime.sh`.
- `.cache/` — **git-ignored**; transient source clone + build tree for the runtime build.

## Clean-machine testing checklist

Verify someone else can clone and run with nothing unique to the author's machine
(best on a second Mac or a fresh macOS user account):

- [ ] **Fresh clone**, different directory and username: `git clone <url> ~/vv-test && cd ~/vv-test` (confirm it works outside `/Users/<author>/…`).
- [ ] **No global env assumptions**: open a brand-new terminal; do **not** export `LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH`/`NBCC_FHETCH_DRIVER` (the bridge sets them itself).
- [ ] **Tools present**: `xcode-select -p`, `cmake --version`, `python3 --version` (≥3.10). If missing, `xcode-select --install` and install cmake.
- [ ] **Pin recorded**: `vendor/runtime.lock` lists the `niobium_client_commit` the runtime is built from; after setup, `cat vendor/fhe_runtime/VERSION` matches it.
- [ ] **One command**: `./serve/run.sh` provisions the runtime from source (first run 10–30+ min, needs internet), builds the binaries, and prints the URL. Re-running reuses `vendor/fhe_runtime/` and just serves.
- [ ] **No hardcoded paths**: `grep -rn "/Users/" serve/ Makefile.vitalvault vendor/fhe_dsl` returns nothing (README examples aside).
- [ ] **Started via Terminal, not the file**: opening `ui/index.html` directly does **not** work (error, no scores) — start the bridge in Terminal and open the localhost URL.
- [ ] **UI loads** at `http://127.0.0.1:8010/`; the top bar reads "real CKKS ring 65536"; there is **no** "computed in JavaScript" banner and **no** "Run under real FHE" button.
- [ ] **Submit runs FHE**: entering data (or "explore with sample data") shows the progress steps (keygen→encrypt→compute→decrypt) and the "several minutes" warning; **no** results appear until it finishes.
- [ ] **Results are FHE**: the results page shows the green "Computed under CKKS homomorphic encryption" provenance with `evaluator saw secret key: false`.
- [ ] **Failure path**: stop the bridge mid-run (or disconnect) → the UI shows the red error screen and **does not** show any scores.
- [ ] **Concurrency**: while one run is in progress, a second submission returns HTTP 429 ("already running").
- [ ] **Cleanup**: after a run, `ls $TMPDIR/vv_fhe_full_*` shows nothing left behind.
