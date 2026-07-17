import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os

DB_USER = "postgres"
DB_PASS = "UFABC"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "cobertura_db"

def setup_database():
    print("Conectando ao PostgreSQL padrão para criar o banco...")
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{DB_NAME}'")
        exists = cur.fetchone()
        
        if not exists:
            print(f"Criando banco de dados '{DB_NAME}'...")
            cur.execute(f"CREATE DATABASE {DB_NAME}")
        else:
            print(f"Banco '{DB_NAME}' já existe.")
            
        cur.close()
        conn.close()
        
        print(f"Conectando ao banco '{DB_NAME}' para habilitar PostGIS...")
        conn_db = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
        conn_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur_db = conn_db.cursor()
        
        print("Habilitando extensão PostGIS...")
        cur_db.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        cur_db.close()
        conn_db.close()
        
        print("Setup finalizado com sucesso! PostGIS está pronto.")
        
    except Exception as e:
        print(f"Erro durante o setup do banco de dados: {e}")

if __name__ == "__main__":
    setup_database()
