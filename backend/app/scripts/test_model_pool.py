"""
Manual test for ModelPoolManager.
"""

from app.services.llm.model_catalog import ModelCatalogService
from app.services.llm.model_pool import ModelPoolManager


def main() -> None:
    catalog = ModelCatalogService()

    models = catalog.get_free_models()

    pool = ModelPoolManager(models)

    print("=" * 60)
    print(f"Total Models: {pool.total_models()}")
    print("=" * 60)

    print("\nCurrent Model:")
    print(pool.get_current_model())

    print("\nRotating Models:\n")

    while True:
        try:
            print(pool.move_next())
        except RuntimeError as exc:
            print(f"\nFinished: {exc}")
            break


if __name__ == "__main__":
    main()