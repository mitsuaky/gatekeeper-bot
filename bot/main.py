import asyncio

import asyncpg
import discord
from aiohttp import ClientSession
from core.config import Config
from core.logging import setup_logger
from core.database import PostgresPool
from discord.ext import commands
from helpers.context import GatekeeperContext
from loguru import logger
from core.config import config


class GatekeeperBot(commands.Bot):
    def __init__(
        self,
        config: Config,
        web_client: ClientSession,
        pool: asyncpg.Pool,
    ):
        self.config = config
        self.web_client = web_client
        self.pool = pool

        allowed_mentions = discord.AllowedMentions(
            roles=False,
            everyone=False,
            users=True,
        )
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(self.config.bot.prefix),
            pm_help=None,
            chunk_guilds_at_startup=False,
            allowed_mentions=allowed_mentions,
            intents=intents,
            enable_debug_events=True,
        )

    async def get_or_fetch_guild(self, guild_id: int) -> discord.Guild | None:
        """Looks up a guild in cache or fetches if not found.

        Args:
            guild_id (int): The guild ID to search for.

        Returns:
            Optional[Guild]: The guild or None if not found.
        """
        guild = self.get_guild(guild_id)
        if guild is not None:
            return guild

        if not self.is_ws_ratelimited():
            try:
                guild = await self.fetch_guild(guild_id)
            except discord.HTTPException:
                return None
            else:
                return guild

    async def get_or_fetch_member(self, guild: discord.Guild | int, member_id: int) -> discord.Member | None:
        """Looks up a member in cache or fetches if not found.

        Args:
            guild (discord.Guild | int): The guild to search for the member in.
            member_id (int): The member ID to search for.

        """
        # Tries to get the guild if only guild id was passed
        if isinstance(guild, int):
            _guild = await self.get_or_fetch_guild(guild)
            if _guild is None:
                return None
            guild = _guild

        member = guild.get_member(member_id)
        if member is not None:
            return member

        if self.is_ws_ratelimited():
            try:
                # Get member from api
                member = await guild.fetch_member(member_id)
            except discord.HTTPException:
                return None
            else:
                return member
        # Get member from websocket
        members = await guild.query_members(limit=1, user_ids=[member_id], cache=True)
        if not members:
            return None
        return members[0]

    async def setup_hook(self):
        initial_extensions = self.config.bot.initial_cogs
        if initial_extensions:
            logger.info("Loading initial extensions.")
            for extension in initial_extensions:
                try:
                    logger.info(f"Loading extension {extension}")
                    await self.load_extension(extension)
                except Exception:
                    logger.exception(f"Error while loading extension {extension}")

    async def on_ready(self):
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()
            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")  # type: ignore

    async def on_message(self, message: discord.Message) -> None:
        ctx = await self.get_context(message, cls=GatekeeperContext)
        await self.invoke(ctx)


async def main():
    setup_logger()  # intercept logging and send to loguru

    async with ClientSession() as aio_client:
        async with PostgresPool(config.db.dsn) as pool:
            async with GatekeeperBot(config, aio_client, pool) as bot:
                # always load jishaku to have at least basic remote control/debug
                await bot.load_extension("jishaku")
                await bot.start(config.bot.token)


if __name__ == "__main__":
    asyncio.run(main())
