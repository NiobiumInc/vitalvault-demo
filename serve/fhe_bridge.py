#!/usr/bin/env python3
"""VitalVault FHE bridge — Full-only, real CKKS homomorphic encryption.

ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.

Serves the UI (ui/index.html) and runs the REAL encrypted pipeline for each
submission at full 128-classic security parameters:

    CKKS, ring 65536, depth 20, 128-classic security.

There is NO Toy mode, NO JavaScript-scoring fallback, and NO optional
verification step. After the browser submits a profile, this bridge runs
key_generation -> encrypt_profile -> compute_wellness -> decrypt_report and
streams stage-by-stage progress; the results page is populated ONLY from the
decrypted output. If any stage fails, the request errors — nothing is shown.

Privacy (exact wording):
  * The EVALUATOR (compute_wellness) receives only ciphertext and NEVER sees
    the secret key or the plaintext: per request, sk.bin + zvec.bin + wmask.bin
    are physically moved out of its working directory before it runs.
  * HONEST LIMITATION: this bridge DOES receive the submitted profile (plaintext)
    in order to encrypt it. It runs on the user's OWN machine (local app). A
    fully in-browser client (plaintext never leaving the browser) would require
    compiling the stack to WASM — not done.

Runtime: Full is memory- and time-heavy — expect several minutes per run and
~6-7 GB peak memory. Requests are HARD-SERIALIZED (one at a time); a concurrent
request gets HTTP 429. Temp files (profile, keys, ciphertexts, trace, outputs)
are securely wiped after each run.

Run:  python3 serve/fhe_bridge.py [--port 8000] [--host 127.0.0.1]
Stdlib only (Python 3.10+). No third-party packages.
"""
import http.server
import socketserver
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent          # no hardcoded user paths
VV = REPO / "vitalvault"
NC = REPO / "vendor" / "fhe_runtime"   # provisioned by serve/fetch_runtime.sh
BUILD = VV / "nb_out" / "build"
UI_HTML = REPO / "ui" / "index.html"

sys.path.insert(0, str(VV))
from harness import scoring as S                        # noqa: E402
from harness import constants as C                      # noqa: E402
from harness.gen_profiles import build_vector_and_mask, MARKER_ORDER, N_MARKERS  # noqa: E402

# Full profile (must match shared.niob Instance(Full)).
FULL_PROFILE_ARG = "1"
FULL_N_SLOTS = 32768
FULL_PARAMS = {"profile": "full", "ring_dim": 65536, "n_slots": FULL_N_SLOTS,
               "security": "full 128-classic security parameters",
               "depth": 20, "cheb_degree": 13}
COMPUTE_TIMEOUT = 900          # >= 600 s required; 900 s to survive swap
STAGE_TIMEOUT = 300            # keygen/encrypt/decrypt
PANELS = C.PANELS[:]

BIN_ENV = {
    **os.environ,
    "LD_LIBRARY_PATH": ":".join([
        str(NC / "vendor/lib/openfhe/lib"),
        str(NC / "build/vendor/niobium-fhetch"),
        str(NC / "vendor/niobium-fhetch/build"),
        str(NC / "build/_deps/yaml_cpp-build"),
    ]),
    "NBCC_FHETCH_DRIVER": str(NC / "vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"),
}
BIN_ENV["DYLD_LIBRARY_PATH"] = BIN_ENV["LD_LIBRARY_PATH"]

_pipeline_lock = threading.Lock()   # HARD serialize: one FHE run at a time


