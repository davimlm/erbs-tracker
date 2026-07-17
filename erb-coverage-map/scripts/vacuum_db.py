import asyncio
import asyncpg

async def run():
    print("Iniciando VACUUM ANALYZE na tabela h3_grid_precalc...")
    try:
        # Precisamos conectar fora de um bloco de transação padrão para rodar VACUUM
        conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
        # Algumas versões do asyncpg precisam que isolamento seja ajustado para permitir comandos utilitários, 
        # mas comandos puros geralmente funcionam fora de blocos transaction explicitly
        await conn.execute("VACUUM ANALYZE h3_grid_precalc;")
        print("Sucesso! As estatísticas do índice espacial foram atualizadas.")
        await conn.close()
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == '__main__':
    asyncio.run(run())
