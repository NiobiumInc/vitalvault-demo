# VitalVault — local Full-FHE app

**ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.**

VitalVault runs the **real** 25-marker / 8-panel wellness model under **CKKS fully
homomorphic encryption**, entirely on your own Apple-silicon Mac. There is **no
JavaScript preview, no Toy mode, no verification button, and no fallback**: after
you submit your profile, the app runs `key_generation → encrypt_profile →
compute_wellness → decrypt_report` at **full 128-classic security parameters
(ring 65536, depth 20)** and shows results **only** from the decrypted output.

## Requirements

| | |
|---|---|
| **OS** | macOS (Apple silicon / **arm64** — M1 or newer). Intel Macs and Linux are **not** supported by the prebuilt binaries; see *Platform* below. |
| **RAM** | **16 GB recommended.** 8 GB works but swaps heavily → each run is slower (see timings). |
| **Disk** | ~**4 GB** free while running (keys ~1.4 GB + ciphertexts ~1.7 GB per run, in a temp dir that is securely wiped afterward), plus ~2-3 GB for the one-time OpenFHE/client build tree. |
| **Tools** | Xcode Command Line Tools (`xcode-select --install`), `cmake`, `python3` (3.10+), `git`. No Python packages needed. |
| **Time** | First build of OpenFHE + the Niobium client is **10-30 min** (one time). Each FHE run is **~3 min** (16 GB) to **~8 min** (8 GB, swapping). |

## How to run it

**You must start the bridge from a Terminal and open the localhost URL in your
browser. Do NOT open `ui/index.html` directly** — opening the file has no bridge
to talk to, so the encrypted pipeline can't run and the app will only show an
error. The bridge (which runs the FHE binaries) and the page must be same-origin.

### First time — build, then run (one command)

```bash
git clone --recurse-submodules <repo-url> vitalvault-private
cd vitalvault-private
./serve/run.sh            # builds anything missing, then serves on http://127.0.0.1:8010/
```

`run.sh` is idempotent: it builds OpenFHE + the client + `fhetch_driver` + the
VitalVault stage binaries only if they're absent, then starts the bridge.
(If you cloned without submodules first: `git submodule update --init --recursive`.)

### Once built — the exact working flow

In a Terminal:

```bash
cd ~/Desktop/vitalvault-private          # wherever you cloned the repo
python3 serve/fhe_bridge.py --port 8010
```

Then open in your browser:

```
http://127.0.0.1:8010/
```

Enter vitals/labs (or "explore with sample data"). The encrypted pipeline runs
automatically with a live progress view (**Generating keys → Encrypting →
Computing on ciphertext → Decrypting**) and clearly warns it can take several
minutes. Results appear **only** after the real FHE run succeeds.

### What `run.sh` does (equivalent manual build steps)
```bash
make -C third_party/niobium-client build-release          # OpenFHE + libnbfhetch + examples
make -f Makefile.vitalvault \
     third_party/niobium-client/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver
make -f Makefile.vitalvault vitalvault                     # DSL -> C++ -> stage binaries
python3 serve/fhe_bridge.py --port 8010                    # then open http://127.0.0.1:8010/
```

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
| compute_wellness | ~154 s (up to ~487 s on 8 GB) | trace 160 MB |
| decrypt_report | ~5 s | — |

Peak memory footprint ~**6.66 GB**. Decrypted result vs the Python/JS oracle:
**biological_age Δ 3.87e-3**; panel scores within the degree-13 Chebyshev bound
(≤ 0.076 on the 0–100 scale, on single-marker abs-penalty panels). Ciphertext-only
proof passes (evaluator produced all 8 panels with `sk`/`zvec`/`wmask` withheld).

## Platform

All binaries + dylibs are **Mach-O arm64** and link `/usr/lib/libSystem.B.dylib`
+ `/usr/lib/libc++.1.dylib` — **macOS-only**. They will **not** run on Linux
(Mach-O ≠ ELF) or Intel macOS. To run elsewhere you must **rebuild the entire
stack** (OpenFHE, niobium-fhetch/`libnbfhetch` + `fhetch_driver`, the Niobium
client, and the VitalVault stage binaries) for that platform. The build system
is Apache-2.0 and supports Linux, but it is a from-scratch compile on the target.
For sharing today, the intended path is: **others clone and run on their own
Apple-silicon Macs.**

## Clean-machine testing checklist

Verify someone else can clone and run with nothing unique to the author's machine.
Best done on a *second* Mac or a fresh macOS user account.

- [ ] **Fresh clone**, different directory and username: `git clone --recurse-submodules <url> ~/vv-test && cd ~/vv-test` (confirm it works outside `/Users/<author>/…`).
- [ ] **No global env assumptions**: open a brand-new terminal; do **not** export `LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH`/`NBCC_FHETCH_DRIVER` (the bridge sets them itself).
- [ ] **Tools present**: `xcode-select -p`, `cmake --version`, `python3 --version` (≥3.10). If missing, `xcode-select --install` and install cmake.
- [ ] **Submodule pinned**: `git submodule status` shows `third_party/niobium-client` at the expected commit (no `+`/`-` prefix).
- [ ] **One command**: `./serve/run.sh` completes the build (first run 10-30 min) and prints the URL. Re-running skips already-built pieces.
- [ ] **No hardcoded paths**: `grep -rn "/Users/" serve/ Makefile.vitalvault` returns nothing (the author's home path must not appear).
- [ ] **Started via Terminal, not the file**: confirm opening `ui/index.html` directly does **not** work (shows an error, no scores) — the bridge must be started in Terminal and the app opened at the localhost URL.
- [ ] **UI loads** at `http://127.0.0.1:8010/`; the top bar reads "real CKKS ring 65536"; there is **no** "computed in JavaScript" banner and **no** "Run under real FHE" button.
- [ ] **Submit runs FHE**: entering data (or "explore with sample data") shows the progress steps (keygen→encrypt→compute→decrypt) and the "several minutes" warning; **no** results appear until it finishes.
- [ ] **Results are FHE**: the results page shows the green "Computed under CKKS homomorphic encryption" provenance with `evaluator saw secret key: false`.
- [ ] **Failure path**: stop the bridge mid-run (or disconnect) → the UI shows the red error screen and **does not** show any scores.
- [ ] **Concurrency**: while one run is in progress, a second submission returns HTTP 429 ("already running").
- [ ] **Cleanup**: after a run, `ls $TMPDIR/vv_fhe_full_*` shows nothing left behind.
- [ ] **Disk/RAM**: confirm ≥4 GB free disk and note RAM (16 GB smooth; 8 GB works but slow).
```
grep -rn "/Users/" serve/ Makefile.vitalvault   # must print nothing
```
