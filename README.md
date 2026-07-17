# VitalVault — Privacy-Preserving Biomarker Analytics

> **Illustrative / demo-only. Not a medical device. Not for clinical use.**
> Every number this app produces — wellness scores, a biological-age estimate,
> follow-up nudges — is built on *illustrative* reference ranges and scoring
> constants chosen for demonstration. They are **not** clinically validated and
> must never be presented as medical advice or diagnosis.

VitalVault computes wellness insights from a person's most sensitive health
data — labs, vitals, body measurements — **without the computing server ever
seeing that data in the clear.** The inputs are encrypted on the user's device,
the server runs the entire scoring computation on the ciphertext using fully
homomorphic encryption (FHE), and only the user can decrypt the result.

This document explains how that works: the protocol, who sees what, what is and
isn't protected, the two build profiles, and the eight-stage process used to
build it.

---

## 0. Try the interactive demo

The quickest way to understand VitalVault is to use it. The repo includes a
self-contained browser demo at **`ui/index.html`** — enter your own age, vitals,
and (optionally) lab values, and it produces a personalized biological-age
estimate, system scores, drivers, and follow-up nudges.

### Run it locally

It's a single static HTML file with no build step and no dependencies, so any of
these works from a terminal:

```bash
# macOS — open in your default browser
open ui/index.html

# Linux
xdg-open ui/index.html

# or serve it (any OS) if you prefer a localhost URL — useful for testing on a
# phone over the same network:
cd ui
python3 -m http.server 8000
# then visit http://localhost:8000/  (or http://<your-ip>:8000/ from a phone)
```

There's nothing to install. On the welcome screen you can either enter your own
values or tap *"explore with sample data"* for an instant populated dashboard.

### What the demo actually computes — read this

> **The browser demo runs entirely in local JavaScript. It is NOT the FHE
> pipeline.** The scoring you see is computed in your browser by a JavaScript
> *port* of the Python scoring harness (`harness/scoring.py` + `constants.py`).
> It mirrors that model closely — the same standardization, per-marker penalty
> curves, biological-age terms, optional-field masking, and confidence logic —
> so the numbers are representative of what the real system produces. But no
> encryption happens on this page; nothing is sent anywhere; it is a design and
> scoring demonstration, not a privacy demonstration.

> **The FHE pipeline was verified separately in the backend prototype.** The
> actual encrypted computation — server scoring on ciphertext it cannot
> decrypt — was built and run as the `.niob` pipeline described in the rest of this
> document. On the Toy profile it was run end-to-end and its decrypted output
> matched the cleartext reference within CKKS noise (see §4). The browser demo
> and the FHE pipeline share the *same scoring model*; they differ only in
> *where and how* the computation happens.

### Demo path vs. future FHE path

|  | **Browser demo (today)** | **FHE path (the real product)** |
|---|---|---|
| Where scoring runs | In your browser, in JavaScript | On a server, on encrypted data it cannot read |
| What the math is | A faithful port of the scoring harness | The same model, compiled to an FHE circuit |
| Privacy | None claimed — it's all local, nothing sent | The server never sees plaintext; only you decrypt |
| Status | Working, interactive | Circuit verified on the Toy profile; production (Full) profile and a browser↔server deployment are future work (see §4 and the roadmap) |
| Purpose | Show the experience and the scoring | Show — and provide — the privacy guarantee |

In short: **the demo shows what VitalVault feels like and what it computes; the
FHE pipeline is how it would compute that privately in production.** Wiring the
verified pipeline output into this UI, and eventually running the encryption
client-side in the browser, are the next steps on the roadmap — not yet done.

> **Reminder — illustrative / demo-only.** Like everything in VitalVault, the
> browser demo uses illustrative reference ranges and scoring constants that are
> **not clinically validated**. It is not a medical device, does not provide a
> diagnosis, and must never be used as medical advice. Always consult a qualified
> provider.

---

## 1. What VitalVault produces

From a fixed set of 17 markers across four panels (Core vitals, Metabolic,
Lipid, Thyroid), VitalVault returns:

- **System scores** (0–100) for each panel — how well that system's markers sit
  within healthy reference ranges.
- A **biological-age estimate** — a transparent, illustrative index that nudges
  the user's chronological age up or down based on their biomarkers. It is
  explicitly *not* a clinical or mortality measure.
- **Per-marker contributions** — what pushed each score and the bio-age estimate,
  so the result is interpretable rather than a black box.
