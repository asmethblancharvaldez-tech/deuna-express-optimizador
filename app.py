import streamlit as st
import pandas as pd
import requests
import time
from urllib.parse import quote_plus

st.set_page_config(
    page_title="DeUna Express | Planificador de rutas",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
USER_AGENT = "deuna-express-academic-cvrp/2.0"

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_address(address: str):
    q = address.strip()
    if "colombia" not in q.lower():
        q += ", Fonseca, La Guajira, Colombia"
    params = {"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "co"}
    r = requests.get(NOMINATIM_URL, params=params,
                     headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "display_name": data[0].get("display_name", q)
    }

@st.cache_data(ttl=3600, show_spinner=False)
def osrm_matrix(coords):
    coord_text = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"{OSRM_TABLE_URL}/{coord_text}"
    r = requests.get(url, params={"annotations": "distance,duration"}, timeout=40)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError("No fue posible construir la matriz de rutas.")
    distances = [[v / 1000 if v is not None else 1e9 for v in row]
                 for row in data["distances"]]
    durations = [[v / 60 if v is not None else 1e9 for v in row]
                 for row in data["durations"]]
    return distances, durations

def route_load(route, demands):
    return sum(demands[i] for i in route if i != 0)

def clarke_wright(dist, demands, capacities):
    """
    Clarke & Wright paralelo para CVRP.
    0 = depósito; 1..n = clientes.
    Se crean rutas unitarias y se fusionan por ahorro descendente,
    respetando la capacidad máxima disponible.
    """
    n = len(demands) - 1
    routes = [[i] for i in range(1, n + 1)]
    max_capacity = max(capacities)

    savings = []
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            s = dist[0][i] + dist[0][j] - dist[i][j]
            savings.append((s, i, j))
    savings.sort(reverse=True)

    def locate(customer):
        for idx, r in enumerate(routes):
            if customer in r:
                return idx
        return None

    for _, i, j in savings:
        ri, rj = locate(i), locate(j)
        if ri is None or rj is None or ri == rj:
            continue
        a, b = routes[ri], routes[rj]
        if i not in (a[0], a[-1]) or j not in (b[0], b[-1]):
            continue
        if route_load(a, demands) + route_load(b, demands) > max_capacity:
            continue

        candidates = []
        if a[-1] == i and b[0] == j:
            candidates.append(a + b)
        if a[0] == i and b[-1] == j:
            candidates.append(b + a)
        if a[0] == i and b[0] == j:
            candidates.append(list(reversed(a)) + b)
        if a[-1] == i and b[-1] == j:
            candidates.append(a + list(reversed(b)))
        if not candidates:
            continue

        merged = candidates[0]
        for idx in sorted([ri, rj], reverse=True):
            routes.pop(idx)
        routes.append(merged)

    # Asignación de rutas a motos por capacidad.
    route_info = [(r, route_load(r, demands)) for r in routes]
    route_info.sort(key=lambda x: x[1], reverse=True)
    bikes = sorted([(c, k + 1) for k, c in enumerate(capacities)], reverse=True)

    assigned, unassigned = [], []
    used = set()
    for route, load in route_info:
        options = [(c, k) for c, k in bikes if k not in used and c >= load]
        if not options:
            unassigned.append((route, load))
            continue
        c, k = min(options, key=lambda x: x[0])
        used.add(k)
        assigned.append({"moto": k, "capacidad": c, "ruta": route, "carga": load})
    return assigned, unassigned

def route_metrics(route, dist, dur):
    seq = [0] + route + [0]
    km = sum(dist[seq[i]][seq[i+1]] for i in range(len(seq)-1))
    minutes = sum(dur[seq[i]][seq[i+1]] for i in range(len(seq)-1))
    return km, minutes, seq

def maps_link(seq, points):
    labels = [points[i]["address"] for i in seq]
    if len(labels) < 2:
        return ""
    origin = quote_plus(labels[0])
    destination = quote_plus(labels[-1])
    waypoints = quote_plus("|".join(labels[1:-1]))
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"
    if waypoints:
        url += f"&waypoints={waypoints}"
    return url

st.title("🛵 DeUna Express")
st.subheader("Planificador de rutas de distribución por lotes")
st.caption(
    "Prototipo académico basado en un Problema de Ruteo de Vehículos con Capacidad "
    "(CVRP) y la heurística de ahorros de Clarke & Wright."
)

with st.sidebar:
    st.header("Configuración del lote")
    batch = st.text_input("Identificador del batch", "Batch 1")
    bloque = st.selectbox("Bloque de operación",
                          ["Matutino", "Mediodía", "Vespertino"])
    depot = st.text_input(
        "Dirección del depósito",
        placeholder="Escriba la dirección de la sede en Fonseca"
    )
    motos = st.number_input("Motocicletas disponibles", min_value=1,
                            max_value=30, value=3, step=1)
    st.markdown("**Capacidad por motocicleta (pedidos)**")
    capacities = []
    for k in range(int(motos)):
        capacities.append(
            int(st.number_input(f"Moto {k+1}", min_value=1, max_value=100,
                                value=10, step=1, key=f"cap_{k}"))
        )
    st.info("Criterio del trabajo de grado: menor distancia total.")

st.header("Pedidos del batch")
st.write("Ingrese un cliente por fila. La demanda corresponde al número de pedidos o unidades de capacidad asignadas a ese cliente.")

default = pd.DataFrame({
    "Pedido": ["P001", "P002", "P003", "P004"],
    "Cliente": ["", "", "", ""],
    "Dirección": ["", "", "", ""],
    "Demanda": [1, 1, 1, 1]
})

orders = st.data_editor(
    default,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Pedido": st.column_config.TextColumn("Pedido"),
        "Cliente": st.column_config.TextColumn("Cliente"),
        "Dirección": st.column_config.TextColumn("Dirección"),
        "Demanda": st.column_config.NumberColumn(
            "Demanda", min_value=1, step=1, default=1
        )
    }
)

if st.button("🚀 Generar rutas optimizadas", type="primary", use_container_width=True):
    clean = orders.copy()
    clean["Dirección"] = clean["Dirección"].fillna("").astype(str).str.strip()
    clean = clean[clean["Dirección"] != ""].reset_index(drop=True)

    if not depot.strip():
        st.error("Ingrese la dirección del depósito.")
        st.stop()
    if clean.empty:
        st.error("Ingrese al menos una dirección de cliente.")
        st.stop()
    if clean["Demanda"].fillna(1).sum() > sum(capacities):
        st.error(
            f"La demanda total ({int(clean['Demanda'].fillna(1).sum())}) supera "
            f"la capacidad total disponible ({sum(capacities)})."
        )
        st.stop()

    with st.spinner("Geocodificando direcciones y construyendo la matriz de distancias..."):
        points = []
        dep = geocode_address(depot)
        if not dep:
            st.error("No fue posible localizar el depósito. Revise la dirección.")
            st.stop()
        points.append({"address": depot, **dep})

        failed = []
        for idx, row in clean.iterrows():
            g = geocode_address(row["Dirección"])
            if not g:
                failed.append(row["Dirección"])
            else:
                points.append({"address": row["Dirección"], **g})
            time.sleep(1)

        if failed:
            st.error("No fue posible localizar: " + "; ".join(failed))
            st.stop()

        coords = [(p["lat"], p["lon"]) for p in points]
        try:
            dist, dur = osrm_matrix(coords)
        except Exception as e:
            st.error(f"No fue posible calcular la matriz de recorridos: {e}")
            st.stop()

    demands = [0] + [int(v) for v in clean["Demanda"].fillna(1).tolist()]
    assigned, unassigned = clarke_wright(dist, demands, capacities)

    if unassigned:
        st.warning(
            "La heurística no pudo asignar todas las rutas a la flota con las "
            "capacidades indicadas. Revise las capacidades o aumente el número de motos."
        )

    st.success(f"Rutas generadas para {batch} – {bloque}")

    total_km, total_min = 0.0, 0.0
    result_rows = []

    for item in sorted(assigned, key=lambda x: x["moto"]):
        km, minutes, seq = route_metrics(item["ruta"], dist, dur)
        total_km += km
        total_min += minutes
        customer_names = []
        for node in item["ruta"]:
            row = clean.iloc[node - 1]
            name = str(row["Cliente"]).strip()
            customer_names.append(name if name else str(row["Pedido"]))

        st.markdown(f"### 🛵 Moto {item['moto']}")
        st.write("**Secuencia:** Depósito → " + " → ".join(customer_names) + " → Depósito")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Carga", f"{item['carga']} pedidos")
        c2.metric("Capacidad", f"{item['capacidad']} pedidos")
        c3.metric("Distancia", f"{km:.2f} km")
        c4.metric("Tiempo estimado", f"{minutes:.1f} min")
        st.markdown(f"[Abrir recorrido en Google Maps]({maps_link(seq, points)})")

        result_rows.append({
            "Moto": item["moto"],
            "Ruta": "Depósito → " + " → ".join(customer_names) + " → Depósito",
            "Carga": item["carga"],
            "Capacidad": item["capacidad"],
            "Distancia (km)": round(km, 2),
            "Tiempo estimado (min)": round(minutes, 1)
        })

    st.divider()
    st.subheader("Resumen del batch")
    a, b, c, d = st.columns(4)
    a.metric("Clientes", len(clean))
    b.metric("Motos utilizadas", len(assigned))
    c.metric("Distancia total", f"{total_km:.2f} km")
    d.metric("Tiempo acumulado estimado", f"{total_min:.1f} min")

    if result_rows:
        results = pd.DataFrame(result_rows)
        st.dataframe(results, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar resultados CSV",
            results.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{batch.replace(' ', '_')}_rutas.csv",
            mime="text/csv"
        )

    with st.expander("Metodología implementada"):
        st.write(
            "La aplicación representa cada lote como una instancia estática de CVRP. "
            "Las direcciones se geocodifican, se obtiene una matriz de distancias y "
            "tiempos de viaje por red vial y se aplica la heurística de ahorros de "
            "Clarke & Wright. Las fusiones de rutas se aceptan únicamente cuando "
            "respetan la capacidad disponible de las motocicletas."
        )