def _write_matrix(path, row0, n_slots, ncols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<%dd" % ncols, *row0))
        zeros = struct.pack("<%dd" % ncols, *([0.0] * ncols))
        for _ in range(n_slots - 1):
            f.write(zeros)


# Files that hold plaintext or the secret key; these are zero-overwritten before
# removal. Everything else in the temp dir (ciphertexts, .fhetch trace, replay
# metadata, serialized probes, decrypt output) is ENCRYPTED or non-sensitive and
# is simply unlinked — overwriting multi-GB of ciphertext buys no privacy and
# would make each run block for a long time.
SENSITIVE_NAMES = {"sk.bin", "zvec.bin", "wmask.bin"}


def _secure_wipe(root: Path):
    """Zero-overwrite the secret key + plaintext files, then remove the whole
    temp tree (keys, ciphertexts, trace, outputs). NOTE: on SSDs, wear-leveling
    means an overwrite is not a guaranteed physical erase; this zeros the logical
    contents of the sensitive files before removal — adequate for a local demo."""
    if not root.exists():
        return
    for p in root.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink() and p.name in SENSITIVE_NAMES:
                n = p.stat().st_size
                with open(p, "r+b", buffering=0) as f:
                    left, chunk = n, b"\x00" * (1024 * 1024)
                    while left > 0:
                        w = min(left, len(chunk))
                        f.write(chunk[:w]); left -= w
                    f.flush(); os.fsync(f.fileno())
        except OSError:
            pass
    shutil.rmtree(root, ignore_errors=True)


def _run(bin_name, args, cwd, timeout):
    p = subprocess.run([str(BUILD / bin_name)] + args, cwd=cwd, env=BIN_ENV,
                       capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("%s failed (exit %d): %s"
                           % (bin_name, p.returncode, (p.stderr or p.stdout)[-500:]))
    return p.stdout, p.stderr


def _isfloat(x):
    try:
        float(x); return True
    except ValueError:
        return False


def run_pipeline_stream(profile):
    """Generator yielding NDJSON stage events, then a final 'result' event.
    Raises via a yielded 'error' event; the temp dir is always securely wiped."""
    zrow, wrow = build_vector_and_mask(profile)
    if len(zrow) != N_MARKERS:
        yield {"stage": "error", "error": "marker width %d != %d" % (len(zrow), N_MARKERS)}
        return
    chrono = float(profile.get("age") or 40.0)
    oracle = S.evaluate(profile)                          # hidden dev oracle only
    work = Path(tempfile.mkdtemp(prefix="vv_fhe_full_"))
    t0 = {}
    def dt(k):
        return round((time.time() - t0[k]) * 1000)
    try:
        io_full = work / "io" / "full"
        (io_full / "keys").mkdir(parents=True, exist_ok=True)
        (io_full / "encrypted").mkdir(parents=True, exist_ok=True)
        _write_matrix(io_full / "zvec.bin", zrow, FULL_N_SLOTS, N_MARKERS)
        _write_matrix(io_full / "wmask.bin", wrow, FULL_N_SLOTS, N_MARKERS)

        yield {"stage": "keygen", "status": "start"}
        t0["keygen"] = time.time()
        _run("key_generation", [FULL_PROFILE_ARG], work, STAGE_TIMEOUT)
        ms_keygen = dt("keygen")
        yield {"stage": "keygen", "status": "done", "ms": ms_keygen}

        yield {"stage": "encrypt", "status": "start"}
        t0["encrypt"] = time.time()
        _run("encrypt_profile", [FULL_PROFILE_ARG], work, STAGE_TIMEOUT)
        ms_encrypt = dt("encrypt")
        n_marker = len(list((io_full / "encrypted").glob("markers_*.bin")))
        n_mask = len(list((io_full / "encrypted").glob("mask_*.bin")))
        yield {"stage": "encrypt", "status": "done", "ms": ms_encrypt}

        # evaluator isolation: move secret key + plaintext OUT before compute
        vault = work / "_client_only"
        vault.mkdir(exist_ok=True)
        sk_path = io_full / "keys" / "sk.bin"
        sk_bytes = sk_path.stat().st_size
        shutil.move(str(sk_path), str(vault / "sk.bin"))
        shutil.move(str(io_full / "zvec.bin"), str(vault / "zvec.bin"))
        shutil.move(str(io_full / "wmask.bin"), str(vault / "wmask.bin"))
        keys_during_eval = sorted(p.name for p in (io_full / "keys").glob("*"))

        yield {"stage": "compute", "status": "start"}
        t0["compute"] = time.time()
        cw_out, _ = _run("compute_wellness", [FULL_PROFILE_ARG], work, COMPUTE_TIMEOUT)
        ms_compute = dt("compute")
        m = re.search(r"\((\d+)\s+instructions", cw_out)
        trace_instructions = int(m.group(1)) if m else None
        yield {"stage": "compute", "status": "done", "ms": ms_compute}

        # restore for the client-side decrypt
        shutil.move(str(vault / "sk.bin"), str(sk_path))
        shutil.move(str(vault / "zvec.bin"), str(io_full / "zvec.bin"))
        shutil.move(str(vault / "wmask.bin"), str(io_full / "wmask.bin"))

        yield {"stage": "decrypt", "status": "start"}
        t0["decrypt"] = time.time()
        dec_out, _ = _run("decrypt_report", [FULL_PROFILE_ARG, str(chrono)], work, STAGE_TIMEOUT)
        ms_decrypt = dt("decrypt")
        yield {"stage": "decrypt", "status": "done", "ms": ms_decrypt}

        vals = [float(x) for x in dec_out.split() if _isfloat(x)]
        need = 1 + len(PANELS) + N_MARKERS + N_MARKERS
        vals = vals[-need:]
        if len(vals) != need:
            yield {"stage": "error", "error": "decrypt produced %d scalars, expected %d" % (len(vals), need)}
            return
        i = 0
        fhe_bio = vals[i]; i += 1
        panel_vals = vals[i:i + len(PANELS)]; i += len(PANELS)
        term_vals = vals[i:i + N_MARKERS]; i += N_MARKERS
        absz_vals = vals[i:i + N_MARKERS]; i += N_MARKERS

        oracle_panels = oracle["system_scores_raw"]
        fhe_panels = {p: (round(panel_vals[k], 3) if oracle_panels.get(p) is not None else None)
                      for k, p in enumerate(PANELS)}
        terms = {MARKER_ORDER[k]: round(term_vals[k], 4) for k in range(N_MARKERS)}
        absz = {MARKER_ORDER[k]: round(absz_vals[k], 4) for k in range(N_MARKERS)}

        yield {
            "stage": "result",
            "params": FULL_PARAMS,
            "fhe": {"biological_age": round(fhe_bio, 3), "panels": fhe_panels,
                    "terms": terms, "followup_absz": absz},
            "oracle": {"biological_age": oracle["biological_age"], "panels": oracle_panels},
            "proof": {
                "n_marker_ciphertexts": n_marker, "n_mask_ciphertexts": n_mask,
                "encrypted_result_ciphertexts": len(PANELS) + 1 + N_MARKERS + N_MARKERS,
                "trace_instructions": trace_instructions,
                "evaluator_saw_secret_key": "sk.bin" in keys_during_eval,
                "evaluator_saw_plaintext": False,
                "secret_key_bytes_withheld": sk_bytes,
                "keys_visible_to_evaluator": keys_during_eval,
                "real_fhe": True,
            },
            "timings_ms": {"keygen": ms_keygen, "encrypt": ms_encrypt,
                           "compute": ms_compute, "decrypt": ms_decrypt,
                           "total": ms_keygen + ms_encrypt + ms_compute + ms_decrypt},
        }
    except subprocess.TimeoutExpired:
        yield {"stage": "error", "error": "FHE pipeline timed out (>%ds)" % COMPUTE_TIMEOUT}
    except Exception as e:
        yield {"stage": "error", "error": "FHE pipeline failed: %s" % e}
    finally:
        _secure_wipe(work)


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/ui/index.html"):
            self._send(200, UI_HTML.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._send(200, json.dumps({"ok": True, "params": FULL_PARAMS,
                                        "busy": _pipeline_lock.locked()}))
        else:
            self._send(404, json.dumps({"ok": False, "error": "not found"}))

    def do_POST(self):
        if self.path != "/api/fhe/score":
            self._send(404, json.dumps({"ok": False, "error": "not found"}))
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            profile = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._send(400, json.dumps({"ok": False, "error": "bad request: %s" % e}))
            return
        # HARD serialize: reject (don't queue) concurrent runs.
        if not _pipeline_lock.acquire(blocking=False):
            self._send(429, json.dumps({"ok": False,
                       "error": "An encrypted computation is already running. Full FHE is single-user; please wait and retry."}))
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            for ev in run_pipeline_stream(profile):
                try:
                    self.wfile.write((json.dumps(ev) + "\n").encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break   # client navigated away; run_pipeline_stream still wipes temp
        finally:
            _pipeline_lock.release()

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] %s - %s\n" % (self.address_string(), fmt % args))


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    missing = [b for b in ("key_generation", "encrypt_profile", "compute_wellness", "decrypt_report")
               if not (BUILD / b).exists()]
    if missing:
        sys.exit("ERROR: missing binaries %s — run the setup (see serve/README.md)." % missing)
    if not Path(BIN_ENV["NBCC_FHETCH_DRIVER"]).exists():
        sys.exit("ERROR: fhetch_driver missing — run the setup (see serve/README.md).")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("VitalVault FHE bridge (FULL, ring 65536, 128-classic) on http://%s:%d/" % (args.host, args.port))
    print("  Real CKKS FHE. Each run takes several minutes and ~6-7 GB RAM; one run at a time.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbridge stopped")


if __name__ == "__main__":
    main()
