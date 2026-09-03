import discord
from discord import app_commands
from discord.ext import commands
import json
import os

class BotSpeak(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_users = self.load_allowed_users()
        print(f"[BotSpeak] Loaded {len(self.allowed_users)} allowed users")

    def load_allowed_users(self):
        try:
            with open('configs/private.keys', 'r') as f:
                secrets = json.load(f)
            return [str(uid) for uid in secrets.get('bot_speak_users', [])]
        except Exception as e:
            print(f"[BotSpeak] Config error: {e}")
            return []

    def is_allowed(self, user_id: str):
        return user_id in self.allowed_users

    speak_group = app_commands.Group(name="speak", description="Make the bot speak")

    @speak_group.command(name="here", description="Make the bot send a message in this channel")
    @app_commands.describe(message="Message to send")
    async def speak_here(self, interaction: discord.Interaction, message: str):
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return
        await interaction.response.send_message("✅ Sent!", ephemeral=True)
        await interaction.channel.send(message)

    @speak_group.command(name="in", description="Make the bot send a message in a specific channel")
    @app_commands.describe(channel="Target channel", message="Message to send")
    async def speak_in(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return
        try:
            await channel.send(message)
            await interaction.response.send_message(f"✅ Sent to {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @speak_group.command(name="reply", description="Make the bot reply to a message")
    @app_commands.describe(message_id="Message ID to reply to", message="Message to send")
    async def speak_reply(self, interaction: discord.Interaction, message_id: str, message: str):
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
            return
        try:
            target = await interaction.channel.fetch_message(int(message_id))
            await target.reply(message)
            await interaction.response.send_message("✅ Replied!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BotSpeak(bot))
    print("BotSpeak plugin loaded")
