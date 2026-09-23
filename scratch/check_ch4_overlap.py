import pypdf
import re

reader = pypdf.PdfReader('rapport_yosra.pdf')
yosra_all = ' '.join([p.extract_text() or '' for p in reader.pages[:79]])

with open('rapport_stage_cartagen.tex', 'r', encoding='utf-8') as f:
    tex = f.read()

for ch_name, pattern in [
    ('Chapter 4', r'\\chapter\{Implementation, Experimental Results, and Deployment\}(.*?)\\chapter\{General Conclusion'),
    ('General Conclusion', r'\\chapter\{General Conclusion\}(.*?)\\begin\{thebibliography\}'),
    ('Annexes', r'\\begin\{appendices\}(.*?)\\end\{document\}')
]:
    match = re.search(pattern, tex, re.DOTALL)
    if match:
        txt = match.group(1)
        paras = [p.strip() for p in txt.split('\n\n') if len(p.strip().split()) > 10]
        matches_found = 0
        for idx, p in enumerate(paras):
            clean_p = re.sub(r'\\[a-zA-Z]+(\[[^\]]*\])?(\{([^}]*)\})?', r'\3', p)
            clean_p = re.sub(r'[{}\\%]', '', clean_p)
            words = clean_p.split()
            for i in range(len(words)-5):
                ng = ' '.join(words[i:i+6]).lower()
                if ng in yosra_all.lower():
                    matches_found += 1
                    break
        print(f'{ch_name}: {len(paras)} paragraphs, {matches_found} matches found.')
