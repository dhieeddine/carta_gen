import pypdf
import re

reader = pypdf.PdfReader('rapport_yosra.pdf')
yosra_ch34 = ''
for p in range(31, 65):
    yosra_ch34 += ' ' + (reader.pages[p].extract_text() or '')

with open('rapport_stage_cartagen.tex', 'r', encoding='utf-8') as f:
    tex = f.read()

ch3_match = re.search(r'\\chapter\{System Analysis, Modeling, and Architecture\}(.*?)\\chapter\{Implementation', tex, re.DOTALL)
if ch3_match:
    ch3_text = ch3_match.group(1)
    ch3_paras = [p.strip() for p in ch3_text.split('\n\n') if len(p.strip().split()) > 10]
    print(f'Total Chapter 3 paragraphs: {len(ch3_paras)}')
    matches_found = 0
    for idx, p in enumerate(ch3_paras):
        clean_p = re.sub(r'\\[a-zA-Z]+(\[[^\]]*\])?(\{([^}]*)\})?', r'\3', p)
        clean_p = re.sub(r'[{}\\%]', '', clean_p)
        words = clean_p.split()
        for i in range(len(words)-5):
            ng = ' '.join(words[i:i+6]).lower()
            if ng in yosra_ch34.lower():
                print(f'Match in ch3 para {idx}: "{ng}"')
                matches_found += 1
                break
    print(f'Total matches found in Chapter 3: {matches_found}')
else:
    print('Chapter 3 not found')
