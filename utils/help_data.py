"""Date pentru panoul de ajutor Aivor — public vs staff; texte explicative pentru fiecare comandă."""

from __future__ import annotations

import discord

# Categorii vizibile pentru orice membru (uz personal)
CATEGORY_ORDER_PUBLIC: tuple[str, ...] = (
    "economie",
    "level",
    "fun",
    "info",
)

# Categorii doar pentru staff moderare / configurare server
CATEGORY_ORDER_STAFF: tuple[str, ...] = (
    "mod",
    "automod",
    "ticket",
    "log",
)

# Ordinea completă (pentru staff) — folosit la grid complet
CATEGORY_ORDER: tuple[str, ...] = CATEGORY_ORDER_PUBLIC + CATEGORY_ORDER_STAFF

STAFF_KEYS = frozenset(CATEGORY_ORDER_STAFF)

# label scurt, emoji, descriere pentru Select (max ~100 caractere fiecare câmp)
CATEGORY_META: dict[str, tuple[str, str, str]] = {
    "economie": ("Economie", "💰", "Bani, magazin, inventar, cazino — ghid complet"),
    "level": ("Level & XP", "📈", "Rank, clasament, profil de nivel"),
    "mod": ("Moderare", "🛡️", "Ban, kick, mute, warn, curățare canal"),
    "automod": ("AutoMod PRO", "⚡", "Spam, linkuri, zalgo, blacklist, escaladare 3/5/7"),
    "ticket": ("Tickete", "🎫", "Panel, claim, transcript, staff"),
    "log": ("Jurnale", "📜", "Canale dedicate pentru evenimente și modlog"),
    "fun": ("Fun & social", "🎲", "AFK, glob, ship, glume, snipe"),
    "info": ("Info & utilitare", "ℹ️", "Ping, uptime, server, utilizator, help"),
}

# Notă scurtă la subsolul fiecărui modul (slash + prefix)
HELP_USAGE_NOTE = (
    "\n\n—\n*Comenzi **hybrid**: tastează **`/`** + numele în Discord sau prefix **`!`** / **`a!`** în chat "
    "(ex.: `!daily` · `/daily`).*"
)

# Intro de o propoziție sub titlul categoriei (înainte de câmpuri sau de lista lungă)
CATEGORY_INTRO: dict[str, str] = {
    "economie": (
        "Economia Aivor folosește **cash** (în buzunar) și **bancă** (sigur). "
        "Câștigi prin activități zilnice, lucrezi, cumperi din magazin și poți paria la mini-jocuri."
    ),
    "level": (
        "Scrii mesaje pe server și acumulezi **XP** pentru **nivel**. "
        "Staff-ul poate lega roluri și recompense de anumite niveluri."
    ),
    "fun": (
        "Comenzi de relaxare: stări AFK, răspunsuri aleatoare, compatibilitate, zaruri și altele — fără impact economic serios."
    ),
    "info": (
        "Verifici latența botului, cât timp rulează, date despre server și membri, plus panoul central de ajutor."
    ),
    "mod": (
        "Instrumente pentru echipa de moderare: acțiuni asupra membrilor, curățare mesaje, blocare canal, istoric cazuri."
    ),
    "automod": (
        "AutoMod PRO: anti-spam inteligent, linkuri/invite, CAPS, mențiuni, zalgo, pseudonime, blacklist pe severități, escaladare 3/5/7."
    ),
    "ticket": (
        "Utilizatorii deschid canale private de suport; staff-ul revendică, adaugă oameni și închide cu confirmare."
    ),
    "log": (
        "Legi canale separate unde botul scrie evenimente generale, acțiuni de mod, tickete și AutoMod."
    ),
}

