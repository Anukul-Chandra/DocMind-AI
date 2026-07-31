import asyncio

from app.services.llm.model_catalog import ModelCatalogService
from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.openrouter import OpenRouterProvider


async def main():
    catalog = ModelCatalogService()

    models = catalog.get_free_models()

    pool = ModelPoolManager(models)

    provider = OpenRouterProvider(pool)

    response = await provider.generate(
        prompt="Say hello in one sentence."
    )

    print("\nModel:")
    print(pool.get_current_model())

    print("\nResponse:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())