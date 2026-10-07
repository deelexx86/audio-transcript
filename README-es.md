# Audio Transcript

[English](README.md) · [Русский](README-ru.md) · [Español](README-es.md) · [Deutsch](README-de.md)

Audio Transcript es una utilidad de escritorio para Windows 11 que convierte mensajes de voz de Telegram, archivos de audio y el sonido de vídeos locales en texto fiel. Ofrece una cola secuencial, vista previa, copia al portapapeles y archivos TXT y Markdown.

El reconocimiento se ejecuta localmente con `faster-whisper` y CTranslate2. Tras descargar las dependencias y los modelos, los archivos locales se procesan sin internet. El audio y los textos permanecen en el equipo; no se utilizan API de transcripción, cuentas, telemetría, almacenamiento en la nube, base de datos ni servidor.

## Requisitos

- Windows 11 y Python de 64 bits, versión 3.11 o 3.12.
- Internet para la instalación y las descargas de audio de YouTube.
- Para YouTube: Node.js 22+ o Deno 2.3+ disponible en PATH.
- Espacio suficiente para los dos modelos Whisper.

La aplicación utiliza la CPU con CTranslate2 `int8`; no requiere una GPU dedicada.

## Instalación inicial

Desde PowerShell, en la raíz del repositorio:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\bootstrap_models.bat
```

El script descarga los modelos CTranslate2 en carpetas del proyecto:

- `models\whisper-large-v3`: **Precisión — Whisper large-v3**.
- `models\whisper-large-v3-turbo`: **Rápido — Whisper large-v3-turbo**.

Se puede repetir: omite los modelos completos. Git ignora sus archivos. El inicio normal nunca descarga modelos; si falta uno, aparece un error con instrucciones.

## Inicio e idioma

Haga doble clic en `run.bat`. Utiliza `.venv\Scripts\pythonw.exe`; no necesita terminal para el uso cotidiano.

Seleccione **Idioma de la interfaz** encima del panel de ajustes: English, Русский, Español o Deutsch. El selector sigue visible con los ajustes ocultos y funciona durante el procesamiento. El cambio es inmediato y se guarda en `config/settings.json`. La primera vez se usa un idioma compatible de la interfaz de Windows; en caso contrario se utiliza inglés.

Solo cambia la interfaz. El idioma del audio se detecta automáticamente; el texto transcrito, los nombres de archivo y los metadatos Markdown se conservan. Los detalles técnicos de los errores mantienen su redacción original.

## Flujo de trabajo

1. Abra **Ajustes** si es necesario. Elija **Precisión** para máxima fidelidad o **Rápido** para reducir el tiempo de CPU.
2. Introduzca opcionalmente un hablante predeterminado. Puede editarlo en cada fila.
3. Elija **Carpeta del proyecto / transcripts** o **Junto al archivo de origen**.
4. Arrastre archivos, pulse **+ Archivos**, **+ Carpeta** o **Bandeja de entrada** para explorar `inbox\`. No se recorren subcarpetas. También puede pegar un enlace de YouTube y pulsar **Añadir enlace** o Enter.
5. Ordene con **Subir / Bajar**, incluso varias filas seleccionadas. Pulse una cabecera para ordenar de forma ascendente y otra vez para invertirlo. **Añadido** indica la fecha y hora locales de incorporación a esta sesión, no la modificación del archivo.
6. Pulse **Transcribir**. La cola se procesa secuencialmente en el orden mostrado y la ventana sigue respondiendo. No se puede reordenar durante el procesamiento.
7. Seleccione una fila completada para leerla, pulse **Copiar** para obtener el texto limpio o **Abrir carpeta** para ver los archivos generados.

**Detener** solicita una cancelación segura: conserva resultados completos, impide iniciar el siguiente archivo y permite reiniciar los pendientes. **Reintentar selección** procesa únicamente las filas seleccionadas con error o canceladas, en orden; no afecta a otras filas. **Quitar completados** elimina las filas terminadas. Quitar filas o vaciar la cola nunca elimina los archivos de origen ni las transcripciones.

**Ocultar ajustes** libera espacio para la cola y la vista previa. El botón de apertura resume el modelo y el destino; la descripción completa aparece al pasar el cursor. El estado del panel se guarda localmente. Ordenar es una acción puntual: las nuevas entradas se añaden al final y los movimientos manuales sustituyen el orden previo. Las duraciones desconocidas van primero en orden ascendente. La cola y las fechas de incorporación no se restauran al reiniciar.

## Vídeos de YouTube

**Añadir enlace** valida y añade un vídeo sin contactar con YouTube. **Transcribir** descarga el audio y utiliza el modelo Whisper local seleccionado. Los vídeos y archivos locales comparten la cola secuencial. Se muestran por separado los progresos de descarga y reconocimiento. Detener cancela en el siguiente punto seguro; una solicitud de red activa puede tardar hasta su límite de espera.

Si YouTube solicita una comprobación antibot, se muestra **Esperando reintento** durante 10 segundos y se intenta una vez más con una nueva sesión de invitado del descargador. Detener también cancela la espera. Si vuelve a fallar, puede usar **Reintentar selección** más tarde; la cola continúa. Otras categorías no activan este reintento adicional, aunque el descargador mantiene sus reintentos limitados de conexiones y fragmentos.

La vista de error distingue comprobaciones antibot, restricciones de acceso, vídeos no disponibles, errores de red/servidor, solicitudes multimedia rechazadas, componentes ausentes y formatos de audio ausentes. Incluye etapa, intentos, versiones y hasta cinco advertencias fijas. No conserva registros originales del descargador, cookies, cabeceras ni URL multimedia; no se escribe un registro de diagnóstico en disco.

Admite `youtube.com/watch?v=...`, `youtu.be/...`, Shorts y enlaces de vídeos incrustados. Elimina seguimiento, marcas de tiempo y parámetros de listas: siempre procesa un vídeo completo. No admite enlaces exclusivos de listas/canales, emisiones en directo ni emisiones futuras. El vídeo debe ser accesible sin iniciar sesión; no importa cookies del navegador ni utiliza cuentas.

`yt-dlp` descarga audio en una carpeta temporal `config/youtube-*`, que se elimina tras éxito, error o cancelación. Un cierre forzado o un corte eléctrico puede dejarla pendiente. No crea un archivo permanente de vídeos/audio ni elimina los archivos locales de origen.

YouTube siempre guarda en `transcripts/YYYY/YYYY-MM-DD/youtube-VIDEO_ID/`, incluso si el destino local es junto al origen. Las colisiones reciben un sufijo numérico. Markdown incluye URL y título; TXT contiene solo el texto del modelo local. El título aparece al completar la fila. Un reintento vuelve a descargar el audio.

`yt-dlp[default]` incluye los scripts JavaScript correspondientes para resolver comprobaciones. Requiere Node.js o Deno compatible; consulte la [guía oficial de yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS). No necesita instalar FFmpeg aparte: PyAV decodifica el audio. Los componentes y modelos no se instalan automáticamente durante el uso.

Actualice el entorno tras obtener cambios:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Los cambios del servicio pueden requerir actualizar el descargador por separado:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"
```

