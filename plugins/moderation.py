import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import timedelta, datetime

WARNS_FILE = 'configs/warnings.json'

def load_warnings():
    if os.path.exists(WARNS_FILE):
        with open(WARNS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_warnings(data):
    os.makedirs('configs', exist_ok=True)
    with open(WARNS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("[Moderation] Plugin loaded")

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.describe(member="Member to ban", reason="Reason for ban", delete_days="Days of messages to delete (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: int = 0):
        try:
            delete_days = max(0, min(7, delete_days))
            await member.ban(reason=reason, delete_message_days=delete_days)
            embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
            embed.add_field(name="Member", value=f"{member} ({member.id})", inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="User ID to unban", reason="Reason for unban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(f"✅ Unbanned {user}", ephemeral=False)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout (mute) a member")
    @app_commands.describe(member="Member to timeout", minutes="Duration in minutes", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
        try:
            duration = timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            embed = discord.Embed(title="🔇 Member Timed Out", color=discord.Color.yellow())
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Duration", value=f"{minutes} min", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.describe(member="Member to remove timeout from")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.timeout(None)
            await interaction.response.send_message(f"✅ Timeout removed for {member.mention}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    warn_group = app_commands.Group(name="warn", description="Warning system")

    @warn_group.command(name="add", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_add(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        warnings = load_warnings()
        user_id = str(member.id)
        if user_id not in warnings:
            warnings[user_id] = []
        warnings[user_id].append({
            "reason": reason,
            "moderator": str(interaction.user.id),
            "timestamp": datetime.now().isoformat()
        })
        save_warnings(warnings)
        count = len(warnings[user_id])
        embed = discord.Embed(title="⚠️ Member Warned", color=discord.Color.gold())
        embed.add_field(name="Member", value=member.mention, inline=True)
        embed.add_field(name="Total Warnings", value=str(count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)

    @warn_group.command(name="list", description="List warnings for a member")
    @app_commands.describe(member="Member to check")
    async def warn_list(self, interaction: discord.Interaction, member: discord.Member):
        warnings = load_warnings()
        user_warnings = warnings.get(str(member.id), [])
        if not user_warnings:
            await interaction.response.send_message(f"{member.mention} has no warnings.", ephemeral=True)
            return
        lines = []
        for i, w in enumerate(user_warnings, 1):
            lines.append(f"{i}. {w['reason']} (by <@{w['moderator']}> on {w['timestamp'][:10]})")
        text = "\n".join(lines)
        await interaction.response.send_message(f"**Warnings for {member.mention}:**\n{text}", ephemeral=True)

    @warn_group.command(name="clear", description="Clear all warnings for a member")
    @app_commands.describe(member="Member to clear warnings for")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_clear(self, interaction: discord.Interaction, member: discord.Member):
        warnings = load_warnings()
        user_id = str(member.id)
        if user_id in warnings:
            del warnings[user_id]
            save_warnings(warnings)
            await interaction.response.send_message(f"✅ Cleared warnings for {member.mention}")
        else:
            await interaction.response.send_message(f"{member.mention} has no warnings.", ephemeral=True)

    @warn_group.command(name="remove", description="Remove a specific warning by index")
    @app_commands.describe(member="Member", index="Warning number to remove (from /warn list)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_remove(self, interaction: discord.Interaction, member: discord.Member, index: int):
        warnings = load_warnings()
        user_id = str(member.id)
        user_warnings = warnings.get(user_id, [])
        if 1 <= index <= len(user_warnings):
            removed = user_warnings.pop(index - 1)
            save_warnings(warnings)
            await interaction.response.send_message(f"✅ Removed warning: {removed['reason']}")
        else:
            await interaction.response.send_message("❌ Invalid warning index.", ephemeral=True)

    @app_commands.command(name="purge", description="Delete a number of messages")
    @app_commands.describe(amount="Number of messages to delete (max 100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        amount = max(1, min(100, amount))
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel slowmode")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        seconds = max(0, min(21600, seconds))
        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message("✅ Slowmode disabled.")
        else:
            await interaction.response.send_message(f"✅ Slowmode set to {seconds}s.")

    @app_commands.command(name="lock", description="Lock the current channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Channel locked.")

    @app_commands.command(name="unlock", description="Unlock the current channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Channel unlocked.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
    print("Moderation plugin loaded")
