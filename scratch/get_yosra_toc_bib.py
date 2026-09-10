import pypdf

reader = pypdf.PdfReader(r"d:\Desktop\stage_dgre\carta_gen\rapport_yosra.pdf")
print("--- Page 4 ---")
print(reader.pages[3].extract_text())
print("--- Page 5 ---")
print(reader.pages[4].extract_text())

# Also let's print bibliography pages
for i in range(70, len(reader.pages)):
    text = reader.pages[i].extract_text() or ""
    if len(text.strip()) > 50:
        print(f"--- Bib Page {i+1} ---")
        print(text[:1000])
