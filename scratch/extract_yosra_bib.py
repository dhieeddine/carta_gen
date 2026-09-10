import pypdf

reader = pypdf.PdfReader(r"d:\Desktop\stage_dgre\carta_gen\rapport_yosra.pdf")
with open(r"d:\Desktop\stage_dgre\carta_gen\scratch\yosra_bib.txt", "w", encoding="utf-8") as f:
    for i in range(68, len(reader.pages)):
        text = reader.pages[i].extract_text() or ""
        f.write(f"=== PAGE {i+1} ===\n")
        f.write(text + "\n\n")

print("Saved yosra_bib.txt successfully")
