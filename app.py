"""Método Polo · Inscripción y calendario de clases.

Ejecutar:  streamlit run app.py
"""
import base64
import datetime as dt
import os
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

BASE = Path(__file__).parent
DB = BASE / "inscripciones.db"
TZ = ZoneInfo("America/Panama")

# ---------------------------------------------------------------- configuración
# Cupo = jugadores por sesión (None = sin límite); quien reserva el mismo servicio a la misma hora se suma
# a ese grupo hasta llenar el cupo. Duración en minutos. Edades permitidas (inclusive).
# exclusivo=True: la primera reserva se queda con ese día y hora; nadie más puede reservar en ese horario.
SERVICIOS = {
    "Polo Evaluación": dict(precio="$25", minutos=75, cupo=1, edades=(6, 18), color="#3DBA6A", texto="#0F2A4A",
                            desc="El primer paso: nivel, fortalezas y plan."),
    "Polo 1:1": dict(precio="$45 por sesión", minutos=60, cupo=1, exclusivo=True, edades=(10, 18), color="#336FBF", texto="#FFFFFF",
                     desc="Entrenamiento individual de su posición."),
    "Polo Dúo": dict(precio="$30 por jugador", minutos=60, cupo=2, edades=(10, 18), color="#50A8E2", texto="#0F2A4A",
                     desc="Dos jugadores, misma sesión."),
    "Polo Línea": dict(precio="$15 por jugador", minutos=75, cupo=4, edades=(10, 18), color="#0F2A4A", texto="#FFFFFF",
                       desc="Grupo por posición."),
    "Polo Base": dict(precio="$12", minutos=60, cupo=None, edades=(6, 9), color="#E3F5EA", texto="#0F2A4A",
                      desc="6 a 9 años: juego y todas las posiciones."),
}
# Sesiones que pueden darse a la misma hora (una por entrenador disponible).
SESIONES_SIMULTANEAS = 2
# Horarios de inicio: tardes entre semana, sábados y domingos.
HORARIOS_SEMANA = ["15:00", "16:00", "17:00", "18:00"]
HORARIOS_FIN_DE_SEMANA = ["08:00", "09:00", "10:00", "11:00", "15:00", "16:00", "17:00"]
DIAS_ANTICIPACION = 60
ESTADOS = ["Pendiente", "Confirmada", "Cancelada"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

COLUMNAS = ["servicio", "fecha", "hora", "minutos", "jugador", "nacimiento", "posicion", "pie", "club", "peso",
            "altura", "salud", "acudiente", "parentesco", "whatsapp", "correo", "emergencia", "lugar",
            "residencial", "objetivo", "origen", "imagen", "estado", "notas", "creado"]


# ---------------------------------------------------------------- datos
# Si hay credenciales de Google en los secrets, las reservas se guardan en Google Sheets.
# Si no, se usa un archivo SQLite local (útil para probar en tu computadora).
CAMPOS = ["id"] + COLUMNAS


def ahora():
    return dt.datetime.now(TZ).replace(tzinfo=None)


def usa_sheets():
    try:
        return "gcp_service_account" in st.secrets and "SHEET_URL" in st.secrets
    except Exception:
        return False


@st.cache_resource
def hoja():
    import gspread
    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    ws = gc.open_by_url(st.secrets["SHEET_URL"]).sheet1
    if ws.row_values(1) != CAMPOS:
        ws.update([CAMPOS], "A1")
    return ws


def conectar():
    con = sqlite3.connect(DB)
    con.execute(f"CREATE TABLE IF NOT EXISTS inscripciones (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                f"{', '.join(c + ' TEXT' for c in COLUMNAS)})")
    return con


@st.cache_data(ttl=20, show_spinner=False)
def _leer_sheets():
    filas = hoja().get_all_records(expected_headers=CAMPOS, numericise_ignore=["all"])
    return pd.DataFrame(filas, columns=CAMPOS)


def leer():
    if usa_sheets():
        df = _leer_sheets().copy()
    else:
        with conectar() as con:
            df = pd.read_sql("SELECT * FROM inscripciones", con)
    df = df[df["id"].astype(str).str.strip() != ""]
    df["id"] = df["id"].astype(int)
    df = df.fillna("").astype({c: str for c in COLUMNAS})
    return df.sort_values(["fecha", "hora"]).reset_index(drop=True)


def guardar(fila):
    fila = {**fila, "estado": "Pendiente", "notas": "", "creado": ahora().isoformat(timespec="seconds")}
    valores = [str(fila.get(c, "")) for c in COLUMNAS]
    if usa_sheets():
        ws = hoja()
        ids = [int(x) for x in ws.col_values(1)[1:] if str(x).strip().isdigit()]
        nuevo = max(ids, default=0) + 1
        ws.append_row([nuevo] + valores, value_input_option="RAW")
        _leer_sheets.clear()
        return nuevo
    with conectar() as con:
        cur = con.execute(f"INSERT INTO inscripciones ({', '.join(COLUMNAS)}) VALUES ({', '.join('?' * len(COLUMNAS))})",
                          valores)
        return cur.lastrowid


def actualizar(id_, estado, notas):
    if usa_sheets():
        ws = hoja()
        ids = ws.col_values(1)
        fila = ids.index(str(int(id_))) + 1
        col = CAMPOS.index("estado") + 1  # estado y notas van juntas
        ws.update([[estado, notas]], gspread_rango(fila, col), value_input_option="RAW")
        _leer_sheets.clear()
        return
    with conectar() as con:
        con.execute("UPDATE inscripciones SET estado=?, notas=? WHERE id=?", (estado, notas, int(id_)))


def gspread_rango(fila, col):
    from gspread.utils import rowcol_to_a1
    return f"{rowcol_to_a1(fila, col)}:{rowcol_to_a1(fila, col + 1)}"


def inicio_fin(fecha, hora, minutos):
    ini = dt.datetime.combine(dt.date.fromisoformat(str(fecha)), dt.time.fromisoformat(str(hora)))
    return ini, ini + dt.timedelta(minutes=int(minutos))


def sesiones(df):
    """Agrupa reservas activas en sesiones: grupales comparten servicio y hora; individuales van solas."""
    activas = df[df.estado != "Cancelada"]
    out = {}
    for r in activas.itertuples():
        grupal = es_grupal(SERVICIOS.get(r.servicio, {}))
        clave = (r.servicio, r.fecha, r.hora) if grupal else ("id", r.id)
        s = out.setdefault(clave, dict(servicio=r.servicio, fecha=r.fecha, hora=r.hora, minutos=r.minutos, filas=[]))
        s["filas"].append(r)
    return list(out.values())


def es_grupal(cfg):
    return cfg.get("cupo", 1) != 1


def disponibilidad(df, servicio, fecha):
    """Devuelve [(hora, cupos_libres)] para el servicio en esa fecha (None = sin límite)."""
    cfg = SERVICIOS[servicio]
    horas = HORARIOS_FIN_DE_SEMANA if fecha.weekday() >= 5 else HORARIOS_SEMANA
    del_dia = [s for s in sesiones(df) if s["fecha"] == fecha.isoformat()]
    libres = []
    for h in horas:
        ini, fin = inicio_fin(fecha, h, cfg["minutos"])
        if ini <= ahora():
            continue
        cruzan = [s for s in del_dia if inicio_fin(s["fecha"], s["hora"], s["minutos"])[0] < fin
                  and inicio_fin(s["fecha"], s["hora"], s["minutos"])[1] > ini]
        if any(SERVICIOS.get(s["servicio"], {}).get("exclusivo") for s in cruzan):
            continue  # ya hay una clase exclusiva en ese horario
        if cfg.get("exclusivo"):  # la clase exclusiva necesita el horario libre
            if not cruzan:
                libres.append((h, cfg["cupo"]))
            continue
        misma = [s for s in cruzan if es_grupal(cfg) and s["servicio"] == servicio and s["hora"] == h]
        if misma:  # se suma a un grupo que ya existe
            if cfg["cupo"] is None:
                libres.append((h, None))
            elif cfg["cupo"] - len(misma[0]["filas"]) > 0:
                libres.append((h, cfg["cupo"] - len(misma[0]["filas"])))
        elif len(cruzan) < SESIONES_SIMULTANEAS:
            libres.append((h, cfg["cupo"]))
    return libres


def edad(nacimiento, en):
    return en.year - nacimiento.year - ((en.month, en.day) < (nacimiento.month, nacimiento.day))


def fecha_larga(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


# ---------------------------------------------------------------- estilo
st.set_page_config(page_title="Método Polo · Inscripción", page_icon="⚽", layout="wide")
logo = base64.b64encode((BASE / "assets" / "logo.svg").read_bytes()).decode()
st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stMarkdown, button, input, textarea, select, label {{font-family: 'Montserrat', sans-serif !important;}}
h1, h2, h3 {{font-family: 'Montserrat', sans-serif !important; font-weight: 800 !important; color: #0F2A4A;}}
.polo-head {{display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  border-bottom:3px solid #0F2A4A; padding-bottom:12px; margin-bottom:8px}}
.polo-head img {{height:46px}}
.polo-head span {{font-weight:800; color:#3DBA6A; letter-spacing:.04em}}
.svc {{border-radius:10px; padding:12px 14px; color:#fff; min-height:112px}}
.svc b {{display:block; font-size:1.05rem}} .svc small {{display:block; opacity:.9; line-height:1.35}}
.svc .p {{font-weight:800; font-size:1.2rem; margin-top:6px}}
.k {{font-weight:700; font-size:.75rem; letter-spacing:.14em; text-transform:uppercase; color:#336FBF; margin:18px 0 4px}}
</style>
<div class="polo-head"><img src="data:image/svg+xml;base64,{logo}" alt="Método Polo"><span>Entrena tu posición.</span></div>
""", unsafe_allow_html=True)

pagina = st.sidebar.radio("Menú", ["Inscribirse y reservar", "Calendario de clases"])
st.sidebar.caption("Método Polo · WhatsApp 6320-8340")


# ---------------------------------------------------------------- inscripción
def pagina_inscripcion():
    st.title("Inscripción y reserva de clase")
    st.write("Fútbol personalizado de 6 a 18 años, en tu residencia o en un lugar a coordinar. "
             "Elige la clase, el día y la hora; te escribimos por WhatsApp para confirmar.")

    cols = st.columns(len(SERVICIOS))
    for c, (nombre, cfg) in zip(cols, SERVICIOS.items()):
        c.markdown(f'<div class="svc" style="background:{cfg["color"]};color:{cfg["texto"]}"><b>{nombre}</b>'
                   f'<small>{cfg["desc"]}</small><small>{cfg["minutos"]} min · {cfg["edades"][0]} a {cfg["edades"][1]} años</small>'
                   f'<div class="p">{cfg["precio"]}</div></div>', unsafe_allow_html=True)

    st.markdown('<p class="k">1 · Elige tu clase</p>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.3, 1, 1])
    servicio = c1.selectbox("Servicio", list(SERVICIOS), help="Si es la primera vez, empieza con Polo Evaluación.")
    hoy = ahora().date()
    fecha = c2.date_input("Fecha", value=hoy + dt.timedelta(days=1), min_value=hoy,
                          max_value=hoy + dt.timedelta(days=DIAS_ANTICIPACION), format="DD/MM/YYYY")
    libres = disponibilidad(leer(), servicio, fecha)
    cfg = SERVICIOS[servicio]
    if libres:
        etiquetas = {h: ((f"{h} · queda 1 cupo" if n == 1 else f"{h} · quedan {n} cupos") if n and es_grupal(cfg) else h) for h, n in libres}
        hora = c3.selectbox("Hora", list(etiquetas), format_func=etiquetas.get)
    else:
        hora = None
        c3.warning("No quedan horarios ese día. Prueba otra fecha.")

    st.markdown('<p class="k">2 · Datos de inscripción</p>', unsafe_allow_html=True)
    with st.form("inscripcion", clear_on_submit=False):
        a, b = st.columns(2)
        jugador = a.text_input("Nombre completo del jugador *")
        nacimiento = b.date_input("Fecha de nacimiento *", value=dt.date(hoy.year - 10, 1, 1),
                                  min_value=dt.date(hoy.year - 20, 1, 1), max_value=hoy, format="DD/MM/YYYY")
        a, b, c = st.columns(3)
        posicion = a.selectbox("Posición *", ["Portero", "Defensa (central o lateral)", "Mediocampista",
                                              "Delantero o extremo", "Todavía no lo sabe"])
        pie = b.selectbox("Pie dominante *", ["Derecho", "Izquierdo", "Los dos"])
        club = c.text_input("Club, escuela o colegio donde juega")
        a, b = st.columns(2)
        peso = a.text_input("Peso (kg)")
        altura = b.text_input("Altura (cm)")
        salud = st.text_area("Lesiones, alergias u observaciones médicas *", placeholder="Escribe «Ninguna» si no tiene.")

        a, b, c = st.columns(3)
        acudiente = a.text_input("Nombre del padre, madre o acudiente *")
        parentesco = b.text_input("Parentesco *")
        whatsapp = c.text_input("WhatsApp *", placeholder="6000-0000")
        a, b = st.columns(2)
        correo = a.text_input("Correo electrónico")
        emergencia = b.text_input("Contacto de emergencia (nombre y teléfono) *")

        a, b = st.columns(2)
        lugar = a.radio("¿Dónde sería la clase? *", ["En mi residencia", "Lugar a coordinar con Método Polo"])
        residencial = b.text_input("Nombre del residencial o zona")
        objetivo = st.text_area("¿Qué le gustaría mejorar?")
        origen = st.selectbox("¿Cómo nos conociste?", ["Instagram", "Recomendación de otra familia", "En mi residencial",
                                                       "Club o colegio", "Otro"])
        imagen = st.radio("Uso de imagen *", ["Sí autorizo", "Solo para el informe de progreso (no en redes)",
                                              "No autorizo"], horizontal=True)
        apto = st.checkbox("Declaro que el jugador está apto para realizar actividad física. *")
        codigo = st.checkbox("Me comprometo a animar sin dirigir desde fuera de la cancha y a respetar el plan del "
                             "entrenador. *")
        enviar = st.form_submit_button("Inscribir y reservar", type="primary")

    if not enviar:
        return
    faltan = [n for n, v in [("nombre del jugador", jugador), ("observaciones médicas", salud),
                             ("acudiente", acudiente), ("parentesco", parentesco), ("WhatsApp", whatsapp),
                             ("contacto de emergencia", emergencia)] if not v.strip()]
    if not apto or not codigo:
        faltan.append("las dos casillas de autorización")
    e = edad(nacimiento, fecha)
    if hora is None:
        st.error("Elige una fecha con horarios disponibles.")
    elif faltan:
        st.error("Falta completar: " + ", ".join(faltan) + ".")
    elif not cfg["edades"][0] <= e <= cfg["edades"][1]:
        st.error(f"{servicio} es para jugadores de {cfg['edades'][0]} a {cfg['edades'][1]} años y el jugador tendrá "
                 f"{e} años ese día. Elige otro servicio.")
    elif hora not in [h for h, _ in disponibilidad(leer(), servicio, fecha)]:
        st.error("Ese horario se acaba de ocupar. Elige otra hora.")
    else:
        guardar(dict(servicio=servicio, fecha=fecha.isoformat(), hora=hora, minutos=cfg["minutos"],
                     jugador=jugador.strip(), nacimiento=nacimiento.isoformat(), posicion=posicion, pie=pie,
                     club=club, peso=peso, altura=altura, salud=salud, acudiente=acudiente, parentesco=parentesco,
                     whatsapp=whatsapp, correo=correo, emergencia=emergencia, lugar=lugar,
                     residencial=residencial, objetivo=objetivo, origen=origen, imagen=imagen))
        st.success(f"¡Listo! Reservamos **{servicio}** para **{jugador.strip()}** el **{fecha_larga(fecha)}** a las "
                   f"**{hora}**. Te escribiremos al {whatsapp} para confirmar el lugar. Método Polo · 6320-8340")
        st.balloons()


# ---------------------------------------------------------------- calendario
def pagina_calendario():
    st.title("Calendario de clases")
    try:
        clave = st.secrets["ADMIN_PASSWORD"]
    except Exception:
        clave = os.environ.get("ADMIN_PASSWORD", "polo2026")
    if not st.session_state.get("admin"):
        pw = st.text_input("Clave de entrenadores", type="password")
        if pw and pw == clave:
            st.session_state.admin = True
            st.rerun()
        elif pw:
            st.error("Clave incorrecta.")
        return

    df = leer()
    elegidos = st.multiselect("Servicios", list(SERVICIOS), default=list(SERVICIOS))
    ver_canceladas = st.toggle("Mostrar canceladas", value=False)
    st.markdown(" ".join(f'<span style="background:{c["color"]};color:{c["texto"]};padding:3px 10px;border-radius:5px;'
                         f'font-weight:700;font-size:.8rem;margin-right:6px">{n}</span>' for n, c in SERVICIOS.items()),
                unsafe_allow_html=True)

    eventos = []
    for s in sesiones(df):
        if s["servicio"] not in elegidos:
            continue
        cfg = SERVICIOS.get(s["servicio"], dict(color="#888", texto="#fff", cupo=1))
        ini, fin = inicio_fin(s["fecha"], s["hora"], s["minutos"])
        nombres = ", ".join(r.jugador for r in s["filas"])
        pendiente = any(r.estado == "Pendiente" for r in s["filas"])
        n = len(s["filas"])
        cupo = "" if not es_grupal(cfg) else (f" · {n}/{cfg['cupo']}" if cfg["cupo"] else f" · {n} jug.")
        eventos.append(dict(title=f"{'⏳ ' if pendiente else ''}{s['servicio']}{cupo} · {nombres}",
                            start=ini.isoformat(), end=fin.isoformat(), backgroundColor=cfg["color"],
                            borderColor=cfg["color"], textColor=cfg["texto"]))
    if ver_canceladas:
        for r in df[(df.estado == "Cancelada") & df.servicio.isin(elegidos)].itertuples():
            ini, fin = inicio_fin(r.fecha, r.hora, r.minutos)
            eventos.append(dict(title=f"✕ {r.servicio} · {r.jugador}", start=ini.isoformat(), end=fin.isoformat(),
                                backgroundColor="#DCE4EE", borderColor="#C8323C", textColor="#4A5D75"))

    calendar(events=eventos, key="cal", options=dict(
        locale="es", firstDay=1, initialView="timeGridWeek", slotMinTime="07:00:00", slotMaxTime="20:30:00",
        allDaySlot=False, height=680, nowIndicator=True,
        headerToolbar=dict(left="prev,next today", center="title", right="dayGridMonth,timeGridWeek,listWeek"),
        buttonText=dict(today="Hoy", month="Mes", week="Semana", list="Lista")),
        custom_css=".fc-event-title{font-weight:700}.fc-toolbar-title{font-weight:800;color:#0F2A4A}")
    st.caption("⏳ = reserva pendiente de confirmar por WhatsApp.")

    st.subheader("Reservas")
    if df.empty:
        st.info("Todavía no hay reservas.")
        return
    vista = df[df.servicio.isin(elegidos)][["id", "fecha", "hora", "servicio", "jugador", "posicion", "whatsapp",
                                             "lugar", "residencial", "estado", "notas"]]
    editado = st.data_editor(vista, hide_index=True, use_container_width=True, disabled=[c for c in vista.columns
                             if c not in ("estado", "notas")],
                             column_config={"estado": st.column_config.SelectboxColumn("estado", options=ESTADOS)})
    if st.button("Guardar cambios", type="primary"):
        for r in editado.itertuples():
            actualizar(r.id, r.estado, r.notas or "")
        st.success("Cambios guardados.")
        st.rerun()
    st.download_button("Descargar todas las reservas (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                       "reservas-metodo-polo.csv", "text/csv")


if pagina == "Inscribirse y reservar":
    pagina_inscripcion()
else:
    pagina_calendario()