## Formatos, carpetas y resultados

Audio: `.ogg` (incluido Telegram Ogg/Opus), `.mp3`, `.m4a`, `.wav`, `.webm`, `.amr` (AMR-NB / AMR-WB).

Vídeo: `.mp4`, `.m4v`, `.mkv`, `.mov`, `.avi`, `.wmv`, `.asf`, `.flv`, `.webm`, `.mpg`, `.mpeg`, `.ts`, `.mts`, `.m2ts`, `.vob`, `.ogv`, `.3gp`, `.3g2`. Se añaden mediante las acciones habituales. PyAV decodifica directamente la primera pista de audio; no hace falta exportar audio ni instalar FFmpeg. No procesa imágenes ni subtítulos. La compatibilidad depende de una pista legible, sin cifrado y compatible con el decodificador. Un vídeo sin audio o ilegible produce un error individual; la cola continúa.

Los archivos de origen pueden permanecer en cualquier ubicación local: nunca se copian, mueven, renombran ni eliminan. Los vídeos comparten destinos, protección contra sobrescritura, TXT/Markdown, vista previa y copia con los archivos de audio.

- `inbox\`: carpeta opcional de entrada; se explora sin subcarpetas.
- `models\`: los dos modelos locales.
- `transcripts\`: destino predeterminado.
- `config\settings.json`: preferencias locales, excluidas de Git.

El destino del proyecto utiliza la fecha de procesamiento:

```text
transcripts\YYYY\YYYY-MM-DD\source-name\
  transcript.txt
  transcript.md
