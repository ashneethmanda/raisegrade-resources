#!/usr/bin/env python3
"""
Batch extract text from PDFs using pdftotext
- Reads all PDFs from INPUT_DIR (recursively)
- Writes .txt files into OUTPUT_DIR, mirroring folder structure
"""

from pathlib import Path
import subprocess
import sys

# ========== CONFIG ==========
INPUT_DIR = Path("/Users/ashneeth/Desktop/OCR_Results/cs")          # <-- folder with PDFs
OUTPUT_DIR = Path("/Users/ashneeth/Desktop/ocr_2/cs")              # <-- folder where .txt will go
USE_LAYOUT = True  # Set to False if you don't want -layout option
# ============================

def run_pdftotext(pdf: Path, txt: Path):
    """Run pdftotext on one file"""
    cmd = ["pdftotext"]
    if USE_LAYOUT:
        cmd.append("-layout")
    cmd += [str(pdf), str(txt)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"[ERROR] {pdf.name} -> {proc.stderr.decode(errors='ignore').strip()}")
        return False
    return True

def main():
    root = INPUT_DIR.expanduser().resolve()
    out_base = OUTPUT_DIR.expanduser().resolve()

    if not root.exists():
        print("Input folder not found:", root)
        sys.exit(1)

    out_base.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(root.rglob("*.pdf"))  # finds all PDFs recursively
    if not pdfs:
        print("No PDFs found under", root)
        return

    print(f"Found {len(pdfs)} PDF(s) under {root}\n")

    for i, pdf in enumerate(pdfs, start=1):
        # build output path that mirrors input structure
        rel = pdf.relative_to(root)
        target_dir = out_base / rel.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        txt_file = target_dir / (pdf.stem + ".txt")

        print(f"[{i}/{len(pdfs)}] Extracting {pdf.name} -> {txt_file}")
        ok = run_pdftotext(pdf, txt_file)
        if ok:
            if txt_file.stat().st_size == 0:
                print(f"   WARNING: {txt_file.name} is empty (no selectable text in PDF).")
        else:
            print(f"   FAILED on {pdf.name}")

    print("\nDone.")
    print("All extracted texts saved in:", out_base)

if __name__ == "__main__":
    main()
