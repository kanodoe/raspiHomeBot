from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger
from app.services.acestep_service import AceStepService
from app.services.ollama_service import OllamaService
import asyncio
import io

class AceStepController(BaseModule):
    """
    Module to manage ACE-Step API, Ollama and song generation.
    """
    __slots__ = ("last_generated_songs",)

    def __init__(self, bus):
        super().__init__(bus)
        self.last_generated_songs = {} # {source: {"audio": bytes, "metadata": dict, "task_id": str}}

    async def start(self):
        self.bus.subscribe("cmd.acestep.start", self._handle_start)
        self.bus.subscribe("cmd.acestep.stop", self._handle_stop)
        self.bus.subscribe("cmd.ollama.start", self._handle_ollama_start)
        self.bus.subscribe("cmd.ollama.stop", self._handle_ollama_stop)
        self.bus.subscribe("cmd.acestep.generate", self._handle_generate)
        self.bus.subscribe("cmd.acestep.save", self._handle_save)
        self.bus.subscribe("cmd.acestep.cache_for_admin", self._handle_cache_for_admin)
        logger.info("AceStepController module initialized.")

    async def _handle_cache_for_admin(self, data: Dict[str, Any]):
        """Guarda la última canción enviada al admin para que pueda usar /save_song."""
        admin_chat_id = data.get("admin_chat_id")
        if admin_chat_id is None:
            return
        source = f"chat_{admin_chat_id}"
        self.last_generated_songs[source] = {
            "audio": data["audio"],
            "metadata": data["metadata"],
            "task_id": data["task_id"],
        }

    async def _handle_start(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"AceStepController: Starting ACE-Step API (source: {source})")
        
        success, error_msg = await AceStepService.start_api()
        if success:
            # Check if it's really ready or just starting
            if await AceStepService.is_api_ready():
                await self.bus.publish("notify.status", {"message": "✅ ACE-Step API iniciada y lista.", "source": source})
            else:
                await self.bus.publish("notify.status", {"message": "⏳ ACE-Step API se está iniciando (puede tardar unos momentos en estar disponible).", "source": source})
        else:
            msg = error_msg or "Error al iniciar la API de ACE-Step."
            await self.bus.publish("notify.error", {"message": f"❌ {msg}", "source": source})

    async def _handle_stop(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"AceStepController: Stopping ACE-Step API (source: {source})")
        
        success = await AceStepService.stop_api()
        if success:
            await self.bus.publish("notify.status", {"message": "🛑 ACE-Step API detenida correctamente.", "source": source})
        else:
            await self.bus.publish("notify.error", {"message": "⚠️ Error al intentar detener la API de ACE-Step. Puede que ya estuviera cerrada.", "source": source})

    async def _handle_ollama_start(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"AceStepController: Starting Ollama (source: {source})")
        
        success, error_msg = await OllamaService.start_ollama()
        if success:
            if await OllamaService.is_available():
                await self.bus.publish("notify.status", {"message": "✅ Ollama iniciado y listo.", "source": source})
            else:
                await self.bus.publish("notify.status", {"message": "⏳ Ollama se está iniciando...", "source": source})
        else:
            msg = error_msg or "Error al iniciar Ollama. Asegúrate de que esté en el PATH o sea accesible."
            await self.bus.publish("notify.error", {"message": f"❌ {msg}", "source": source})

    async def _handle_ollama_stop(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"AceStepController: Stopping Ollama (source: {source})")
        
        success = await OllamaService.stop_ollama()
        if success:
            await self.bus.publish("notify.status", {"message": "🛑 Ollama detenido correctamente.", "source": source})
        else:
            await self.bus.publish("notify.error", {"message": "⚠️ No se pudo detener Ollama. Puede que se iniciara externamente o no sea accesible vía SSH.", "source": source})

    async def _handle_generate(self, data: Dict[str, Any]):
        source = data.get("source")
        prompt = data.get("prompt")
        lyrics = data.get("lyrics", "")
        user_id = data.get("user_id")
        username = data.get("username") or (str(user_id) if user_id else "?")

        logger.info(f"AceStepController: Generating song (source: {source}, prompt: {prompt})")
        
        # Check if API is ready, if not, try to start it
        if not await AceStepService.is_api_ready():
            await self.bus.publish("notify.status", {"message": "⏳ La API de ACE-Step no está lista. Intentando iniciarla...", "source": source})
            success, error_msg = await AceStepService.start_api()
            if success:
                await self.bus.publish("notify.status", {"message": "✅ API de ACE-Step iniciada. Enviando tarea...", "source": source})
            else:
                msg = error_msg or "No se pudo iniciar la API de ACE-Step. Abortando generación."
                await self.bus.publish("notify.error", {"message": f"❌ {msg} Si el servicio no está disponible, contacta al administrador.", "source": source})
                return

        task_id = await AceStepService.generate_song(prompt, lyrics)
        if not task_id:
            await self.bus.publish("notify.error", {"message": "Error al enviar la tarea de generación. Si el servicio no está disponible, contacta al administrador.", "source": source})
            return

        display_name = data.get("display_name") or username
        await self.bus.publish("notify.status", {"message": f"Tarea de generación enviada (ID: {task_id}). Procesando...", "source": source})
        
        # Poll for completion
        max_attempts = 60 # 5 minutes approx with 5s sleep
        for _ in range(max_attempts):
            await asyncio.sleep(5)
            status_data = await AceStepService.get_task_status(task_id)
            if not status_data:
                continue
            
            status = status_data.get("status")
            if status == "completed":
                audio_path = status_data.get("audio_path")
                if audio_path:
                    audio_bytes = await AceStepService.download_audio(audio_path)
                    if audio_bytes:
                        # Cache for potential saving later
                        self.last_generated_songs[source] = {
                            "audio": audio_bytes,
                            "metadata": status_data,
                            "task_id": task_id
                        }
                        
                        await self.bus.publish("notify.audio", {
                            "audio": audio_bytes,
                            "filename": f"song_{task_id}.mp3",
                            "source": source,
                            "caption": f"¡Aquí tienes tu canción!\nEstilo: {prompt}"
                        })
                        # Copia al admin: quién generó + audio + JSON para guardar
                        await self.bus.publish("notify.admin.song_generated", {
                            "audio": audio_bytes,
                            "metadata": status_data,
                            "task_id": task_id,
                            "filename": f"song_{task_id}.mp3",
                            "user_id": user_id,
                            "username": username,
                            "display_name": display_name,
                            "prompt": prompt,
                            "lyrics": lyrics,
                        })
                        return
                await self.bus.publish("notify.error", {"message": "Canción generada pero no se pudo obtener el audio.", "source": source})
                return
            elif status == "failed":
                error_msg = status_data.get("error", "Error desconocido")
                await self.bus.publish("notify.error", {"message": f"Error en la generación: {error_msg} Si el servicio no está disponible, contacta al administrador.", "source": source})
                return
        
    async def _handle_save(self, data: Dict[str, Any]):
        source = data.get("source")
        song_data = self.last_generated_songs.get(source)
        
        if not song_data:
            logger.warning(f"AceStepController: No recent song found to save for {source}")
            await self.bus.publish("notify.error", {"message": "No hay ninguna canción reciente para guardar.", "source": source})
            return
            
        logger.info(f"AceStepController: Saving song {song_data['task_id']} (source: {source})")
        
        success = await AceStepService.save_song_locally(
            song_data["task_id"], 
            song_data["audio"], 
            song_data["metadata"]
        )
        
        if success:
            await self.bus.publish("notify.status", {"message": f"✅ Canción guardada correctamente en el servidor (ID: {song_data['task_id']}).", "source": source})
        else:
            await self.bus.publish("notify.error", {"message": "❌ Error al intentar guardar la canción localmente.", "source": source})
