import pypdf
import re
from rapidfuzz import fuzz

def clean_latex(text):
    text = re.sub(r'%.*?\n', '\n', text)
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', ' ', text)
    text = re.sub(r'[{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

reader = pypdf.PdfReader('rapport_yosra.pdf')
# Extract Yosra pages 1 to 79 (exclude bibliography pp. 80-84)
yosra_body_pages = {}
yosra_body_sentences = []
for i in range(len(reader.pages)):
    p_num = i + 1
    if p_num >= 80: # Bibliography & annexes
        continue
    txt = reader.pages[i].extract_text() or ''
    txt = re.sub(r'\s+', ' ', txt).strip()
    if txt:
        yosra_body_pages[p_num] = txt
        sents = re.split(r'(?<=[.!?])\s+', txt)
        for s in sents:
            s_clean = s.strip()
            if len(s_clean.split()) >= 6:
                yosra_body_sentences.append({'page': p_num, 'text': s_clean})

with open('rapport_stage_cartagen.tex', 'r', encoding='utf-8') as f:
    tex_content = f.read()

# Isolate body text before \begin{thebibliography}
if r'\begin{thebibliography}' in tex_content:
    body_tex = tex_content.split(r'\begin{thebibliography}')[0]
else:
    body_tex = tex_content

# Break body_tex into sections / paragraphs
lines = body_tex.split('\n')
paragraphs = []
cur_lines = []
cur_start = 1

for idx, l in enumerate(lines, 1):
    strip_l = l.strip()
    if not strip_l or strip_l.startswith('%'):
        if cur_lines:
            txt = clean_latex(' '.join(cur_lines))
            if len(txt.split()) >= 8:
                paragraphs.append({
                    'start_line': cur_start,
                    'end_line': idx - 1,
                    'text': txt,
                    'raw': '\n'.join(cur_lines)
                })
            cur_lines = []
        cur_start = idx + 1
    else:
        if not cur_lines:
            cur_start = idx
        cur_lines.append(strip_l)

if cur_lines:
    txt = clean_latex(' '.join(cur_lines))
    if len(txt.split()) >= 8:
        paragraphs.append({
            'start_line': cur_start,
            'end_line': len(lines),
            'text': txt,
            'raw': '\n'.join(cur_lines)
        })

print(f"Analyzing {len(paragraphs)} body paragraphs against Yosra body...")

findings = []

for p in paragraphs:
    p_text = p['text']
    p_words = p_text.split()
    
    # 1. Check n-grams of 5 or more words
    n = 6
    matching_ngrams = []
    for i in range(len(p_words) - n + 1):
        ng = " ".join(p_words[i:i+n]).lower()
        # skip generic phrases like "in the context of the"
        if ng in ["in the context of the", "as shown in figure", "as shown in table", "at the same time"]:
            continue
        for y_page, y_text in yosra_body_pages.items():
            if ng in y_text.lower():
                matching_ngrams.append((ng, y_page))
                break

    # 2. Check sentence fuzzy similarity >= 60%
    sents = re.split(r'(?<=[.!?])\s+', p_text)
    fuzzy_matches = []
    for s in sents:
        s_words = s.strip().split()
        if len(s_words) >= 7:
            for ys in yosra_body_sentences:
                r = fuzz.token_sort_ratio(s.lower(), ys['text'].lower())
                if r >= 65:
                    fuzzy_matches.append({
                        'ratio': r,
                        'report_sent': s.strip(),
                        'yosra_page': ys['page'],
                        'yosra_sent': ys['text']
                    })
    
    if matching_ngrams or fuzzy_matches:
        findings.append({
            'start_line': p['start_line'],
            'end_line': p['end_line'],
            'para_excerpt': p_text[:120] + "...",
            'ngrams': matching_ngrams,
            'fuzzy': fuzzy_matches
        })

print(f"Found {len(findings)} paragraphs in the report body with potential similarity to Yosra body.")

for f in findings:
    print(f"\n==================================================")
    print(f"Report Lines {f['start_line']}-{f['end_line']}:")
    print(f"Excerpt: {f['para_excerpt']}")
    if f['ngrams']:
        print(f"N-grams (>= 6 words matched):")
        # unique ngrams
        seen_ng = set()
        for ng, yp in f['ngrams']:
            if ng not in seen_ng:
                print(f"   - [p.{yp}]: \"{ng}\"")
                seen_ng.add(ng)
    if f['fuzzy']:
        print(f"Fuzzy sentence matches (>= 65% similarity):")
        for fz in f['fuzzy']:
            print(f"   - [p.{fz['yosra_page']}] ({fz['ratio']}%): \"{fz['report_sent']}\"")
            print(f"     vs Yosra: \"{fz['yosra_sent']}\"")
