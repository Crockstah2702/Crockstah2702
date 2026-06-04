"""Weather tool using wttr.in (no API key needed)."""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def get_weather(location: str = "auto", format: str = "detailed") -> str:
    """Get current weather for a location."""
    try:
        import httpx
        loc = location.strip()
        if loc.lower() in ["auto", "mein standort", "hier"]:
            loc = ""  # wttr.in auto-detects

        async with httpx.AsyncClient(timeout=10.0) as client:
            if format == "brief":
                url = f"https://wttr.in/{loc}?format=3"
                resp = await client.get(url)
                return resp.text.strip()
            else:
                url = f"https://wttr.in/{loc}?format=j1"
                resp = await client.get(url)
                data = resp.json()

                current = data["current_condition"][0]
                area = data["nearest_area"][0]
                city = area["areaName"][0]["value"]
                country = area["country"][0]["value"]

                desc = current["lang_de"][0]["value"] if "lang_de" in current else current["weatherDesc"][0]["value"]
                temp_c = current["temp_C"]
                feels = current["FeelsLikeC"]
                humidity = current["humidity"]
                wind_kmph = current["windspeedKmph"]
                wind_dir = current["winddir16Point"]
                visibility = current["visibility"]
                uv = current["uvIndex"]

                weather_3day = data.get("weather", [])
                forecast_lines = []
                days = ["Heute", "Morgen", "Übermorgen"]
                for i, day in enumerate(weather_3day[:3]):
                    max_t = day["maxtempC"]
                    min_t = day["mintempC"]
                    desc_day = day["hourly"][4]["lang_de"][0]["value"] if "lang_de" in day["hourly"][4] else day["hourly"][4]["weatherDesc"][0]["value"]
                    forecast_lines.append(f"  {days[i]}: {min_t}°C - {max_t}°C, {desc_day}")

                result = [
                    f"🌍 **Wetter für {city}, {country}**",
                    f"🌡️ Temperatur: {temp_c}°C (gefühlt {feels}°C)",
                    f"☁️ Beschreibung: {desc}",
                    f"💧 Luftfeuchtigkeit: {humidity}%",
                    f"💨 Wind: {wind_kmph} km/h {wind_dir}",
                    f"👁️ Sichtweite: {visibility} km",
                    f"☀️ UV-Index: {uv}",
                    f"\n**3-Tage-Vorhersage:**",
                    *forecast_lines
                ]
                return "\n".join(result)

    except Exception as e:
        return f"Wetterdaten nicht verfügbar: {e}\nTipp: Prüfe deine Internetverbindung."


async def get_forecast(location: str, days: int = 3) -> str:
    """Get weather forecast."""
    return await get_weather(location)