# Câmpuri (titlu, conținut) — conținut ≤ ~1000 caractere; None = un singur bloc în description
CATEGORY_FIELDS: dict[str, list[tuple[str, str]]] = {
    "economie": [
        (
            "💵 Venituri & cont",
            (
                "**`/daily`** — recompensă zilnică; bonus de **streak** dacă revii zile la rând.\n"
                "**`/work`** — lucrezi un job aleatoriu; **cooldown** între ture.\n"
                "**`/beg`** — cerșești pe stradă; sumă mică, **cooldown**.\n"
                "**`/balans`** (`balance`) — vezi **cash** și **bancă**.\n"
                "**`/depozit`** (`deposit`) — muți bani din cash în **bancă** (mai sigur la jaf).\n"
                "**`/retrage`** (`withdraw`) — scoți din bancă în cash.\n"
                "**`/pay`** `@membru` `sumă` — trimiți cash altcuiva (**limită zilnică** anti-abuz).\n"
                "**`/leaderboard`** (`top_economie`) — top bogați pe server.\n"
                "**`/profil_economie`** — rezumat detaliat (balanță, obiecte, statistici).\n"
                "**`/tranzactii`** — ultimele mișcări în cont (tip, sumă, notă)."
            ),
        ),
        (
            "🛒 Magazin & inventar",
            (
                "**`/shop`** — lista de **iteme** cu ID, preț și raritate.\n"
                "**`/cumpara`** (`buy`) `id` `[cantitate]` — cumperi din magazin.\n"
                "**`/vinde`** (`sell`) `id` `[cantitate]` — vinzi din inventar.\n"
                "**`/foloseste`** (`use`) `id` — activezi un **item special** (efecte definite în magazin).\n"
                "**`/inventar`** `[@membru]` — ce deții tu sau alt membru."
            ),
        ),
        (
            "🎰 Mini-jocuri & risc",
            (
                "**`/slots`** `miză` — pacanele; câștig sau pierdere din **cash**.\n"
                "**`/coinflip`** `cap|pajura` `miză` — pariu simplu pe monedă.\n"
                "**`/roata`** — roata norocului; **cost fix** din cash, multiplicator aleatoriu.\n"
                "**`/blackjack`** `miză` — o mână rapidă contra dealerului.\n"
                "**`/jaf`** `@membru` — încerci să iei cash de la altcineva; **șanse**, **cooldown** și limite."
            ),
        ),
    ],
    "level": [
        (
            "📊 Comenzi",
            (
                "**`/rank`** `[@membru]` — poziția ta sau a altcuiva în **clasamentul XP** pe server.\n"
                "**`/toplevel`** — **top niveluri** (leaderboard).\n"
                "**`/profil_level`** — XP, nivel, progres până la următorul nivel."
            ),
        ),
    ],
    "fun": [
        (
            "🗨️ Social & stări",
            (
                "**`/afk`** `[motiv]` — marchezi **absent**; la mențiune, alții văd motivul (scurt).\n"
                "**`/eightball`** (`8ball`) `[întrebare]` — **glob magic** cu răspuns amuzant (nu e sfat real).\n"
                "**`/ship`** `@a` `@b` — **compatibilitate** procentuală între doi membri.\n"
                "**`/snipe`** — arată **ultimul mesaj șters** din canalul curent (dacă există)."
            ),
        ),
        (
            "🎯 Distracție rapidă",
            (
                "**`/zaruri`** `[fețe]` — număr aleatoriu (implicit 1–6, poți seta fețe).\n"
                "**`/moneda`** — cap sau pajură, **fără pariu**.\n"
                "**`/hack_fake`** `@membru` — simulare glumeț de „hack” (mesaje progresive).\n"
                "**`/nota`** `subiect` — primești o **notă 1–10** aleatorie pe un text."
            ),
        ),
    ],
    "info": [
        (
            "⚡ Monitorizare",
            (
                "**`/ping`** / **`aivorping`** — **latență** bot (heartbeat Discord).\n"
                "**`/uptime`** — de cât timp rulează procesul botului (de la ultima repornire).\n"
                "**`/botinfo`** — servere, versiuni **discord.py** / Python, scurt **prezentare**."
            ),
        ),
        (
            "🏠 Server & utilizatori",
            (
                "**`/serverinfo`** — membri, canale, boost, verificare, **ID** server.\n"
                "**`/userinfo`** `[@membru]` — cont, intrare pe server, **roluri** (implicit: tu).\n"
                "**`/help`** `[categorie]` — **panoul** cu meniu; alege modulul din listă sau `!help economie`."
            ),
        ),
    ],
    "mod": [
        (
            "👤 Membri",
            (
                "**`/ban`** `@membru` `motiv` — **exclude** definitiv (necesită motiv).\n"
                "**`/unban`** `id_utilizator` — scoate banul după **ID**.\n"
                "**`/kick`** `@membru` `[motiv]` — dă afară din server.\n"
                "**`/mute`** `@membru` `minute` — **timeout** Discord.\n"
                "**`/unmute`** `@membru` — scoate timeout-ul.\n"
                "**`/warn`** `@membru` `motiv` — **avertisment** înregistrat.\n"
                "**`/warnings`** `@membru` — lista warn-urilor.\n"
                "**`/clearwarns`** `@membru` — șterge toate warn-urile."
            ),
        ),
        (
            "💬 Canal",
            (
                "**`/clear`** `număr` — șterge **mesaje** vechi (limită sigură, max. 200).\n"
                "**`/lock`** — blochează canalul (**@everyone** nu mai poate scrie).\n"
                "**`/unlock`** — deblochează.\n"
                "**`/slowmode`** `secunde` — interval între mesaje (**0** = oprit)."
            ),
        ),
        (
            "📋 Istoric",
            (
                "**`/case`** — ultimele **acțiuni de moderare** înregistrate de bot."
            ),
        ),
    ],
    "automod": [
        (
            "⚙️ Panou & praguri",
            (
                "**`/automod`** — **status** complet (module, praguri, whitelist).\n"
                "**`/automod toggle`** `modul` `on|off` — ex. `anti_link`, `enabled`, **`public_channel_notice`** (mesaj scurt în chat; implicit **off** = doar ștergere + log).\n"
                "**`/automod strikes`** `mute_la` `kick_la` `ban_la` `[minute]` — escaladare (implicit **3 / 5 / 7**) + durată timeout.\n"
                "**`/automod_prag`** / **`/automod_mute`** — alias legacy pentru prag timeout și minute."
            ),
        ),
        (
            "🛡️ Liste & filtre",
            (
                "**`/automod whitelist`** `add|remove` `channel|role` `ID sau mențiune` — **ignoră** AutoMod în canal/rol.\n"
                "**`/automod domain`** `add|remove` `domeniu` — **whitelist** pentru linkuri (fără listă = toate linkurile blocate).\n"
                "**`/automod inviteallow`** `add|remove` `text` — subșir permis în invitații.\n"
                "**`/blacklist_add`** `fraza` `[severitate]` — **low** (doar șterge) · **medium** · **high** (2 strike-uri) · **critical** (timeout dur).\n"
                "**`/blacklist_remove`** — scoți o frază."
            ),
        ),
    ],
    "ticket": [
        (
            "🎫 Panel & configurare",
            (
                "**`/ticketpanel`** — trimite **mesajul cu meniu** (tip ticket + buton deschidere); doar **admin**.\n"
                "**`/setticketstaff`** `[rol]` — rol dedicat staff ticket (opțional); fără rol revine la **Manage Channels**."
            ),
        ),
        (
            "✉️ În ticket",
            (
                "**`/close`** — cere **închidere**; apare confirmare în canal.\n"
                "**`!add`** / **`!remove`** `@membru` — prefix **doar în ticket**: adaugi sau scoți pe cineva (staff).\n"
                "**`/ticket_add`** / **`/ticket_remove`** — varianta **slash** (permisiuni canal).\n"
                "**`/ticket_claim`** — marchezi ticketul ca preluat de tine.\n"
                "**`/ticket_reopen`** `@membru` — deschizi ticket **nou** după unul închis (dacă există istoric)."
            ),
        ),
    ],
    "log": [
        (
            "📜 Canale log",
            (
                "**`/setlogchannel`** — canal pentru **evenimente generale**.\n"
                "**`/setmodlog`** — canal pentru **acțiuni de moderare**.\n"
                "**`/setticketlog`** — canal pentru **tickete** (deschis/închis/etc.).\n"
                "**`/setautomodlog`** — canal pentru evenimente **AutoMod**."
            ),
        ),
    ],
}

