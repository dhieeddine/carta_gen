import pypdf

reader = pypdf.PdfReader(r"d:\Desktop\stage_dgre\carta_gen\rapport_stage_cartagen.pdf")
print("Total pages:", len(reader.pages))

for i, page in enumerate(reader.pages[:8]):
    text = page.extract_text() or ""
    if "contents" in text.lower() or "table of contents" in text.lower():
        print(f"=== Page {i+1} ===")
        print(text[:1500])
