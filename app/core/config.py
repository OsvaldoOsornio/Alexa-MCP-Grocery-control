"""Configuración de la aplicación vía variables de entorno."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings cargados desde el entorno / archivo .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:changeme@localhost:5432/zero_waste_sous_chef"

    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    mcp_server_name: str = "zero-waste-sous-chef"
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia cacheada de Settings."""
    return Settings()
