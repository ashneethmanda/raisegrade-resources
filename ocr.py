#!/usr/bin/env python3
"""
Batch OCR Script for PDFs
- Scans a folder for all PDFs
- Runs OCR to make them searchable
- Extracts text into .txt files
- Saves results in a chosen output folder
"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import shutil
import sys

# ==============================
# CONFIGURATION
# ==============================
INPUT_DIR = Path("/Users/ashneeth/Desktop/resources/chem")   # <--- change this if your PDFs are in another folder
OUTPUT_DIR = Path("/Users/ashneeth/Desktop/OCR_Results/chemistry")       # <--- change this to where you want results saved
WORKERS = 3   # number of files processed in parallel
# ==============================

def check_tools():
    """Check if ocrmypdf and pdftotext are installed."""
    for cmd in ("ocrmypdf", "pdftotext"):
        if not shutil.which(cmd):
            print(f"ERROR: {cmd} not found. Install it before running.")
            sys.exit(1)

def run_cmd(cmd):
    """Run a shell command and capture output."""
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        out = proc.stdout.decode(errors="ignore") + proc.stderr.decode(errors="ignore")
        return proc.returncode == 0, out
    except Exception as e:
        return False, str(e)

def process_one(pdf_path: Path, root: Path, out_root: Path):
    """Process a single PDF: always force OCR + extract text."""
    rel_parent = pdf_path.parent.relative_to(root)
    target_dir = out_root / rel_parent
    target_dir.mkdir(parents=True, exist_ok=True)

    searchable = target_dir / (pdf_path.stem + "_searchable.pdf")
    txt_file = target_dir / (pdf_path.stem + ".txt")

    print(f"[START] {pdf_path.name}")

    # Step 1: OCR to searchable PDF (force OCR even if text exists)
    ok, out = run_cmd([
        "ocrmypdf",
        "--deskew",
        "--force-ocr",   # <--- this forces OCR always
        str(pdf_path),
        str(searchable)
    ])
    if not ok:
        print(f"[ERROR] ocrmypdf failed for {pdf_path}:\n{out.strip()}")
        return False

    # Step 2: Extract text to .txt
    ok2, out2 = run_cmd(["pdftotext", str(searchable), str(txt_file)])
    if not ok2:
        print(f"[ERROR] pdftotext failed for {searchable}:\n{out2.strip()}")
        return False

    print(f"[OK] {pdf_path.name} -> {searchable.name}, {txt_file.name}")
    return True

def find_pdfs(root: Path):
    """Return all PDFs under root."""
    return sorted([p for p in root.rglob("*.pdf") if p.is_file()])

def main():
    root = INPUT_DIR.expanduser().resolve()
    out_base = OUTPUT_DIR.expanduser().resolve()

    if not root.exists():
        print("Input folder does not exist:", root)
        sys.exit(1)

    out_base.mkdir(parents=True, exist_ok=True)
    check_tools()

    pdfs = find_pdfs(root)
    if not pdfs:
        print("No PDFs found under", root)
        return

    print(f"Found {len(pdfs)} PDF(s) under {root}. Using {WORKERS} workers.")
    success, failed = 0, 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process_one, p, root, out_base): p for p in pdfs}
        for fut in as_completed(futures):
            try:
                if fut.result():
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                print(f"[EXCEPTION] {e}")

    print("\nAll done.")
    print(f"Success: {success}, Failed: {failed}")
    print("Outputs saved under:", out_base)

if __name__ == "__main__":
    main()
