import pypdf
import re

pdf_path = r"d:\Desktop\stage_dgre\carta_gen\rapport_stage_cartagen.pdf"
reader = pypdf.PdfReader(pdf_path)
print(f"Total pages: {len(reader.pages)}")

# Let's inspect the aux file or log to see all bib keys, or define the list of references
bib_keys = [
    "alavi2001", "argote2000", "bukowitz2000", "cross2000", "dalkir2017",
    "davenport1998", "huber1991", "king2005", "meyer1996", "nonaka1994",
    "nonaka1995", "tuomi1999", "wiig1993", "baptiste2024", "brown2009",
    "koskinen2018", "vonhippel1986", "dgre2023", "elgourari2024", "fao2022",
    "jort2001", "onagri2023", "shepard1968", "thiessen1911", "iso2016",
    "postgis2024", "postgresql2024", "stonebraker2018", "docker2024",
    "hu2021", "lewis2020", "wooldridge2009", "owasp2024"
]

# Read .aux file to get the number mapping of each bib key
aux_path = r"d:\Desktop\stage_dgre\carta_gen\rapport_stage_cartagen.aux"
key_to_num = {}
with open(aux_path, "r", encoding="utf-8") as f:
    for line in f:
        # \bibcite{alavi2001}{1}
        m = re.search(r"\\bibcite\{([^}]+)\}\{([^}]+)\}", line)
        if m:
            key_to_num[m.group(1)] = m.group(2)

print("Key to number mapping:")
for k, v in key_to_num.items():
    print(f"  {k} -> [{v}]")

# Now search each page for the bracketed number or author/year
key_pages = {k: [] for k in bib_keys}

for page_idx, page in enumerate(reader.pages):
    page_num = page_idx + 1
    text = page.extract_text() or ""
    
    # We don't count the bibliography chapter itself as citation page
    # Bibliography is around page 48-52
    if "Bibliography" in text and ("MIS Quarterly" in text or "MIT Press" in text or "Oxford University Press" in text):
        continue
        
    for k in bib_keys:
        num = key_to_num.get(k)
        # Check patterns: [X], [X, Y], [X-Z] etc.
        # Also check author name
        found = False
        if num:
            # Pattern matching [X] or [..., X, ...]
            # e.g. [1], [1, 2], [1-3]
            patterns = [
                rf"\[{num}\]",
                rf"\[{num},",
                rf",\s*{num}\]",
                rf",\s*{num},",
                rf"\[\s*{num}\s*\]"
            ]
            for p in patterns:
                if re.search(p, text):
                    found = True
                    break
        if found:
            key_pages[k].append(page_num)

print("\n=== CITATION PAGES SUMMARY ===")
for k in sorted(bib_keys):
    pages = key_pages[k]
    print(f"{k} (ref [{key_to_num.get(k, '?')}]) -> Pages: {pages}")
