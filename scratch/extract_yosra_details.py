import pypdf

reader = pypdf.PdfReader(r"d:\Desktop\stage_dgre\carta_gen\rapport_yosra.pdf")

# Extract Table of contents pages (pages 4 to 8)
print("=== TOC FROM YOSRA ===")
for i in range(3, 8):
    print(f"--- Page {i+1} ---")
    print(reader.pages[i].extract_text())

# Find references at the end
print("=== BIBLIOGRAPHY / REFERENCES FROM YOSRA ===")
for i in range(len(reader.pages)-10, len(reader.pages)):
    text = reader.pages[i].extract_text() or ""
    if "reference" in text.lower() or "bibliograph" in text.lower():
        print(f"--- Page {i+1} ---")
        print(text[:1500])
