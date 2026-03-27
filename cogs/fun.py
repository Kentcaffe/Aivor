from __future__ import annotations

import asyncio
import hashlib
import random
import time
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from utils.aivor_embeds import aivor_embed
from utils.json_store import load_json_file, save_json_file
from utils.safe_reply import hybrid_reply

_MAGIC_8_RO: tuple[str, ...] = (
    "Da, sigur.",
    "Fără îndoială.",
    "Absolut.",
    "Poți conta pe asta.",
    "Da, clar.",
    "Conform semnelor, da.",
    "Foarte probabil.",
    "Pare bine.",
    "Da.",
    "Răspunsul e probabil da.",
    "Răspuns neclar, mai întreabă.",
    "Întreabă mai târziu.",
    "Mai bine nu-ți spun acum.",
    "Nu pot prezice acum.",
    "Concentrează-te și întreabă din nou.",
    "Nu te baza pe asta.",
    "Răspunsul meu e nu.",
    "Sursele spun nu.",
    "Perspectiva nu e bună.",
    "Foarte îndoielnic.",
)

_AFF = _MAGIC_8_RO[0:10]
_NEU = _MAGIC_8_RO[10:15]
_NEG = _MAGIC_8_RO[15:20]


def _classify_8ball(q: str) -> str:
    """Tema întrebării — folosită ca să nu dea „Pare bine.” la orice, fără legătură."""
    if any(
        p in q
        for p in (
            "nu reușesc",
            "nu reusesc",
            "nu o să trec",
            "nu o sa trec",
            "o să pic",
            "o sa pic",
            "am să pic",
            "am sa pic",
            "sigur pic",
            "am să pic la",
        )
    ):
        return "worry"
    if any(
        w in q
        for w in (
            "reușesc",
            "reusesc",
            "reusi",
            "examen",
            "examenul",
            "bac",
            "test",
            "nota",
            "promov",
            "trec",
            "admitere",
            "facultate",
            "licență",
            "licenta",
            "școală",
            "scoala",
            "meditații",
            "meditatii",
            "învăț",
            "invat",
        )
    ):
        return "hope"
    if any(
        w in q
        for w in (
            "iubire",
            "iubesc",
            "iubește",
            "iubeste",
            "relație",
            "relatie",
            "împreună",
            "impreuna",
            "îl iub",
            "il iub",
            "o iub",
            "cu el",
            "cu ea",
            "mă iubește",
            "ma iubeste",
        )
    ):
        return "love"
    if any(w in q for w in ("bani", "salariu", "bogat", "sărac", "sarac", "câștig", "castig", "loterie", "noroc la")):
        return "money"
    if any(w in q for w in ("sănătate", "sanatate", "bolnav", "spital", "doctor")):
        return "health"
    return "neutral"


