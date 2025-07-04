#!/usr/bin/env python3

# Auto-instalación de dependencias si no están disponibles
try:
    import discord
except ImportError:
    print("📦 discord.py no encontrado. Instalando automáticamente...")
    import subprocess
    import sys

    # Intentar instalar discord.py
    install_methods = [
        [sys.executable, "-m", "pip", "install", "discord.py"],
        [sys.executable, "-m", "pip", "install", "--user", "discord.py"],
        ["pip3", "install", "discord.py"],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "discord.py"],
    ]

    installed = False
    for method in install_methods:
        try:
            result = subprocess.run(method, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                print(f"✅ discord.py instalado con: {' '.join(method)}")
                installed = True
                break
        except:
            continue

    if not installed:
        print("❌ No se pudo instalar discord.py automáticamente")
        print("🔧 Instala manualmente con: pip install discord.py")
        exit(1)

    # Intentar importar después de la instalación
    try:
        import discord
        print("✅ discord.py importado correctamente")
    except ImportError:
        print("❌ Error: discord.py instalado pero no se puede importar")
        print("🔧 Reinicia el bot o instala manualmente")
        exit(1)

from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import asyncio
import pytz
from zoneinfo import ZoneInfo

from time_tracker import TimeTracker

# Configuración del bot
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
time_tracker = TimeTracker()

# Rol especial para tiempo ilimitado (se carga desde config.json)
UNLIMITED_TIME_ROLE_ID = None

# Variables para IDs de canales de notificación
NOTIFICATION_CHANNEL_ID = 1385005232685318281
PAUSE_NOTIFICATION_CHANNEL_ID = 1385005232685318282
CANCELLATION_NOTIFICATION_CHANNEL_ID = 1385005232685318284
MOVEMENTS_CHANNEL_ID = 1385005232685318277  # Canal para notificaciones de movimientos

# Configuración de zona horaria Chile
CHILE_TZ = ZoneInfo("America/Santiago")
START_TIME_HOUR = 14  # 1 PM
START_TIME_MINUTE = 38  # 13 minutos

# Task para verificar hora de inicio
auto_start_task = None

# Cargar configuración completa desde config.json
config = {}
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    UNLIMITED_TIME_ROLE_ID = config.get('unlimited_time_role_id')
    if UNLIMITED_TIME_ROLE_ID:
        print(f"✅ Rol de tiempo ilimitado cargado desde config: ID {UNLIMITED_TIME_ROLE_ID}")

    # Cargar IDs de canales de notificación desde config
    notification_channels = config.get('notification_channels', {})
    NOTIFICATION_CHANNEL_ID = notification_channels.get('milestones', 1385005232685318281)
    PAUSE_NOTIFICATION_CHANNEL_ID = notification_channels.get('pauses', 1387194620961751070)
    CANCELLATION_NOTIFICATION_CHANNEL_ID = notification_channels.get('cancellations', 1387194756211146792)

    print(f"✅ Canales de notificación cargados:")
    print(f"  - Milestones: {NOTIFICATION_CHANNEL_ID}")
    print(f"  - Pausas: {PAUSE_NOTIFICATION_CHANNEL_ID}")
    print(f"  - Cancelaciones: {CANCELLATION_NOTIFICATION_CHANNEL_ID}")

except Exception as e:
    print(f"⚠️ No se pudo cargar configuración: {e}")
    config = {}
    # Valores por defecto si no se puede cargar config
    NOTIFICATION_CHANNEL_ID = 1387194559318196416
    PAUSE_NOTIFICATION_CHANNEL_ID = 1387194620961751070
    CANCELLATION_NOTIFICATION_CHANNEL_ID = 1387194756211146792

# Task para verificar milestones periódicamente
milestone_check_task = None

@bot.event
async def on_ready():
    print(f'{bot.user} se ha conectado a Discord!')

    # Verificar que el canal de notificaciones existe
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if channel:
        if hasattr(channel, 'name'):
            print(f'Canal de notificaciones encontrado: {channel.name} (ID: {channel.id})')
        else:
            print(f'Canal de notificaciones encontrado (ID: {channel.id})')
    else:
        print(f'⚠️ Canal de notificaciones no encontrado con ID: {NOTIFICATION_CHANNEL_ID}')

    try:
        # Sincronización global primero
        print("🔄 Sincronizando comandos globalmente...")
        synced_global = await bot.tree.sync()
        print(f'✅ Sincronizados {len(synced_global)} comando(s) slash globalmente')

        # Sincronización específica del guild si hay guilds
        if bot.guilds:
            for guild in bot.guilds:
                try:
                    print(f"🔄 Sincronizando comandos en {guild.name} (ID: {guild.id})...")
                    synced_guild = await bot.tree.sync(guild=guild)
                    print(f'✅ Sincronizados {len(synced_guild)} comando(s) en {guild.name}')
                except Exception as guild_error:
                    print(f'⚠️ Error sincronizando en {guild.name}: {guild_error}')

        # Listar todos los comandos registrados
        commands = [cmd.name for cmd in bot.tree.get_commands()]
        print(f'📋 Comandos registrados ({len(commands)}): {", ".join(commands)}')

        print("💡 Si los comandos no aparecen inmediatamente:")
        print("   • Espera 1-5 minutos para que Discord los propague")
        print("   • Reinicia tu cliente de Discord")
        print("   • Verifica que el bot tenga permisos de 'applications.commands'")

    except Exception as e:
        print(f'❌ Error al sincronizar comandos: {e}')

def is_admin():
    """Decorator para verificar si el usuario tiene permisos"""
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            if not hasattr(interaction, 'guild') or not interaction.guild:
                print(f"❌ Usuario {interaction.user.display_name} sin guild")
                return False

            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                print(f"❌ No se pudo obtener member para {interaction.user.display_name}")
                return False

            if member.bot:
                print(f"❌ {interaction.user.display_name} es un bot")
                return False

            print(f"✅ {interaction.user.display_name} puede usar comandos (acceso abierto)")
            return True

        except Exception as e:
            print(f"Error en verificación de permisos para {interaction.user.display_name}: {e}")
            return False

    return discord.app_commands.check(predicate)

def load_config():
    """Cargar configuración desde config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return {}

def has_unlimited_time_role(member: discord.Member) -> bool:
    """Verificar si el usuario tiene el rol de tiempo ilimitado"""
    if UNLIMITED_TIME_ROLE_ID is None:
        return False

    for role in member.roles:
        if role.id == UNLIMITED_TIME_ROLE_ID:
            return True
    return False

def calculate_credits(total_seconds: float, role_type: str = "normal") -> int:
    """Calcular créditos basado en el tiempo total y el rol - SISTEMA SIMPLIFICADO"""
    try:
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            return 0

        total_hours = total_seconds / 3600

        if role_type == "gold":
            if total_hours >= 2.0:
                return 10  # 2 horas = 10 créditos
            elif total_hours >= 1.0:
                return 5   # 1 hora = 5 créditos
            else:
                return 0   # Menos de 1 hora = 0 créditos
        else:
            # Usuarios sin rol específico (normal)
            if total_hours >= 1.0:
                return 3   # 1 hora = 3 créditos
            else:
                return 0   # Menos de 1 hora = 0 créditos

    except Exception as e:
        print(f"Error calculando créditos: {e}")
        return 0

def get_user_role_type(member: discord.Member) -> str:
    """Determina el tipo de rol del usuario - SISTEMA SIMPLIFICADO"""
    if not member:
        return "normal"

    # Solo verificar Gold
    for role in member.roles:
        role_name_lower = role.name.lower()
        if "gold" in role_name_lower:
            return "gold"

    return "normal"

def get_role_info(member: discord.Member) -> str:
    """Obtiene la información del rol de mayor jerarquía del usuario"""
    if member and member.roles:
        user_roles = [role for role in member.roles if role.name != "@everyone"]
        if user_roles:
            highest_role = max(user_roles, key=lambda role: role.position)
            return f" ({highest_role.name})"
    return ""

@bot.tree.command(name="iniciar_tiempo", description="Iniciar el seguimiento de tiempo para un usuario")
@discord.app_commands.describe(usuario="El usuario para quien iniciar el seguimiento de tiempo")
@is_admin()
async def iniciar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    if usuario.bot:
        await interaction.response.send_message("❌ No se puede rastrear el tiempo de bots.")
        return

    # Verificar si el usuario tiene el rol de tiempo ilimitado
    has_unlimited_role = has_unlimited_time_role(usuario)

    # Verificar límites según el rol del usuario
    total_time = time_tracker.get_total_time(usuario.id)
    total_hours = total_time / 3600

    # Verificar el tipo de rol del usuario
    role_type = get_user_role_type(usuario)

    if role_type == "gold":
        # Usuarios con rol Gold: límite de 2 horas
        if total_hours >= 2.0:
            await interaction.response.send_message(
                f"❌ {usuario.mention} ya ha alcanzado el límite máximo de 2 horas."
            )
            return
    elif not has_unlimited_role:
        # Usuarios sin rol específico: límite de 1 hora
        if total_hours >= 1.0:
            await interaction.response.send_message(
                f"❌ {usuario.mention} ya ha alcanzado el límite máximo de 1 hora."
            )
            return
    else:
        # Usuarios con rol especial: límite de 4 horas
        if total_hours >= 4.0:
            await interaction.response.send_message(
                f"❌ {usuario.mention} ya ha alcanzado el límite máximo de 4 horas."
            )
            return

    # Verificar si el usuario tiene tiempo pausado
    user_data = time_tracker.get_user_data(usuario.id)
    if user_data and user_data.get('is_paused', False):
        await interaction.response.send_message(
            f"⚠️ {usuario.mention} tiene tiempo pausado. Usa `/despausar_tiempo` para continuar el tiempo."
        )
        return

    # Obtener hora actual en Chile
    chile_now = datetime.now(CHILE_TZ)
    current_hour = chile_now.hour
    current_minute = chile_now.minute

    # Verificar si es antes de la hora configurada (13:31)
    is_before_start_time = (current_hour < START_TIME_HOUR) or (current_hour == START_TIME_HOUR and current_minute < START_TIME_MINUTE)
    
    if is_before_start_time:
        # Pre-registro: registrar usuario pero no iniciar cronómetro
        success = time_tracker.pre_register_user(usuario.id, usuario.display_name)
        if success:
            # Guardar quién hizo el pre-registro
            time_tracker.set_pre_register_initiator(usuario.id, interaction.user.id, interaction.user.display_name)
            await interaction.response.send_message(
                f"📝 El tiempo de {usuario.mention} ha sido registrado por {interaction.user.mention}"
            )
        else:
            await interaction.response.send_message(f"⚠️ {usuario.mention} ya está pre-registrado o activo")
    else:
        # Hora configurada o después: iniciar normalmente
        success = time_tracker.start_tracking(usuario.id, usuario.display_name)
        if success:
            await interaction.response.send_message(f"⏰ El tiempo de {usuario.mention} ha sido iniciado por {interaction.user.mention}")
        else:
            await interaction.response.send_message(f"⚠️ El tiempo de {usuario.mention} ya está activo")

@bot.tree.command(name="pausar_tiempo", description="Pausar el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario para quien pausar el tiempo")
@is_admin()
async def pausar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    user_data = time_tracker.get_user_data(usuario.id)
    total_time_before = time_tracker.get_total_time(usuario.id)

    success = time_tracker.pause_tracking(usuario.id)
    if success:
        total_time_after = time_tracker.get_total_time(usuario.id)
        session_time = total_time_after - total_time_before
        pause_count = time_tracker.get_pause_count(usuario.id)
        formatted_total_time = time_tracker.format_time_human(total_time_after)
        formatted_session_time = time_tracker.format_time_human(session_time) if session_time > 0 else "0 Segundos"

        if pause_count >= 3:
            time_tracker.cancel_user_tracking(usuario.id)
            await interaction.response.send_message(
                f"⏸️ El tiempo de {usuario.mention} ha sido pausado\n"
                f"🚫 **{usuario.mention} lleva {pause_count} pausas - Tiempo cancelado automáticamente por exceder el límite**"
            )
            await send_auto_cancellation_notification(usuario.display_name, formatted_total_time, interaction.user.mention, pause_count)
        else:
            await interaction.response.send_message(f"⏸️ El tiempo de {usuario.mention} ha sido pausado")
            await send_pause_notification(usuario.display_name, total_time_after, interaction.user.mention, formatted_session_time, pause_count)
    else:
        await interaction.response.send_message(f"⚠️ No hay tiempo activo para {usuario.mention}")

@bot.tree.command(name="despausar_tiempo", description="Despausar el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario para quien despausar el tiempo")
@is_admin()
async def despausar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    paused_duration = time_tracker.get_paused_duration(usuario.id)
    success = time_tracker.resume_tracking(usuario.id)
    if success:
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_paused_duration = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"
        await interaction.response.send_message(
            f"▶️ El tiempo de {usuario.mention} ha sido despausado\n"
            f"**Tiempo pausado:** {formatted_paused_duration}\n"
            f"**Despausado por:** {interaction.user.mention}"
        )
        await send_unpause_notification(usuario.display_name, total_time, interaction.user.mention, formatted_paused_duration)
    else:
        await interaction.response.send_message(f"⚠️ No se puede despausar - {usuario.mention} no tiene tiempo pausado")

@bot.tree.command(name="sumar_minutos", description="Sumar minutos al tiempo de un usuario")
@discord.app_commands.describe(
    usuario="El usuario al que sumar tiempo",
    minutos="Cantidad de minutos a sumar"
)
@is_admin()
async def sumar_minutos(interaction: discord.Interaction, usuario: discord.Member, minutos: int):
    if minutos <= 0:
        await interaction.response.send_message("❌ La cantidad de minutos debe ser positiva")
        return

    success = time_tracker.add_minutes(usuario.id, usuario.display_name, minutos)
    if success:
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_time = time_tracker.format_time_human(total_time)
        await interaction.response.send_message(
            f"✅ Sumados {minutos} minutos a {usuario.mention} por {interaction.user.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
        await check_time_milestone(usuario.id, usuario.display_name)
    else:
        await interaction.response.send_message(f"❌ Error al sumar tiempo para {usuario.mention}")

@bot.tree.command(name="restar_minutos", description="Restar minutos del tiempo de un usuario")
@discord.app_commands.describe(
    usuario="El usuario al que restar tiempo",
    minutos="Cantidad de minutos a restar"
)
@is_admin()
async def restar_minutos(interaction: discord.Interaction, usuario: discord.Member, minutos: int):
    if minutos <= 0:
        await interaction.response.send_message("❌ La cantidad de minutos debe ser positiva")
        return

    success = time_tracker.subtract_minutes(usuario.id, minutos)
    if success:
        total_time = time_tracker.get_total_time(usuario.id)
        formatted_time = time_tracker.format_time_human(total_time)
        await interaction.response.send_message(
            f"➖ Restados {minutos} minutos de {usuario.mention} por {interaction.user.mention}\n"
            f"⏱️ Tiempo total: {formatted_time}"
        )
    else:
        await interaction.response.send_message(f"❌ Error al restar tiempo para {usuario.mention}")

# Clase para manejar la paginación
class TimesView(discord.ui.View):
    def __init__(self, sorted_users, guild, max_per_page=25):
        super().__init__(timeout=300)
        self.sorted_users = sorted_users
        self.guild = guild
        self.max_per_page = max_per_page
        self.current_page = 0
        self.total_pages = (len(sorted_users) + max_per_page - 1) // max_per_page

        if self.total_pages <= 1:
            self.clear_items()

    def get_embed(self):
        """Crear embed para la página actual"""
        start_idx = self.current_page * self.max_per_page
        end_idx = min(start_idx + self.max_per_page, len(self.sorted_users))
        current_users = self.sorted_users[start_idx:end_idx]
        user_list = []

        for _, user_id, data in current_users:
            try:
                user_id_int = int(user_id)
                member = self.guild.get_member(user_id_int) if self.guild else None

                if member:
                    user_mention = member.mention
                    role_type = get_user_role_type(member)
                else:
                    user_name = data.get('name', f'Usuario {user_id}')
                    user_mention = f"**{user_name}** `(ID: {user_id})`"
                    role_type = "normal"

                total_time = time_tracker.get_total_time(user_id_int)
                formatted_time = time_tracker.format_time_human(total_time)

                status = "🔴 Inactivo"
                if data.get('is_active', False):
                    status = "🟢 Activo"
                elif data.get('is_paused', False):
                    total_hours = total_time / 3600
                    has_special_role = has_unlimited_time_role(member) if member else False
                    role_type = get_user_role_type(member) if member else "normal"

                    # Verificar límites según el tipo de rol
                    if (data.get("milestone_completed", False) or 
                        (has_special_role and total_hours >= 4.0) or 
                        (role_type == "gold" and total_hours >= 2.0) or
                        (role_type == "normal" and total_hours >= 1.0)):
                        status = "✅ Terminado"
                    else:
                        status = "⏸️ Pausado"

                credits = calculate_credits(total_time, role_type)
                credit_info = f" 💰 {credits} Créditos" if credits > 0 else ""
                role_info = get_role_info(member) if member else ""
                user_list.append(f"📌 {user_mention}{role_info} - ⏱️ {formatted_time}{credit_info} {status}")

            except Exception as e:
                print(f"Error procesando usuario {user_id}: {e}")
                continue

        embed = discord.Embed(
            title="⏰ Tiempos Registrados",
            description="\n".join(user_list) if user_list else "No hay usuarios en esta página",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.set_footer(text=f"Página {self.current_page + 1}/{self.total_pages} • Total: {len(self.sorted_users)} usuarios")
        return embed

    @discord.ui.button(label='◀️ Anterior', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='▶️ Siguiente', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self.update_buttons()
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='📄 Ir a página', style=discord.ButtonStyle.primary)
    async def go_to_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PageModal(self)
        await interaction.response.send_modal(modal)

    def update_buttons(self):
        """Actualizar estado de los botones según la página actual"""
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page >= self.total_pages - 1)

    async def on_timeout(self):
        """Deshabilitar botones cuando expire el timeout"""
        for item in self.children:
            item.disabled = True

class PageModal(discord.ui.Modal, title='Ir a Página'):
    def __init__(self, view):
        super().__init__()
        self.view = view

    page_number = discord.ui.TextInput(
        label='Número de página',
        placeholder=f'Ingresa un número entre 1 y {999}',
        required=True,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value)
            if 1 <= page <= self.view.total_pages:
                self.view.current_page = page - 1
                self.view.update_buttons()
                embed = self.view.get_embed()
                await interaction.response.edit_message(embed=embed, view=self.view)
            else:
                await interaction.response.send_message(
                    f"❌ Página inválida. Debe estar entre 1 y {self.view.total_pages}", 
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("❌ Por favor ingresa un número válido", ephemeral=True)

@bot.tree.command(name="ver_tiempos", description="Ver todos los tiempos registrados")
@is_admin()
async def ver_tiempos(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=False)
    except Exception as e:
        print(f"Error al defer la interacción: {e}")
        try:
            await interaction.response.send_message("🔄 Procesando tiempos...", ephemeral=False)
        except Exception:
            return

    try:
        tracked_users = await asyncio.wait_for(
            asyncio.to_thread(time_tracker.get_all_tracked_users),
            timeout=5.0
        )

        if not tracked_users:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("📊 No hay usuarios con tiempo registrado", ephemeral=False)
                else:
                    await interaction.followup.send("📊 No hay usuarios con tiempo registrado")
            except Exception as e:
                print(f"Error enviando mensaje de sin usuarios: {e}")
            return

        # Ordenar usuarios alfabéticamente por nombre
        sorted_users = []
        for user_id, data in tracked_users.items():
            user_name = data.get('name', f'Usuario {user_id}')
            sorted_users.append((user_name.lower(), user_id, data))

        sorted_users.sort(key=lambda x: x[0])

        # Si hay pocos usuarios, usar el método simple (sin paginación)
        if len(sorted_users) <= 25:
            user_list = []
            for _, user_id, data in sorted_users:
                try:
                    user_id_int = int(user_id)
                    member = interaction.guild.get_member(user_id_int) if interaction.guild else None

                    if member:
                        user_mention = member.mention
                        role_type = get_user_role_type(member)
                    else:
                        user_name = data.get('name', f'Usuario {user_id}')
                        user_mention = f"**{user_name}** `(ID: {user_id})`"
                        role_type = "normal"

                    total_time = time_tracker.get_total_time(user_id_int)
                    formatted_time = time_tracker.format_time_human(total_time)

                    status = "🔴 Inactivo"
                    if data.get('is_active', False):
                        status = "🟢 Activo"
                    elif data.get('is_paused', False):
                        total_hours = total_time / 3600
                        has_special_role = has_unlimited_time_role(member) if member else False
                        role_type = get_user_role_type(member) if member else "normal"

                        # Verificar límites según el tipo de rol
                        if (data.get("milestone_completed", False) or 
                            (has_special_role and total_hours >= 4.0) or 
                            (role_type == "gold" and total_hours >= 2.0) or
                            (role_type == "normal" and total_hours >= 1.0)):
                            status = "✅ Terminado"
                        else:
                            status = "⏸️ Pausado"

                    credits = calculate_credits(total_time, role_type)
                    credit_info = f" 💰 {credits} Créditos" if credits > 0 else ""
                    role_info = get_role_info(member) if member else ""

                    user_list.append(f"📌 {user_mention}{role_info} - ⏱️ {formatted_time}{credit_info} {status}")

                except Exception as e:
                    print(f"Error procesando usuario {user_id}: {e}")
                    continue

            if not user_list:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ Error al procesar usuarios registrados", ephemeral=False)
                    else:
                        await interaction.followup.send("❌ Error al procesar usuarios registrados")
                except Exception as e:
                    print(f"Error enviando mensaje de error: {e}")
                return

            # Embed simple sin paginación
            embed = discord.Embed(
                title="⏰ Tiempos Registrados",
                description="\n".join(user_list),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Total: {len(user_list)} usuarios")

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.followup.send(embed=embed)
        else:
            # Usar paginación para muchos usuarios
            view = TimesView(sorted_users, interaction.guild, max_per_page=25)
            embed = view.get_embed()

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)

    except asyncio.TimeoutError:
        error_msg = "❌ Timeout al obtener usuarios. Intenta de nuevo."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=False)
            else:
                await interaction.followup.send(error_msg)
        except Exception as e:
            print(f"Error enviando mensaje de timeout: {e}")

    except Exception as e:
        print(f"Error general en ver_tiempos: {e}")
        import traceback
        traceback.print_exc()

        error_msg = "❌ Error interno del comando. Revisa los logs del servidor."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=False)
            else:
                await interaction.followup.send(error_msg)
        except Exception as e2:
            print(f"No se pudo enviar mensaje de error final: {e2}")

@bot.tree.command(name="reiniciar_tiempo", description="Reiniciar el tiempo de un usuario a cero")
@discord.app_commands.describe(usuario="El usuario cuyo tiempo se reiniciará")
@is_admin()
async def reiniciar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    success = time_tracker.reset_user_time(usuario.id)
    if success:
        await interaction.response.send_message(f"🔄 Tiempo reiniciado para {usuario.mention} por {interaction.user.mention}")
    else:
        await interaction.response.send_message(f"❌ No se encontró registro de tiempo para {usuario.mention}")

@bot.tree.command(name="reiniciar_todos_tiempos", description="Reiniciar todos los tiempos de todos los usuarios")
@is_admin()
async def reiniciar_todos_tiempos(interaction: discord.Interaction):
    usuarios_reiniciados = time_tracker.reset_all_user_times()
    if usuarios_reiniciados > 0:
        await interaction.response.send_message(f"🔄 Tiempos reiniciados para {usuarios_reiniciados} usuario(s)")
    else:
        await interaction.response.send_message("❌ No hay usuarios con tiempo registrado para reiniciar")

@bot.tree.command(name="limpiar_base_datos", description="ELIMINAR COMPLETAMENTE todos los usuarios registrados de la base de datos")
@is_admin()
async def limpiar_base_datos(interaction: discord.Interaction):
    tracked_users = time_tracker.get_all_tracked_users()
    user_count = len(tracked_users)

    if user_count == 0:
        await interaction.response.send_message("❌ No hay usuarios registrados en la base de datos")
        return

    embed = discord.Embed(
        title="⚠️ CONFIRMACIÓN REQUERIDA",
        description="Esta acción eliminará COMPLETAMENTE todos los datos de usuarios",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.add_field(
        name="📊 Datos que se eliminarán:",
        value=f"• {user_count} usuarios registrados\n"
              f"• Todo el historial de tiempo\n"
              f"• Sesiones activas\n"
              f"• Contadores de pausas\n"
              f"• Estados de notificaciones\n"
              f"• **TODOS los comandos de pago quedarán vacíos**",
        inline=False
    )
    embed.add_field(
        name="⚠️ ADVERTENCIA:",
        value="Esta acción NO se puede deshacer\n"
              "Los usuarios tendrán que registrarse de nuevo\n"
              "Afecta: `/paga_recluta` y `/paga_gold`",
        inline=False
    )
    embed.add_field(
        name="🔄 Para continuar:",
        value="Usa el comando `/limpiar_base_datos_confirmar` con `confirmar: 'SI'`",
        inline=False
    )
    embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="limpiar_base_datos_confirmar", description="CONFIRMAR eliminación completa de la base de datos")
@discord.app_commands.describe(confirmar="Escribe 'SI' para confirmar la eliminación completa")
@is_admin()
async def limpiar_base_datos_confirmar(interaction: discord.Interaction, confirmar: str):
    if confirmar.upper() != "SI":
        await interaction.response.send_message("❌ Operación cancelada. Debes escribir 'SI' para confirmar")
        return

    tracked_users = time_tracker.get_all_tracked_users()
    user_count = len(tracked_users)

    if user_count == 0:
        await interaction.response.send_message("❌ No hay usuarios registrados en la base de datos")
        return

    success = time_tracker.clear_all_data()

    if success:
        embed = discord.Embed(
            title="🗑️ BASE DE DATOS LIMPIADA",
            description="Todos los datos de usuarios han sido eliminados completamente",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📊 Datos eliminados:",
            value=f"• {user_count} usuarios registrados\n"
                  f"• Todo el historial de tiempo\n"
                  f"• Sesiones activas\n"
                  f"• Archivo user_times.json reiniciado",
            inline=False
        )
        embed.add_field(
            name="✅ Estado actual:",
            value="Base de datos completamente limpia\n"
                  "Sistema listo para nuevos registros",
            inline=False
        )
        embed.set_footer(text=f"Ejecutado por {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Error al limpiar la base de datos")

@bot.tree.command(name="cancelar_tiempo", description="Cancelar completamente el tiempo de un usuario")
@discord.app_commands.describe(usuario="El usuario cuyo tiempo se cancelará por completo")
@is_admin()
async def cancelar_tiempo(interaction: discord.Interaction, usuario: discord.Member):
    user_data = time_tracker.get_user_data(usuario.id)
    total_time = time_tracker.get_total_time(usuario.id)
    user_id = usuario.id

    if user_data:
        formatted_time = time_tracker.format_time_human(total_time)
        success = time_tracker.cancel_user_tracking(user_id)
        if success:
            await interaction.response.send_message(f"🗑️ El tiempo de {usuario.mention} ha sido cancelado")
            await send_cancellation_notification(usuario.display_name, interaction.user.mention, formatted_time)
        else:
            await interaction.response.send_message(f"❌ Error al cancelar el tiempo para {usuario.mention}")
    else:
        await interaction.response.send_message(f"❌ No se encontró registro de tiempo para {usuario.mention}")

@bot.tree.command(name="configurar_canal_tiempos", description="Configurar el canal donde se enviarán las notificaciones de tiempo completado")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de tiempo completado")
@is_admin()
async def configurar_canal_tiempos(interaction: discord.Interaction, canal: discord.TextChannel):
    global NOTIFICATION_CHANNEL_ID
    NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"🎯 Canal de notificaciones de tiempo configurado: {canal.mention}")

@bot.tree.command(name="configurar_canal_pausas", description="Configurar el canal donde se enviarán las notificaciones de pausas")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de pausas")
@is_admin()
async def configurar_canal_pausas(interaction: discord.Interaction, canal: discord.TextChannel):
    global PAUSE_NOTIFICATION_CHANNEL_ID
    PAUSE_NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"⏸️ Canal de notificaciones de pausas configurado: {canal.mention}")

@bot.tree.command(name="configurar_canal_cancelaciones", description="Configurar el canal donde se enviarán las notificaciones de cancelaciones")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de cancelaciones")
@is_admin()
async def configurar_canal_cancelaciones(interaction: discord.Interaction, canal: discord.TextChannel):
    global CANCELLATION_NOTIFICATION_CHANNEL_ID
    CANCELLATION_NOTIFICATION_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"🗑️ Canal de notificaciones de cancelaciones configurado: {canal.mention}")

@bot.tree.command(name="configurar_canal_movimientos", description="Configurar el canal donde se enviarán las notificaciones de movimientos/inicios automáticos")
@discord.app_commands.describe(canal="El canal donde se enviarán las notificaciones de movimientos")
@is_admin()
async def configurar_canal_movimientos(interaction: discord.Interaction, canal: discord.TextChannel):
    global MOVEMENTS_CHANNEL_ID
    MOVEMENTS_CHANNEL_ID = canal.id
    await interaction.response.send_message(f"📋 Canal de notificaciones de movimientos configurado: {canal.mention}")

@bot.tree.command(name="saber_tiempo", description="Ver estadísticas detalladas de un usuario")
@discord.app_commands.describe(usuario="El usuario del que ver estadísticas")
@is_admin()
async def saber_tiempo_admin(interaction: discord.Interaction, usuario: discord.Member):
    user_data = time_tracker.get_user_data(usuario.id)

    if not user_data:
        await interaction.response.send_message(f"❌ No se encontraron datos para {usuario.mention}")
        return

    total_time = time_tracker.get_total_time(usuario.id)
    formatted_time = time_tracker.format_time_human(total_time)

    embed = discord.Embed(
        title=f"📊 Estadísticas de {usuario.display_name}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )

    embed.add_field(name="⏱️ Tiempo Total", value=formatted_time, inline=True)

    has_special_role = has_unlimited_time_role(usuario)

    status = "🟢 Activo" if user_data.get('is_active', False) else "🔴 Inactivo"
    if user_data.get('is_paused', False):
        total_hours = total_time / 3600
        has_special_role = has_unlimited_time_role(usuario) if usuario else False
        role_type = get_user_role_type(usuario) if usuario else "normal"

        # Verificar límites según el tipo de rol
        if (user_data.get("milestone_completed", False) or 
            (has_special_role and total_hours >= 4.0) or 
            (role_type == "gold" and total_hours >= 2.0) or
            (role_type == "normal" and total_hours >= 1.0)):
            status = "✅ Terminado"
        else:
            status = "⏸️ Pausado"

    embed.add_field(name="📍 Estado", value=status, inline=True)

    if user_data.get('is_paused', False):
        paused_duration = time_tracker.get_paused_duration(usuario.id)
        formatted_paused_time = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"
        embed.add_field(
            name=f"⏸️ Tiempo Pausado de {usuario.display_name}",
            value=formatted_paused_time,
            inline=False
        )

    pause_count = time_tracker.get_pause_count(usuario.id)
    if pause_count > 0:
        pause_text = "pausa" if pause_count == 1 else "pausas"
        embed.add_field(
            name="📊 Contador de Pausas",
            value=f"{pause_count} {pause_text} de 3 máximo",
            inline=True
        )

    embed.set_thumbnail(url=usuario.avatar.url if usuario.avatar else usuario.default_avatar.url)
    embed.set_footer(text="Estadísticas actualizadas")

    await interaction.response.send_message(embed=embed)

# =================== SISTEMA DE ROLES SIMPLIFICADO ===================

@bot.tree.command(name="dar_cargo_gold", description="Asignar el rol Gold a un usuario")
@discord.app_commands.describe(usuario="El usuario al que asignar el rol", rol="El rol Gold a asignar")
@is_admin()
async def dar_cargo_gold(interaction: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    """Asignar rol Gold a un usuario"""
    try:
        if usuario.bot:
            await interaction.response.send_message("❌ No se pueden asignar roles a bots.", ephemeral=True)
            return

        if rol in usuario.roles:
            await interaction.response.send_message(
                f"⚠️ {usuario.mention} ya tiene el rol 🏆 **{rol.name}**",
                ephemeral=True
            )
            return

        await usuario.add_roles(rol, reason=f"Rol asignado por {interaction.user.display_name}")

        embed = discord.Embed(
            title="✅ Rol Asignado",
            description=f"🏆 **{rol.name}** ha sido asignado a {usuario.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Usuario", value=usuario.mention, inline=True)
        embed.add_field(name="🎭 Rol", value=f"🏆 {rol.name}", inline=True)
        embed.add_field(name="👮 Asignado por", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Tipo: Gold")

        await interaction.response.send_message(embed=embed)
        print(f"✅ Rol Gold ({rol.name}) asignado a {usuario.display_name} por {interaction.user.display_name}")

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ No tengo permisos para asignar este rol. Verifica que mi rol esté por encima del rol que intentas asignar.",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(f"❌ Error al asignar el rol: {e}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error inesperado al asignar el rol.", ephemeral=True)
        print(f"Error asignando rol Gold: {e}")

@bot.tree.command(name="quitar_cargo", description="Quitar un rol específico de un usuario")
@discord.app_commands.describe(usuario="El usuario al que quitar el rol", rol="El rol a quitar")
@is_admin()
async def quitar_cargo(interaction: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    """Comando para quitar roles específicos"""
    try:
        if usuario.bot:
            await interaction.response.send_message("❌ No se pueden quitar roles de bots.", ephemeral=True)
            return

        if rol not in usuario.roles:
            await interaction.response.send_message(
                f"⚠️ {usuario.mention} no tiene el rol **{rol.name}**",
                ephemeral=True
            )
            return

        await usuario.remove_roles(rol, reason=f"Rol removido por {interaction.user.display_name}")

        embed = discord.Embed(
            title="✅ Rol Removido",
            description=f"**{rol.name}** ha sido removido de {usuario.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Usuario", value=usuario.mention, inline=True)
        embed.add_field(name="🎭 Rol Removido", value=rol.name, inline=True)
        embed.add_field(name="👮 Removido por", value=interaction.user.mention, inline=False)

        await interaction.response.send_message(embed=embed)
        print(f"✅ Rol {rol.name} removido de {usuario.display_name} por {interaction.user.display_name}")

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ No tengo permisos para quitar este rol. Verifica que mi rol esté por encima del rol que intentas quitar.",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(f"❌ Error al quitar el rol: {e}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error inesperado al quitar el rol.", ephemeral=True)
        print(f"Error quitando rol: {e}")

@bot.tree.command(name="ver_roles_usuario", description="Ver todos los roles de un usuario")
@discord.app_commands.describe(usuario="El usuario del que ver los roles")
@is_admin()
async def ver_roles_usuario(interaction: discord.Interaction, usuario: discord.Member):
    """Ver todos los roles de un usuario"""
    try:
        user_roles = usuario.roles[1:]  # Excluir @everyone

        if not user_roles:
            await interaction.response.send_message(
                f"📋 {usuario.mention} no tiene roles asignados (excepto @everyone)",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🎭 Roles de {usuario.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.set_thumbnail(url=usuario.avatar.url if usuario.avatar else usuario.default_avatar.url)

        # Verificar si tiene rol Gold
        role_type = get_user_role_type(usuario)
        if role_type == "gold":
            gold_roles = [role for role in user_roles if "gold" in role.name.lower()]
            if gold_roles:
                gold_text = ""
                for role in gold_roles:
                    gold_text += f"🏆 **{role.name}**\n"
                embed.add_field(name="⭐ Rol Gold", value=gold_text, inline=False)

        # Otros roles
        other_roles = [role for role in user_roles if "gold" not in role.name.lower()]
        if other_roles:
            otros_text = ""
            for role in other_roles[:10]:  # Limitar a 10 roles
                otros_text += f"• {role.name}\n"
            if len(other_roles) > 10:
                otros_text += f"... y {len(other_roles) - 10} más"
            embed.add_field(name="📋 Otros Roles", value=otros_text, inline=False)

        embed.add_field(name="📊 Total de Roles", value=str(len(user_roles)), inline=True)
        embed.set_footer(text="Información de roles")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message("❌ Error al obtener información de roles.", ephemeral=True)
        print(f"Error obteniendo roles de usuario: {e}")

@bot.tree.command(name="ver_pre_registrados", description="Ver usuarios pre-registrados esperando las 8 PM")
@is_admin()
async def ver_pre_registrados(interaction: discord.Interaction):
    """Mostrar usuarios que están pre-registrados"""
    try:
        pre_registered_users = time_tracker.get_pre_registered_users()

        if not pre_registered_users:
            await interaction.response.send_message("📋 No hay usuarios pre-registrados actualmente")
            return

        chile_now = datetime.now(CHILE_TZ)

        embed = discord.Embed(
            title="📋 Usuarios Pre-registrados",
            description="Usuarios esperando el inicio automático a las 13:00 Chile",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        user_list = []
        for user_id_str, data in pre_registered_users.items():
            try:
                user_id = int(user_id_str)
                member = interaction.guild.get_member(user_id) if interaction.guild else None

                if member:
                    user_mention = member.mention
                else:
                    user_name = data.get('name', f'Usuario {user_id}')
                    user_mention = f"**{user_name}** `(ID: {user_id})`"

                pre_register_time = data.get('pre_register_time', '')
                if pre_register_time:
                    try:
                        register_dt = datetime.fromisoformat(pre_register_time)
                        time_str = register_dt.strftime("%H:%M")
                    except:
                        time_str = "N/A"
                else:
                    time_str = "N/A"

                user_list.append(f"📌 {user_mention} - Registrado a las {time_str}")

            except Exception as e:
                print(f"Error procesando usuario pre-registrado {user_id_str}: {e}")
                continue

        if user_list:
            embed.add_field(
                name=f"👥 Usuarios ({len(user_list)})",
                value="\n".join(user_list),
                inline=False
            )

        embed.add_field(
            name="⏰ Hora actual Chile",
            value=chile_now.strftime("%H:%M:%S"),
            inline=True
        )

        embed.add_field(
            name="🕐 Próximo inicio",
            value=f"{START_TIME_HOUR}:{START_TIME_MINUTE:02d} Chile",
            inline=True
        )

        embed.set_footer(text=f"Los tiempos se iniciarán automáticamente a las {START_TIME_HOUR}:{START_TIME_MINUTE:02d}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message("❌ Error al obtener usuarios pre-registrados.", ephemeral=True)
        print(f"Error obteniendo pre-registrados: {e}")

@bot.tree.command(name="mi_tiempo", description="Ver tu propio tiempo registrado")
async def mi_tiempo(interaction: discord.Interaction):
    """Comando para que los usuarios vean su propio tiempo"""
    try:
        user_id = interaction.user.id
        user_data = time_tracker.get_user_data(user_id)

        if not user_data:
            await interaction.response.send_message(
                "❌ No tienes tiempo registrado aún. Un administrador debe iniciarte el tiempo primero.", 
                ephemeral=True
            )
            return

        total_time = time_tracker.get_total_time(user_id)
        formatted_time = time_tracker.format_time_human(total_time)

        # Obtener tipo de rol del usuario
        member = interaction.guild.get_member(user_id) if interaction.guild else None
        role_type = get_user_role_type(member) if member else "normal"
        has_special_role = has_unlimited_time_role(member) if member else False

        # Crear embed con información del usuario
        embed = discord.Embed(
            title=f"⏰ Tu Tiempo - {interaction.user.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.add_field(name="⏱️ Tiempo Total", value=formatted_time, inline=True)

        # Determinar estado
        status = "🟢 Activo" if user_data.get('is_active', False) else "🔴 Inactivo"
        if user_data.get('is_paused', False):
            total_hours = total_time / 3600

            # Verificar límites según el tipo de rol
            if (user_data.get("milestone_completed", False) or 
                (has_special_role and total_hours >= 4.0) or 
                (role_type == "gold" and total_hours >= 2.0) or
                (role_type == "normal" and total_hours >= 1.0)):
                status = "✅ Terminado"
            else:
                status = "⏸️ Pausado"

        embed.add_field(name="📍 Estado", value=status, inline=True)

        # Mostrar tiempo pausado si aplica
        if user_data.get('is_paused', False):
            paused_duration = time_tracker.get_paused_duration(user_id)
            formatted_paused_time = time_tracker.format_time_human(paused_duration) if paused_duration > 0 else "0 Segundos"
            embed.add_field(
                name="⏸️ Tiempo Pausado",
                value=formatted_paused_time,
                inline=False
            )

        # Mostrar contador de pausas si hay
        pause_count = time_tracker.get_pause_count(user_id)
        if pause_count > 0:
            pause_text = "pausa" if pause_count == 1 else "pausas"
            embed.add_field(
                name="📊 Pausas",
                value=f"{pause_count} {pause_text} de 3 máximo",
                inline=True
            )

        # Mostrar créditos ganados
        credits = calculate_credits(total_time, role_type)
        embed.add_field(
            name="💰 Créditos Ganados",
            value=f"{credits} créditos",
            inline=True
        )

        # Mostrar límites según rol
        if has_special_role:
            embed.add_field(
                name="🎭 Tu Rol",
                value="⭐ Rol Especial - Límite: 4 horas",
                inline=False
            )
        elif role_type == "gold":
            embed.add_field(
                name="🎭 Tu Rol",
                value="🏆 Gold - Límite: 2 horas",
                inline=False
            )
        else:
            embed.add_field(
                name="🎭 Tu Rol",
                value="👤 Recluta - Límite: 1 hora",
                inline=False
            )

        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
        embed.set_footer(text="Tu información personal de tiempo")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message("❌ Error al obtener tu información de tiempo.", ephemeral=True)
        print(f"Error en comando mi_tiempo para {interaction.user.display_name}: {e}")

@bot.tree.command(name="lista_roles_sistema", description="Ver información sobre el sistema de roles simplificado")
@is_admin()
async def lista_roles_sistema(interaction: discord.Interaction):
    """Mostrar información sobre el sistema simplificado"""
    try:
        embed = discord.Embed(
            title="🎭 Sistema de Roles Simplificado",
            description="Información sobre los roles disponibles en el sistema",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )

        embed.add_field(
            name="📊 Roles Disponibles",
            value="🏆 **Gold** - Rol especial con beneficios\n"
                  "👤 **Sin Rol Específico** - Usuarios normales/reclutas",
            inline=False
        )

        embed.add_field(
            name="💡 Comandos Disponibles",
            value="• `/dar_cargo_gold` - Asignar rol Gold\n"
                  "• `/quitar_cargo` - Quitar cualquier rol\n"
                  "• `/ver_roles_usuario` - Ver roles de un usuario\n"
                  "• `/paga_recluta` - Ver usuarios sin rol específico\n"
                  "• `/paga_gold` - Ver usuarios con rol Gold",
            inline=False
        )

        embed.add_field(
            name="💰 Sistema de Créditos por Tiempo",
            value="**🏆 Gold:**\n"
                  "• 5 créditos por 1 hora\n"
                  "• 10 créditos por 2 horas\n"
                  "• Límite: 2 horas\n\n"
                  "**👤 Sin Rol Específico:**\n"
                  "• 3 créditos por 1 hora\n"
                  "• Límite: 1 hora",
            inline=False
        )

        embed.add_field(
            name="⚠️ Roles Eliminados",
            value="Se eliminaron: Medios, Altos, Imperiales, Nobleza, Monarquía, Supremos\n"
                  "También se eliminó el sistema de asistencias (era exclusivo para cargos altos)",
            inline=False
        )

        embed.set_footer(text="Sistema simplificado - Solo Gold y usuarios normales")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message("❌ Error al mostrar información del sistema de roles.", ephemeral=True)
        print(f"Error mostrando lista de roles: {e}")

# =================== COMANDOS DE PAGO SIMPLIFICADOS ===================

class PaymentView(discord.ui.View):
    def __init__(self, filtered_users, role_name, guild, search_term=None):
        super().__init__(timeout=300)
        self.filtered_users = filtered_users
        self.role_name = role_name
        self.guild = guild
        self.search_term = search_term
        self.current_page = 0
        self.max_per_page = 15
        self.total_pages = (len(filtered_users) + self.max_per_page - 1) // self.max_per_page if filtered_users else 1

        if self.total_pages <= 1:
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.label in ['◀️ Anterior', '▶️ Siguiente']:
                    item.disabled = True

    def get_embed(self):
        """Crear embed para la página actual"""
        start_idx = self.current_page * self.max_per_page
        end_idx = min(start_idx + self.max_per_page, len(self.filtered_users))
        current_users = self.filtered_users[start_idx:end_idx]

        role_emoji = "👤"
        if "Gold" in self.role_name:
            role_emoji = "🏆"

        title = f"{role_emoji} Pago - {self.role_name}"
        if self.search_term:
            title += f" (Búsqueda: '{self.search_term}')"

        embed = discord.Embed(
            title=title,
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )

        if not current_users:
            embed.description = f"No se encontraron usuarios para {self.role_name}"
            if self.search_term:
                embed.description += f" con el término '{self.search_term}'"
            embed.set_footer(text="No hay datos para mostrar")
            return embed

        user_list = []
        total_credits = 0

        for user_data in current_users:
            try:
                user_id = user_data['user_id']
                member = self.guild.get_member(user_id) if self.guild else None

                if member:
                    user_mention = member.mention
                else:
                    user_name = user_data.get('name', f'Usuario {user_id}')
                    user_mention = f"**{user_name}** `(ID: {user_id})`"

                total_time = user_data['total_time']
                formatted_time = time_tracker.format_time_human(total_time)
                credits = user_data['credits']
                total_credits += credits

                data = user_data.get('data', {})
                status = "🔴 Inactivo"
                if data.get('is_active', False):
                    status = "🟢 Activo"
                elif data.get('is_paused', False):
                    total_hours = total_time / 3600
                    has_special_role = has_unlimited_time_role(member) if member else False
                    role_type = get_user_role_type(member) if member else "normal"

                    if (data.get("milestone_completed", False) or 
                        (user_data.get('has_special_role', False) and total_hours >= 4.0) or 
                        (role_type == "gold" and total_hours >= 2.0) or
                        (role_type == "normal" and total_hours >= 1.0)):
                        status = "✅ Terminado"
                    else:
                        status = "⏸️ Pausado"

                user_list.append(f"📌 {user_mention} - ⏱️ {formatted_time} - 💰 {credits} Créditos {status}")

            except Exception as e:
                print(f"Error procesando usuario en pago: {e}")
                continue

        embed.description = "\n".join(user_list)

        embed.add_field(
            name="📊 Resumen de Página",
            value=f"Usuarios: {len(current_users)}\nCréditos en página: {total_credits}",
            inline=True
        )

        total_users = len(self.filtered_users)
        total_all_credits = sum(user['credits'] for user in self.filtered_users)

        embed.add_field(
            name="🎯 Total General",
            value=f"Usuarios: {total_users}\nCréditos totales: {total_all_credits}",
            inline=True
        )

        embed.set_footer(text=f"Página {self.current_page + 1}/{self.total_pages} • {total_users} usuarios en total")
        return embed

    @discord.ui.button(label='◀️ Anterior', style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='▶️ Siguiente', style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self.update_buttons()
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='🔍 Buscar Usuario', style=discord.ButtonStyle.primary)
    async def search_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchUserModal(self)
        await interaction.response.send_modal(modal)

    def update_buttons(self):
        """Actualizar estado de los botones"""
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page >= self.total_pages - 1)

    async def on_timeout(self):
        """Deshabilitar botones cuando expire"""
        for item in self.children:
            item.disabled = True

class SearchUserModal(discord.ui.Modal, title='Buscar Usuario'):
    def __init__(self, payment_view):
        super().__init__()
        self.payment_view = payment_view

    search_term = discord.ui.TextInput(
        label='Nombre del usuario',
        placeholder='Escribe parte del nombre del usuario...',
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        search_term = self.search_term.value.lower().strip()

        matching_users = []
        for user_data in self.payment_view.filtered_users:
            user_name = user_data.get('name', '').lower()
            if search_term in user_name:
                matching_users.append(user_data)

        if not matching_users:
            await interaction.response.send_message(
                f"❌ No se encontraron usuarios con '{self.search_term.value}' en {self.payment_view.role_name}",
                ephemeral=True
            )
            return

        new_view = PaymentView(matching_users, self.payment_view.role_name, self.payment_view.guild, search_term)
        embed = new_view.get_embed()

        await interaction.response.edit_message(embed=embed, view=new_view)

def get_users_by_role_filter(role_filter_func, role_name: str, interaction: discord.Interaction):
    """Función auxiliar para obtener usuarios filtrados por rol"""
    try:
        tracked_users = time_tracker.get_all_tracked_users()
        filtered_users = []

        for user_id_str, data in tracked_users.items():
            try:
                user_id = int(user_id_str)
                member = interaction.guild.get_member(user_id) if interaction.guild else None

                if not role_filter_func(member, data):
                    continue

                total_time = time_tracker.get_total_time(user_id)

                if total_time <= 0:
                    continue

                if member:
                    role_type = get_user_role_type(member)
                    has_special_role = has_unlimited_time_role(member)
                else:
                    role_type = "normal"
                    has_special_role = False

                credits = calculate_credits(total_time, role_type)

                user_info = {
                    'user_id': user_id,
                    'name': data.get('name', f'Usuario {user_id}'),
                    'total_time': total_time,
                    'credits': credits,
                    'role_type': role_type,
                    'has_special_role': has_special_role,
                    'data': data
                }

                filtered_users.append(user_info)

            except Exception as e:
                print(f"Error procesando usuario {user_id_str}: {e}")
                continue

        filtered_users.sort(key=lambda x: x['name'].lower())
        return filtered_users

    except Exception as e:
        print(f"Error en get_users_by_role_filter: {e}")
        return []

@bot.tree.command(name="paga_recluta", description="Ver usuarios sin rol específico con sus horas y créditos")
@is_admin()
async def paga_recluta(interaction: discord.Interaction):
    """Mostrar usuarios sin rol específico (normales) con sus créditos"""
    await interaction.response.defer()

    def filter_normal_users(member, data):
        """Filtrar usuarios sin rol específico"""
        if not member:
            return True

        role_type = get_user_role_type(member)
        return role_type == "normal"

    filtered_users = get_users_by_role_filter(filter_normal_users, "Reclutas (Sin Rol)", interaction)

    if not filtered_users:
        await interaction.followup.send("❌ No se encontraron reclutas con tiempo registrado")
        return

    view = PaymentView(filtered_users, "Reclutas (Sin Rol)", interaction.guild)
    embed = view.get_embed()
    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(name="paga_gold", description="Ver usuarios con rol Gold con sus horas y créditos")
@is_admin()
async def paga_gold(interaction: discord.Interaction):
    """Mostrar usuarios con rol Gold con sus créditos"""
    await interaction.response.defer()

    gold_role_id = 1382198935971430440

    def filter_gold_users(member, data):
        """Filtrar usuarios con rol Gold"""
        if not member:
            return False

        for role in member.roles:
            if role.id == gold_role_id:
                return True

        role_type = get_user_role_type(member)
        return role_type == "gold"

    filtered_users = get_users_by_role_filter(filter_gold_users, "Gold", interaction)

    if not filtered_users:
        await interaction.followup.send("❌ No se encontraron usuarios con rol Gold con tiempo registrado")
        return

    view = PaymentView(filtered_users, "Gold", interaction.guild)
    embed = view.get_embed()
    await interaction.followup.send(embed=embed, view=view)

# =================== NOTIFICACIONES ===================

async def send_auto_cancellation_notification(user_name: str, total_time: str, cancelled_by: str, pause_count: int):
    """Enviar notificación cuando un usuario es cancelado automáticamente por 3 pausas"""
    channel = bot.get_channel(CANCELLATION_NOTIFICATION_CHANNEL_ID)
    if channel:
        try:
            message = f"🚫 **CANCELACIÓN AUTOMÁTICA**\n**{user_name}** ha sido cancelado automáticamente por exceder el límite de pausas\n**Tiempo total perdido:** {total_time}\n**Pausas alcanzadas:** {pause_count}/3\n**Última pausa ejecutada por:** {cancelled_by}"
            await channel.send(message)
            print(f"✅ Notificación de cancelación automática enviada para {user_name}")
        except Exception as e:
            print(f"❌ Error enviando notificación de cancelación automática: {e}")

async def send_cancellation_notification(user_name: str, cancelled_by: str, cancelled_time: str = ""):
    """Enviar notificación cuando un usuario es cancelado"""
    channel = bot.get_channel(CANCELLATION_NOTIFICATION_CHANNEL_ID)
    if channel:
        try:
            if cancelled_time:
                message = f"🗑️ El seguimiento de tiempo de **{user_name}** ha sido cancelado\n**Tiempo cancelado:** {cancelled_time}\n**Cancelado por:** {cancelled_by}"
            else:
                message = f"🗑️ El seguimiento de tiempo de **{user_name}** ha sido cancelado por {cancelled_by}"
            await channel.send(message)
            print(f"✅ Notificación de cancelación enviada para {user_name}")
        except Exception as e:
            print(f"❌ Error enviando notificación de cancelación: {e}")

async def send_pause_notification(user_name: str, total_time: float, paused_by: str, session_time: str = "", pause_count: int = 0):
    """Enviar notificación cuando un usuario es pausado"""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            channel = bot.get_channel(PAUSE_NOTIFICATION_CHANNEL_ID)
            if not channel:
                print(f"❌ Canal de pausas no encontrado: {PAUSE_NOTIFICATION_CHANNEL_ID}")
                return

            formatted_total_time = time_tracker.format_time_human(total_time)
            pause_text = f"pausa" if pause_count == 1 else f"pausas"

            if session_time and session_time != "0 Segundos":
                message = f"⏸️ El tiempo de **{user_name}** ha sido pausado\n**Tiempo de sesión pausado:** {session_time}\n**Tiempo total acumulado:** {formatted_total_time}\n**Pausado por:** {paused_by}\n📊 **{user_name}** lleva {pause_count} {pause_text}"
            else:
                message = f"⏸️ El tiempo de **{user_name}** ha sido pausado por {paused_by}\n**Tiempo total acumulado:** {formatted_total_time}\n📊 **{user_name}** lleva {pause_count} {pause_text}"

            await asyncio.wait_for(channel.send(message), timeout=10.0)
            print(f"✅ Notificación de pausa enviada para {user_name}")
            return

        except asyncio.TimeoutError:
            print(f"⚠️ Timeout enviando notificación de pausa para {user_name} (intento {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"⚠️ Error enviando notificación de pausa para {user_name} (intento {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

async def send_unpause_notification(user_name: str, total_time: float, unpaused_by: str, paused_duration: str = ""):
    """Enviar notificación cuando un usuario es despausado"""
    max_retries = 3

    channel_id = config.get("notification_channels", {}).get("unpause")
    if not channel_id:
        print("❌ Canal de despausas no configurado")
        return

    for attempt in range(max_retries):
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"❌ Canal de despausas no encontrado: {channel_id}")
                return

            formatted_total_time = time_tracker.format_time_human(total_time)

            if paused_duration:
                message = f"▶️ El tiempo de **{user_name}** ha sido despausado\n**Tiempo total acumulado:** {formatted_total_time}\n**Tiempo pausado:** {paused_duration}\n**Despausado por:** {unpaused_by}"
            else:
                message = f"▶️ **{user_name}** ha sido despausado por {unpaused_by}. Tiempo acumulado: {formatted_total_time}"

            await asyncio.wait_for(channel.send(message), timeout=10.0)
            print(f"✅ Notificación de despausa enviada para {user_name}")
            return

        except asyncio.TimeoutError:
            print(f"⚠️ Timeout enviando notificación de despausa para {user_name} (intento {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"⚠️ Error enviando notificación de despausa para {user_name} (intento {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

async def check_time_milestone(user_id: int, user_name: str):
    """Verificar si el usuario ha alcanzado milestones de tiempo y enviar notificaciones"""
    try:
        user_data = time_tracker.get_user_data(user_id)
        if not user_data:
            return

        guild = None
        member = None
        try:
            guild = bot.guilds[0] if bot.guilds else None
            if guild:
                member = guild.get_member(user_id)
        except Exception as e:
            print(f"⚠️ Error obteniendo miembro del servidor para {user_name}: {e}")

        has_unlimited_role = False
        is_external_user = user_data.get('is_external_user', False)

        if member:
            try:
                has_unlimited_role = has_unlimited_time_role(member)
            except Exception as e:
                print(f"⚠️ Error verificando rol especial para {user_name}: {e}")
                has_unlimited_role = False

        if not user_data.get('is_active', False):
            return

        if not user_data.get('last_start'):
            return

        try:
            session_start = datetime.fromisoformat(user_data['last_start'])
        except (ValueError, TypeError) as e:
            print(f"⚠️ Error parseando fecha de inicio para {user_name}: {e}")
            return

        if user_data.get('is_paused', False) and user_data.get('pause_start'):
            try:
                pause_start = datetime.fromisoformat(user_data['pause_start'])
                session_time = (pause_start - session_start).total_seconds()
            except (ValueError, TypeError) as e:
                print(f"⚠️ Error parseando fecha de pausa para {user_name}: {e}")
                return
        else:
            current_time = datetime.now()
            session_time = (current_time - session_start).total_seconds()

        if session_time < 3600:
            return

        total_time = time_tracker.get_total_time(user_id)

        if 'notified_milestones' not in user_data:
            user_data['notified_milestones'] = []
            try:
                time_tracker.save_data()
            except Exception as e:
                print(f"⚠️ Error guardando datos para {user_name}: {e}")

        notified_milestones = user_data.get('notified_milestones', [])
        total_hours = int(total_time // 3600)
        hour_milestone = total_hours * 3600

        missing_milestones = []
        for h in range(1, total_hours + 1):
            milestone = h * 3600
            if milestone not in notified_milestones:
                missing_milestones.append((milestone, h))

        if missing_milestones:
            milestone_to_notify, hours_to_notify = missing_milestones[-1]

            for milestone, _ in missing_milestones:
                if milestone not in notified_milestones:
                    notified_milestones.append(milestone)
            user_data['notified_milestones'] = notified_milestones

            try:
                time_tracker.save_data()
            except Exception as e:
                print(f"⚠️ Error guardando milestones para {user_name}: {e}")

            try:
                time_tracker.stop_tracking(user_id)
            except Exception as e:
                print(f"⚠️ Error deteniendo tracking para {user_name}: {e}")

            await send_milestone_notification(user_name, member, is_external_user, hours_to_notify, total_time)

            return

        elif hour_milestone not in notified_milestones:
            notified_milestones.append(hour_milestone)
            user_data['notified_milestones'] = notified_milestones

            try:
                time_tracker.save_data()
            except Exception as e:
                print(f"⚠️ Error guardando milestone para {user_name}: {e}")

            try:
                time_tracker.stop_tracking(user_id)
                if has_unlimited_role:
                    user_data_refresh = time_tracker.get_user_data(user_id)
                    if user_data_refresh:
                        user_data_refresh['milestone_completed'] = True
                        time_tracker.save_data()
            except Exception as e:
                print(f"⚠️ Error deteniendo tracking final para {user_name}: {e}")

            await send_milestone_notification(user_name, member, is_external_user, total_hours, total_time)

    except Exception as e:
        print(f"❌ Error crítico en check_time_milestone para {user_name}: {e}")
        import traceback
        traceback.print_exc()

async def send_milestone_notification(user_name: str, member, is_external_user: bool, hours: int, total_time: float):
    """Enviar notificación de milestone con sistema de retry ultra-robusto"""
    max_retries = 5
    base_delay = 1
    max_timeout = 30

    for attempt in range(max_retries):
        try:
            channel = await asyncio.wait_for(
                asyncio.to_thread(bot.get_channel, NOTIFICATION_CHANNEL_ID),
                timeout=5.0
            )

            if not channel:
                print(f"❌ Canal de notificaciones no encontrado: {NOTIFICATION_CHANNEL_ID}")
                return

            formatted_time = time_tracker.format_time_human(total_time)

            if member and not is_external_user:
                user_reference = member.mention
            else:
                user_reference = f"**{user_name}**"

            if hours == 1:
                message = f"🎉 {user_reference} ha completado 1 Hora! Tiempo acumulado: {formatted_time} "
            else:
                message = f"🎉 {user_reference} ha completado {hours} Horas! Tiempo acumulado: {formatted_time} "

            current_timeout = min(10 + (attempt * 5), max_timeout)

            await asyncio.wait_for(channel.send(message), timeout=current_timeout)
            print(f"✅ Notificación enviada exitosamente: {user_name} completó {hours} hora(s) (intento {attempt + 1}, timeout: {current_timeout}s)")
            return

        except asyncio.TimeoutError:
            delay = base_delay * (2 ** attempt)
            print(f"⚠️ Timeout ({current_timeout if 'current_timeout' in locals() else 'N/A'}s) enviando notificación para {user_name} (intento {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                print(f"🔄 Reintentando en {delay}s...")
                await asyncio.sleep(delay)
        except discord.HTTPException as e:
            if "50013" in str(e):
                print(f"❌ Sin permisos para enviar mensaje en canal {NOTIFICATION_CHANNEL_ID}")
                return
            elif "50035" in str(e):
                print(f"❌ Mensaje inválido para {user_name}: {e}")
                return
            print(f"⚠️ Error HTTP enviando notificación para {user_name} (intento {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        except discord.NotFound:
            print(f"❌ Canal de notificaciones no encontrado: {NOTIFICATION_CHANNEL_ID}")
            return
        except Exception as e:
            print(f"⚠️ Error inesperado enviando notificación para {user_name} (intento {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

    print(f"🚨 TODOS LOS INTENTOS FALLARON para {user_name}. Intentando notificación de emergencia...")
    try:
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            emergency_message = f"⚠️ {user_reference if 'user_reference' in locals() else user_name} completó {hours}h - Notificación de emergencia"
            await asyncio.wait_for(channel.send(emergency_message), timeout=10.0)
            print(f"✅ Notificación de emergencia enviada para {user_name}")
            return
    except Exception as emergency_error:
        print(f"❌ Falló notificación de emergencia para {user_name}: {emergency_error}")

    print(f"❌ CRÍTICO: No se pudo enviar notificación para {user_name} después de {max_retries} intentos + emergencia")

# =================== VERIFICACIÓN PERIÓDICA ===================

async def check_missing_milestones():
    """Verificar y notificar milestones perdidos para todos los usuarios con procesamiento paralelo"""
    try:
        tracked_users = await asyncio.wait_for(
            asyncio.to_thread(time_tracker.get_all_tracked_users),
            timeout=15.0
        )

        max_users_per_cycle = 100
        max_concurrent = 10

        user_items = list(tracked_users.items())[:max_users_per_cycle]

        async def process_user_chunk(chunk):
            """Procesar un chunk de usuarios en paralelo"""
            tasks = []
            for user_id_str, data in chunk:
                task = process_single_user_milestone(user_id_str, data)
                tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)

        chunk_size = max_concurrent
        for i in range(0, len(user_items), chunk_size):
            chunk = user_items[i:i + chunk_size]
            try:
                await asyncio.wait_for(process_user_chunk(chunk), timeout=30.0)
                await asyncio.sleep(0.2)
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout procesando chunk {i//chunk_size + 1}")
                continue

    except asyncio.TimeoutError:
        print("⚠️ Timeout obteniendo usuarios tracked")
    except Exception as e:
        print(f"❌ Error verificando milestones perdidos: {e}")

async def process_single_user_milestone(user_id_str: str, data: dict):
    """Procesar milestone de un solo usuario con manejo robusto de errores"""
    try:
        user_id = int(user_id_str)
        user_name = data.get('name', f'Usuario {user_id}')

        total_time = await asyncio.wait_for(
            asyncio.to_thread(time_tracker.get_total_time, user_id),
            timeout=3.0
        )

        guild = None
        member = None
        try:
            guild = bot.guilds[0] if bot.guilds else None
            if guild:
                member = guild.get_member(user_id)
        except Exception as e:
            print(f"⚠️ Error obteniendo miembro para {user_name}: {e}")

        has_unlimited_role = False
        is_external_user = data.get('is_external_user', False)

        if member:
            try:
                has_unlimited_role = has_unlimited_time_role(member)
            except Exception as e:
                print(f"⚠️ Error verificando rol para {user_name}: {e}")
                has_unlimited_role = False

        if 'notified_milestones' not in data:
            data['notified_milestones'] = []

        notified_milestones = data.get('notified_milestones', [])
        total_hours = int(total_time // 3600)

        missing_milestones = []
        for h in range(1, total_hours + 1):
            milestone = h * 3600
            if milestone not in notified_milestones:
                missing_milestones.append((milestone, h))

        if missing_milestones:
            milestone_to_notify, hours_to_notify = missing_milestones[-1]

            for milestone, _ in missing_milestones:
                if milestone not in notified_milestones:
                    notified_milestones.append(milestone)
            data['notified_milestones'] = notified_milestones

            try:
                await asyncio.wait_for(
                    asyncio.to_thread(time_tracker.save_data),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout guardando milestones para {user_name}")

            if hours_to_notify >= 1:
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(time_tracker.stop_tracking, user_id),
                        timeout=2.0
                    )

                    if has_unlimited_role:
                        user_data = time_tracker.get_user_data(user_id)
                        if user_data:
                            user_data['milestone_completed'] = True
                            await asyncio.wait_for(
                                asyncio.to_thread(time_tracker.save_data),
                                timeout=2.0
                            )
                except asyncio.TimeoutError:
                    print(f"⚠️ Timeout deteniendo tracking para {user_name}")

            await send_milestone_notification(user_name, member, is_external_user, hours_to_notify, total_time)

            data['last_milestone_check'] = total_time
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(time_tracker.save_data),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout guardando última verificación para {user_name}")

    except asyncio.TimeoutError:
        print(f"⚠️ Timeout procesando usuario {user_id_str}")
    except Exception as e:
        print(f"⚠️ Error procesando usuario {user_id_str}: {e}")

async def periodic_milestone_check():
    """Verificar milestones periódicamente para usuarios activos"""
    milestone_check_count = 0
    error_count = 0
    max_errors = 5

    while True:
        try:
            await asyncio.sleep(5)
            milestone_check_count += 1

            if milestone_check_count % 12 == 1:
                try:
                    await asyncio.wait_for(check_missing_milestones(), timeout=30.0)
                except asyncio.TimeoutError:
                    print("⚠️ Timeout en verificación de milestones perdidos")
                except Exception as e:
                    print(f"⚠️ Error en verificación de milestones perdidos: {e}")

            try:
                tracked_users = await asyncio.wait_for(
                    asyncio.to_thread(time_tracker.get_all_tracked_users),
                    timeout=15.0
                )

                active_users = [
                    (user_id_str, data) for user_id_str, data in tracked_users.items()
                    if data.get('is_active', False) and not data.get('is_paused', False)
                ]

                max_active_users = 80
                active_users = active_users[:max_active_users]

                chunk_size = 5
                for i in range(0, len(active_users), chunk_size):
                    chunk = active_users[i:i + chunk_size]

                    tasks = []
                    for user_id_str, data in chunk:
                        try:
                            user_id = int(user_id_str)
                            user_name = data.get('name', f'Usuario {user_id}')

                            task = asyncio.wait_for(
                                check_time_milestone(user_id, user_name),
                                timeout=15.0
                            )
                            tasks.append(task)
                        except Exception as e:
                            print(f"⚠️ Error creando task para usuario {user_id_str}: {e}")

                    if tasks:
                        try:
                            await asyncio.gather(*tasks, return_exceptions=True)
                        except Exception as e:
                            print(f"⚠️ Error en procesamiento paralelo de chunk: {e}")

                        await asyncio.sleep(0.3)

                print(f"✅ Verificados {len(active_users)} usuarios activos en chunks paralelos")

            except asyncio.TimeoutError:
                print("⚠️ Timeout obteniendo usuarios activos")
            except Exception as e:
                print(f"⚠️ Error obteniendo usuarios activos: {e}")

            error_count = 0

        except Exception as e:
            error_count += 1
            print(f"❌ Error en verificación periódica de milestones (#{error_count}): {e}")

            if error_count >= max_errors:
                print(f"🚨 Demasiados errores consecutivos ({error_count}). Pausando verificaciones por 60 segundos...")
                await asyncio.sleep(60)
                error_count = 0
            else:
                sleep_time = min(10 * (2 ** error_count), 60)
                await asyncio.sleep(sleep_time)

async def auto_start_at_1pm():
    """Verificar y iniciar automáticamente tiempos a las 13:00 Chile"""
    while True:
        try:
            await asyncio.sleep(30)  # Verificar cada 30 segundos

            chile_now = datetime.now(CHILE_TZ)
            current_hour = chile_now.hour
            current_minute = chile_now.minute

            # Verificar si son exactamente las 13:31 (solo en el minuto exacto)
            if current_hour == START_TIME_HOUR and current_minute == START_TIME_MINUTE:
                print(f"🕐 Son las {START_TIME_HOUR}:{START_TIME_MINUTE:02d} Chile - Iniciando tiempos automáticamente...")

                # Obtener usuarios pre-registrados
                pre_registered_users = time_tracker.get_pre_registered_users()

                if pre_registered_users:
                    started_users = []

                    for user_id_str, data in pre_registered_users.items():
                        user_id = int(user_id_str)
                        user_name = data.get('name', f'Usuario {user_id}')

                        # Obtener información del admin que hizo el pre-registro
                        initiator_info = time_tracker.get_pre_register_initiator(user_id)

                        # Iniciar tiempo automáticamente
                        success = time_tracker.start_tracking_from_pre_register(user_id)
                        if success:
                            # Intentar obtener el objeto del miembro para la mención
                            member = None
                            try:
                                if bot.guilds:
                                    guild = bot.guilds[0]
                                    member = guild.get_member(user_id)
                            except Exception as e:
                                print(f"⚠️ Error obteniendo miembro para notificación: {e}")

                            # Usar mención si es posible, sino usar nombre
                            if member:
                                user_reference = member.mention
                            else:
                                user_reference = f"**{user_name}**"

                            if initiator_info:
                                admin_name = initiator_info.get('admin_name', 'Admin desconocido')
                                started_users.append(f"• {user_reference} - Pre-registrado por: {admin_name}")
                            else:
                                started_users.append(f"• {user_reference} - Pre-registrado por: Admin desconocido")

                    if started_users:
                        # Notificación automática deshabilitada
                        # await send_auto_start_notification(started_users, chile_now)
                        print(f"✅ Iniciados automáticamente {len(started_users)} usuarios a las 13:37 (sin notificación)")

                # Esperar 70 segundos para evitar múltiples ejecuciones
                await asyncio.sleep(70)

        except Exception as e:
            print(f"❌ Error en auto-inicio a las 8 PM: {e}")
            await asyncio.sleep(30)

async def send_auto_start_notification(started_users: list, timestamp: datetime):
    """Enviar notificación de inicio automático al canal de movimientos con paginación"""
    try:
        channel = bot.get_channel(MOVEMENTS_CHANNEL_ID)
        if not channel:
            print(f"❌ Canal de movimientos no encontrado: {MOVEMENTS_CHANNEL_ID}")
            return

        # Configuración de paginación
        max_users_per_page = 30
        total_users = len(started_users)

        if total_users <= max_users_per_page:
            # Si hay 30 o menos usuarios, enviar en un solo embed como antes
            embed = discord.Embed(
                title=f"🕐 Inicio Automático - {START_TIME_HOUR}:{START_TIME_MINUTE:02d} Chile",
                description="Los siguientes usuarios han iniciado su tiempo automáticamente:",
                color=discord.Color.green(),
                timestamp=timestamp
            )

            users_text = "\n".join(started_users)
            embed.add_field(
                name=f"👥 Usuarios iniciados ({total_users})",
                value=users_text,
                inline=False
            )

            embed.add_field(
                name="⏰ Hora de inicio",
                value=timestamp.strftime("%H:%M:%S"),
                inline=True
            )

            embed.set_footer(text="Sistema de inicio automático activado")

            await channel.send(embed=embed)
            print(f"✅ Notificación de inicio automático enviada ({total_users} usuarios)")

        else:
            # Si hay más de 30 usuarios, usar paginación
            total_pages = (total_users + max_users_per_page - 1) // max_users_per_page

            # Enviar primer embed con resumen
            summary_embed = discord.Embed(
                title=f"🕐 Inicio Automático - {START_TIME_HOUR}:{START_TIME_MINUTE:02d} Chile",
                description=f"**{total_users}** usuarios han iniciado su tiempo automáticamente",
                color=discord.Color.green(),
                timestamp=timestamp
            )

            summary_embed.add_field(
                name="📊 Resumen",
                value=f"• Total de usuarios: **{total_users}**\n"
                      f"• Páginas: **{total_pages}**\n"
                      f"• Usuarios por página: **{max_users_per_page}**",
                inline=False
            )

            summary_embed.add_field(
                name="⏰ Hora de inicio",
                value=timestamp.strftime("%H:%M:%S"),
                inline=True
            )

            summary_embed.set_footer(text=f"Inicio automático - Página 1/{total_pages + 1}")

            await channel.send(embed=summary_embed)
            print(f"✅ Resumen de inicio automático enviado ({total_users} usuarios)")

            # Enviar páginas con usuarios
            for page in range(total_pages):
                start_idx = page * max_users_per_page
                end_idx = min(start_idx + max_users_per_page, total_users)
                page_users = started_users[start_idx:end_idx]

                page_embed = discord.Embed(
                    title=f"📋 Lista de Usuarios - Página {page + 1}/{total_pages}",
                    color=discord.Color.blue(),
                    timestamp=timestamp
                )

                users_text = "\n".join(page_users)
                page_embed.add_field(
                    name=f"👥 Usuarios {start_idx + 1}-{end_idx} de {total_users}",
                    value=users_text,
                    inline=False
                )

                page_embed.set_footer(text=f"Inicio automático - Página {page + 2}/{total_pages + 1}")

                await channel.send(embed=page_embed)

                # Pequeña pausa entre páginas para evitar rate limits
                if page < total_pages - 1:  # No pausar después de la última página
                    await asyncio.sleep(0.5)

            print(f"✅ Todas las páginas enviadas ({total_pages} páginas, {total_users} usuarios)")

    except Exception as e:
        print(f"❌ Error enviando notificación de inicio automático: {e}")

        # Fallback: enviar notificación simple en caso de error
        try:
            fallback_embed = discord.Embed(
                title=f"🕐 Inicio Automático - {START_TIME_HOUR}:{START_TIME_MINUTE:02d} Chile",
                description=f"⚠️ {len(started_users)} usuarios iniciaron automáticamente\n"
                           f"(Error mostrando lista completa)",
                color=discord.Color.orange(),
                timestamp=timestamp
            )
            await channel.send(embed=fallback_embed)
            print("✅ Notificación de fallback enviada")
        except Exception as fallback_error:
            print(f"❌ Error crítico enviando notificación de fallback: {fallback_error}")

async def start_periodic_checks():
    """Iniciar las verificaciones periódicas"""
    global milestone_check_task, auto_start_task

    if milestone_check_task is None:
        milestone_check_task = bot.loop.create_task(periodic_milestone_check())
        print('✅ Task de verificación de milestones iniciado')

    if auto_start_task is None:
        auto_start_task = bot.loop.create_task(auto_start_at_1pm())
        print('✅ Task de inicio automático a las 13:00 Chile iniciado')

@bot.event
async def on_connect():
    """Evento que se ejecuta cuando el bot se conecta"""
    await start_periodic_checks()

# =================== MANEJO DE ERRORES ===================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    try:
        command_name = interaction.command.name if interaction.command else 'desconocido'
        print(f"Error en comando /{command_name}: {type(error).__name__}")

        if isinstance(error, discord.app_commands.CommandInvokeError):
            original_error = error.original if hasattr(error, 'original') else error

            if isinstance(original_error, discord.NotFound) and "10062" in str(original_error):
                print(f"⚠️ Interacción /{command_name} expirada (10062) - no respondiendo")
                return
            elif "Unknown interaction" in str(original_error):
                print(f"⚠️ Interacción /{command_name} desconocida - no respondiendo")
                return

        if isinstance(error, discord.app_commands.CheckFailure):
            error_msg = "❌ No tienes permisos para usar este comando."
        elif isinstance(error, discord.app_commands.CommandInvokeError):
            error_msg = "❌ Error interno del comando. El administrador ha sido notificado."
        elif isinstance(error, discord.app_commands.TransformerError):
            error_msg = "❌ Error en los parámetros. Verifica los valores ingresados."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            error_msg = f"⏰ Comando en cooldown. Intenta de nuevo en {error.retry_after:.1f}s"
        else:
            error_msg = "❌ Error inesperado. Intenta de nuevo."

        try:
            if not interaction.response.is_done():
                await asyncio.wait_for(
                    interaction.response.send_message(error_msg, ephemeral=True),
                    timeout=2.0
                )
            else:
                await asyncio.wait_for(
                    interaction.followup.send(error_msg, ephemeral=True),
                    timeout=2.0
                )
        except asyncio.TimeoutError:
            print(f"⚠️ Timeout respondiendo a error en /{command_name}")
        except discord.NotFound:
            print(f"⚠️ Interacción /{command_name} no encontrada al responder error")
        except discord.HTTPException as e:
            if "10062" not in str(e):
                print(f"⚠️ Error HTTP respondiendo a /{command_name}: {e}")
        except Exception as e:
            print(f"⚠️ Error inesperado respondiendo a /{command_name}: {e}")

    except Exception as e:
        print(f"❌ Error crítico en manejo global de errores: {e}")

def get_discord_token():
    """Obtener token de Discord de forma segura desde config.json o variables de entorno"""
    if config and config.get('discord_bot_token'):
        token = config.get('discord_bot_token')
        if token and isinstance(token, str) and token.strip():
            print("✅ Token cargado desde config.json")
            return token.strip()

    env_token = os.getenv('DISCORD_BOT_TOKEN')
    if env_token and isinstance(env_token, str) and env_token.strip():
        print("✅ Token cargado desde variables de entorno")
        return env_token.strip()

    print("❌ Error: No se encontró el token de Discord")
    print("┌─ Configura tu token de Discord de una de estas formas:")
    print("│")
    print("│ OPCIÓN 1 (Recomendado): En config.json")
    print("│ Edita config.json y cambia:")
    print('│ "discord_bot_token": "tu_token_aqui"')
    print("│")
    print("│ OPCIÓN 2: Variable de entorno")
    print("│ export DISCORD_BOT_TOKEN='tu_token_aqui'")
    print("└─")
    return None

if __name__ == "__main__":
    print("🤖 Iniciando Discord Time Tracker Bot SIMPLIFICADO...")
    print("📋 Cargando configuración...")

    token = get_discord_token()
    if not token:
        exit(1)

    print("🔗 Conectando a Discord...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Error: Token de Discord inválido")
        print("   Verifica que el token sea correcto en config.json")
        print("   O en las variables de entorno si usas esa opción")
    except KeyboardInterrupt:
        print("🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
        print("   Revisa la configuración y vuelve a intentar")