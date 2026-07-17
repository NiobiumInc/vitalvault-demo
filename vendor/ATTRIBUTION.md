# Third-party attribution — FHE runtime

VitalVault provisions a native FHE runtime into the git-ignored
`vendor/fhe_runtime/` (built from source by `serve/fetch_runtime.sh`, or, in a
future opt-in phase, downloaded as a prebuilt archive). That runtime bundles the
following third-party components. Their license texts ship inside
`vendor/fhe_runtime/` (`LICENSE`, `NOTICE`) once provisioned; this file records
attribution in the committed repo since the runtime itself is not committed.

| Component | Source | License |
|---|---|---|
| Niobium client / FHETCH (`libnbfhetch`, `fhetch_driver`, auto-facade) | https://github.com/NiobiumInc/niobium-client @ `f21df4e…` (submodule `niobium-fhetch`) | Apache-2.0 (+ `NOTICE`) |
| OpenFHE (Niobium-instrumented branch) | vendored under niobium-fhetch/vendor/openfhe | BSD-2-Clause |
| yaml-cpp | fetched by the OpenFHE/client build | MIT |

The Niobium DSL compiler copied into `vendor/fhe_dsl/` is Apache-2.0 (see
`vendor/fhe_dsl/LICENSE`).

**Redistribution note:** committing or hosting *prebuilt* runtime binaries
(phase 2) requires confirming redistribution terms for the instrumented OpenFHE +
FHETCH build (Apache-2.0 + BSD-2 permit it; verify no additional terms) and is
gated on sign-off. The default from-source path redistributes nothing — each user
builds locally at the pinned commit.
