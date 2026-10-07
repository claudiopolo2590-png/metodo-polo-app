# Método Polo · App de inscripción y calendario

Una app en Streamlit con dos pantallas:

- **Inscribirse y reservar** (para las familias): eligen servicio, fecha y hora entre los horarios libres, completan los datos del jugador y del acudiente, y aceptan las autorizaciones. La reserva queda como *Pendiente*.
- **Calendario de clases** (para los entrenadores, con clave): calendario semanal, mensual o en lista con cada clase en el color de su servicio, filtro por servicio, tabla para confirmar o cancelar reservas y descarga en CSV.

## Reglas que ya trae

| Servicio | Duración | Cupo por sesión | Edades | Precio |
| --- | --- | --- | --- | --- |
| Polo Evaluación | 75 min | 1 | 6 a 18 | $25 |
| Polo 1:1 | 60 min | 1 | 10 a 18 | $45 por sesión |
| Polo Dúo | 60 min | 2 | 10 a 18 | $30 por jugador |
| Polo Línea | 75 min | 8 | 10 a 18 | $15 por jugador |
| Polo Base | 60 min | 10 | 6 a 9 | $12 |

- Horarios de inicio: lunes a viernes de 15:00 a 18:00; sábados y domingos de 08:00 a 11:00 y de 15:00 a 17:00.
- Hasta 2 clases a la misma hora (una por entrenador). Las clases grupales se llenan hasta su cupo sin ocupar otro entrenador.
- Se puede reservar hasta 60 días adelante.

Todo esto se cambia al inicio de `app.py` (`SERVICIOS`, `SESIONES_SIMULTANEAS`, `HORARIOS_SEMANA`, `HORARIOS_FIN_DE_SEMANA`, `DIAS_ANTICIPACION`).

## Probarla en tu computadora

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en el navegador. La clave de entrenadores por defecto es `polo2026`: cámbiala antes de compartir la app.

## Conectarla a Google Sheets (cuenta metodopolo@gmail.com)

Las reservas se guardan en una hoja de Google Sheets de metodopolo@gmail.com. Se hace una sola vez, entrando con esa cuenta:

1. **Crear la hoja.** En sheets.google.com crea una hoja en blanco llamada "Reservas · App Método Polo" y copia su enlace. La app escribe los encabezados sola.
2. **Crear la llave de acceso para la app** (cuenta de servicio):
   - Entra a console.cloud.google.com y crea un proyecto, por ejemplo "metodo-polo".
   - En *APIs y servicios → Biblioteca*, activa **Google Sheets API** y **Google Drive API**.
   - En *IAM y administración → Cuentas de servicio*, crea una cuenta (por ejemplo "app-reservas"). No necesita roles.
   - Dentro de esa cuenta, en *Claves → Agregar clave → JSON*, descarga el archivo .json. Guárdalo en privado: es la llave.
3. **Compartir la hoja** con el correo de la cuenta de servicio (termina en `iam.gserviceaccount.com`, está dentro del .json) como **Editor**.

Después copia `.streamlit/secrets.toml.ejemplo`, pega el enlace de la hoja y los datos del .json, y ponlo en los *Secrets* de Streamlit Cloud (paso 3 de abajo). Si la app no encuentra esos datos, guarda las reservas en un archivo local (`inscripciones.db`), que sirve solo para pruebas.

## Publicarla gratis en Streamlit Community Cloud

1. Sube esta carpeta a un repositorio de GitHub (el `.gitignore` evita subir los datos y la clave).
2. Entra a share.streamlit.io, conecta GitHub y elige el repositorio y `app.py`.
3. En *Settings → Secrets* pega el contenido de `.streamlit/secrets.toml.ejemplo` ya completado (clave de entrenadores, enlace de la hoja y datos del .json).
4. Comparte el enlace de la app en la bio de Instagram y por WhatsApp.

Las reservas quedan en la hoja de Google: ahí puedes verlas, filtrarlas o corregirlas. Si cambias algo a mano, no borres ni cambies la columna `id`.
