"""
Manual integration test for the OpenRouter Model Catalog.
"""

from app.core.config import settings
from app.services.llm.model_catalog import ModelCatalogService


def main() -> None:
    """Run the OpenRouter model catalog test."""
    service = ModelCatalogService(api_key=settings.openrouter_api_key)

    models = service.get_free_models()

    print("=" * 60)
    print(f"Total Free Models: {len(models)}")
    print("=" * 60)

    for index, model in enumerate(models, start=1):
        print(f"{index:02d}. {model}")


if __name__ == "__main__":
    main()