import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import json
import time

STATE_FILE = "configs/twitch_streams.json"

def load_secrets():
    with open('configs/private.keys', 'r') as f:
        return json.load(f)

class TwitchNotifier(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        secrets = load_secrets()
        self.client_id = secrets.get("twitch_client_id")
        self.client_secret = secrets.get("twitch_client_secret")
        self.access_token = None
        self.token_expires_at = 0
        self.monitored_streams = self.load_data()
        self.session = None
        self.announced = set()  # Track announced streams
        print(f"Twitch plugin initialized", flush=True)

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.check_twitch.start()
        print("Twitch notifier cog loaded", flush=True)

    async def cog_unload(self):
        self.check_twitch.cancel()
        if self.session:
            await self.session.close()

    def load_data(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_data(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.monitored_streams, f, indent=2)

    async def get_access_token(self):
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        if not self.client_id or not self.client_secret:
            print("[Twitch] Missing credentials", flush=True)
            return None

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        try:
            async with self.session.post(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.access_token = data["access_token"]
                    self.token_expires_at = time.time() + data["expires_in"] - 60
                    return self.access_token
        except Exception as e:
            print(f"[Twitch] Error getting token: {e}", flush=True)
        return None

    async def get_stream_data(self, streamer_name: str):
        token = await self.get_access_token()
        if not token:
            return None

        url = f"https://api.twitch.tv/helix/streams?user_login={streamer_name.lower()}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}"
        }

        try:
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    streams = data.get("data", [])
                    return streams[0] if streams else None
        except Exception as e:
            print(f"[Twitch] Error: {e}", flush=True)
        return None

    @tasks.loop(minutes=2.0)
    async def check_twitch(self):
        if not self.client_id or not self.client_secret:
            return

        for streamer, info in list(self.monitored_streams.items()):
            stream_data = await self.get_stream_data(streamer)
            is_live_now = stream_data is not None

            if is_live_now:
                # Announce only once per stream
                if streamer not in self.announced:
                    self.announced.add(streamer)
                    channel = self.bot.get_channel(info["channel_id"])
                    if channel:
                        await self.announce_stream(channel, stream_data, streamer)
            else:
                # Remove from announced set when they go offline
                self.announced.discard(streamer)

    async def announce_stream(self, channel, stream_data, streamer):
        """Announce stream to Discord"""
        try:
            title = stream_data.get("title", "No Title")
            game = stream_data.get("game_name", "Unknown Game")
            user_name = stream_data.get("user_name", streamer)
            thumbnail = stream_data.get("thumbnail_url", "").format(width=1280, height=720)

            embed = discord.Embed(
                title=f"🔴 {user_name} is LIVE on Twitch!",
                url=f"https://twitch.tv/{streamer}",
                color=discord.Color.purple()
            )
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Category", value=game, inline=True)
            embed.set_image(url=thumbnail)

            ping = "@everyone " if self.monitored_streams[streamer].get('ping_enabled', True) else ""
            await channel.send(content=f"{ping}**{user_name}** went live!", embed=embed)
            print(f"[Twitch] Announced {streamer}", flush=True)
        except Exception as e:
            print(f"[Twitch] Announce error: {e}", flush=True)

    @check_twitch.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="twitch_add", description="Add streamer")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(streamer="Streamer name", ping="Enable @everyone ping")
    async def add_streamer(self, interaction: discord.Interaction, streamer: str, ping: bool = True):
        await interaction.response.defer(thinking=True)
        
        streamer_clean = streamer.lower().strip()
        stream_info = await self.get_stream_data(streamer_clean)

        self.monitored_streams[streamer_clean] = {
            "channel_id": interaction.channel_id,
            "ping_enabled": ping
        }
        self.save_data()

        # If they're already live, announce immediately
        if stream_info:
            self.announced.add(streamer_clean)
            channel = interaction.channel
            await self.announce_stream(channel, stream_info, streamer_clean)
            await interaction.followup.send(f"✅ Watching **{streamer_clean}** (ping: {'enabled' if ping else 'disabled'}) - LIVE now!")
        else:
            ping_status = "enabled" if ping else "disabled"
            await interaction.followup.send(f"✅ Watching **{streamer_clean}** (ping: {ping_status})")

    @app_commands.command(name="twitch_remove", description="Remove streamer")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def remove_streamer(self, interaction: discord.Interaction, streamer: str):
        streamer_clean = streamer.lower().strip()

        if streamer_clean in self.monitored_streams:
            del self.monitored_streams[streamer_clean]
            self.announced.discard(streamer_clean)
            self.save_data()
            await interaction.response.send_message(f"🗑 Stopped tracking **{streamer_clean}**")

    @app_commands.command(name="twitch_toggle", description="Toggle ping")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def toggle_ping(self, interaction: discord.Interaction, streamer: str, enabled: bool):
        streamer_clean = streamer.lower().strip()

        if streamer_clean not in self.monitored_streams:
            await interaction.response.send_message(f"❌ Not tracked", ephemeral=True)
            return

        self.monitored_streams[streamer_clean]['ping_enabled'] = enabled
        self.save_data()

        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Ping {status} for **{streamer_clean}**", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchNotifier(bot))
    print("Twitch notifier plugin loaded", flush=True)
