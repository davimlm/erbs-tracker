import asyncio
import httpx

async def test_admin():
    async with httpx.AsyncClient() as client:
        res = await client.get('http://127.0.0.1:8000/api/admin/status')
        print(res.status_code)
        print(res.text)

if __name__ == '__main__':
    asyncio.run(test_admin())
