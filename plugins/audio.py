import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
import logging

AUDIO_DIR = 'configs/audio'
FFMPEG = '/usr/local/bin/ffmpeg'

# Temporary Discord voice diagnostics
logging.basicConfig(level=logging.INFO)
logging.getLogger('discord.voice_client').setLevel(logging.DEBUG)
logging.getLogger('discord.gateway').setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)

class Audio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.loop_file = None
        os.makedirs(AUDIO_DIR, exist_ok=True)
        print(f"[Audio] Plugin loaded")

    def load_allowed_users(self):
        try:
            with open('configs/private.keys', 'r') as f:
                secrets = json.load(f)
            return [str(uid) for uid in secrets.get('bot_speak_users', [])]
        except:
            return []

    def is_allowed(self, user_id: str):
        return user_id in self.load_allowed_users()

    def get_audio_files(self):
        return sorted([f for f in os.listdir(AUDIO_DIR)
                      if f.endswith(('.mp3', '.wav', '.ogg', '.opus', '.flac', '.m4a'))])

    audio_group = app_commands.Group(name="audio", description="Audio commands")

    @audio_group.command(name="play", description="Play an audio file in your voice channel")
    @app_commands.describe(filename="Audio file to play", loop="Loop the audio")
    async def play(self, interaction: discord.Interaction, filename: str, loop: bool = False):
        print(f"[Audio] play called by {interaction.user.id}", flush=True)
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Join a voice channel first!", ephemeral=True)
            return

        filepath = os.path.join(AUDIO_DIR, filename)
        if not os.path.exists(filepath):
            files = self.get_audio_files()
            file_list = "\n".join(files) if files else "No files available"
            await interaction.response.send_message(
                f"❌ File not found.\n```\n{file_list}\n```", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild.id
            voice_channel = interaction.user.voice.channel
            print(f"[Audio] Connecting to {voice_channel.name}", flush=True)
            
            # Use existing bot voice client if available
            vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
            if vc:
                if vc.channel.id != voice_channel.id:
                    await vc.move_to(voice_channel)
                if vc.is_playing():
                    vc.stop()
            else:
                print("[Audio] Attempting voice connection...", flush=True)
                try:
                    vc = await voice_channel.connect(timeout=30, reconnect=True)
                    print(
                        f"[Audio] connect() returned: "
                        f"connected={vc.is_connected()}, "
                        f"channel={vc.channel}",
                        flush=True
                    )

                    print(
                        f"[Audio] VoiceClient state: "
                        f"connection_state={getattr(vc, 'connection_state', None)}, "
                        f"ws={getattr(vc, 'ws', None)}, "
                        f"session_id={getattr(vc, 'session_id', None)}",
                        flush=True
                    )

                    if not vc.is_connected():
                        await interaction.followup.send(
                            "❌ Discord voice connection failed. "
                            "The bot could not establish the voice connection.",
                            ephemeral=True
                        )
                        print(
                            "[Audio] Voice connection failed - "
                            "will not attempt playback.",
                            flush=True
                        )
                        return

                except Exception as e:
                    import traceback
                    print(
                        f"[Audio] VOICE CONNECT FAILED: "
                        f"{type(e).__name__}: {e}",
                        flush=True
                    )
                    print(traceback.format_exc(), flush=True)
                    raise

            self.voice_clients[guild_id] = vc

            print(f"[Audio] Connected: {vc.is_connected()}", flush=True)

            # Give Discord's voice connection a moment to fully establish.
            await asyncio.sleep(2)

            print(
                f"[Audio] Voice state after 2s: "
                f"connected={vc.is_connected()}, "
                f"channel={vc.channel}, "
                f"playing={vc.is_playing()}",
                flush=True
            )
            self.loop_file = filepath if loop else None

            def after_play(error):
                if error:
                    print(f"[Audio] Error: {error}", flush=True)
                else:
                    print(f"[Audio] Done: {filename}", flush=True)
                if self.loop_file and guild_id in self.voice_clients:
                    vc2 = self.voice_clients[guild_id]
                    if vc2.is_connected():
                        src = discord.FFmpegPCMAudio(self.loop_file, executable=FFMPEG)
                        vc2.play(src, after=after_play)

            print(f"[Audio] Starting {filepath}", flush=True)
            source = discord.FFmpegPCMAudio(filepath, executable=FFMPEG)
            vc.play(source, after=after_play)
            print(f"[Audio] Playing: {vc.is_playing()}", flush=True)
            loop_text = " 🔁" if loop else ""
            await interaction.followup.send(f"▶️ Playing: **{filename}**{loop_text}", ephemeral=True)
        except Exception as e:
            import traceback
            print(f"[Audio] Error: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @audio_group.command(name="stop", description="Stop audio and leave voice channel")
    async def stop(self, interaction: discord.Interaction):
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        self.loop_file = None
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.is_playing():
                vc.stop()
            await vc.disconnect()
            del self.voice_clients[guild_id]
            await interaction.response.send_message("⏹️ Stopped.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Not in a voice channel.", ephemeral=True)

    @audio_group.command(name="list", description="List available audio files")
    async def list_files(self, interaction: discord.Interaction):
        files = self.get_audio_files()
        if not files:
            await interaction.response.send_message("No audio files in configs/audio/", ephemeral=True)
            return
        file_list = "\n".join([f"• {f}" for f in files])
        await interaction.response.send_message(f"**Audio files:**\n{file_list}", ephemeral=True)

    @audio_group.command(name="upload", description="Upload an audio file")
    @app_commands.describe(file="Audio file to upload")
    async def upload(self, interaction: discord.Interaction, file: discord.Attachment):
        if not self.is_allowed(str(interaction.user.id)):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return

        if not any(file.filename.endswith(ext) for ext in ('.mp3', '.wav', '.ogg', '.opus', '.flac', '.m4a')):
            await interaction.response.send_message("❌ Only audio files allowed.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        filepath = os.path.join(AUDIO_DIR, file.filename)
        await file.save(filepath)
        await interaction.followup.send(f"✅ Uploaded: **{file.filename}**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Audio(bot))
    print("Audio plugin loaded")
