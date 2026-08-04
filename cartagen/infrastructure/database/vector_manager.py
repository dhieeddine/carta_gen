# -*- coding: utf-8 -*-

import os
import zvec
from typing import List, Dict, Any, Optional

class VectorManager:
    """Gère l'accès, l'indexation et la recherche sémantique dans la base de données vectorielle Zvec."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.zvec_dir = os.path.join(workspace_root, "zvec_store")
        os.makedirs(self.zvec_dir, exist_ok=True)
        
        self.stations_path = os.path.join(self.zvec_dir, "stations")
        self.schemas_path = os.path.join(self.zvec_dir, "schemas")
        self.annuaires_path = os.path.join(self.zvec_dir, "annuaires")
        self.images_path = os.path.join(self.zvec_dir, "images")
        
        self.stations_collection = None
        self.schemas_collection = None
        self.annuaires_collection = None
        self.images_collection = None

    def initialize_collections(self, dimension: int = 384):
        """Définit les schémas et initialise les collections Zvec."""
        import shutil
        
        # 1. Collection Stations
        stations_schema = zvec.CollectionSchema(
            name="stations_index",
            fields=[
                zvec.FieldSchema(name="id_station", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="nom", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        if os.path.exists(self.stations_path):
            try:
                shutil.rmtree(self.stations_path, ignore_errors=True)
            except Exception:
                pass
        if os.path.exists(self.stations_path):
            try:
                self.stations_collection = zvec.open(path=self.stations_path)
            except Exception:
                self.stations_collection = zvec.create_and_open(path=self.stations_path, schema=stations_schema)
        else:
            self.stations_collection = zvec.create_and_open(path=self.stations_path, schema=stations_schema)

        # 2. Collection Schémas
        schemas_schema = zvec.CollectionSchema(
            name="schemas_index",
            fields=[
                zvec.FieldSchema(name="table_name", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="description", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        if os.path.exists(self.schemas_path):
            try:
                shutil.rmtree(self.schemas_path, ignore_errors=True)
            except Exception:
                pass
        if os.path.exists(self.schemas_path):
            try:
                self.schemas_collection = zvec.open(path=self.schemas_path)
            except Exception:
                self.schemas_collection = zvec.create_and_open(path=self.schemas_path, schema=schemas_schema)
        else:
            self.schemas_collection = zvec.create_and_open(path=self.schemas_path, schema=schemas_schema)

        # 3. Collection Annuaires (RAG Documentaire)
        annuaires_schema = zvec.CollectionSchema(
            name="annuaires_index",
            fields=[
                zvec.FieldSchema(name="doc_name", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="page", data_type=zvec.DataType.INT64),
                zvec.FieldSchema(name="text_content", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        if os.path.exists(self.annuaires_path):
            try:
                shutil.rmtree(self.annuaires_path, ignore_errors=True)
            except Exception:
                pass
        if os.path.exists(self.annuaires_path):
            try:
                self.annuaires_collection = zvec.open(path=self.annuaires_path)
            except Exception:
                self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)
        else:
            self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)

        # 4. Collection Images (Cartes dynamiques)
        images_schema = zvec.CollectionSchema(
            name="images_index",
            fields=[
                zvec.FieldSchema(name="filename", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="description", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        if os.path.exists(self.images_path):
            try:
                shutil.rmtree(self.images_path, ignore_errors=True)
            except Exception:
                pass
        if os.path.exists(self.images_path):
            try:
                self.images_collection = zvec.open(path=self.images_path)
            except Exception:
                self.images_collection = zvec.create_and_open(path=self.images_path, schema=images_schema)
        else:
            self.images_collection = zvec.create_and_open(path=self.images_path, schema=images_schema)

    def initialize_annuaires_only(self, dimension: int = 384):
        """Initialise uniquement la collection des annuaires sans toucher aux autres."""
        import shutil
        import time
        annuaires_schema = zvec.CollectionSchema(
            name="annuaires_index",
            fields=[
                zvec.FieldSchema(name="doc_name", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="page", data_type=zvec.DataType.INT64),
                zvec.FieldSchema(name="text_content", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        # Libérer la référence en mémoire
        self.annuaires_collection = None

        if os.path.exists(self.annuaires_path):
            try:
                # 1. Tenter d'ouvrir la collection existante si elle est déjà valide
                self.annuaires_collection = zvec.open(path=self.annuaires_path)
            except Exception:
                # 2. Si l'ouverture échoue, purger et recréer la collection
                lock_file = os.path.join(self.annuaires_path, "LOCK")
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                    except Exception:
                        pass
                time.sleep(0.2)
                try:
                    shutil.rmtree(self.annuaires_path, ignore_errors=True)
                except Exception as e:
                    print(f"[VectorManager] Avertissement suppression annuaires: {e}")
                
                if not os.path.exists(self.annuaires_path):
                    self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)
                else:
                    try:
                        self.annuaires_collection = zvec.open(path=self.annuaires_path)
                    except Exception:
                        self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)
        else:
            self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)

    def initialize_images_only(self, dimension: int = 384):
        """Initialise uniquement la collection des images sans toucher aux autres."""
        import shutil
        import time
        images_schema = zvec.CollectionSchema(
            name="images_index",
            fields=[
                zvec.FieldSchema(name="filename", data_type=zvec.DataType.STRING),
                zvec.FieldSchema(name="description", data_type=zvec.DataType.STRING)
            ],
            vectors=[
                zvec.VectorSchema(
                    name="embedding",
                    data_type=zvec.DataType.VECTOR_FP32,
                    dimension=dimension,
                    index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                )
            ]
        )
        # Fermer la collection existante pour libérer le verrou
        self.images_collection = None
        if os.path.exists(self.images_path):
            lock_file = os.path.join(self.images_path, "LOCK")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception:
                    pass
            time.sleep(0.1)
            try:
                shutil.rmtree(self.images_path, ignore_errors=True)
            except Exception as e:
                print(f"[VectorManager] Avertissement suppression images: {e}")
        if os.path.exists(self.images_path):
            try:
                self.images_collection = zvec.open(path=self.images_path)
            except Exception:
                self.images_collection = zvec.create_and_open(path=self.images_path, schema=images_schema)
        else:
            self.images_collection = zvec.create_and_open(path=self.images_path, schema=images_schema)

    def _safe_open(self, path: str):
        """Ouvre une collection Zvec en gérant silencieusement les accès concurrents et verrous."""
        if not os.path.exists(path):
            return None
        try:
            return zvec.open(path=path)
        except Exception:
            try:
                return zvec.open(path=path, option=zvec.CollectionOption(read_only=True))
            except Exception:
                pass
            lock_file = os.path.join(path, "LOCK")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    return zvec.open(path=path)
                except Exception:
                    pass
            return None

    def load_collections(self):
        """Tente d'ouvrir les collections existantes sans les recréer."""
        if not self.stations_collection:
            self.stations_collection = self._safe_open(self.stations_path)
        if not self.schemas_collection:
            self.schemas_collection = self._safe_open(self.schemas_path)
        if not self.annuaires_collection:
            self.annuaires_collection = self._safe_open(self.annuaires_path)
        if not self.images_collection:
            self.images_collection = self._safe_open(self.images_path)

    def insert_stations(self, docs: List[Dict[str, Any]]):
        """Insère une liste de documents dans l'index des stations (par lots de 1000)."""
        if not self.stations_collection:
            # Essayer d'ouvrir sinon initialiser
            self.load_collections()
            if not self.stations_collection:
                self.initialize_collections()
            
        BATCH_SIZE = 1000
        for i in range(0, len(docs), BATCH_SIZE):
            batch = docs[i:i + BATCH_SIZE]
            z_docs = []
            for doc in batch:
                z_docs.append(zvec.Doc(
                    id=str(doc["id_station"]),
                    vectors={"embedding": doc["embedding"]},
                    fields={
                        "id_station": str(doc["id_station"]),
                        "nom": str(doc["nom"])
                    }
                ))
            self.stations_collection.insert(z_docs)

    def insert_schemas(self, docs: List[Dict[str, Any]]):
        """Insère une liste de documents dans l'index des schémas."""
        if not self.schemas_collection:
            self.load_collections()
            if not self.schemas_collection:
                self.initialize_collections()
            
        z_docs = []
        for i, doc in enumerate(docs):
            z_docs.append(zvec.Doc(
                id=f"schema_{i}",
                vectors={"embedding": doc["embedding"]},
                fields={
                    "table_name": str(doc["table_name"]),
                    "description": str(doc["description"])
                }
            ))
            
        self.schemas_collection.insert(z_docs)

    def insert_annuaires(self, docs: List[Dict[str, Any]]):
        """Insère une liste de documents (chunks de pages de PDF) dans l'index des annuaires."""
        if not self.annuaires_collection:
            self.load_collections()
            if not self.annuaires_collection:
                self.initialize_annuaires_only()
        
        BATCH_SIZE = 1000
        for i in range(0, len(docs), BATCH_SIZE):
            batch = docs[i:i + BATCH_SIZE]
            z_docs = []
            for doc in batch:
                z_docs.append(zvec.Doc(
                    id=doc["doc_name"] + "_" + str(doc["page"]),
                    vectors={"embedding": doc["embedding"]},
                    fields={
                        "doc_name": str(doc["doc_name"]),
                        "page": int(doc["page"]),
                        "text_content": str(doc["text_content"])
                    }
                ))
            self.annuaires_collection.insert(z_docs)

    def insert_images(self, docs: List[Dict[str, Any]]):
        """Insère une liste de descriptions d'images dans l'index des images."""
        if not self.images_collection:
            self.load_collections()
            if not self.images_collection:
                self.initialize_images_only()
                
        BATCH_SIZE = 500
        for i in range(0, len(docs), BATCH_SIZE):
            batch = docs[i:i + BATCH_SIZE]
            z_docs = []
            for doc in batch:
                z_docs.append(zvec.Doc(
                    id=doc["filename"],
                    vectors={"embedding": doc["embedding"]},
                    fields={
                        "filename": str(doc["filename"]),
                        "description": str(doc["description"])
                    }
                ))
            self.images_collection.insert(z_docs)

    def query_stations(self, query_vector: List[float], topk: int = 5) -> List[Dict[str, Any]]:
        """Recherche les stations sémantiquement les plus proches."""
        if not self.stations_collection:
            self.load_collections()
            if not self.stations_collection:
                return []
                
        try:
            results = self.stations_collection.query(
                zvec.VectorQuery("embedding", vector=query_vector),
                topk=topk
            )
            
            matches = []
            for r in results:
                matches.append({
                    "id_station": r.fields.get("id_station"),
                    "nom": r.fields.get("nom"),
                    "score": r.score
                })
            return matches
        except Exception as e:
            print(f"[VectorManager] Erreur recherche stations : {e}")
            return []

    def query_schemas(self, query_vector: List[float], topk: int = 2) -> List[Dict[str, Any]]:
        """Recherche les schémas de table sémantiquement les plus proches."""
        if not self.schemas_collection:
            self.load_collections()
            if not self.schemas_collection:
                return []
                
        try:
            results = self.schemas_collection.query(
                zvec.VectorQuery("embedding", vector=query_vector),
                topk=topk
            )
            
            matches = []
            for r in results:
                matches.append({
                    "table_name": r.fields.get("table_name"),
                    "description": r.fields.get("description"),
                    "score": r.score
                })
            return matches
        except Exception as e:
            print(f"[VectorManager] Erreur recherche schémas : {e}")
            return []

    def query_annuaires(self, query_vector: List[float], topk: int = 5) -> List[Dict[str, Any]]:
        """Recherche les passages d'annuaires sémantiquement les plus proches."""
        if not self.annuaires_collection:
            self.load_collections()
            if not self.annuaires_collection:
                return []
                
        try:
            results = self.annuaires_collection.query(
                zvec.VectorQuery("embedding", vector=query_vector),
                topk=topk
            )
            
            matches = []
            for r in results:
                matches.append({
                    "doc_name": r.fields.get("doc_name"),
                    "page": r.fields.get("page"),
                    "text_content": r.fields.get("text_content"),
                    "score": r.score
                })
            return matches
        except Exception as e:
            print(f"[VectorManager] Erreur recherche annuaires : {e}")
            return []

    def query_images(self, query_vector: List[float], topk: int = 2) -> List[Dict[str, Any]]:
        """Effectue une recherche sémantique dans l'index des images."""
        if not self.images_collection:
            self.load_collections()
            if not self.images_collection:
                return []
                
        try:
            results = self.images_collection.query(
                zvec.VectorQuery("embedding", vector=query_vector),
                topk=topk
            )
            
            matches = []
            for r in results:
                matches.append({
                    "filename": r.fields.get("filename"),
                    "description": r.fields.get("description"),
                    "score": r.score
                })
            return matches
        except Exception as e:
            print(f"[VectorManager] Erreur recherche images : {e}")
            return []

    def get_embedding_model(self):
        """Lazy loading du modèle SentenceTransformer pour éviter de ralentir le démarrage de l'API."""
        if not hasattr(self, '_model') or self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model

    def query_stations_by_text(self, text: str, topk: int = 5) -> List[Dict[str, Any]]:
        """Vectorise la requête textuelle et cherche les stations les plus similaires dans Zvec."""
        try:
            model = self.get_embedding_model()
            query_vector = model.encode(text).tolist()
            return self.query_stations(query_vector, topk=topk)
        except Exception as e:
            print(f"[VectorManager] Erreur vectorisation/recherche stations : {e}")
            return []

    def query_schemas_by_text(self, text: str, topk: int = 2) -> List[Dict[str, Any]]:
        """Vectorise la requête textuelle et cherche les schémas les plus similaires dans Zvec."""
        try:
            model = self.get_embedding_model()
            query_vector = model.encode(text).tolist()
            return self.query_schemas(query_vector, topk=topk)
        except Exception as e:
            print(f"[VectorManager] Erreur vectorisation/recherche schémas : {e}")
            return []

    def query_annuaires_by_text(self, text: str, topk: int = 5) -> List[Dict[str, Any]]:
        """Vectorise la requête textuelle et cherche les passages les plus similaires dans les annuaires indexés."""
        try:
            model = self.get_embedding_model()
            query_vector = model.encode(text).tolist()
            return self.query_annuaires(query_vector, topk=topk)
        except Exception as e:
            print(f"[VectorManager] Erreur vectorisation/recherche annuaires : {e}")
            return []

    def query_images_by_text(self, text: str, topk: int = 2) -> List[Dict[str, Any]]:
        """Vectorise la requête textuelle et cherche les images sémantiquement les plus pertinentes."""
        try:
            model = self.get_embedding_model()
            query_vector = model.encode(text).tolist()
            return self.query_images(query_vector, topk=topk)
        except Exception as e:
            print(f"[VectorManager] Erreur vectorisation/recherche images : {e}")
            return []

