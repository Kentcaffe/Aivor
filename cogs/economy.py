from __future__ import annotations

import json
import random
import time
from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from utils.aivor_embeds import aivor_embed
from utils.db import execute, fetch_all, fetch_one
from utils.safe_reply import hybrid_reply

# Rarități (afișare RO)
RARITATE = {
    "common": "Comun",
    "uncommon": "Neobișnuit",
    "rare": "Rar",
    "epic": "Epic",
    "legendary": "Legendar",
}

# Catalog shop: id -> meta (preț, vânzare, raritate, efect la /use)
SHOP_CATALOG: dict[str, dict] = {
    "snack": {
        "nume": "Snack Aivor",
        "pret": 120,
        "vanzare": 45,
        "raritate": "common",
        "descriere": "Mic bonus de energie.",
        "efect": "cash_small",
    },
    "cafea": {
        "nume": "Cafea Premium",
        "pret": 350,
        "vanzare": 120,
        "raritate": "uncommon",
        "descriere": "Te ajută să fii productiv.",
        "efect": "cash_med",
    },
    "laptop": {
        "nume": "Laptop Pro",
        "pret": 4200,
        "vanzare": 1800,
        "raritate": "rare",
        "descriere": "Perfect pentru grind-ul economic.",
        "efect": "bank_interest_hint",
    },
    "inel": {
        "nume": "Inel Legendar",
        "pret": 25000,
        "vanzare": 8000,
        "raritate": "legendary",
        "descriere": "Item special cu bonus la șanse.",
        "efect": "luck_boost",
    },
    "cheie": {
        "nume": "Cheie Mister",
        "pret": 5000,
        "vanzare": 1500,
        "raritate": "epic",
        "descriere": "Deschide un reward aleatoriu mare.",
        "efect": "mystery_box",
    },
}

JOBS = [
    ("Developer", 220, 520),
    ("Designer", 180, 480),
    ("Moderator", 200, 500),
    ("Streamer", 250, 600),
    ("Antreprenor", 300, 700),
]

# Anti-abuz: limite zilnice
MAX_PAY_PER_DAY = 500_000
MAX_ROB_PER_DAY = 8


def _today() -> str:
    return date.today().isoformat()


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


