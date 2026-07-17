# vendor/fhe_dsl — provenance

The Niobium DSL cross-compiler (`xcomp/`) and its user documentation (`docs/`)
are copied verbatim from the **niobium-client** repository at the pinned commit
used by VitalVault. This is source (pure-Python compiler + Markdown); it contains
no built binaries.

- Source repo:   https://github.com/NiobiumInc/niobium-client
- Pinned commit: `f21df4e8fa2c9ceae0bd1a905f08d6a8fe69709d`
- Copied from:   `dsl_fhe/xcomp/` and `dsl_fhe/{NB_LANGUAGE,GRAMMAR,HOWTO,README}.md`
- License:       Apache-2.0 (see `LICENSE`)

`xcomp/` compiles VitalVault's `.niob` sources to OpenFHE C++. It depends only on
the Python standard library. The native FHE runtime it links against is NOT here
— it is provisioned into the git-ignored `vendor/fhe_runtime/` (see
`../runtime.lock` and `serve/fetch_runtime.sh`).

If the pinned commit is bumped, re-copy `xcomp/` + `docs/` from that commit and
update `../runtime.lock` to match.
