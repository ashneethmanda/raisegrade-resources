#!/usr/bin/env python3
"""
High-accuracy OCR + extract + spellcheck pipeline.

What it does for every PDF under INPUT_DIR:
  1) Runs ocrmypdf with aggressive options and --force-ocr to produce *_searchable.pdf
  2) Extracts selectable text page-by-page into .txt with --- PAGE N --- headers (uses PyMuPDF)
  3) Creates a .docx copy (for quick manual proofreading in Word)
  4) Runs a simple spell-check to list "suspicious" words (so you only correct likely errors)
Config at top: change INPUT_DIR / OUTPUT_DIR / WORKERS / CUSTOM_DICT_FILE as needed.
"""

from pathlib import Path
import subprocess
import shutil
import sys
import re
import fitz                # pymupdf
from spellchecker import SpellChecker
from docx import Document
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ========== CONFIG - change these paths to your folders ==========
INPUT_DIR = Path("/Users/ashneeth/Desktop/OCR_Results/chemistry")       # <--- where your PDFs are
OUTPUT_DIR = Path("/Users/ashneeth/Desktop/ocr_2/chemistry")  # <--- where outputs go
WORKERS = 2                                                      # <--- parallelism
CUSTOM_DICT_FILE = Path("/Users/ashneeth/Desktop/custom_words.txt")  # optional; domain words, one per line
# =================================================================

# OCR command template - you can add more ocrmypdf flags if needed
OCRMYPDF_BASE_ARGS = [
    "ocrmypdf",
    "--force-ocr",          # force OCR even if PDF already has text
    "--deskew",
    "--remove-background",
    "--clean",
    "--clean-final",
    "--rotate-pages",
    "--image-dpi", "400",   # higher DPI helps, try 300-600 depending on source quality
    "-l", "eng"             # change/add languages if needed, e.g. "eng+spa"
]

# helpers
def check_tools():
    for cmd in ("ocrmypdf", "pdftotext", "tesseract"):
        if not shutil.which(cmd):
            print(f"ERROR: required command not found in PATH: {cmd}")
            sys.exit(1)

def run_cmd(cmd_list):
    try:
        proc = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        out = (proc.stdout or b"").decode(errors="ignore") + (proc.stderr or b"").decode(errors="ignore")
        return proc.returncode == 0, out
    except Exception as e:
        return False, str(e)

def ocr_to_searchable(pdf_path: Path, searchable_path: Path):
    args = OCRMYPDF_BASE_ARGS + [str(pdf_path), str(searchable_path)]
    ok, out = run_cmd(args)
    return ok, out

def extract_text_from_searchable(searchable_pdf: Path, out_txt: Path):
    doc = fitz.open(str(searchable_pdf))
    with out_txt.open("w", encoding="utf-8") as f:
        for i, page in enumerate(doc, start=1):
            text = page.get_text()  # selectable text
            f.write(f"--- PAGE {i} ---\n")
            if text:
                f.write(text)
            else:
                f.write("[NO TEXT ON PAGE]\n")
            f.write("\n\n")
    doc.close()

def write_docx_from_text(txt_path: Path, docx_path: Path):
    doc = Document()
    with txt_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            doc.add_paragraph(line.rstrip())
    doc.save(str(docx_path))

def load_custom_words(path: Path):
    if not path or not path.exists():
        return []
    return [w.strip() for w in path.read_text(encoding="utf-8").splitlines() if w.strip()]

def simple_spellcheck(txt_path: Path, issues_out: Path, custom_words):
    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    # minimal tokenization to words (keep chemical tokens? you can customize)
    words = re.findall(r"[A-Za-zÀ-ÿ0-9\-\']{2,}", text)  # includes numbers/hyphens for e.g. "H2O"
    spell = SpellChecker(language=None)  # start empty then load english
    # load default english frequency list
    try:
        spell.word_frequency.load_text_file(spell.word_frequency.filename)  # try to ensure english loaded (depends)
    except Exception:
        pass
    spell.word_frequency.add_words(custom_words)
    # find unknowns - limit to alphabetic-ish tokens we care about
    candidates = set(w for w in words if not re.match(r'^\d+$', w))  # drop purely numeric tokens
    unknown = spell.unknown(candidates)
    # write suggestions
    with issues_out.open("w", encoding="utf-8") as out:
        out.write("Suspicious words and suggestions (automated):\n\n")
        for w in sorted(unknown):
            # skip tokens that look like chemical formulas (heuristic: contain digits and letters, e.g. H2O)
            if re.search(r'\d', w) and re.search(r'[A-Za-z]', w):
                # include but mark as "chemical-like"
                out.write(f"{w}  (chemical-like token - review manually)\n")
                continue
            sugg = spell.candidates(w)
            out.write(f"{w} -> suggestions: {', '.join(list(sugg)[:5])}\n")
    return len(unknown)

def process_pdf_file(pdf_path: Path, root: Path, out_base: Path, custom_words):
    rel = pdf_path.relative_to(root)
    target_dir = out_base / rel.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    searchable = target_dir / (pdf_path.stem + "_searchable.pdf")
    txtfile = target_dir / (pdf_path.stem + ".txt")
    docxfile = target_dir / (pdf_path.stem + ".docx")
    issuesfile = target_dir / (pdf_path.stem + "_issues.txt")

    print(f"[START] {pdf_path.name}")

    ok, out = ocr_to_searchable(pdf_path, searchable)
    if not ok:
        print(f"[ERROR] ocrmypdf failed for {pdf_path.name}:\n{out.strip()[:400]}")
        return False

    # extract text (page headers included)
    try:
        extract_text_from_searchable(searchable, txtfile)
    except Exception as e:
        print(f"[ERROR] text extraction failed for {pdf_path.name}: {e}")
        return False

    # create docx for manual proofreading
    try:
        write_docx_from_text(txtfile, docxfile)
    except Exception as e:
        print(f"[WARN] docx creation failed for {pdf_path.name}: {e}")

    # spellcheck and write suspicious words
    try:
        num_issues = simple_spellcheck(txtfile, issuesfile, custom_words)
        print(f"[OK] {pdf_path.name} -> text saved ({txtfile.name}), issues: {num_issues}")
    except Exception as e:
        print(f"[WARN] spellcheck failed for {pdf_path.name}: {e}")

    return True

def main():
    check_tools()
    root = INPUT_DIR.expanduser().resolve()
    out_base = OUTPUT_DIR.expanduser().resolve()
    out_base.mkdir(parents=True, exist_ok=True)
    custom_words = load_custom_words(CUSTOM_DICT_FILE)

    pdfs = sorted([p for p in root.rglob("*.pdf") if p.is_file()])
    if not pdfs:
        print("No PDFs found under", root)
        return

    print(f"Found {len(pdfs)} PDFs. Processing with {WORKERS} worker(s).")
    successes, fails = 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process_pdf_file, p, root, out_base, custom_words): p for p in pdfs}
        for fut in tqdm(as_completed(futures), total=len(futures)):
            p = futures[fut]
            try:
                ok = fut.result()
            except Exception as e:
                ok = False
                print(f"[EXCEPTION] {p.name} -> {e}")
            if ok:
                successes += 1
            else:
                fails += 1

    print("\nDone.")
    print("Success:", successes, "Failed:", fails)
    print("Outputs in:", out_base)

if __name__ == "__main__":
    main()
