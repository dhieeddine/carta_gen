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
        
        self.stations_collection = None
        self.schemas_collection = None
        self.annuaires_collection = None

    def initialize_collections(self, dimension: int = 384):
        """Définit les schémas et initialise les collections Zvec."""
        import shutil
        if os.path.exists(self.stations_path):
            shutil.rmtree(self.stations_path, ignore_errors=True)
        if os.path.exists(self.schemas_path):
            shutil.rmtree(self.schemas_path, ignore_errors=True)
        if os.path.exists(self.annuaires_path):
            shutil.rmtree(self.annuaires_path, ignore_errors=True)
            
        # 1. Collection Stations
        stations_schema = zvec.CollectionSchema(
            name="stations_index",
            fields=[
                zvec.FieldSchema(name="id_station", data_type=zvec.DataType.INT64),
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
        self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)

    def initialize_annuaires_only(self, dimension: int = 384):
        """Initialise uniquement la collection des annuaires sans toucher aux autres."""
        import shutil
        if os.path.exists(self.annuaires_path):
            shutil.rmtree(self.annuaires_path, ignore_errors=True)
            
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
        self.annuaires_collection = zvec.create_and_open(path=self.annuaires_path, schema=annuaires_schema)

    def load_collections(self):
        """Tente d'ouvrir les collections existantes sans les recréer."""
        try:
            if os.path.exists(self.stations_path):
                self.stations_collection = zvec.open(path=self.stations_path)
            if os.path.exists(self.schemas_path):
                self.schemas_collection = zvec.open(path=self.schemas_path)
            if os.path.exists(self.annuaires_path):
                self.annuaires_collection = zvec.open(path=self.annuaires_path)
        except Exception as e:
            print(f"[VectorManager] Erreur de chargement des index : {e}")

    def insert_stations(self, docs: List[Dict[str, Any]]):
        """Insère une liste de documents dans l'index des stations."""
        if not self.stations_collection:
            # Essayer d'ouvrir sinon initialiser
            self.load_collections()
            if not self.stations_collection:
                self.initialize_collections()
            
        z_docs = []
        for doc in docs:
            z_docs.append(zvec.Doc(
                id=str(doc["id_station"]),
                vectors={"embedding": doc["embedding"]},
                fields={
                    "id_station": int(doc["id_station"]),
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

