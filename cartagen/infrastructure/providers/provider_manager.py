# -*- coding: utf-8 -*-

import os
import json
import requests
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

class ProviderManager:
    """Gestionnaire dynamique des providers LLM (Cloud, API Key, Colab, Kaggle, Ollama, Local)."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.config_path = os.path.join(workspace_root, "providers_config.json")
        self.providers: Dict[str, Dict[str, Any]] = {}
        self._load_providers()

    def _load_providers(self):
        """Charge les providers depuis .env et le fichier JSON persistant."""
        load_dotenv(os.path.join(self.workspace_root, ".env"), override=True)
        # 1. Configs par défaut issues du .env
        default_providers = {
            "kaggle": {
                "id": "kaggle",
                "name": "Kaggle GPU (VisCoder2-7B Ngrok)",
                "exec_type": "kaggle",
                "model": os.getenv("OLLAMA_MODEL", "VisCoder2-7B"),
                "endpoint_url": os.getenv("OLLAMA_COLAB_URL", "https://deonna-veracious-belen.ngrok-free.dev"),
                "api_key": "",
                "description": "Tunnel d'exécution Kaggle GPU (VisCoder2-7B / Ngrok)"
            },
            "openrouter": {
                "id": "openrouter",
                "name": "OpenRouter API (Cloud)",
                "exec_type": "api_key",
                "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "endpoint_url": "https://openrouter.ai/api/v1/chat/completions",
                "description": "API OpenRouter avec modèles haute performance (Llama 3.3 70B, etc.)"
            },
            "groq": {
                "id": "groq",
                "name": "Groq Cloud API",
                "exec_type": "api_key",
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "api_key": os.getenv("GROQ_API_KEY", ""),
                "endpoint_url": "https://api.groq.com/openai/v1/chat/completions",
                "description": "Inférence ultra-rapide sur LPU Groq"
            },
            "openai": {
                "id": "openai",
                "name": "OpenAI API (GPT-4o)",
                "exec_type": "api_key",
                "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "endpoint_url": "https://api.openai.com/v1/chat/completions",
                "description": "Modèle GPT-4o d'OpenAI"
            },
            "colab": {
                "id": "colab",
                "name": "Google Colab Tunnel (Ngrok/Tunnel)",
                "exec_type": "colab",
                "model": "llama3",
                "endpoint_url": os.getenv("OLLAMA_COLAB_URL", "http://localhost:11434"),
                "api_key": "",
                "description": "Tunnel d'exécution sur Google Colab GPU"
            },
            "ollama": {
                "id": "ollama",
                "name": "Ollama (Serveur Local)",
                "exec_type": "ollama",
                "model": os.getenv("OLLAMA_MODEL", "llama3"),
                "endpoint_url": "http://localhost:11434",
                "api_key": "",
                "description": "Serveur local Ollama (localhost:11434)"
            },
            "local": {
                "id": "local",
                "name": "VisCoder2-7B (Local VRAM PyTorch)",
                "exec_type": "local",
                "model": "TIGER-Lab/VisCoder2-7B",
                "endpoint_url": "",
                "api_key": "",
                "description": "Exécution locale en 4-bit sur GPU local via Transformers"
            }
        }

        self.providers = default_providers

        # 2. Charger les surcharges personnalisées enregistrées sur disque
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                    for k, v in custom.items():
                        self.providers[k] = v
            except Exception as e:
                print(f"[ProviderManager] Erreur chargement providers_config.json : {e}")

    def save_providers(self):
        """Sauvegarde les providers personnalisés sur disque."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.providers, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ProviderManager] Erreur sauvegarde providers_config.json : {e}")

    def get_providers_list(self) -> List[Dict[str, Any]]:
        """Retourne la liste complète des providers sous forme structurée pour le Frontend."""
        load_dotenv(os.path.join(self.workspace_root, ".env"), override=True)
        self._load_providers()
        result = []
        # Lire le provider par défaut DEPUIS .env (pas de valeur codée en dur)
        default_provider_id = os.getenv("LLM_PROVIDER", "openrouter").lower()

        for pid, pinfo in self.providers.items():
            result.append({
                "id": pinfo["id"],
                "name": pinfo.get("name", pid),
                "exec_type": pinfo.get("exec_type", "api_key"),
                "model": pinfo.get("model", ""),
                "endpoint_url": pinfo.get("endpoint_url", ""),
                "has_api_key": bool(pinfo.get("api_key", "").strip()),
                "description": pinfo.get("description", ""),
                "is_default": (pid == default_provider_id)
            })
        return result

    def add_or_update_provider(self, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ajoute ou met à jour dynamiquement un provider LLM."""
        pid = provider_data.get("id", "").strip().lower()
        if not pid:
            name = provider_data.get("name", "custom").strip().lower()
            pid = name.replace(" ", "_")

        exec_type = provider_data.get("exec_type", "api_key").lower()
        endpoint_url = provider_data.get("endpoint_url", "").strip()

        # Ajustement d'URL par défaut selon exec_type
        if exec_type == "openrouter" and not endpoint_url:
            endpoint_url = "https://openrouter.ai/api/v1/chat/completions"
        elif exec_type == "groq" and not endpoint_url:
            endpoint_url = "https://api.groq.com/openai/v1/chat/completions"
        elif exec_type == "openai" and not endpoint_url:
            endpoint_url = "https://api.openai.com/v1/chat/completions"

        config = {
            "id": pid,
            "name": provider_data.get("name", pid),
            "exec_type": exec_type,
            "model": provider_data.get("model", "llama3"),
            "endpoint_url": endpoint_url,
            "api_key": provider_data.get("api_key", "").strip(),
            "description": provider_data.get("description", f"Provider personnalisé ({exec_type})")
        }

        self.providers[pid] = config
        self.save_providers()

        # Mettre à jour l'environnement si nécessaire
        if config["api_key"]:
            if exec_type == "openrouter":
                os.environ["OPENROUTER_API_KEY"] = config["api_key"]
            elif exec_type == "groq":
                os.environ["GROQ_API_KEY"] = config["api_key"]
            elif exec_type == "openai":
                os.environ["OPENAI_API_KEY"] = config["api_key"]

        if config["endpoint_url"] and exec_type in ["colab", "kaggle", "ollama"]:
            os.environ["OLLAMA_COLAB_URL"] = config["endpoint_url"]

        return config

    def call_llm_api(self, provider_id: str, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Méthode unifiée d'appel LLM pour n'importe quel provider (Cloud, Colab, Kaggle, Ollama)."""
        pid = provider_id.lower()
        pinfo = self.providers.get(pid, self.providers.get("openrouter", {}))

        exec_type = pinfo.get("exec_type", "api_key").lower()
        model_name = pinfo.get("model", "llama3")
        endpoint_url = pinfo.get("endpoint_url", "").strip()
        api_key = pinfo.get("api_key", "").strip()

        print("\n" + "╔" + "═"*78 + "╗")
        print(f"║ [ProviderManager -> Envoi LLM] Provider: {pinfo.get('name', pid)} ({exec_type.upper()})")
        print(f"║ Endpoint: {endpoint_url or 'Défaut API Cloud'} | Modèle: {model_name}")
        print("╚" + "═"*78 + "╝")

        # Headers HTTP universels avec déblocage Ngrok/Bypass
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "ngrok-skip-browser-warning": "true",
            "User-Agent": "CartaGenAgent/1.0",
            "Bypass-Tunnel-Remainder": "true"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if exec_type == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/dhieeddine/Net2Terraform-WebInterface"
            headers["X-Title"] = "CartaGen-MultiAgent"

        # Format 1 : API OpenAI-Compatible (OpenRouter, Groq, OpenAI, v1/chat/completions)
        if "chat/completions" in endpoint_url or exec_type in ["api_key", "openrouter", "groq", "openai"]:
            if not endpoint_url:
                if pid == "groq":
                    endpoint_url = "https://api.groq.com/openai/v1/chat/completions"
                    api_key = api_key or os.getenv("GROQ_API_KEY", "")
                elif pid == "openai":
                    endpoint_url = "https://api.openai.com/v1/chat/completions"
                    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
                else:
                    endpoint_url = "https://openrouter.ai/api/v1/chat/completions"
                    api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")

            if api_key and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {api_key}"

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.05
            }

            res = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"]

        # Format 2 : API Ollama / Colab / Kaggle / Tunnel (Tolérance multi-routes /generate & /api/generate)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        url_base = endpoint_url.rstrip("/")

        candidates = []
        if exec_type == "kaggle" or "ngrok" in url_base or "localtunnel" in url_base:
            candidates = [
                f"{url_base}/generate",
                f"{url_base}/api/generate",
                f"{url_base}/v1/chat/completions",
                url_base
            ]
        else:
            candidates = [
                url_base if url_base.endswith("/generate") or url_base.endswith("/api/generate") else f"{url_base}/api/generate",
                f"{url_base}/generate",
                url_base
            ]

        unique_candidates = []
        for c in candidates:
            if c not in unique_candidates:
                unique_candidates.append(c)

        last_error = None
        for candidate_url in unique_candidates:
            payload = {
                "model": model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.05}
            }

            try:
                res = requests.post(candidate_url, headers=headers, json=payload, timeout=180)
                if res.status_code == 404:
                    continue
                res.raise_for_status()
                
                try:
                    data = res.json()
                except Exception as json_err:
                    print(f"[ProviderManager] Erreur décodage JSON sur {candidate_url}: {json_err}. Réponse brute: {res.text[:150]}")
                    continue

                if "response" in data:
                    return data["response"]
                elif "generated_text" in data:
                    return data["generated_text"]
                elif "text" in data:
                    return data["text"]
                elif "choices" in data:
                    return data["choices"][0]["message"]["content"]
                elif isinstance(data, str):
                    return data
                else:
                    return str(data)
            except Exception as err:
                last_error = err

        if last_error:
            raise last_error