class Economy(commands.Cog):
    """Economie premium Aivor — cash, bancă, shop, jocuri, profil."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._bj_sessions: dict[tuple[int, int], dict] = {}

    def _ensure_user(self, guild_id: int, user_id: int) -> dict:
        execute(
            """
            INSERT OR IGNORE INTO economy_users(guild_id, user_id, cash, bank, last_daily, last_work, inventory_json, profile_json)
            VALUES(?, ?, 500, 0, 0, 0, '{}', '{}')
            """,
            (guild_id, user_id),
        )
        row = fetch_one(
            """
            SELECT cash, bank, last_daily, last_work, inventory_json, profile_json
            FROM economy_users
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        return dict(row) if row else {}

    def _profile(self, raw: str) -> dict:
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    def _save_user(
        self,
        guild_id: int,
        user_id: int,
        *,
        cash: int,
        bank: int,
        last_daily: float,
        last_work: float,
        inventory: dict,
        profile: dict,
    ) -> None:
        execute(
            """
            UPDATE economy_users
            SET cash = ?, bank = ?, last_daily = ?, last_work = ?, inventory_json = ?, profile_json = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (
                cash,
                bank,
                last_daily,
                last_work,
                json.dumps(inventory, ensure_ascii=False),
                json.dumps(profile, ensure_ascii=False),
                guild_id,
                user_id,
            ),
        )

    def _tx(self, guild_id: int, user_id: int, t: str, amount: int, note: str) -> None:
        execute(
            "INSERT INTO economy_transactions(guild_id, user_id, type, amount, note) VALUES(?, ?, ?, ?, ?)",
            (guild_id, user_id, t, amount, note),
        )

    def _abuse_check(self, profile: dict, key: str, limit: int) -> bool:
        day = _today()
        stats = profile.setdefault("abuse", {})
        if stats.get("day") != day:
            stats.clear()
            stats["day"] = day
        stats[key] = int(stats.get(key, 0)) + 1
        return stats[key] <= limit

    def _seconds_left(self, last_ts: float, cooldown: int) -> int:
        return max(0, int((last_ts + cooldown) - time.time()))

    # ---------- Comenzi principale ----------

    @commands.hybrid_command(name="daily", description="Recompensă zilnică; bonus streak dacă revii zile consecutive.")
    async def daily(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        last_ymd = prof.get("last_daily_ymd")
        today = _today()
        streak = int(prof.get("streak", 0))
        if last_ymd == today:
            left = self._seconds_left(float(u["last_daily"]), 86400)
            h, m = left // 3600, (left % 3600) // 60
            await hybrid_reply(ctx, content=f"⏳ Ai primit deja daily-ul azi. Revino în `{h}h {m}m`.", ephemeral=True)
            return
        if last_ymd == _yesterday():
            streak += 1
        else:
            streak = 1
        base = random.randint(400, 900)
        bonus = min(streak * 40, 2000)
        reward = base + bonus
        cash = int(u["cash"]) + reward
        prof["last_daily_ymd"] = today
        prof["streak"] = streak
        prof.setdefault("total_earned", 0)
        prof["total_earned"] = int(prof["total_earned"]) + reward
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=cash,
            bank=int(u["bank"]),
            last_daily=time.time(),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "daily", reward, f"Streak x{streak}")
        embed = aivor_embed(
            "Daily Aivor",
            f"**+{reward}$** (bază + bonus streak)\n**Streak curent:** `{streak}` zile",
            fields=[("Bonus streak", f"+{bonus}$", True), ("Total câștigat azi", f"{reward}$", True)],
        )
        await hybrid_reply(ctx, embed=embed)

    @commands.hybrid_command(name="work", description="Lucrezi un job aleatoriu; câștig cash (cooldown între ture).")
    async def work(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        left = self._seconds_left(float(u["last_work"]), 1200)
        if left > 0:
            await hybrid_reply(ctx, content=f"⏳ Pauză de muncă. Revino în `{left // 60}m {left % 60}s`.", ephemeral=True)
            return
        job, lo, hi = random.choice(JOBS)
        pay = random.randint(lo, hi)
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        prof.setdefault("jobs", {})
        prof["jobs"][job] = int(prof["jobs"].get(job, 0)) + 1
        cash = int(u["cash"]) + pay
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=cash,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=time.time(),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "work", pay, job)
        embed = aivor_embed("Muncă", f"Ai lucrat ca **{job}** și ai câștigat **`{pay}$`**.")
        await hybrid_reply(ctx, embed=embed)

    @commands.hybrid_command(name="beg", description="Cerșești o sumă mică; aștepți între încercări.")
    async def beg(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        prof = self._profile(u["profile_json"])
        last_beg = float(prof.get("last_beg", 0))
        if self._seconds_left(last_beg, 300) > 0:
            s = self._seconds_left(last_beg, 300)
            await hybrid_reply(ctx, content=f"⏳ Ești prea obosit să cerșești. Așteaptă `{s}s`.", ephemeral=True)
            return
        gain = random.randint(15, 120)
        prof["last_beg"] = time.time()
        cash = int(u["cash"]) + gain
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=cash,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "beg", gain, "Cerșit")
        await hybrid_reply(ctx, embed=aivor_embed("Cerșit", f"Cineva ți-a dat **`{gain}$`**."))

    async def _balance_embed(self, guild: discord.Guild, member: discord.Member) -> discord.Embed:
        u = self._ensure_user(guild.id, member.id)
        prof = self._profile(u["profile_json"])
        total = int(u["cash"]) + int(u["bank"])
        streak = int(prof.get("streak", 0))
        return aivor_embed(
            f"Balanță · {member.display_name}",
            f"**Cash:** `{int(u['cash'])}$`\n**Bancă:** `{int(u['bank'])}$`\n**Total:** `{total}$`",
            fields=[("Streak daily", f"{streak} zile", True), ("ID", str(member.id), True)],
        )

    async def _send_balance(self, ctx: commands.Context, utilizator: discord.Member | None) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        m = utilizator or ctx.author
        await hybrid_reply(ctx, embed=await self._balance_embed(ctx.guild, m))

    @commands.hybrid_command(name="balans", aliases=["balance"], description="Afișează cash (buzunar) și bancă.")
    @app_commands.describe(utilizator="Opțional: alt membru")
    async def balans(self, ctx: commands.Context, utilizator: discord.Member | None = None) -> None:
        await self._send_balance(ctx, utilizator)

    async def _depozit_impl(self, ctx: commands.Context, suma: int) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < suma:
            await hybrid_reply(ctx, content="❌ Nu ai suficient cash.", ephemeral=True)
            return
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) - suma,
            bank=int(u["bank"]) + suma,
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "deposit", suma, "Depozit")
        await hybrid_reply(ctx, embed=aivor_embed("Depozit", f"Ai depus **`{suma}$`** în bancă."))

    @commands.hybrid_command(name="depozit", aliases=["deposit"], description="Muți bani din cash în bancă (mai sigur la jaf).")
    async def depozit(self, ctx: commands.Context, suma: app_commands.Range[int, 1, 2_000_000]) -> None:
        await self._depozit_impl(ctx, suma)

    async def _retrage_impl(self, ctx: commands.Context, suma: int) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["bank"]) < suma:
            await hybrid_reply(ctx, content="❌ Bancă insuficientă.", ephemeral=True)
            return
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + suma,
            bank=int(u["bank"]) - suma,
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "withdraw", suma, "Retragere")
        await hybrid_reply(ctx, embed=aivor_embed("Retragere", f"Ai retras **`{suma}$`**."))

    @commands.hybrid_command(name="retrage", aliases=["withdraw"], description="Scoți bani din bancă în cash.")
    async def retrage(self, ctx: commands.Context, suma: app_commands.Range[int, 1, 2_000_000]) -> None:
        await self._retrage_impl(ctx, suma)

    @commands.hybrid_command(name="pay", description="Trimite cash altui membru; există limită zilnică anti-abuz.")
    async def pay(self, ctx: commands.Context, utilizator: discord.Member, suma: app_commands.Range[int, 1, 2_000_000]) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        if utilizator.bot or utilizator.id == ctx.author.id:
            await hybrid_reply(ctx, content="❌ Membru invalid.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        prof = self._profile(u["profile_json"])
        if not self._abuse_check(prof, "pay_count", 50):
            await hybrid_reply(ctx, content="❌ Limită zilnică de transferuri atinsă.", ephemeral=True)
            return
        if int(u["cash"]) < suma:
            await hybrid_reply(ctx, content="❌ Cash insuficient.", ephemeral=True)
            return
        if suma > MAX_PAY_PER_DAY:
            await hybrid_reply(ctx, content="❌ Sumă prea mare într-o singură tranzacție.", ephemeral=True)
            return
        t = self._ensure_user(ctx.guild.id, utilizator.id)
        tp = self._profile(t["profile_json"])
        inv_u = json.loads(u["inventory_json"] or "{}")
        inv_t = json.loads(t["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) - suma,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv_u,
            profile=prof,
        )
        self._save_user(
            ctx.guild.id,
            utilizator.id,
            cash=int(t["cash"]) + suma,
            bank=int(t["bank"]),
            last_daily=float(t["last_daily"]),
            last_work=float(t["last_work"]),
            inventory=inv_t,
            profile=tp,
        )
        self._tx(ctx.guild.id, ctx.author.id, "pay_out", -suma, f"-> {utilizator.id}")
        self._tx(ctx.guild.id, utilizator.id, "pay_in", suma, f"<- {ctx.author.id}")
        await hybrid_reply(ctx, embed=aivor_embed("Transfer", f"Ai trimis **`{suma}$`** către {utilizator.mention}."))

    async def _leaderboard_impl(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        await ctx.defer()
        rows = fetch_all(
            "SELECT user_id, cash, bank FROM economy_users WHERE guild_id = ? ORDER BY (cash+bank) DESC LIMIT 10",
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.followup.send("Nu există date încă.")
            return
        lines = []
        for i, r in enumerate(rows, 1):
            mem = ctx.guild.get_member(int(r["user_id"]))
            name = mem.display_name if mem else f"ID {r['user_id']}"
            tot = int(r["cash"]) + int(r["bank"])
            lines.append(f"**{i}.** {name} — `{tot}$`")
        await ctx.followup.send(embed=aivor_embed("Clasament economie Aivor", "\n".join(lines)))

    @commands.hybrid_command(name="leaderboard", aliases=["top_economie"], description="Clasament bogăție pe acest server.")
    async def leaderboard(self, ctx: commands.Context) -> None:
        await self._leaderboard_impl(ctx)

    @commands.hybrid_command(name="profil_economie", description="Rezumat economic detaliat: balanță, obiecte, statistici.")
    @app_commands.describe(utilizator="Membru")
    async def profil_economie(self, ctx: commands.Context, utilizator: discord.Member | None = None) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        m = utilizator or ctx.author
        u = self._ensure_user(ctx.guild.id, m.id)
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        jobs = prof.get("jobs", {})
        top_job = max(jobs.items(), key=lambda x: x[1]) if jobs else ("—", 0)
        lines = [f"**{SHOP_CATALOG[k]['nume']}** x{qty}" for k, qty in sorted(inv.items()) if k in SHOP_CATALOG][:8]
        inv_preview = "\n".join(lines) if lines else "*Inventar gol (cumpără din shop)*"
        embed = aivor_embed(
            f"Profil economic · {m.display_name}",
            f"**Cash:** `{int(u['cash'])}$` · **Bancă:** `{int(u['bank'])}$`\n**Streak daily:** `{prof.get('streak', 0)}`",
            fields=[
                ("Job preferat", f"{top_job[0]} ({top_job[1]} ture)", False),
                ("Inventar (extras)", inv_preview, False),
                ("Total câștigat (est.)", f"`{prof.get('total_earned', 0)}$`", True),
            ],
        )
        await hybrid_reply(ctx, embed=embed)

    @commands.hybrid_command(name="shop", description="Lista magazin: ID item, preț, raritate.")
    async def shop(self, ctx: commands.Context) -> None:
        lines = []
        for iid, meta in SHOP_CATALOG.items():
            r = RARITATE.get(meta["raritate"], meta["raritate"])
            lines.append(f"**`{iid}`** — {meta['nume']} · `{meta['pret']}$` · *{r}*\n_{meta['descriere']}_")
        await hybrid_reply(ctx, embed=aivor_embed("Magazin Aivor", "\n\n".join(lines)))

    @commands.hybrid_command(name="cumpara", aliases=["buy"], description="Cumperi din magazin după ID (opțional cantitate).")
    async def cumpara(self, ctx: commands.Context, item_id: str, cantitate: app_commands.Range[int, 1, 99] = 1) -> None:
        await self._buy_impl(ctx, item_id.lower().strip(), cantitate)

    async def _buy_impl(self, ctx: commands.Context, item_id: str, cantitate: int) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        if item_id not in SHOP_CATALOG:
            await hybrid_reply(ctx, content="❌ ID invalid. Folosește `/shop` sau `!shop`.", ephemeral=True)
            return
        meta = SHOP_CATALOG[item_id]
        price = meta["pret"] * cantitate
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < price:
            await hybrid_reply(ctx, content="❌ Cash insuficient.", ephemeral=True)
            return
        inv = json.loads(u["inventory_json"] or "{}")
        inv[item_id] = inv.get(item_id, 0) + cantitate
        prof = self._profile(u["profile_json"])
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) - price,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "buy", -price, f"{cantitate}x {item_id}")
        r = RARITATE.get(meta["raritate"], meta["raritate"])
        await hybrid_reply(ctx,
            embed=aivor_embed("Cumpărare", f"Ai cumpărat **`{cantitate}x {meta['nume']}`** pentru **`{price}$`**.\nRaritate: **{r}**")
        )

    @commands.hybrid_command(name="vinde", aliases=["sell"], description="Vinzi iteme din inventar după ID.")
    async def vinde(self, ctx: commands.Context, item_id: str, cantitate: app_commands.Range[int, 1, 99] = 1) -> None:
        await self._sell_impl(ctx, item_id.lower().strip(), cantitate)

    async def _sell_impl(self, ctx: commands.Context, item_id: str, cantitate: int) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        if item_id not in SHOP_CATALOG:
            await hybrid_reply(ctx, content="❌ ID invalid.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        inv = json.loads(u["inventory_json"] or "{}")
        if inv.get(item_id, 0) < cantitate:
            await hybrid_reply(ctx, content="❌ Nu ai suficiente iteme.", ephemeral=True)
            return
        meta = SHOP_CATALOG[item_id]
        gain = meta["vanzare"] * cantitate
        inv[item_id] = inv[item_id] - cantitate
        if inv[item_id] <= 0:
            del inv[item_id]
        prof = self._profile(u["profile_json"])
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + gain,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "sell", gain, f"{cantitate}x {item_id}")
        await hybrid_reply(ctx, embed=aivor_embed("Vânzare", f"Ai vândut pentru **`{gain}$`**."))

    @commands.hybrid_command(name="foloseste", aliases=["use"], description="Activezi un item special din inventar (efecte din shop).")
    @app_commands.describe(item_id="ID din shop")
    async def foloseste(self, ctx: commands.Context, item_id: str) -> None:
        await self._use_impl(ctx, item_id.lower().strip())

    async def _use_impl(self, ctx: commands.Context, item_id: str) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        if item_id not in SHOP_CATALOG:
            await hybrid_reply(ctx, content="❌ ID invalid.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        inv = json.loads(u["inventory_json"] or "{}")
        if inv.get(item_id, 0) < 1:
            await hybrid_reply(ctx, content="❌ Nu ai acest item.", ephemeral=True)
            return
        eff = SHOP_CATALOG[item_id]["efect"]
        prof = self._profile(u["profile_json"])
        msg = ""
        bonus = 0
        if eff == "cash_small":
            bonus = random.randint(40, 120)
            msg = f"Ai primit **`{bonus}$`** din consumabil."
        elif eff == "cash_med":
            bonus = random.randint(120, 350)
            msg = f"Ai primit **`{bonus}$`**."
        elif eff == "bank_interest_hint":
            msg = "Bonus intel: depozitele mari sunt mai sigure decât pariurile."
        elif eff == "luck_boost":
            prof["luck_until"] = time.time() + 3600
            msg = "Noroc sporit la jocuri timp de **1h** (simulat)."
        elif eff == "mystery_box":
            bonus = random.choice([200, 500, 1200, 5000, 200])
            msg = f"Cutia mister: **`{bonus}$`**!"
        inv[item_id] -= 1
        if inv[item_id] <= 0:
            del inv[item_id]
        cash = int(u["cash"]) + bonus
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=cash,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        if bonus:
            self._tx(ctx.guild.id, ctx.author.id, "use", bonus, item_id)
        await hybrid_reply(ctx, embed=aivor_embed("Folosire item", msg))

    @commands.hybrid_command(name="inventar", description="Itemele tale sau ale altui membru (mențiune opțională).")
    async def inventar(self, ctx: commands.Context, utilizator: discord.Member | None = None) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        m = utilizator or ctx.author
        u = self._ensure_user(ctx.guild.id, m.id)
        inv = json.loads(u["inventory_json"] or "{}")
        if not inv:
            await hybrid_reply(ctx, content=f"{m.mention} nu are iteme.")
            return
        lines = []
        for k, q in sorted(inv.items()):
            if k in SHOP_CATALOG:
                meta = SHOP_CATALOG[k]
                r = RARITATE.get(meta["raritate"], meta["raritate"])
                lines.append(f"`{k}` **{meta['nume']}** x{q} — {r}")
            else:
                lines.append(f"`{k}` x{q}")
        await hybrid_reply(ctx, embed=aivor_embed(f"Inventar · {m.display_name}", "\n".join(lines)))

    # ---------- Jocuri ----------

    @commands.hybrid_command(name="slots", description="Pacanele: pariezi din cash; linii și câștiguri aleatorii.")
    async def slots(self, ctx: commands.Context, miza: app_commands.Range[int, 25, 50_000]) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < miza:
            await hybrid_reply(ctx, content="❌ Cash insuficient.", ephemeral=True)
            return
        reels = [random.choice(["🍒", "🍋", "💎", "7️⃣", "🍀"]) for _ in range(3)]
        mult = 0
        if len(set(reels)) == 1:
            mult = 6
        elif len(set(reels)) == 2:
            mult = 2
        win = miza * mult
        delta = win - miza
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + delta,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "slots", delta, " ".join(reels))
        await hybrid_reply(ctx, embed=aivor_embed("Slots Aivor", f"{' '.join(reels)}\n**Rezultat:** `{delta:+}$`"))

    @commands.hybrid_command(name="coinflip", description="Alegi cap sau pajură și o miză (minim din cash).")
    @app_commands.describe(alegere="cap sau pajura", miza="Sumă pariată")
    async def coinflip(self, ctx: commands.Context, alegere: str, miza: app_commands.Range[int, 50, 100_000]) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        a = alegere.lower().strip()
        if a not in ("cap", "pajura", "pajură"):
            await hybrid_reply(ctx, content="❌ Scrie `cap` sau `pajura`.", ephemeral=True)
            return
        if "pajur" in a:
            pick = "pajura"
        else:
            pick = "cap"
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < miza:
            await hybrid_reply(ctx, content="❌ Cash insuficient.", ephemeral=True)
            return
        outcome = random.choice(["cap", "pajura"])
        win = miza if outcome == pick else -miza
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + win,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "coinflip", win, outcome)
        await hybrid_reply(ctx,
            embed=aivor_embed("Coinflip", f"Rezultat: **{outcome}**\n**{'Câștig' if win > 0 else 'Pierdere'}:** `{win:+}$`")
        )

    @commands.hybrid_command(name="roata", description="Roata norocului: cost fix 100$ cash, multiplicator aleatoriu.")
    async def roata(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        cost = 100
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < cost:
            await hybrid_reply(ctx, content="❌ Îți trebuie cel puțin 100$ cash.", ephemeral=True)
            return
        mult = random.choices([0, 0.5, 1, 2, 5], weights=[20, 25, 30, 15, 10])[0]
        gain = int(cost * mult) - cost
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + gain,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "wheel", gain, "roata")
        await hybrid_reply(ctx, embed=aivor_embed("Roata Aivor", f"Multiplier x{mult}\n**Rezultat:** `{gain:+}$`"))

    @commands.hybrid_command(name="jaf", description="Încerci să iei cash de la alt membru; cooldown și limite zilnice.")
    async def jaf(self, ctx: commands.Context, tinta: discord.Member) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        if tinta.bot or tinta.id == ctx.author.id:
            await hybrid_reply(ctx, content="❌ Țintă invalidă.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        prof = self._profile(u["profile_json"])
        if not self._abuse_check(prof, "rob_count", MAX_ROB_PER_DAY):
            await hybrid_reply(ctx, content="❌ Limită zilnică de jafuri atinsă.", ephemeral=True)
            return
        if self._seconds_left(float(prof.get("last_rob", 0)), 1800) > 0:
            s = self._seconds_left(float(prof.get("last_rob", 0)), 1800)
            await hybrid_reply(ctx, content=f"⏳ Așteaptă `{s // 60}m` pentru următorul jaf.", ephemeral=True)
            return
        tv = self._ensure_user(ctx.guild.id, tinta.id)
        if int(tv["cash"]) < 80:
            await hybrid_reply(ctx, content="❌ Ținta nu are destui bani lichizi.", ephemeral=True)
            return
        chance = 0.38
        if prof.get("luck_until", 0) > time.time():
            chance += 0.07
        success = random.random() < chance
        prof["last_rob"] = time.time()
        tp = self._profile(tv["profile_json"])
        inv_u = json.loads(u["inventory_json"] or "{}")
        inv_t = json.loads(tv["inventory_json"] or "{}")
        if success:
            pct = random.uniform(0.05, 0.14)
            stolen = int(int(tv["cash"]) * pct)
            stolen = max(40, min(stolen, 25_000))
            self._save_user(
                ctx.guild.id,
                tinta.id,
                cash=int(tv["cash"]) - stolen,
                bank=int(tv["bank"]),
                last_daily=float(tv["last_daily"]),
                last_work=float(tv["last_work"]),
                inventory=inv_t,
                profile=tp,
            )
            self._save_user(
                ctx.guild.id,
                ctx.author.id,
                cash=int(u["cash"]) + stolen,
                bank=int(u["bank"]),
                last_daily=float(u["last_daily"]),
                last_work=float(u["last_work"]),
                inventory=inv_u,
                profile=prof,
            )
            self._tx(ctx.guild.id, ctx.author.id, "rob", stolen, f"la {tinta.id}")
            self._tx(ctx.guild.id, tinta.id, "rob_victim", -stolen, f"de {ctx.author.id}")
            msg = f"Succes! Ai luat **`{stolen}$`** de la {tinta.mention}."
        else:
            fine = min(200, int(u["cash"]) // 10)
            self._save_user(
                ctx.guild.id,
                ctx.author.id,
                cash=int(u["cash"]) - fine,
                bank=int(u["bank"]),
                last_daily=float(u["last_daily"]),
                last_work=float(u["last_work"]),
                inventory=inv_u,
                profile=prof,
            )
            self._tx(ctx.guild.id, ctx.author.id, "rob_fail", -fine, "amenda")
            msg = f"Prins! Ai plătit o amendă de **`{fine}$`**."
        await hybrid_reply(ctx, embed=aivor_embed("Jaf", msg))

    @commands.hybrid_command(name="blackjack", description="O mână de blackjack contra dealerului; miză din cash.")
    async def blackjack(self, ctx: commands.Context, miza: app_commands.Range[int, 50, 50_000]) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        u = self._ensure_user(ctx.guild.id, ctx.author.id)
        if int(u["cash"]) < miza:
            await hybrid_reply(ctx, content="❌ Cash insuficient.", ephemeral=True)
            return

        def draw() -> int:
            c = random.randint(1, 13)
            val = 11 if c == 1 else min(10, c)
            return val

        p = draw() + draw()
        d = draw() + draw()
        outcome = "push"
        delta = 0
        if p > 21:
            outcome = "lose"
            delta = -miza
        elif d > 21 or p > d:
            outcome = "win"
            delta = miza
        elif p < d:
            outcome = "lose"
            delta = -miza
        else:
            delta = 0
        prof = self._profile(u["profile_json"])
        inv = json.loads(u["inventory_json"] or "{}")
        self._save_user(
            ctx.guild.id,
            ctx.author.id,
            cash=int(u["cash"]) + delta,
            bank=int(u["bank"]),
            last_daily=float(u["last_daily"]),
            last_work=float(u["last_work"]),
            inventory=inv,
            profile=prof,
        )
        self._tx(ctx.guild.id, ctx.author.id, "blackjack", delta, f"P{p} D{d}")
        await hybrid_reply(ctx,
            embed=aivor_embed(
                "Blackjack Aivor",
                f"**Tu:** {p} · **Dealer:** {d}\n**Rezultat:** `{outcome}` → `{delta:+}$`",
            )
        )

    @commands.hybrid_command(name="tranzactii", description="Ultimele tranzacții în cont (tip, sumă, notă).")
    async def tranzactii(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await hybrid_reply(ctx, content="Folosește comanda pe server.", ephemeral=True)
            return
        rows = fetch_all(
            """
            SELECT type, amount, note, created_at FROM economy_transactions
            WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 12
            """,
            (ctx.guild.id, ctx.author.id),
        )
        if not rows:
            await hybrid_reply(ctx, content="Nu ai tranzacții încă.", ephemeral=True)
            return
        lines = [
            f"`{time.strftime('%d/%m %H:%M', time.localtime(int(r['created_at'])))}` **{r['type']}** `{int(r['amount']):+}$` — {r['note']}"
            for r in rows
        ]
        await hybrid_reply(ctx, embed=aivor_embed("Istoric tranzacții", "\n".join(lines)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
