import os
import hashlib
import argparse

from openai import OpenAI
from sqlalchemy import create_engine, text
from tqdm import tqdm

DATABASE_URL = os.environ["DATABASE_URL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536

client = OpenAI(api_key=OPENAI_API_KEY)
engine = create_engine(DATABASE_URL)


def create_vector_structure():
    """Crea extensión, tabla e índice si todavía no existen."""

    sql = """
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS product_embeddings (
        product_id INTEGER PRIMARY KEY
            REFERENCES products(id)
            ON DELETE CASCADE,

        embedding_text TEXT NOT NULL,

        embedding VECTOR(1536) NOT NULL,

        model VARCHAR(100) NOT NULL,

        content_hash VARCHAR(64) NOT NULL,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_product_embeddings_hnsw
    ON product_embeddings
    USING hnsw (embedding vector_cosine_ops);
    """

    with engine.begin() as conn:
        conn.execute(text(sql))

    print("✓ Estructura vectorial preparada")


def build_embedding_text(product):
    """
    Construye el texto semántico del producto.

    NO incluimos:
    - precio
    - stock
    - SKU
    - EAN
    - IDs
    """

    fields = [
        product.family,
        product.subfamily,
        product.short_description,
        product.commercial_description,
        product.technical_description,
    ]

    fields = [
        str(value).strip()
        for value in fields
        if value is not None and str(value).strip()
    ]

    return ". ".join(fields)


def calculate_hash(value: str):
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def get_products(limit=None):
    sql = """
        SELECT
            p.id,
            p.family,
            p.subfamily,
            p.short_description,
            p.commercial_description,
            p.technical_description
        FROM products p
        ORDER BY p.id
    """

    params = {}

    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        return conn.execute(
            text(sql),
            params
        ).fetchall()


def get_existing_hash(product_id):
    sql = """
        SELECT content_hash
        FROM product_embeddings
        WHERE product_id = :product_id
    """

    with engine.connect() as conn:
        return conn.execute(
            text(sql),
            {"product_id": product_id}
        ).scalar()


def generate_embedding(value: str):
    response = client.embeddings.create(
        model=MODEL,
        input=value
    )

    return response.data[0].embedding


def save_embedding(
    product_id,
    embedding_text,
    embedding,
    content_hash
):
    sql = """
    INSERT INTO product_embeddings (
        product_id,
        embedding_text,
        embedding,
        model,
        content_hash,
        created_at,
        updated_at
    )
    VALUES (
        :product_id,
        :embedding_text,
        CAST(:embedding AS vector),
        :model,
        :content_hash,
        NOW(),
        NOW()
    )

    ON CONFLICT (product_id)
    DO UPDATE SET

        embedding_text = EXCLUDED.embedding_text,
        embedding = EXCLUDED.embedding,
        model = EXCLUDED.model,
        content_hash = EXCLUDED.content_hash,
        updated_at = NOW();
    """

    vector_string = "[" + ",".join(
        str(x) for x in embedding
    ) + "]"

    with engine.begin() as conn:
        conn.execute(
            text(sql),
            {
                "product_id": product_id,
                "embedding_text": embedding_text,
                "embedding": vector_string,
                "model": MODEL,
                "content_hash": content_hash,
            },
        )


def process_products(limit=None):
    products = get_products(limit)

    generated = 0
    skipped = 0
    errors = 0

    print(f"\nProductos encontrados: {len(products)}")
    print(f"Modelo: {MODEL}")
    print("Generando embeddings...\n")

    progress = tqdm(
        products,
        total=len(products),
        desc="Embeddings",
        unit="producto",
        dynamic_ncols=True
    )

    for product in progress:
        try:
            embedding_text = build_embedding_text(product)

            if not embedding_text:
                skipped += 1
                continue

            content_hash = calculate_hash(embedding_text)
            existing_hash = get_existing_hash(product.id)

            if existing_hash == content_hash:
                skipped += 1
                progress.set_postfix(
                    generados=generated,
                    omitidos=skipped,
                    errores=errors
                )
                continue

            embedding = generate_embedding(embedding_text)

            if len(embedding) != DIMENSIONS:
                raise RuntimeError(
                    f"Dimensión inesperada: {len(embedding)}"
                )

            save_embedding(
                product.id,
                embedding_text,
                embedding,
                content_hash
            )

            generated += 1

        except Exception as e:
            errors += 1
            tqdm.write(
                f"ERROR producto {product.id}: {e}"
            )

        progress.set_postfix(
            generados=generated,
            omitidos=skipped,
            errores=errors
        )

    print("\nProceso terminado")
    print("-----------------")
    print(f"Total:       {len(products)}")
    print(f"Generados:   {generated}")
    print(f"Sin cambios: {skipped}")
    print(f"Errores:     {errors}")

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Número máximo de productos"
    )

    args = parser.parse_args()

    create_vector_structure()

    process_products(args.limit)


if __name__ == "__main__":
    main()