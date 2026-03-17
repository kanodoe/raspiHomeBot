import os
import zipfile
import shutil
from datetime import datetime, timedelta
from typing import List, Optional
from app.core.config import settings
from app.core.logging import logger

class LogService:
    LOG_DIR = os.path.dirname(settings.LOG_FILE) or "logs"
    RETENTION_DAYS = 7

    @classmethod
    def rotate_logs(cls):
        """
        Comprime el archivo de log actual, lo guarda con la fecha de ayer
        y elimina los respaldos de más de 7 días.
        Luego vacía el archivo de log actual.
        """
        try:
            if not os.path.exists(cls.LOG_DIR):
                os.makedirs(cls.LOG_DIR)

            # 1. Comprimir el log actual si existe y no está vacío
            if os.path.exists(settings.LOG_FILE) and os.path.getsize(settings.LOG_FILE) > 0:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                zip_filename = f"home_bot_{yesterday}.zip"
                zip_path = os.path.join(cls.LOG_DIR, zip_filename)

                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(settings.LOG_FILE, os.path.basename(settings.LOG_FILE))
                
                logger.info(f"Log rotado y comprimido en: {zip_path}")

                # 2. Vaciar el archivo de log actual
                with open(settings.LOG_FILE, 'w') as f:
                    f.truncate(0)
                logger.info("Archivo de log actual vaciado.")
            else:
                logger.info("No hay logs para rotar o el archivo está vacío.")

            # 3. Eliminar respaldos antiguos (> 7 días)
            cls.cleanup_old_logs()

        except Exception as e:
            logger.error(f"Error al rotar logs: {e}")

    @classmethod
    def cleanup_old_logs(cls):
        """Elimina archivos .zip de logs con más de RETENTION_DAYS de antigüedad."""
        now = datetime.now()
        retention_limit = now - timedelta(days=cls.RETENTION_DAYS)

        for filename in os.listdir(cls.LOG_DIR):
            if filename.endswith(".zip") and filename.startswith("home_bot_"):
                file_path = os.path.join(cls.LOG_DIR, filename)
                try:
                    # Intentar extraer la fecha del nombre del archivo: home_bot_YYYY-MM-DD.zip
                    date_str = filename.replace("home_bot_", "").replace(".zip", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < retention_limit:
                        os.remove(file_path)
                        logger.info(f"Log antiguo eliminado: {filename}")
                except (ValueError, OSError) as e:
                    # Si no se puede parsear la fecha, usamos la fecha de modificación
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_mtime < retention_limit:
                        os.remove(file_path)
                        logger.info(f"Log antiguo eliminado (por mtime): {filename}")

    @classmethod
    def list_logs(cls) -> List[str]:
        """Devuelve una lista de nombres de archivos de log comprimidos disponibles."""
        if not os.path.exists(cls.LOG_DIR):
            return []
        
        logs = [f for f in os.listdir(cls.LOG_DIR) if f.endswith(".zip") and f.startswith("home_bot_")]
        return sorted(logs, reverse=True)

    @classmethod
    def get_log_path(cls, filename: str) -> Optional[str]:
        """Devuelve la ruta completa a un archivo de log si existe y es válido."""
        if not filename.endswith(".zip") or ".." in filename or "/" in filename or "\\" in filename:
            return None
        
        file_path = os.path.join(cls.LOG_DIR, filename)
        if os.path.exists(file_path):
            return file_path
        return None