# Texte doar staff (fără câmpuri separate) — concatenate la level/info
HELP_STAFF_EXTRA_LEVEL = (
    "**`/setlevelrole`** `nivel` `@rol` — acordă un **rol** automat la nivelul setat.\n"
    "**`/setlevelreward`** `nivel` `sumă` — **bani** la urcarea nivelului.\n"
    "**`/xpconfig`** `secunde` — **pauză** minimă între mesaje care dau XP."
)

HELP_STAFF_EXTRA_INFO = "**`/setup`** — **ghid scurt** de configurare Aivor pe acest server (admin)."


def is_moderation_staff(member: discord.Member | None) -> bool:
    """Staff care poate vedea comenzi de moderare / configurare în help."""
    if member is None:
        return False
    p = member.guild_permissions
    return bool(
        p.administrator
        or p.manage_guild
        or p.manage_channels
        or p.manage_messages
        or p.moderate_members
        or p.kick_members
        or p.ban_members
    )


def category_embed_parts(key: str, *, is_staff: bool) -> tuple[str, list[tuple[str, str]]]:
    """
    Returnează (descriere, câmpuri).
    Dacă lista de câmpuri e goală, descrierea conține tot textul modulului.
    """
    if key in STAFF_KEYS and not is_staff:
        return (
            "🔒 *Această categorie este rezervată **staff**-ului cu permisiuni de moderare sau configurare.*",
            [],
        )

    intro = CATEGORY_INTRO.get(key, "")
    fields = list(CATEGORY_FIELDS.get(key, []))

    if key == "level" and is_staff:
        fields.append(
            (
                "🛠️ Configurare (staff)",
                HELP_STAFF_EXTRA_LEVEL,
            ),
        )

    if key == "info" and is_staff:
        fields.append(
            (
                "🛠️ Configurare (staff)",
                HELP_STAFF_EXTRA_INFO,
            ),
        )

    if not fields:
        return (intro + HELP_USAGE_NOTE, [])

    desc = f"_{intro}_" + HELP_USAGE_NOTE
    return (desc, fields)


# Compatibilitate: text simplu pentru validare sau alte apeluri vechi
def category_body(key: str, *, is_staff: bool) -> str:
    """Un singur string (fără structură pe câmpuri) — pentru compatibilitate."""
    desc, fields = category_embed_parts(key, is_staff=is_staff)
    if not fields:
        return desc
    lines = [desc.rstrip()]
    for name, val in fields:
        lines.append(f"\n**{name}**\n{val}")
    return "\n".join(lines)


# Compatibilitate: set de chei valide (conținutul nu mai e folosit)
HELP_SECTIONS: dict[str, str] = {k: "" for k in CATEGORY_ORDER}


def all_category_keys_for_user(is_staff: bool) -> tuple[str, ...]:
    if is_staff:
        return CATEGORY_ORDER
    return CATEGORY_ORDER_PUBLIC
