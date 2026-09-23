import pypdf
import re
from rapidfuzz import fuzz

def clean_latex(text):
    # Remove comments
    text = re.sub(r'%.*?\n', '\n', text)
    # Remove commands like \textbf{...}, \cite{...}
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', ' ', text)
    text = re.sub(r'[{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 1. Load Yosra PDF
reader = pypdf.PdfReader('rapport_yosra.pdf')
yosra_pages = {}
for i, page in enumerate(reader.pages):
    txt = clean_text(page.extract_text() or '')
    if txt:
        yosra_pages[i + 1] = txt

# Also split Yosra into sentences
yosra_sentences = []
for p_num, p_text in yosra_pages.items():
    # Split by period, exclamation, question
    sents = re.split(r'(?<=[.!?])\s+', p_text)
    for s in sents:
        s_clean = s.strip()
        if len(s_clean.split()) >= 6:
            yosra_sentences.append({'page': p_num, 'text': s_clean})

print(f"Loaded {len(yosra_sentences)} sentences from Yosra.")

# 2. Load LaTeX
with open('rapport_stage_cartagen.tex', 'r', encoding='utf-8') as f:
    tex_lines = f.readlines()

# Extract paragraphs and line numbers from LaTeX
tex_paragraphs = []
current_para = []
start_line = 1

for line_idx, line in enumerate(tex_lines, 1):
    stripped = line.strip()
    if not stripped or stripped.startswith('%'):
        if current_para:
            p_text = clean_latex(' '.join(current_para))
            if len(p_text.split()) >= 6:
                tex_paragraphs.append({
                    'start_line': start_line,
                    'end_line': line_idx - 1,
                    'raw': ' '.join(current_para),
                    'clean': p_text
                })
            current_para = []
        start_line = line_idx + 1
    else:
        if not current_para:
            start_line = line_idx
        current_para.append(stripped)

if current_para:
    p_text = clean_latex(' '.join(current_para))
    if len(p_text.split()) >= 6:
        tex_paragraphs.append({
            'start_line': start_line,
            'end_line': len(tex_lines),
            'raw': ' '.join(current_para),
            'clean': p_text
        })

print(f"Loaded {len(tex_paragraphs)} paragraphs from LaTeX report.")

# 3. Match Analysis
# Find n-gram matches (length >= 7 consecutive words)
all_yosra_text_lower = " ".join([p.lower() for p in yosra_pages.values()])

exact_matches = []
high_fuzzy_matches = []

for para in tex_paragraphs:
    words = para['clean'].split()
    para_clean_lower = para['clean'].lower()
    
    # Check 7-word n-grams
    n = 7
    matched_ngrams = []
    if len(words) >= n:
        for i in range(len(words) - n + 1):
            ngram = " ".join(words[i:i+n]).lower()
            # remove common stopwords strings
            if ngram in all_yosra_text_lower:
                matched_ngrams.append(ngram)
                
    if matched_ngrams:
        # Find which page in Yosra
        found_pages = set()
        for ng in matched_ngrams:
            for p_num, p_text in yosra_pages.items():
                if ng in p_text.lower():
                    found_pages.add(p_num)
        exact_matches.append({
            'start_line': para['start_line'],
            'end_line': para['end_line'],
            'para_text': para['clean'][:150] + "...",
            'ngrams_count': len(matched_ngrams),
            'sample_ngram': matched_ngrams[0],
            'yosra_pages': sorted(list(found_pages))
        })

    # Also sentence-level fuzzy similarity against Yosra sentences
    para_sents = re.split(r'(?<=[.!?])\s+', para['clean'])
    for ps in para_sents:
        ps_clean = ps.strip()
        ps_words = ps_clean.split()
        if len(ps_words) >= 8:
            for ys in yosra_sentences:
                # Quick length check
                if abs(len(ps_words) - len(ys['text'].split())) > 12:
                    continue
                ratio = fuzz.ratio(ps_clean.lower(), ys['text'].lower())
                if ratio >= 65:
                    high_fuzzy_matches.append({
                        'line': para['start_line'],
                        'ratio': ratio,
                        'report_sent': ps_clean,
                        'yosra_page': ys['page'],
                        'yosra_sent': ys['text']
                    })

print(f"\n--- RESULTS SUMMARY ---")
print(f"Exact n-gram overlapping paragraphs: {len(exact_matches)}")
print(f"High fuzzy/similarity sentence matches (ratio >= 65%): {len(high_fuzzy_matches)}")

print("\n--- SAMPLE EXACT N-GRAM MATCHES ---")
for m in exact_matches[:15]:
    print(f"Report Lines {m['start_line']}-{m['end_line']} (Yosra p.{m['yosra_pages']}): {m['sample_ngram']}")
    print(f"   Excerpt: {m['para_text']}")

print("\n--- SAMPLE HIGH FUZZY SENTENCE MATCHES ---")
# Sort by ratio descending
high_fuzzy_matches.sort(key=lambda x: x['ratio'], reverse=True)
for m in high_fuzzy_matches[:20]:
    print(f"Ratio {m['ratio']}% | Line {m['line']} vs Yosra p.{m['yosra_page']}:")
    print(f"   Report: {m['report_sent']}")
    print(f"   Yosra : {m['yosra_sent']}\n")
