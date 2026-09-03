import discord
from discord import app_commands
from discord.ext import commands
import json
import os

IGN_FILE = 'configs/user_igns.json'

def load_igns():
    if os.path.exists(IGN_FILE):
        with open(IGN_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_igns(data):
    os.makedirs('configs', exist_ok=True)
    with open(IGN_FILE, 'w') as f:
        json.dump(data, f, indent=2)

class IGNAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ign_admin_group = app_commands.Group(name="ign_admin", description="Admin IGN management")

    @ign_admin_group.command(name="set", description="Set IGN for a user")
    @app_commands.describe(user="Discord user", ingame_name="Their in-game name")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_ign(self, interaction: discord.Interaction, user: discord.Member, ingame_name: str):
        try:
            igns = load_igns()
            igns[str(user.id)] = ingame_name
            save_igns(igns)
            await interaction.response.send_message(
                f"✅ Set IGN for {user.display_name} to **{ingame_name}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @ign_admin_group.command(name="get", description="Get IGN for a user")
    @app_commands.describe(user="Discord user")
    @app_commands.checks.has_permissions(administrator=True)
    async def get_ign(self, interaction: discord.Interaction, user: discord.Member):
        igns = load_igns()
        ign = igns.get(str(user.id))
        if ign:
            await interaction.response.send_message(
                f"**{user.display_name}** IGN: **{ign}**", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"**{user.display_name}** has no IGN set", ephemeral=True)

    @ign_admin_group.command(name="remove", description="Remove IGN for a user")
    @app_commands.describe(user="Discord user")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_ign(self, interaction: discord.Interaction, user: discord.Member):
        igns = load_igns()
        if str(user.id) in igns:
            del igns[str(user.id)]
            save_igns(igns)
            await interaction.response.send_message(
                f"✅ Removed IGN for {user.display_name}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"**{user.display_name}** has no IGN set", ephemeral=True)

    @ign_admin_group.command(name="list", description="List all IGNs")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_igns(self, interaction: discord.Interaction):
        igns = load_igns()
        if not igns:
            await interaction.response.send_message("No IGNs set", ephemeral=True)
            return

        lines = []
        for user_id, ign in igns.items():
            member = interaction.guild.get_member(int(user_id))
            name = member.display_name if member else f"Unknown ({user_id})"
            lines.append(f"• **{name}**: {ign}")

        text = "\n".join(lines)
        await interaction.response.send_message(f"**IGN List:**\n{text}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IGNAdmin(bot))
    print("IGN Admin plugin loaded")
