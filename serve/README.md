# VitalVault — local Full-FHE app

**ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.**

VitalVault runs the **real** 25-marker / 8-panel wellness model under **CKKS fully
homomorphic encryption**, entirely on your own Apple-silicon Mac. There is **no
JavaScript preview, no Toy mode, no verification button, and no fallback**: after
you submit your profile, the app runs `key_generation → encrypt_profile →
compute_wellness → decrypt_report` at **full 128-classic security parameters
(ring 65536, depth 20)** and shows results **only** from the decrypted output.

The Niobium DSL compiler + FHE toolchain (OpenFHE, FHETCH, `fhetch_driver`) live
in the **`third_party/niobium-client` git submodule**, pinned to a specific
commit. Clone recursively and the whole toolchain comes with the repo; the first
`./serve/run.sh` builds it locally.

## Requirements

| | |
|---|---|
| **OS** | **Apple-silicon macOS (arm64, M1 or newer).** Intel Macs and Linux are not supported by the built toolchain (see *Platform*). |
| **RAM** | **16 GB recommended.** 8 GB works but swaps → each FHE run is slower. |
| **Disk** | ~**4 GB** free while running (keys ~1.4 GB + ciphertexts ~1.7 GB per run, in a temp dir wiped afterward), plus the submodule source + build tree. |
| **Tools** | Xcode Command Line Tools (`xcode-select --install`), `cmake`, `python3` (3.10+), `git`. No Python packages needed. |
| **Internet** | Required for the initial recursive clone / submodule init. |

## How to run it (clean clone)

```bash
git clone --recurse-submodules <repo-url>
cd <repo-folder>
./serve/run.sh
```

Then open **http://127.0.0.1:8010/** in a browser.

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

**Start the bridge from a Terminal and open the localhost URL. Do NOT open
`ui/index.html` directly** — the page needs the local bridge (which runs the FHE
binaries) at the same origin; opening the file alone just shows an error.

### What the first run does

`./serve/run.sh` is idempotent and, on a fresh clone, does three things:

1. **Init the submodule** (if you didn't clone recursively) and **build the
   native toolchain** — OpenFHE + `libnbfhetch` + auto-facade + `fhetch_driver`.
   This is the long step: **~15–30+ minutes** the first time, depending on your
   Mac (RAM/cores). It builds inside `third_party/niobium-client` and is cached,
   so it only happens once.
2. **Build the VitalVault stage binaries** from the submodule's DSL compiler
   (`third_party/niobium-client/dsl_fhe/xcomp`) — ~1–2 minutes.
3. **Serve** the app on `http://127.0.0.1:8010/`.

Later launches reuse the built toolchain and skip straight to serving. Once set
up you can also start it directly:

```bash
python3 serve/fhe_bridge.py --port 8010     # then open http://127.0.0.1:8010/
```

Enter vitals/labs (or "explore with sample data"). Sample data fills the form so
you can review and edit every value, then submit from a final review screen — the
encrypted pipeline starts only on submit. It runs with a live progress view
(**Generating encryption keys → Encrypting profile → Computing on encrypted data
→ Decrypting results**). **Each Full ring-65536 calculation takes several
minutes** (roughly 3 min on 16 GB, longer on 8 GB); results appear **only** after
the real FHE run succeeds.

## How it works / privacy

| Stage | Role | Sees secret key? | Sees plaintext? |
|---|---|---|---|
| key_generation | client | yes (creates) | — |
| encrypt_profile | client | — | yes |
| **compute_wellness** | **evaluator** | **no** — `sk.bin` moved out | **no** — `zvec/wmask` moved out |
| decrypt_report | client | yes | yes |

**Exact privacy boundary:** everything runs on your **local machine** — your data
never leaves your computer. The **evaluator (`compute_wellness`) receives only
ciphertext and never sees the secret key or the plaintext inputs**: per request,
`sk.bin`, `zvec.bin`, and `wmask.bin` are physically relocated out of its working
directory before it runs. The bridge process (also local, same machine) does
handle your submitted profile in cleartext in order to encrypt it — a fully
in-browser client (plaintext never leaving the browser tab) would require
compiling the stack to WASM and is not done here.

The scores, biological age, per-marker bio-age terms, and follow-up magnitudes
are all produced by the FHE pipeline. Standardization, presence/masking, banding,
the composite blend, and per-marker display are **client-side by design** (the
VitalVault trust split, not a second scoring engine). The JavaScript scoring code
in `ui/index.html` is retained **only** as a hidden development oracle for
accuracy checks — it never produces what the user sees.

**Requests are hard-serialized** (one FHE run at a time; a concurrent request
gets HTTP 429).

**Temporary-file cleanup after each run:** plaintext and secret-key files
(`zvec.bin`, `wmask.bin`, `sk.bin`) receive **best-effort overwriting** before
deletion; encrypted ciphertexts and the `.fhetch` trace are deleted normally
(overwriting encrypted data adds no privacy and would stall each run). The
overwriting is best-effort, not an absolute secure-erasure guarantee — on SSDs,
wear-leveling can retain residual copies the filesystem cannot address.

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

## Platform

The built toolchain + stage binaries are **Mach-O arm64** and link
`/usr/lib/libSystem.B.dylib` + `/usr/lib/libc++.1.dylib` — **Apple-silicon macOS
only**. They will not run on Linux (Mach-O ≠ ELF) or Intel macOS. Porting
elsewhere means building the submodule for that platform (its sources are
Apache-2.0 / BSD-2), which is not wired up here. The intended path is: **others
clone recursively and run on their own Apple-silicon Macs.**

## Clean-machine checklist

Verify someone else can clone and run with nothing unique to the author's machine
(best on a second Mac or a fresh macOS user account):

- [ ] **Recursive clone**, different dir/username: `git clone --recurse-submodules <url> ~/vv-test && cd ~/vv-test` (works outside `/Users/<author>/…`).
- [ ] **Submodule pinned**: `git submodule status` shows `third_party/niobium-client` at the expected commit (no `+`/`-` prefix); `third_party/niobium-client/dsl_fhe/xcomp/nbc.py` exists.
- [ ] **No global env assumptions**: brand-new terminal; do **not** export `LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH`/`NBCC_FHETCH_DRIVER` (the bridge sets them).
- [ ] **One command**: `./serve/run.sh` builds the submodule toolchain (first run 15–30+ min), builds the stage binaries, and prints the URL. Re-running skips the build and just serves.
- [ ] **No hardcoded paths**: `grep -rn "/Users/" serve/ Makefile.vitalvault` returns nothing (README examples aside).
- [ ] **Started via Terminal, not the file**: opening `ui/index.html` directly does not work (error, no scores).
- [ ] **UI loads** at `http://127.0.0.1:8010/`; top bar reads "real CKKS ring 65536"; no "computed in JavaScript" banner and no "Run under real FHE" button.
- [ ] **Sample data**: "explore with sample data" shows a "Sample data loaded" cue, fills the form, walks every screen (editable), and reaches the review screen — it does **not** auto-submit.
- [ ] **Manual + sample both reach the review screen** and start FHE only on submit.
- [ ] **Progress** shows the four streamed stages, current + completed, elapsed time, and the "several minutes" note; the compute stage stays active for the long portion.
- [ ] **Results are FHE**: green "Computed under CKKS homomorphic encryption" provenance with `evaluator saw secret key: false`.
- [ ] **Failure path**: stop the bridge mid-run → red error screen, no scores.
- [ ] **Concurrency**: a second submission while one is running returns HTTP 429.
- [ ] **Cleanup**: after a run, `ls $TMPDIR/vv_fhe_full_*` shows nothing left behind.
