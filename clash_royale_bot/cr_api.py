import aiohttp

BASE_URL = "https://api.clashroyale.com/v1"


class ClashRoyaleAPI:
    def __init__(self, api_key: str):
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def _get(self, path: str):
        url = f"{BASE_URL}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json(), None
                    elif resp.status == 404:
                        return None, "Spieler/Clan nicht gefunden. Bitte Tag prüfen."
                    elif resp.status == 403:
                        return None, "API-Key ungültig oder abgelaufen."
                    else:
                        return None, f"API-Fehler: HTTP {resp.status}"
        except aiohttp.ClientError as e:
            return None, f"Netzwerkfehler: {e}"

    async def get_player(self, tag: str):
        return await self._get(f"/players/%23{tag}")

    async def get_clan(self, tag: str):
        return await self._get(f"/clans/%23{tag}")

    async def get_cards(self):
        return await self._get("/cards")

    async def get_top_players(self, location_id: str = "global"):
        return await self._get(f"/locations/{location_id}/rankings/players")
