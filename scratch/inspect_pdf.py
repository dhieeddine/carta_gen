import os
import pypdf

def inspect_pdf(pdf_path, name):
    print(f"=================== {name} ===================")
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total Pages: {len(reader.pages)}")
    
    # Check title/first page
    first_page = reader.pages[0].extract_text()
    print("--- FIRST PAGE (sample) ---")
    print(first_page[:600])
    
    # Search for TOC
    print("--- SEARCHING TABLE OF CONTENTS ---")
    for i, page in enumerate(reader.pages[:15]):
        text = page.extract_text() or ""
        lower = text.lower()
        if "table of contents" in lower or "sommaire" in lower or "table des matières" in lower:
            print(f"Page {i+1} has TOC:")
            print(text[:1200])
            print("...")

if __name__ == "__main__":
    inspect_pdf(r"d:\Desktop\stage_dgre\carta_gen\rapport_yosra.pdf", "RAPPORT YOSRA")
    inspect_pdf(r"d:\Desktop\stage_dgre\carta_gen\rapport_stage_cartagen.pdf", "RAPPORT CARTAGEN EXISTING")
