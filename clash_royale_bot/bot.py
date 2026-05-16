import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from cr_api import ClashRoyaleAPI

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
api = ClashRoyaleAPI(os.getenv("CR_API_KEY"))


@bot.event
async def on_ready():
    print(f"Bot eingeloggt als {bot.user}")


@bot.command(name="player", help="Zeigt Stats eines Spielers. Bsp: !player #ABC123")
async def player(ctx, tag: str):
    tag = tag.upper().replace("O", "0").lstrip("#")
    async with ctx.typing():
        data, error = await api.get_player(tag)
    if error:
        await ctx.send(f"Fehler: {error}")
        return

    embed = discord.Embed(
        title=f"{data['name']} (#{tag})",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Trophäen", value=data.get("trophies", "?"), inline=True)
    embed.add_field(name="Beste Trophäen", value=data.get("bestTrophies", "?"), inline=True)
    embed.add_field(name="Arena", value=data.get("arena", {}).get("name", "?"), inline=True)
    embed.add_field(name="Gewonnene Schlachten", value=data.get("wins", "?"), inline=True)
    embed.add_field(name="Verlorene Schlachten", value=data.get("losses", "?"), inline=True)
    embed.add_field(name="3-Kronen-Siege", value=data.get("threeCrownWins", "?"), inline=True)

    clan = data.get("clan")
    if clan:
        embed.add_field(name="Clan", value=f"{clan['name']} (#{clan['tag'].lstrip('#')})", inline=False)
    else:
        embed.add_field(name="Clan", value="Kein Clan", inline=False)

    deck = data.get("currentDeck", [])
    if deck:
        deck_str = ", ".join(card["name"] for card in deck)
        embed.add_field(name="Aktuelles Deck", value=deck_str, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="clan", help="Zeigt Clan-Infos. Bsp: !clan #ABC123")
async def clan(ctx, tag: str):
    tag = tag.upper().replace("O", "0").lstrip("#")
    async with ctx.typing():
        data, error = await api.get_clan(tag)
    if error:
        await ctx.send(f"Fehler: {error}")
        return

    embed = discord.Embed(
        title=f"{data['name']} (#{tag})",
        description=data.get("description", "Keine Beschreibung"),
        color=discord.Color.blue(),
    )
    embed.add_field(name="Trophäen", value=data.get("clanScore", "?"), inline=True)
    embed.add_field(name="Mitglieder", value=f"{data.get('members', '?')}/50", inline=True)
    embed.add_field(name="Typ", value=data.get("type", "?"), inline=True)
    embed.add_field(name="Benötigte Trophäen", value=data.get("requiredTrophies", "?"), inline=True)
    embed.add_field(name="Gespendete Karten", value=data.get("donationsPerWeek", "?"), inline=True)

    location = data.get("location", {})
    if location:
        embed.add_field(name="Standort", value=location.get("name", "?"), inline=True)

    top_members = data.get("memberList", [])[:5]
    if top_members:
        top_str = "\n".join(
            f"{i+1}. {m['name']} — {m['trophies']} 🏆"
            for i, m in enumerate(top_members)
        )
        embed.add_field(name="Top 5 Mitglieder", value=top_str, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="cards", help="Zeigt alle verfügbaren Karten")
async def cards(ctx):
    async with ctx.typing():
        data, error = await api.get_cards()
    if error:
        await ctx.send(f"Fehler: {error}")
        return

    items = data.get("items", [])
    common = [c["name"] for c in items if c.get("rarity") == "common"]
    rare = [c["name"] for c in items if c.get("rarity") == "rare"]
    epic = [c["name"] for c in items if c.get("rarity") == "epic"]
    legendary = [c["name"] for c in items if c.get("rarity") == "legendary"]

    embed = discord.Embed(title="Clash Royale Karten", color=discord.Color.purple())
    embed.add_field(name=f"Gewöhnlich ({len(common)})", value=", ".join(common[:10]) + ("..." if len(common) > 10 else ""), inline=False)
    embed.add_field(name=f"Selten ({len(rare)})", value=", ".join(rare[:10]) + ("..." if len(rare) > 10 else ""), inline=False)
    embed.add_field(name=f"Episch ({len(epic)})", value=", ".join(epic[:10]) + ("..." if len(epic) > 10 else ""), inline=False)
    embed.add_field(name=f"Legendär ({len(legendary)})", value=", ".join(legendary), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="top", help="Zeigt die Top 10 Spieler weltweit")
async def top(ctx):
    async with ctx.typing():
        data, error = await api.get_top_players()
    if error:
        await ctx.send(f"Fehler: {error}")
        return

    players = data.get("items", [])[:10]
    embed = discord.Embed(title="Top 10 Spieler weltweit", color=discord.Color.red())
    lines = [
        f"{i+1}. **{p['name']}** — {p['trophies']} 🏆  (Clan: {p.get('clan', {}).get('name', 'kein Clan')})"
        for i, p in enumerate(players)
    ]
    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command(name="hilfe", help="Zeigt alle Befehle")
async def hilfe(ctx):
    embed = discord.Embed(title="Clash Royale Bot — Befehle", color=discord.Color.green())
    embed.add_field(name="!player #TAG", value="Spieler-Stats anzeigen", inline=False)
    embed.add_field(name="!clan #TAG", value="Clan-Infos anzeigen", inline=False)
    embed.add_field(name="!cards", value="Alle Karten auflisten", inline=False)
    embed.add_field(name="!top", value="Top 10 Spieler weltweit", inline=False)
    embed.add_field(name="!hilfe", value="Diese Hilfe anzeigen", inline=False)
    await ctx.send(embed=embed)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
