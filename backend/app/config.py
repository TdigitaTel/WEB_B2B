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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
