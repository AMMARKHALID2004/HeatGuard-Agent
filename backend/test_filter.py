import asyncio
import httpx
from app.config import get_settings
from datetime import datetime

async def test():
    settings = get_settings()
    api_key = settings.fortyguard_api_key
    base_url = settings.fortyguard_base_url

    polygon_aoi = [[-74.017, 40.705], [-74.003, 40.705], [-74.003, 40.718], [-74.017, 40.718], [-74.017, 40.705]]
    date_time = datetime(2026, 8, 26, 7, 41)

    payload = {
        'polygon_aoi': {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'properties': {},
                'geometry': {'type': 'Polygon', 'coordinates': [polygon_aoi]},
            }],
        },
        'date_time': {
            'start_date': date_time.strftime('%Y-%m-%d'),
            'start_time': date_time.strftime('%H:%M'),
            'filter_type': 1,
        },
        'granularity': 100,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f'{base_url}/heatmap', headers={'api-key': api_key}, json=payload)
        data = resp.json()
        activity_id = data.get('data', {}).get('activity_id')
        print(f'Activity ID: {activity_id}')

        for i in range(10):
            await asyncio.sleep(3)
            resp = await client.get(f'{base_url}/status/{activity_id}', headers={'api-key': api_key})
            data = resp.json().get('data', {})
            status = data.get('status')
            print(f'Poll {i+1}: {status}')
            if status == 'completed':
                result = data.get('result')
                import json
                print(f'Result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}')
                if isinstance(result, dict):
                    print(f'map_data: {json.dumps(result.get("map_data", {}), default=str)[:1000]}')
                    print(f'stats_data: {json.dumps(result.get("stats_data", {}), default=str)[:1000]}')
                break

asyncio.run(test())