```

El modo junto al origen crea `source-name_transcript\`. Nunca sobrescribe carpetas existentes: añade `_2`, `_3`, etc. TXT contiene exclusivamente el texto del modelo. Markdown añade origen, hora, duración, idioma detectado, hablante opcional y modelo realmente utilizado.

## Privacidad

PyAV decodifica localmente y Whisper, almacenado en el proyecto, reconoce en la CPU. Los archivos locales no generan solicitudes de red intencionadas. YouTube contacta con el servicio y sus servidores multimedia; el reconocimiento sigue siendo local y las transcripciones no se suben. No se resume ni reescribe el significado ni se duplica permanentemente el audio de origen. La función YouTube, solicitada explícitamente anteriormente, amplía el límite original de entrada sin conexión de `BRIEF.md`; ese archivo no se modifica. `inbox\`, `transcripts\`, `models\`, `.venv\` y `config\settings.json` son datos privados de ejecución protegidos por las reglas de Git.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m audio_transcript --smoke-test
```

Elimine `QT_QPA_PLATFORM` del entorno del terminal antes del inicio visible normal si sigue definida.

## Mantenimiento de traducciones

Se utilizan `QTranslator` y Qt Linguist. Los `.ts` editables y `.qm` compilados de `src/audio_transcript/translations/` se incluyen en el paquete Python. No se usa un servicio de traducción ni descargas en ejecución. El catálogo inglés también proporciona plurales correctos. Se cargan traducciones de Qt para sus diálogos estándar; los diálogos nativos de Windows siguen el idioma de Windows.

En `MainWindow`, envuelva los nuevos textos con `self.tr("English source text")`. Use plantillas completas con variables nombradas y `self.tr("%n item(s)", None, count)` para cantidades. También se extrae `_status("English source text", ...)`. No vincule las claves internas de ajustes, perfiles, estados ni los archivos generados a las etiquetas traducidas.

```powershell
# Extraer textos nuevos/modificados y conservar las traducciones:
.\.venv\Scripts\python.exe scripts\update_translations.py --update
# Editar los cuatro .ts en Qt Linguist o un editor XML y compilar:
.\.venv\Scripts\python.exe scripts\update_translations.py
.\.venv\Scripts\python.exe -m pytest
```

Incluya `.ts` y `.qm` juntos en cada commit. Las pruebas verifican cobertura, variables, plurales, coherencia de catálogos compilados y cambios de idioma en ejecución. Mantenga alineados los cuatro README.

## Solución de problemas

- **Modelo ausente:** ejecute `bootstrap_models.bat` con internet. Ambas carpetas necesitan `config.json`, `model.bin` y `tokenizer.json`.
- **Audio ilegible:** compruebe integridad y extensión. Un error individual no detiene las siguientes entradas.
- **CPU lenta:** use Rápido; los modelos grandes consumen mucha CPU y memoria, sobre todo con grabaciones largas.
- **`run.bat` indica que falta la instalación:** cree `.venv` e instale el proyecto con los comandos anteriores.
- **Vídeo sin audio:** necesita una pista; si hay varias, se utiliza la primera.
- **Carpeta o bandeja vacía:** solo se buscan archivos compatibles directamente en esa carpeta.
- **Sufijo `_2` o superior:** ya existe una carpeta de resultados; no se sobrescribe.
- **Comprobación antibot:** reproducir en el navegador no garantiza una descarga automatizada. Tras el único reintento a los 10 segundos, pruebe más tarde. Iniciar sesión o actualizar no garantiza resolverlo; no se accede a sesiones, cookies ni cuentas del navegador.
- **Otros errores de YouTube:** consulte categoría y diagnóstico para distinguir red, acceso, formatos o componentes. Compruebe nuevas versiones de `yt-dlp[default]` cuando cambie el servicio.
- **Falta un entorno JavaScript:** añada Node.js 22+ o Deno 2.3+ a PATH y reinicie. No se requiere para archivos locales.
