# -*- coding: utf-8 -*-

import os
import sys
from pypdf import PdfReader
from cartagen.infrastructure.database.vector_manager import VectorManager

def extract_chunks_from_pdf(pdf_path: str, chunk_size: int = 1000, chunk_overlap: int = 200):
    """Extrait le texte d'un PDF page par page et le découpe en chunks de taille fixe."""
    if not os.path.exists(pdf_path):
        print(f"[WARNING] Le fichier PDF n'existe pas : {pdf_path}")
        return []

    print(f"[PDF] Lecture du fichier : {pdf_path}...")
    reader = PdfReader(pdf_path)
    doc_name = os.path.basename(pdf_path)
    
    chunks = []
    
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
            
        # Découpage du texte en chunks avec chevauchement
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end].strip()
            
            if len(chunk_text) > 50:  # Ignorer les morceaux insignifiants
                chunks.append({
                    "doc_name": doc_name,
                    "page": page_idx + 1,
                    "text_content": chunk_text
                })
                
            start += (chunk_size - chunk_overlap)
            
    print(f"[PDF] {len(chunks)} extraits de texte générés pour '{doc_name}'.")
    return chunks

def main():
    workspace_root = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Chemins des PDFs spécifiés par l'utilisateur
    pdf_files = [
        r"D:\Desktop\stage_dgre\backend\2003-04.pdf",
        r"D:\Desktop\stage_dgre\backend\2021-2022 .pdf"
    ]
    
    # 2. Initialisation de Zvec
    v_manager = VectorManager(workspace_root)
    # Ouvrir l'index pour s'assurer qu'il est accessible
    v_manager.load_collections()
    
    # Si la collection d'annuaires n'est pas encore créée, l'initialiser
    if v_manager.annuaires_collection is None:
        print("[Zvec] Création de la collection 'annuaires_index'...")
        v_manager.initialize_annuaires_only()
    
    # 3. Charger le modèle SentenceTransformers
    print("[LLM] Chargement du modèle SentenceTransformer pour les embeddings...")
    model = v_manager.get_embedding_model()
    
    all_chunks = []
    for pdf_path in pdf_files:
        chunks = extract_chunks_from_pdf(pdf_path)
        all_chunks.extend(chunks)
        
    if not all_chunks:
        print("[ERROR] Aucun contenu textuel extrait des fichiers PDF. Ingestion annulée.")
        return
        
    # 4. Vectoriser et insérer par lots de 100
    print(f"[Zvec] Début de l'indexation de {len(all_chunks)} chunks vectoriels...")
    batch_size = 100
    total_docs = len(all_chunks)
    
    indexed_docs = []
    
    for idx, chunk in enumerate(all_chunks):
        embedding = model.encode(chunk["text_content"]).tolist()
        indexed_docs.append({
            "doc_name": chunk["doc_name"],
            "page": chunk["page"],
            "text_content": chunk["text_content"],
            "embedding": embedding
        })
        
        if len(indexed_docs) >= batch_size or idx == total_docs - 1:
            v_manager.insert_annuaires(indexed_docs)
            print(f"[Zvec] Indexation en cours... {idx + 1}/{total_docs} chunks insérés.")
            indexed_docs = []
            
    print("[SUCCESS] Ingestion des annuaires PDF terminée avec succès !")

if __name__ == "__main__":
    main()