def _magic_8_answer(question: str) -> str:
    q_raw = (question or "").strip()
    q = q_raw.lower()
    if len(q) < 2 or q in ("orice", "?", "întrebare", "intrebare", "ceva", "nimic"):
        return random.choice(_MAGIC_8_RO)

    digest = hashlib.md5(q.encode("utf-8")).digest()
    h = int.from_bytes(digest[:8], "big")
    cat = _classify_8ball(q)

    # În fiecare categorie: același text → același răspuns (hash stabil), dar piscă diferit după temă.
    if cat == "hope":
        r = h % 100
        pool = _AFF if r < 72 else _NEU if r < 93 else _NEG
    elif cat == "worry":
        r = h % 100
        pool = _NEG if r < 70 else _NEU if r < 92 else _AFF
    elif cat == "love":
        r = h % 100
        pool = _AFF if r < 78 else _NEU if r < 94 else _NEG
    elif cat == "money":
        r = h % 100
        pool = _AFF if r < 55 else _NEU if r < 88 else _NEG
    elif cat == "health":
        r = h % 100
        pool = _NEU if r < 45 else _AFF if r < 80 else _NEG
    else:
        pool = _MAGIC_8_RO

    idx = (h // 256) % len(pool)
    return pool[idx]


class Fun(commands.Cog):
    """Comenzi fun & social — Aivor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._afk_key = "afk.json"

    def _afk_all(self) -> dict[str, Any]:
        return load_json_file(self._afk_key, {})

    def _save_afk(self, data: dict[str, Any]) -> None:
        save_json_file(self._afk_key, data)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        data = self._afk_all()
        gid = str(message.guild.id)
        uid = str(message.author.id)
        if gid in data and uid in data[gid]:
            del data[gid][uid]
            if not data[gid]:
                del data[gid]
            self._save_afk(data)
            await message.channel.send(f"👋 {message.author.mention} nu mai e AFK.", delete_after=5)
        if message.mentions:
            data = self._afk_all()
            for m in message.mentions:
                if m.bot:
                    continue
                u = str(m.id)
                if gid in data and u in data[gid]:
                    reason = data[gid][u].get("reason", "")
                    await message.channel.send(f"💤 {m.display_name} e AFK: {reason}", delete_after=8)

    @commands.hybrid_command(name="afk", description="Setezi motiv AFK; la mențiune alții văd mesajul scurt.")
    async def afk(self, ctx: commands.Context, *, motiv: str = "Indisponibil"):
        if not ctx.guild:
            return
        data = self._afk_all()
        gid = str(ctx.guild.id)
        data.setdefault(gid, {})
        data[gid][str(ctx.author.id)] = {"reason": motiv[:200], "t": time.time()}
        self._save_afk(data)
        await hybrid_reply(ctx, embed=aivor_embed("AFK", f"{ctx.author.mention} este AFK.\n**Motiv:** {motiv[:200]}"))

    @commands.hybrid_command(
        name="eightball",
        aliases=("8ball", "glob"),
        description="Glob magic 8-Ball: întrebi (opțional) și primești răspuns amuzant.",
    )
    @app_commands.describe(intrebare="Ce vrei să întrebi? (opțional)")
    async def eightball(self, ctx: commands.Context, *, intrebare: str = "Orice"):
        ans = _magic_8_answer(intrebare)
        q_display = intrebare.strip()[:500] if intrebare.strip() else "—"
        await hybrid_reply(
            ctx,
            embed=aivor_embed(
                "🔮 Globul Aivor",
                f"**Întrebare:** {q_display}\n**Răspuns:** {ans}\n"
                f"*Globul potrivește tonul după tema întrebării (școală, iubire, temeri…); "
                f"același text → același răspuns. E doar pentru distracție, nu sfat real.*",
            ),
        )

    @commands.hybrid_command(name="ship", description="Procent de compatibilitate între doi membri menționați.")
    async def ship(self, ctx: commands.Context, a: discord.Member, b: discord.Member):
        pct = (a.id + b.id) % 101
        await hybrid_reply(ctx, embed=aivor_embed("💞 Ship Aivor", f"{a.mention} + {b.mention}\n**Compatibilitate:** `{pct}%`"))

    @commands.hybrid_command(name="zaruri", description="Număr aleatoriu; implicit 1–6, poți seta numărul de fețe.")
    async def zaruri(self, ctx: commands.Context, fete: int = 6):
        fete = max(2, min(100, fete))
        await hybrid_reply(ctx, embed=aivor_embed("🎲 Zaruri", f"Ai dat **`{random.randint(1, fete)}`** (1–{fete})."))

    @commands.hybrid_command(name="moneda", description="Aruncă moneda: cap sau pajură, fără pariu.")
    async def moneda(self, ctx: commands.Context):
        await hybrid_reply(ctx, embed=aivor_embed("🪙 Monedă", f"Rezultat: **{random.choice(['Cap', 'Pajură'])}**"))

    @commands.hybrid_command(name="hack_fake", description="Simulare glumeță de hack pe un membru (nu e real).")
    async def hack_fake(self, ctx: commands.Context, tinta: discord.Member):
        etape = ["[▓░░░░] scanare IP...", "[▓▓▓░░] injectare meme...", "[▓▓▓▓▓] completat."]
        msg = await hybrid_reply(ctx, content=etape[0])
        for e in etape[1:]:
            await asyncio.sleep(0.7)
            await msg.edit(content=e)
        await msg.edit(content=f"✅ {tinta} a fost „hack-uit” în glumă. (Nu e real.)")

    @commands.hybrid_command(name="nota", description="Primești o notă aleatorie 1–10 pentru un subiect text.")
    async def nota(self, ctx: commands.Context, *, subiect: str):
        n = random.randint(1, 10)
        await hybrid_reply(ctx, embed=aivor_embed("📊 Notă Aivor", f"**{subiect[:200]}** primește **`{n}/10`**."))

    @commands.hybrid_command(name="snipe", description="Afișează ultimul mesaj text șters din acest canal.")
    async def snipe(self, ctx: commands.Context):
        sn = getattr(self.bot, "snipes", {}).get(ctx.channel.id)
        if not sn:
            await hybrid_reply(ctx, content="Nu am nimic de snipe aici.")
            return
        await hybrid_reply(
            ctx,
            embed=aivor_embed(
                "Snipe",
                f"**Autor:** {sn['author']}\n**Conținut:** {sn['content'][:1800]}",
            ),
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content:
            return
        if not hasattr(self.bot, "snipes"):
            self.bot.snipes = {}
        self.bot.snipes[message.channel.id] = {
            "author": str(message.author),
            "content": message.content,
            "t": time.time(),
        }


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