- **Follow-up indicators** — calm, non-diagnostic nudges ("worth discussing with
  a provider") for markers that sit well outside their reference range.
- A **data-completeness/confidence** label — how much data informed the result.
  This reflects *completeness, not accuracy*.

The headline framing: **biological age is the engaging signal; follow-up
indicators carry any warning.** The two are independent channels, and a positive
headline never visually overrides an active follow-up nudge.

---

## 2. The protocol (how a request flows)

VitalVault follows the standard FHE client–server shape: one transmission in,
one transmission out, no mid-computation round trips.

```
  CLIENT (the user's device — holds the secret key)
  ───────────────────────────────────────────────────────────
   1. Enter raw inputs (age, height, weight, labs, ...).
   2. Engineer features that need division/branching:
        BMI = weight / height²,  waist-to-height ratio,
        activity 0–4 → 0–1 scalar.            [cleartext, on your own data]
   3. Standardize each marker:  z = (value − midpoint) / half-width,
        clamped to [−3, +3].   Pick per-sex/age reference constants here.
   4. Handle optional labs: any missing marker → z = 0 and mask weight = 0,
        with the panel's remaining weights renormalized.
   5. Encrypt the fixed 17-value z-vector and the weight mask (CKKS).
                         │
                         │  ciphertext only  ─────────────────►
                         ▼
  SERVER / The Fog (no secret key — never sees your values)
  ───────────────────────────────────────────────────────────
   6. Compute on the ciphertext, using fixed plaintext scoring weights:
        • per-marker penalty curves  (Chebyshev approximation)
        • weighted system scores
        • biological-age delta
        • per-marker contributions
        • follow-up indicators
                         │
                         │  encrypted results  ◄──────────────
                         ▼
  CLIENT
  ───────────────────────────────────────────────────────────
   7. Decrypt the results.
   8. Apply client-side finishing (no encrypted cost):
        • biological-age = chronological age + capped delta (−8 .. +10 yr)
        • display floor so the lowest score reads "Worth reviewing", not 0
        • banding, education cards, confidence label, headline qualification.
```

The key architectural rule: **anything that is a transform of a single user's
own inputs, needs division/branching, or is pure presentation, happens on the
client.** Doing arithmetic on data you already hold leaks nothing new, and it
keeps the encrypted circuit shallow. The server only does the genuinely
sensitive part — combining the values into scores it cannot read.

---

## 3. Threat model — what is and isn't protected

### The trust assumption

VitalVault assumes a **semi-honest ("honest-but-curious") server**: it follows
the protocol correctly but may try to learn whatever it can from what it sees.
Against that adversary, FHE protects the data *during computation* — the server
performs the math without ever holding a key that could decrypt anything.

### What IS protected

- **Your raw inputs.** *By design,* the server never sees your labs, vitals, or
  measurements — it only holds ciphertext and the public evaluation keys, which
  cannot decrypt. (In this single-machine demo that separation is architectural,
  not sandbox-enforced — see "Key handling" below.)
- **Even the shape of your data.** Every user submits the identical fixed
  17-marker vector — present and absent markers look the same on the wire
  (absent ones are encrypted zeros with zero mask weight). So the server cannot
  infer *which labs you provided* from ciphertext count, size, or structure.
- **The intermediate computation.** Scores, the bio-age delta, contributions, and
  follow-up indicators are all computed and returned encrypted; the server sees
  none of them in the clear.

### What is NOT protected (read this carefully)

- **The output, once you decrypt it.** FHE protects data *in computation*; it
  does not limit what the *result* reveals. Your scores and bio-age are derived
  from your labs, so they carry information about them. In VitalVault this is
  acceptable because **you are the only party who can decrypt** — you are both
  the data owner and the result consumer. If the design ever allowed a different
  party to decrypt, that would need separate, careful thought.
- **Integrity / correctness of the computation.** A semi-honest server returns
  correct results by assumption. VitalVault does **not** defend against a
  *malicious* server that runs a different function and returns wrong scores.
  There is no proof-of-correct-computation here. Don't claim one.
- **Your device.** If the user's device is compromised, the secret key and
  plaintext inputs are exposed. FHE protects data in transit and in server-side
  computation, not a compromised endpoint.
- **Traffic metadata.** That you used VitalVault, when, and how often is not
  hidden by FHE. (The fixed-shape design does hide *what panels* you sent, but
  not *that* you sent something.)
- **Adaptive-query abuse / decrypt oracles.** A hosted deployment should
  rate-limit, and — more importantly — must never expose a "send me a ciphertext,
  I'll decrypt it and tell you the result" service. CKKS has a sharp, well-known
  property: it is **not secure against an attacker who can submit ciphertexts and
  observe their decrypted outputs**. With enough such query/answer pairs, an
  attacker can reconstruct the secret key. In VitalVault this risk is *zero in
  practice* because the same person encrypts the inputs and decrypts the
  results — there is no decryption service for anyone else to query. But if you
  ever adapt this design so that one party decrypts on behalf of others, that is
  a genuine cryptographic break, not a theoretical edge case. Keep decryption on
  the data owner's side, always.

### Key handling — and why this is a single-machine demo

This is the most important operational point, and it's an honest one.

- **`sk.bin` is your secret key.** Key generation writes it to
  `io/<profile>/keys/sk.bin` as an unencrypted file. Anyone who can read that
  file can decrypt everything VitalVault protects. The whole "the server never
  sees your data" guarantee rests on that file staying private to the client.
- **It lives next to the data it protects.** For demo simplicity, `sk.bin`, the
  encrypted inputs, and the reference outputs all live under the same `io/`
  tree. That means *copying or sharing the `io/` folder ships the secret key
  alongside the ciphertexts it unlocks* — which defeats the point. If you back up
  or share anything, share `io/<profile>/encrypted/` only, never `keys/`.
- **The client/server split here is architectural, not enforced.** In a real
  deployment the client and the compute server are different machines, and only
  ciphertext + public evaluation keys ever travel to the server. In *this* demo
  they are the same process tree on one laptop, reading the same directory.
  Nothing sandboxes the `compute_wellness` ("server") binary from the `sk.bin`
  sitting in the same folder — it simply chooses not to read it. So the privacy
  boundary you see described in Section 2 is the *design's* boundary, faithfully
  modeled, but it is **not** mechanically guaranteed by this single-machine
  setup. Treat the separation as illustrative.
- **What this means in practice:** run the demo on a machine you control, don't
  hand the `io/` folder (or `keys/`) to anyone, and don't mistake "the server
  code didn't read the key" for "the server code *couldn't* read the key." In
  this layout, it could.

### Input validity is not checked — garbage in, confident garbage out

VitalVault standardizes each raw input and **clamps** the result to a bounded
range so the encrypted math stays well-behaved. A side effect: a nonsensical
input (height entered in inches instead of centimeters, a mistyped lab value)
does not get rejected — it gets clamped and scored, producing a confident-looking
result built on bad data. The demo does **not** validate that inputs are in
plausible real-world ranges before encrypting. For a real tool this would need
proper input validation and unit checks; here, assume the inputs are sane,
because nothing enforces it. This is a correctness/UX gap, not a privacy one, but
it's exactly the kind of silent failure a health-adjacent demo should name out
loud.

### One FHE-specific honesty note

CKKS is **approximate** arithmetic — decrypted results carry a small amount of
numerical noise (see the verification numbers below). VitalVault accounts for
this with tolerance margins in its banding, and never displays more precision
than the noise justifies. A score of "99.31" vs a true "99.33" is the encryption
working correctly, not an error.

---

## 4. Two build profiles: Toy vs Full

VitalVault compiles two parameter profiles from the same source. They run the
**same circuit** — only the cryptographic parameters differ.

| | **Toy** (`profile 0`) | **Full** (`profile 1`) |
|---|---|---|
| Ring dimension | 2048 | 65536 (hardware target) |
| Security level | `HEStd_NotSet` (dev only) | **128-bit classic** |
| Slots used | 512 | 32768 |
| Purpose | fast functional + noise verification | production security |
| Speed / memory | seconds, light | heavy (large ciphertexts) |

**Why two profiles?** The Toy profile lets you verify *that the math is correct
and the noise budget holds* in seconds, without waiting on the heavy
128-bit-secure run. It is **not secure** — `HEStd_NotSet` means the small ring is
for development only and must never be used with real data.

The **Full profile is the real one**: ring 65536 at 128-bit classic security.
The same circuit, same scoring, same depth budget — just at parameters that are
cryptographically meaningful and that match Niobium's hardware target. When you
want production security and performance numbers, run `profile 1`.

**What the Toy run proves:** functional correctness, the client/server split, and
that the noise budget survives the full computation (including the deepest
branch). **What it does not prove on its own:** that the Full profile runs in
acceptable time and memory — that's a separate, much heavier validation.

### Verified Toy run (illustrative endurance-athlete profile)

The encrypted pipeline was run end-to-end and its decrypted output compared
against the independently-computed cleartext reference:

| Output | Encrypted | Cleartext reference | Difference |
|---|---|---|---|
| Biological age | 34.508154 | 34.508154 | exact |
| Core score | 99.312273 | 99.331087 | 0.019 |
| Metabolic score | 97.887744 | 97.900208 | 0.012 |
| Lipid score | 99.942265 | 99.956597 | 0.014 |
| Thyroid score | 99.605271 | 99.605271 | exact |

Differences of ~0.01–0.02 on a 0–100 scale are CKKS approximation noise — exactly
what should appear, and well within tolerance. **No bootstrapping was required**,
confirming the depth budget (declared depth 20) was sized correctly for the
deepest branch.

---

## 5. Parameters and the depth budget

- **Scheme:** CKKS (real-valued, approximate — the right fit for continuous
  biomarker scoring).
- **Ring dimension:** 65536 (Full) — Niobium's hardware target.
- **Security:** 128-bit classic (Full).
- **Declared multiplicative depth:** 20.
- **Bootstrapping:** none.

The circuit is deliberately **wide and shallow** — many parallel scoring
branches, each shallow — rather than one deep chain. The deepest dependent
multiplication chain is the follow-up indicator (≈ 2 + 13 squarings ≈ 15
levels). Everything else (the Chebyshev penalty curves ≈ 4 levels, the bio-age
sum ≈ 1) runs in parallel and does not add to the critical path.

> **A note on the compiler's depth warning.** `nbc check` reports a depth warning
> because its static analyzer counts the follow-up squaring loop body once
> (≈ 5 levels) without unrolling the fixed 13-iteration loop. The *actual* runtime
> depth is ≈ 15. Depth 20 is kept deliberately — lowering it toward the reported
> figure would exhaust the noise budget and silently corrupt results. The
> authoritative confirmation is the runtime decrypt-vs-reference match above, not
> the static estimate.

Cost-saving design choices that keep the budget comfortable: standardization is
done client-side (no in-circuit division), scoring weights are plaintext
(cipher×plaintext adds no dependent depth), and the branches are kept parallel.

---

## 6. What the client computes vs. what the server computes

| Calculation | Where | Why |
|---|---|---|
| BMI, waist-to-height ratio | Client | Division on the user's own inputs; leaks nothing; keeps division out of the circuit. |
| Standardization `(x−μ)/σ`, clamping | Client | Division by public constants; lets the client pick per-sex/age ranges so the server runs one fixed circuit. |
| Optional-field masking + weight renormalization | Client | Branching is free in cleartext; keeps the encrypted circuit identical for everyone. |
| **System scores** | **Server (encrypted)** | The sensitive step — combining the actual values. |
| **Biological-age delta** | **Server (encrypted)** | A function across the sensitive markers. |
| **Per-marker contributions** | **Server (encrypted)** | Byproduct of the scoring multiplications; the interpretable output. |
| **Follow-up indicators** | **Server (encrypted)** | Range comparison over the sensitive values. |
| Bio-age chrono-add + caps, display floor, banding, education text, confidence | Client | Pure presentation / branching on the decrypted result; cheaper and safer where the human can see the full picture. |

---

## 7. Repository layout

```
vitalvault/
  README.md            # this document (Stage 8)
  shared.niob            # instance, directories, fixed 17-marker wire types
  client.niob            # CKKS scheme block + key_generation / encrypt_profile /
                       #   decrypt_report stages (client holds the secret key)
  server.niob            # compute_wellness: the encrypted scoring circuit
  harness/             # Stage-3 cleartext ground truth (Python)
    constants.py       # reviewable scoring framework — reference ranges, weights,
                       #   bio-age betas (all ILLUSTRATIVE, with provenance notes)
    scoring.py         # cleartext scoring engine, tagged [CLIENT]/[SERVER]
    personas.py        # five review personas + client-side feature engineering
    stress.py          # stress-tail profiles (clamp / multi-flag / minimal-data)
    gen_profiles.py    # synthetic cohort generator + binary input + reference JSON
  ui/
    index.html         # interactive browser demo — local JS scoring (NOT FHE),
                       #   faithful port of the harness model (see §0)
vendor/
  fhe_dsl/             # vendored (source-only) Niobium DSL compiler (xcomp/) +
                       #   docs + license/provenance. Apache-2.0.
  runtime.lock         # pinned source commit the native FHE runtime is built from
  fhe_runtime/         # git-ignored: native OpenFHE/FHETCH runtime + fhetch_driver,
                       #   provisioned locally by serve/fetch_runtime.sh
serve/
  fhe_bridge.py        # local bridge: serves the UI + runs the FHE stage binaries
  run.sh               # one-command setup + run  (see serve/README.md)
  fetch_runtime.sh     # builds vendor/fhe_runtime from the pinned source
```

### Getting the code

No git submodule is required. The DSL compiler is vendored (source-only) at
`vendor/fhe_dsl/`; the native FHE runtime is built locally on first setup into
the git-ignored `vendor/fhe_runtime/` from the source commit pinned in
`vendor/runtime.lock`.

```bash
git clone https://github.com/leila-db/vitalvault-demo.git
cd vitalvault-demo
./serve/run.sh          # first run provisions the runtime from the pinned source
                        # (needs internet, 10-30+ min), then builds + serves the app
```

See [`serve/README.md`](serve/README.md) for the full run/setup flow, requirements,
and the from-source runtime build (`./serve/fetch_runtime.sh --build-runtime`).

Build/test is driven by `Makefile.vitalvault` at the repo root (it invokes the
vendored compiler in `vendor/fhe_dsl/xcomp` against `vendor/fhe_runtime`):

- `make -f Makefile.vitalvault vitalvault-check` — instant DSL validation.
- `make -f Makefile.vitalvault vitalvault-cohort` — print personas + synthetic cohort (no build).
- `make -f Makefile.vitalvault test-vitalvault` — full record → replay → decrypt
  on the Toy profile, then compare decrypted output to the cleartext reference.

---

## 8. The eight-stage build process

VitalVault was built with the methodology from Niobium's FHE design essays —
each stage gated on the previous one, with the plaintext implementation as the
ground truth that every encrypted version is checked against.

1. **Privacy model.** Parties (client + semi-honest server), single-encryptor,
   client decrypts and consumes the result. Decided who can decrypt (only the
   user) and what the output reveals.
2. **Feasibility.** Confirmed the workload is FHE-friendly: data-oblivious (fixed
   circuit, no branching on encrypted values), stays in the arithmetic lane,
   shallow multiplicative depth, and SIMD-parallel across users.
3. **Plaintext ground truth.** Built the harness — reference ranges, scoring
   curves, bio-age model, optional-field masking, confidence — and validated it
   against five personas and a stress-tail. This is the spec the encrypted
   circuit must reproduce.
4. **Scheme.** CKKS, for real-valued, error-tolerant biomarker scoring.
5. **Circuit.** Designed the packing, the per-marker penalty shapes
   (directional / U-shaped / floored), the bio-age delta, and the follow-up
   indicator — counting multiplicative depth explicitly.
6. **Parameters.** Set depth 20 / ring 65536 / 128-classic / no bootstrapping and
   confirmed the budget with `nbc check`.
7. **Implementation.** Wrote `shared.niob` / `client.niob` / `server.niob`, compiled to
   OpenFHE C++, and debugged by comparing decrypted intermediates against the
   plaintext twin until the encrypted output matched (Section 4).
8. **Protocol & threat model.** This document — what each party sees, what is and
   isn't protected, and the honest limits of the guarantee.

A guiding principle throughout: **the constraints of FHE and the constraints of a
responsible non-diagnostic health tool reinforce each other.** FHE can only
compute smooth arithmetic circuits — which is exactly what continuous wellness
scores are, and exactly what a tool that must never output a diagnosis should be
limited to.

---

## 9. Responsible-use summary

VitalVault is an educational demonstration of privacy-preserving computation. It
is **not** a medical device, does **not** provide diagnoses, and uses
**illustrative** scoring constants that are not clinically validated. Follow-up
indicators are non-diagnostic nudges to consult a qualified provider — never a
clinical conclusion. The privacy guarantee is real but bounded: it protects your
data during server-side computation under a semi-honest server, and it does not
provide computation-integrity proofs, endpoint security, or protection of what
the decrypted result itself reveals.

Finally, treat this as a **single-machine demo**: the secret key (`sk.bin`) is
stored unencrypted next to the data it protects, the client/server separation is
modeled but not sandbox-enforced, decryption must stay on the data owner's side
(CKKS is not safe against decrypt-oracle queries), and inputs are not validated
for real-world plausibility. None of these are flaws in the homomorphic
computation itself — they are deployment and framing limits of a demo, and they
are documented here so the demo's claims match what the code actually does.
