# Bot de Telegram de Kevin — revisión de estabilidad (25/11/2026)

**Estado:** versión de prueba, NO desplegada en el servidor. Partimos exclusivamente del ZIP `save.restricted.bot.carlos-main (2).zip`, conservado sin cambios. Esta variante es independiente de Telegram Backup Manager para Windows (v0.4.4).

## Propósito y alcance

La prioridad de esta revisión es **no perder silenciosamente mensajes ni borrar copias confirmadas**, antes de introducir optimizaciones más ambiciosas o una interfaz web. No cambia la configuración existente de MongoDB ni borra datos de usuario. **No se ejecutó el bot conectado a Telegram real.**

### Cambios implementados

1. **Cancelación no destructiva.** `bot/backup/rollback.py` conserva siempre los mensajes de destino y el registro de entregas confirmadas. Las referencias antiguas a `rollback_message_delivery` siguen funcionando como no-op compatible, sin borrar publicaciones ni metadatos de Notion.
2. **Punto de control seguro.** En `bot/utils/batch/worker.py`, errores de lectura, excepciones, entregas parciales y fallos de Notion **no** avanzan `current_message_id`. El trabajo queda `paused` con `retry_message_id` y puede reanudarse desde el mensaje pendiente. El ledger evita recopiados ya confirmados en otros destinos.
3. **Corrección del último mensaje.** Se considera completada la tarea solo cuando `current_message_id` queda **después** de `last_message_id`.
4. **Cancelación resistente a carreras.** Los campos visuales del trabajador se actualizan con `set_worker_state()` y ya no sobrescriben una orden de pausa/cancelación recibida simultáneamente.
5. **Sincronización prudente.** `Sync Last Indexed` se bloquea si hay trabajos generales incompletos o fallidos. El punto de sincronización ignora los trabajos prioritarios de un topic y se basa solo en trabajos generales completados sin errores de Telegram registrados.
6. **Historial de fallos reconciliado.** Al completar un mensaje anteriormente fallido, se eliminan sus entradas obsoletas de los contadores de errores (sin tocar los fallos de otros mensajes).
7. **Mensajes de estado seguros.** Un error al enviar una notificación de progreso al usuario no convierte en `failed` una tarea completada.
8. **Inicio seguro.** `BATCH_AUTO_RESUME_ON_START=false` por defecto: tras reiniciar el servidor, el bot no reanuda masivamente copias anteriores sin permiso explícito: las marca como pausadas para poder continuar manualmente. También aparece en `.env.example`.
9. **Notion con extracción desactivada por defecto.** `NOTION_EXTRACT_ARCHIVES=false`; si se activa conscientemente, hay límites de 100 archivos y 500 MiB descomprimidos por archivo comprimido, comprobación de rutas, rechazo de enlaces simbólicos y extracción temporal que se limpia después. Un archivo parcialmente subido a Notion se marca como fallido, **no como éxito**. Los archivos comprimidos **no se extraen** durante el uso normal.
10. **Pruebas nuevas.** `tests/test_offline_safety.py`: cancelación no destructiva, fallo/reanudación, recuperación manual tras reiniciar el servidor, límite del último mensaje, carrera de cancelación, ZIP normales, traversals, symlinks y límites.

## Comprobaciones realizadas

- `python -m compileall -q .`: correcto en los archivos del proyecto.
- `python -m unittest tests.test_offline_safety -v`: **11 pruebas superadas**, utilizando simulaciones/funciones extraídas del código real. No implican verificación real de Telegram.
- No ha sido posible ejecutar la batería original que depende de Kurigram, Motor/MongoDB y servicios externos: esas dependencias no están instaladas en este entorno y la instalación de paquetes desde Internet falló.

## Problemas aún pendientes (no declarar el bot “premium” ni completamente fiable)

- **Rendimiento:** el batch sigue recorriendo **cada ID consecutivo** (`range`) y puede tardar mucho en topics con grandes saltos. Se requiere una alternativa de paginación por mensajes existentes con una prueba específica para topics normales y General.
- **Identificación por topic:** el ledger usa chat destino, no topic destino, dentro de un mismo grupo. Hay que diseñar una migración de claves para soportar duplicados legítimos en topics diferentes sin copiar dos veces lo ya guardado.
- **Ventana no atómica de envío:** si Telegram confirma un envío y MongoDB falla justo antes de escribir el ledger, una reanudación podría producir un duplicado. No existe transacción atómica entre Telegram y MongoDB. Se debería estudiar conciliación posterior por ID/atributos.
- **Históricos antiguos:** un batch que la versión de Kevin hubiese marcado como `completed` de manera incorrecta puede conservar huecos. Esta revisión **no repara automáticamente** errores históricos; se necesita una auditoría de origen-destino.
- **Notion:** la extracción en el servidor es cara y requiere límites de uso y espacio adicionales. Se deja desactivada por defecto. Aunque falle un upload parcial, podrían quedar objetos huérfanos en Notion.
- **Tests de integración:** faltan pruebas controladas con una sesión autorizada de Telegram y MongoDB, especialmente para grupos protegidos y adjuntos grandes.

## Despliegue prudente y reversible

1. **No sobrescribir el servidor de producción todavía.** Guardar una copia completa del repositorio, los archivos `.env/config.env`, las sesiones y una copia consistente de MongoDB; proteger esas copias y no adjuntarlas a chats.
2. Probar primero en entorno **de staging**, con un bot, un grupo de origen y uno de destino de prueba, sin usar la misma base MongoDB que producción.
3. Instalar dependencias mediante `requirements.txt` en el servidor y ejecutar la batería original **y** `tests.test_offline_safety`.
4. Mantener `BATCH_AUTO_RESUME_ON_START=false` y `NOTION_EXTRACT_ARCHIVES=false` durante las primeras pruebas.
5. Probar: un mensaje de texto, una foto, un ZIP pequeño, cancelación después de una copia ya confirmada, caída simulada de MongoDB, reanudación sin copiar de nuevo y trabajo que falla a mitad.
6. Inspeccionar de forma independiente el canal de destino y el historial del ledger. Si falla una prueba, detener el despliegue y recuperar el respaldo.
7. Solo después trasladar cambios a producción, en una ventana controlada, manteniendo copia de la versión anterior. Se recomienda pedir autorización para conservar o copiar contenidos de terceros.

## Configuración relevante

```dotenv
# Variables nuevas/seguras para primeras pruebas
BATCH_AUTO_RESUME_ON_START=false
NOTION_EXTRACT_ARCHIVES=false
```

No hay que copiar claves del `.env` a un repositorio público ni compartir archivos `*.session`, tokens del bot o credenciales de MongoDB. El ZIP entregado no incluye sesiones ni claves privadas reales.

## Relación con el otro proyecto

**Este ZIP es del bot servidor de Kevin (Python, Kurigram, MongoDB).** No es una actualización de `TelegramBackupManager_v0_4_4.zip` para Windows. Conserva ambos proyectos independientes.
