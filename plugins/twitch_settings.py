import discord
from discord.ext import commands
from discord import app_commands
import json
import os

CONFIG_FILE = 'twitch_config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"ping_everyone": True}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

class TwitchSettings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("Twitch settings loaded", flush=True)

    twitch_group = app_commands.Group(name="twitch", description="Twitch settings")

    @twitch_group.command(name="ping", description="Toggle @everyone ping for streams")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(enabled="Enable or disable @everyone ping")
    async def toggle_ping(self, interaction: discord.Interaction, enabled: bool):
        config = load_config()
        config['ping_everyone'] = enabled
        save_config(config)
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ @everyone ping {status}", ephemeral=True)
        print(f"Twitch ping toggled: {enabled}", flush=True)

    @twitch_group.command(name="status", description="View Twitch settings")
    async def view_settings(self, interaction: discord.Interaction):
        config = load_config()
        ping_status = "✅ Enabled" if config.get('ping_everyone', True) else "❌ Disabled"
        
        embed = discord.Embed(title="Twitch Settings", color=discord.Color.purple())
        embed.add_field(name="@everyone Ping", value=ping_status, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchSettings(bot))
    print("Twitch settings plugin loaded", flush=True)
