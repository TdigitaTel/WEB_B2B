from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://bermudez:cambia_esta_clave@db:5432/bermudez_b2b"
    jwt_secret: str = "desarrollo_local_cambiar"
    seed_products: int = 15000
    seed_customers: int = 100
    sqlserver_host: str = ""
    sqlserver_port: int = 1433
    sqlserver_database: str = ""
    sqlserver_user: str = ""
    sqlserver_password: str = ""
    sqlserver_image_schema: str = "dbo"
    sqlserver_image_table: str = "imagenes"
    sqlserver_image_key_column: str = "CodigoArticulo"
    sqlserver_image_column: str = "imagen"
    sqlserver_stock_schema: str = "dbo"
    sqlserver_stock_table: str = "tempstockarticulo"
    sqlserver_stock_article_column: str = "CodigoArticulo"
    sqlserver_stock_warehouse_column: str = "CodigoAlmacen"
    sqlserver_stock_units_column: str = "UnidadesSaldo"
    sqlserver_warehouses_schema: str = "dbo"
    sqlserver_warehouses_table: str = "almacenes"
    sqlserver_warehouses_code_column: str = "CodigoAlmacen"
    sqlserver_warehouses_description_column: str = "Almacen"
    sqlserver_stock_excluded_warehouses: str = "97,98"
    sqlserver_articles_schema: str = "dbo"
    sqlserver_articles_table: str = "articulos"
    sqlserver_articles_code_column: str = "CodigoArticulo"
    sqlserver_price_with_tax_column: str = "PrecioVentaConIVA0"
    sqlserver_price_without_tax_column: str = "PrecioVentaSinIVA0"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
